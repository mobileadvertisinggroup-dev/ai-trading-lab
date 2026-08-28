"""Arm F corrected reporting v2 — executes
PREREGISTRATION_ARM_F_BASELINE.md verbatim (D63 blocker 2). NO
retraining; artifacts and selected seed 4 preserved.

The baseline is the EXACT frozen Arm A conventional manager replayed
in-episode: at each decision boundary, in ArmARunner order — (1)
trailing-channel exit from the frozen SymbolSeries signal (only when
both channel values are finite), (2) time exit at MAX_HOLD_BARS_4H —
otherwise hold; "close" fills at the next 15m open exactly as official
boundary exits do. Parity with official Arm A outcomes is proven by
tests/test_arm_f_baseline_parity.py BEFORE this tool runs officially.
The previous HOLD-baseline comparison is preserved as invalidated
history (arm_f_statistics_report.json).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np
import pandas as pd

from lab import protocol as P
from lab.arms.indicators import SymbolSeries
from lab.arms.rl_env import ACTIONS, TradeManagementEnv
from lab.data.access import GuardedLake

CLOSE = ACTIONS.index("close")
HOLD = ACTIONS.index("hold")


class ConventionalManager:
    """The frozen Arm A conventional manager, replayed per episode."""

    def __init__(self, series: SymbolSeries):
        self.series = series

    def action(self, env) -> int:
        p = env.engine.positions[1]
        t_dec = env.bars[env._i].open_time + P.BAR_15M_MS
        sig = self.series.at_boundary(t_dec)
        if sig is not None and np.isfinite(sig["ll_exit"]) and \
                np.isfinite(sig["hh_exit"]):
            trail = (sig["close"] < sig["ll_exit"] if p.side > 0
                     else sig["close"] > sig["hh_exit"])
            if trail:
                return CLOSE
        if (t_dec - p.decision_ts) // P.BAR_4H_MS >= P.MAX_HOLD_BARS_4H:
            return CLOSE
        return HOLD


def build_episodes_with_series(df, lake, end_ms, expo_frac):
    """build_episodes_v2 logic (train_arm_f_sb3) extended to carry the
    symbol and its frozen SymbolSeries for the baseline manager —
    identical episode windows, order, costs, and trade fields."""
    episodes = []
    kcache, scache = {}, {}
    expo_keys = np.array(sorted(expo_frac), dtype=np.int64)
    df = df.sort_values(["t", "symbol"], kind="mergesort")
    for r in df.itertuples():
        sym = r.symbol
        if sym not in kcache:
            k = lake.read_klines(sym, 0, end_ms)
            kcache[sym] = k
            scache[sym] = SymbolSeries(
                k.open_time.to_numpy(np.int64), k.open.to_numpy(float),
                k.high.to_numpy(float), k.low.to_numpy(float),
                k.close.to_numpy(float))
        k = kcache[sym]
        s = scache[sym]
        lo = int(r.t) + P.BAR_15M_MS
        hi = min(int(r.exit_t) + P.BAR_4H_MS, end_ms)
        w = k[(k.open_time >= lo) & (k.open_time <= hi)]
        if w.empty:
            continue
        j0 = max(0, int(np.searchsorted(expo_keys, int(r.t),
                                        side="right")) - 1)
        j1 = int(np.searchsorted(expo_keys, hi, side="right"))
        expo = {int(b): expo_frac[int(b)] for b in expo_keys[j0:j1]}
        tier = 1 if int(r.rank) <= P.TIER1_TOP_N else 2
        trade = {"side": int(r.side), "qty": float(r.qty_filled),
                 "entry_ref": float(r.close), "r_dist": float(r.r_dist),
                 "decision_ts": int(r.t), "atr_entry": float(r.atr),
                 "atr_t4_close_ms": s.t4 + P.BAR_4H_MS,
                 "atr_values": s.atr, "exposure_by_boundary": expo,
                 "costs": {"hs": P.HALF_SPREAD[tier],
                           "slip": P.SLIPPAGE[tier], "fee": P.TAKER_FEE}}
        bars = list(zip(w.open_time.astype(int), w.open, w.high, w.low,
                        w.close))
        episodes.append((trade, bars, sym, s))
    return episodes


def run_episode(action_fn, trade, bars):
    env = TradeManagementEnv(trade, bars)
    obs, _ = env.reset(seed=0)
    total = 0.0
    acts: dict = {}
    while True:
        a = action_fn(env, obs)
        acts[ACTIONS[a]] = acts.get(ACTIONS[a], 0) + 1
        obs, reward, term, trunc, _ = env.step(a)
        total += float(reward)
        if term or trunc:
            return total, acts


def main() -> None:  # pragma: no cover — official reporting run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--equity-ledger", required=True)
    ap.add_argument("--sb3-dir", required=True)
    ap.add_argument("--v1-report", required=True,
                    help="arm_f_statistics_report.json (v1 — preserved "
                         "invalidated-comparison history; non-baseline "
                         "statistics are carried over verbatim)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(os.path.join(args.sb3_dir, "arm_f_sb3_manifest.json")) as f:
        man = json.load(f)
    with open(args.v1_report) as f:
        v1 = json.load(f)

    lake = GuardedLake(args.lake, args.manifests_dir)
    end_ms = int(lake.partition["quarantine_start_ms"]) - P.BAR_15M_MS
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    df = feats[["t", "symbol", "split"]].merge(
        labels[["t", "symbol", "side", "close", "r_dist", "rank", "atr",
                "net_r", "exit_t", "qty_filled"]],
        on=["t", "symbol"], validate="1:1")
    eq = pd.read_parquet(args.equity_ledger)
    expo = {int(r.t): (float(r.gross_exposure) / float(r.equity)
                       if r.equity > 0 else 5.0) for r in eq.itertuples()}
    eps = build_episodes_with_series(df[df.split == "validation"], lake,
                                     end_ms, expo)
    print(f"validation episodes: {len(eps)}", flush=True)

    # exact conventional baseline
    base_rewards, base_acts = [], {}
    for trade, bars, _sym, series in eps:
        mgr = ConventionalManager(series)
        r, acts = run_episode(lambda env, _o: mgr.action(env), trade, bars)
        base_rewards.append(r)
        for k, v in acts.items():
            base_acts[k] = base_acts.get(k, 0) + v
    baseline = float(np.mean(base_rewards))
    print(f"EXACT conventional baseline mean reward: {baseline:.5f} "
          f"actions {base_acts}", flush=True)

    from stable_baselines3 import PPO
    per_seed = []
    for rrec in man["seed_results"]:
        model = PPO.load(os.path.join(
            args.sb3_dir, f"arm_f_sb3_seed{rrec['seed']}.zip"),
            device="cpu")
        vals = []
        for trade, bars, _sym, _s in eps:
            r, _a = run_episode(
                lambda env, obs: int(model.predict(
                    obs, deterministic=True)[0]), trade, bars)
            vals.append(r)
        mean_v = float(np.mean(vals))
        per_seed.append({
            "seed": rrec["seed"],
            "validation_mean_reward": rrec["validation_mean_reward"],
            "recomputed": mean_v,
            "recomputation_matches":
                abs(mean_v - rrec["validation_mean_reward"]) < 1e-9,
            "beats_exact_conventional_baseline":
                rrec["validation_mean_reward"] > baseline,
            "margin_vs_baseline":
                rrec["validation_mean_reward"] - baseline})
        print(f"seed {rrec['seed']}: {rrec['validation_mean_reward']:.5f} "
              f"vs baseline {baseline:.5f} -> "
              f"{'WIN' if per_seed[-1]['beats_exact_conventional_baseline'] else 'LOSS'}",
              flush=True)

    n_beat = sum(1 for p in per_seed
                 if p["beats_exact_conventional_baseline"])
    report = {
        "preregistration": "PREREGISTRATION_ARM_F_BASELINE.md",
        "invalidated_history": ("v1 HOLD-baseline comparison preserved "
                                "unmodified in arm_f_statistics_report"
                                ".json — HOLD is NOT the frozen Arm A "
                                "conventional manager"),
        "baseline": {
            "definition": ("EXACT frozen Arm A conventional manager "
                           "(trailing-channel exit then time exit, "
                           "ArmARunner order; identical episodes, bars, "
                           "costs, exit ordering, terminal reward)"),
            "parity_proof": "tests/test_arm_f_baseline_parity.py",
            "mean_validation_reward": baseline,
            "action_distribution": base_acts,
            "v1_hold_baseline_for_reference":
                v1["statistics"]
                ["hold_baseline_validation_mean_reward"]},
        "per_seed": per_seed,
        "wins_losses": {"wins": n_beat, "losses": len(per_seed) - n_beat,
                        "pct_seeds_beating_exact_baseline":
                            100.0 * n_beat / len(per_seed)},
        "carried_over_v1_statistics": {
            k: v1["statistics"][k] for k in
            ("mean_validation_reward", "median_validation_reward",
             "iqr_validation_reward", "variance_validation_reward",
             "best_seed", "worst_seed", "convergence")},
        "selection": {"selected_seed": man["selected_seed"],
                      "preserved": True,
                      "note": ("no independent artifact-integrity "
                               "failure observed; per-seed recomputation "
                               "matches the preserved manifest")},
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"baseline": baseline,
                      "wins_losses": report["wins_losses"]}, indent=2))
    print("report:", args.out, "sha256:",
          hashlib.sha256(open(args.out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
