"""Arm F official training — Stable-Baselines3 PPO, executing
PREREGISTRATION_ARM_F_SB3.md verbatim (adjudication blocker 1).

Everything variable here was fixed in the pre-registration BEFORE this
script produced any output: algorithm (PPO, SB3 2.7.0), hyperparameters,
official seeds 1..10, the compute-budget/timesteps formula, the
convergence diagnostic, the evaluation procedure, and the seed-selection
rule (highest mean VALIDATION reward, ties -> lower seed). This script
only executes them and records the results.

Episodes are obs-v2 training episodes: OFFICIAL Arm-A ledger trades
extended with the entry-decision ATR (candidate ledger), the frozen
Wilder ATR series over completed 4h bars, the recorded official-run
exposure fraction per boundary (equity ledger's gross_exposure/equity),
and decision_ts — so the training environment builds observations through
the SAME canonical builder, with the SAME provenance, as orchestrator
inference (parity proven in tests/test_observation_parity.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
except ImportError as e:  # pragma: no cover
    raise ImportError("gymnasium required") from e

from lab import protocol as P
from lab.arms.indicators import SymbolSeries
from lab.arms.rl_env import ACTIONS, OBS_DIM, TradeManagementEnv
from lab.data.access import GuardedLake

OFFICIAL_SEEDS = list(range(1, 11))     # pre-registered; none discarded
BUDGET_S_TOTAL = 4 * 3600               # pre-registered: <=4h for 10 seeds
N_STEPS = 512
BATCH_SIZE = 128
GAMMA = 1.0
TIMESTEPS_CAP = 150_000
PROBE_TIMESTEPS = 2_048                 # seed 0, discarded, never evaluated
MA_WINDOW = 50                          # convergence diagnostic


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------- episodes
def build_episodes_v2(df: pd.DataFrame, lake: GuardedLake, end_ms: int,
                      expo_frac: dict[int, float]) -> list[tuple[dict, list]]:
    """One obs-v2 episode per executed labeled trade, ordered by
    (t, symbol) — the pre-registered deterministic episode order."""
    episodes = []
    kcache: dict[str, pd.DataFrame] = {}
    scache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    fcache: dict[str, dict[int, float]] = {}
    expo_keys = np.array(sorted(expo_frac), dtype=np.int64)
    df = df.sort_values(["t", "symbol"], kind="mergesort")
    for r in df.itertuples():
        sym = r.symbol
        if sym not in kcache:
            k = lake.read_klines(sym, 0, end_ms)
            kcache[sym] = k
            s = SymbolSeries(k.open_time.to_numpy(np.int64),
                             k.open.to_numpy(float), k.high.to_numpy(float),
                             k.low.to_numpy(float), k.close.to_numpy(float))
            scache[sym] = (s.t4 + P.BAR_4H_MS, s.atr)
            fdf = lake.read_funding(sym, 0, end_ms)
            fcache[sym] = dict(zip(fdf["funding_time"].astype(np.int64),
                                   fdf["funding_rate"].astype(float)))
        k = kcache[sym]
        atr_t, atr_v = scache[sym]
        lo = int(r.t) + P.BAR_15M_MS
        hi = min(int(r.exit_t) + P.BAR_4H_MS, end_ms)
        w = k[(k.open_time >= lo) & (k.open_time <= hi)]
        if w.empty:
            continue
        # recorded exposure fractions for boundaries inside the episode
        # (most-recent-<=t rule needs one key at/before the first boundary)
        j0 = max(0, int(np.searchsorted(expo_keys, int(r.t),
                                        side="right")) - 1)
        j1 = int(np.searchsorted(expo_keys, hi, side="right"))
        expo = {int(b): expo_frac[int(b)] for b in expo_keys[j0:j1]}
        tier = 1 if int(r.rank) <= P.TIER1_TOP_N else 2
        # D72: frozen funding rates covering the episode window — the
        # environment applies them with ArmARunner/engine semantics, so
        # rewards are net of funding per the policy's actual holding
        fb = {int(ft): fr for ft, fr in fcache[sym].items()
              if lo <= ft <= hi}
        trade = {"side": int(r.side), "qty": float(r.qty_filled),
                 "entry_ref": float(r.close), "r_dist": float(r.r_dist),
                 "decision_ts": int(r.t), "atr_entry": float(r.atr),
                 "atr_t4_close_ms": atr_t, "atr_values": atr_v,
                 "exposure_by_boundary": expo,
                 "funding_by_time": fb,
                 "costs": {"hs": P.HALF_SPREAD[tier],
                           "slip": P.SLIPPAGE[tier], "fee": P.TAKER_FEE}}
        bars = list(zip(w.open_time.astype(int), w.open, w.high, w.low,
                        w.close))
        episodes.append((trade, bars))
    return episodes


class EpisodeCycler(gym.Env):
    """Deterministic cycler over a fixed (t, symbol)-ordered episode list;
    DummyVecEnv-of-1 wraps this (pre-registered). Also records every
    completed episode's terminal reward for the convergence diagnostic."""
    metadata = {"render_modes": []}

    def __init__(self, episodes: list[tuple[dict, list]]):
        super().__init__()
        assert episodes
        self._eps = episodes
        self._k = 0
        self._env: TradeManagementEnv | None = None
        self.episode_rewards: list[float] = []
        tmpl = TradeManagementEnv(*episodes[0])
        self.action_space = tmpl.action_space
        self.observation_space = tmpl.observation_space

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        trade, bars = self._eps[self._k % len(self._eps)]
        self._k += 1
        self._env = TradeManagementEnv(trade, bars)
        return self._env.reset(seed=0)

    def step(self, action):
        obs, reward, term, trunc, info = self._env.step(action)
        if term or trunc:
            self.episode_rewards.append(float(reward))
        return obs, reward, term, trunc, info


# ------------------------------------------------------------- evaluation
def episode_terminal_reward(model, trade: dict, bars: list) -> float:
    env = TradeManagementEnv(trade, bars)
    obs, _ = env.reset(seed=0)
    total = 0.0
    while True:
        a, _ = model.predict(obs, deterministic=True)
        obs, reward, term, trunc, _ = env.step(int(a))
        total += float(reward)
        if term or trunc:
            return total


def evaluate(model, episodes: list[tuple[dict, list]]) -> float:
    if not episodes:
        return 0.0
    return float(np.mean([episode_terminal_reward(model, tr, b)
                          for tr, b in episodes]))


def convergence_flag(rewards: list[float]) -> dict:
    """Pre-registered diagnostic (not selection): moving average window
    MA_WINDOW; non_converged if the final MA < the median MA over the last
    25% of training episodes."""
    if len(rewards) < MA_WINDOW + 4:
        return {"n_episodes": len(rewards), "non_converged": None,
                "note": "too few episodes for the diagnostic"}
    r = np.asarray(rewards, float)
    ma = np.convolve(r, np.ones(MA_WINDOW) / MA_WINDOW, mode="valid")
    tail = ma[int(len(ma) * 0.75):]
    return {"n_episodes": len(rewards), "final_ma": float(ma[-1]),
            "median_ma_last_25pct": float(np.median(tail)),
            "non_converged": bool(ma[-1] < np.median(tail))}


def make_ppo(env, seed: int):
    from stable_baselines3 import PPO
    return PPO("MlpPolicy", env, n_steps=N_STEPS, batch_size=BATCH_SIZE,
               gamma=GAMMA, seed=seed, device="cpu", verbose=0)


def main() -> None:  # pragma: no cover — official training run
    import stable_baselines3
    import torch
    from stable_baselines3.common.vec_env import DummyVecEnv

    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--equity-ledger", required=True,
                    help="official equity ledger WITH gross_exposure")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    torch.set_num_threads(4)

    pins = {"stable_baselines3": stable_baselines3.__version__,
            "torch": torch.__version__}
    assert pins["stable_baselines3"] == "2.7.0", pins
    assert pins["torch"].startswith("2.13.0"), pins

    lake = GuardedLake(args.lake, args.manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    end_ms = q - P.BAR_15M_MS

    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    # features parquet = the purged modeling set (carries split); labels
    # carry every decision-time candidate field including the entry ATR
    df = feats[["t", "symbol", "split"]].merge(
        labels[["t", "symbol", "side", "close", "r_dist", "rank", "atr",
                "net_r", "exit_t", "qty_filled"]],
        on=["t", "symbol"], validate="1:1")

    eq = pd.read_parquet(args.equity_ledger)
    if "gross_exposure" not in eq.columns:
        raise SystemExit("equity ledger lacks gross_exposure — regenerate")
    expo_frac = {int(r.t): (float(r.gross_exposure) / float(r.equity)
                            if r.equity > 0 else 5.0)
                 for r in eq.itertuples()}

    tr = df[df.split == "train"]
    va = df[df.split == "validation"]
    # reviewer check C: NO validation information during policy fitting —
    # the training cycler sees the purged TRAIN split only, provably
    # disjoint from validation; validation enters ONLY through the
    # pre-registered post-hoc selection rule.
    overlap = set(zip(tr.t, tr.symbol)) & set(zip(va.t, va.symbol))
    assert not overlap, f"train/validation overlap: {sorted(overlap)[:5]}"
    print(f"trades: train {len(tr)} / validation {len(va)}", flush=True)
    print("building obs-v2 episodes...", flush=True)
    ep_tr = build_episodes_v2(tr, lake, end_ms, expo_frac)
    ep_va = build_episodes_v2(va, lake, end_ms, expo_frac)
    print(f"episodes: train {len(ep_tr)} / validation {len(ep_va)}",
          flush=True)

    # ---- pre-registered compute profiling: probe seed 0, DISCARDED ------
    probe_env = DummyVecEnv([lambda: EpisodeCycler(ep_tr)])
    probe = make_ppo(probe_env, seed=0)
    t0 = time.time()
    probe.learn(total_timesteps=PROBE_TIMESTEPS)
    probe_s = time.time() - t0
    sps = PROBE_TIMESTEPS / probe_s
    del probe, probe_env                        # discarded, never evaluated
    per_seed_budget = 0.9 * (BUDGET_S_TOTAL / len(OFFICIAL_SEEDS))
    total_timesteps = min(TIMESTEPS_CAP, int(per_seed_budget * sps))
    total_timesteps -= total_timesteps % N_STEPS
    profile = {"probe_timesteps": PROBE_TIMESTEPS,
               "probe_seconds": round(probe_s, 1),
               "steps_per_second": round(sps, 1),
               "formula": "min(150000, floor(0.9*(4h/10)*sps)) "
                          "rounded down to a multiple of n_steps=512",
               "total_timesteps_per_seed": total_timesteps}
    print("compute profile:", json.dumps(profile), flush=True)
    if total_timesteps <= 0:
        raise SystemExit("budget formula yielded 0 timesteps — report, "
                         "do not train")

    # ---- official seeds 1..10 -------------------------------------------
    seed_results = []
    for seed in OFFICIAL_SEEDS:
        cyc = EpisodeCycler(ep_tr)
        env = DummyVecEnv([lambda c=cyc: c])
        model = make_ppo(env, seed=seed)
        t0 = time.time()
        model.learn(total_timesteps=total_timesteps)
        train_s = time.time() - t0
        mpath = os.path.join(args.out_dir, f"arm_f_sb3_seed{seed}.zip")
        model.save(mpath)
        res = {"seed": seed, "algorithm": "SB3-PPO-MlpPolicy",
               "total_timesteps": total_timesteps,
               "train_seconds": round(train_s, 1),
               "convergence": convergence_flag(cyc.episode_rewards),
               "train_mean_reward": evaluate(model, ep_tr),
               "validation_mean_reward": evaluate(model, ep_va),
               "artifact": mpath, "artifact_sha256": sha256_file(mpath)}
        seed_results.append(res)
        print(f"seed {seed}: val {res['validation_mean_reward']:.4f} "
              f"train {res['train_mean_reward']:.4f} "
              f"({train_s:.0f}s, non_converged="
              f"{res['convergence'].get('non_converged')})", flush=True)

    # pre-registered selection: highest mean VALIDATION reward, ties ->
    # LOWER seed (max is stable over the ascending-seed list order only
    # for strict improvement, so make the tie-break explicit)
    best = seed_results[0]
    for r in seed_results[1:]:
        if r["validation_mean_reward"] > best["validation_mean_reward"]:
            best = r

    manifest = {
        "preregistration": "PREREGISTRATION_ARM_F_SB3.md",
        "pins": pins,
        "hyperparameters": {"policy": "MlpPolicy", "n_steps": N_STEPS,
                            "batch_size": BATCH_SIZE, "gamma": GAMMA,
                            "device": "cpu",
                            "others": "SB3 2.7.0 PPO defaults"},
        "obs_schema": {"dim": OBS_DIM, "actions": list(ACTIONS)},
        "episode_order": "(t, symbol) ascending, cycled",
        "compute_profile": profile,
        "official_seeds": OFFICIAL_SEEDS,
        "selected_seed": best["seed"],
        "selection_rule": "highest mean validation reward; ties -> lower "
                          "seed (pre-registered)",
        "validation_isolation": ("training episodes = purged TRAIN split "
                                 "only (disjointness asserted at load); "
                                 "validation consumed ONLY by the "
                                 "pre-registered selection rule; all "
                                 "evaluation predictions "
                                 "deterministic=True"),
        "seed_results": seed_results,
    }
    mpath = os.path.join(args.out_dir, "arm_f_sb3_manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"selected seed {best['seed']} "
          f"(val {best['validation_mean_reward']:.4f}); manifest {mpath}",
          flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
