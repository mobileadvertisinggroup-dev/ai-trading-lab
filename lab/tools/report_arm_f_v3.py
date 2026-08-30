"""Arm F reporting v3 — the D72 funding-corrected comparison.

Same frozen procedure as PREREGISTRATION_ARM_F_BASELINE.md /
PREREGISTRATION_ARM_F_SB3.md (nothing about the baseline definition,
episode construction order, evaluation determinism, or the seed
selection rule changes) — but episodes now carry the frozen funding
rates (D72), so the exact conventional baseline AND every retrained
seed are evaluated net of funding. Produces fresh statistics for the
RETRAINED 10-seed family plus an explicit old-vs-corrected section;
the superseded v1/v2 reports and the superseded no-funding manifest
are preserved unmodified as history.
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
    """The frozen Arm A conventional manager, replayed per episode
    (identical to report_arm_f_v2 — parity proven in
    tests/test_arm_f_baseline_parity.py)."""

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
    """report_arm_f_v2 episode construction + D72 funding_by_time."""
    episodes = []
    kcache, scache, fcache = {}, {}, {}
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
            fdf = lake.read_funding(sym, 0, end_ms)
            fcache[sym] = dict(zip(fdf["funding_time"].astype(np.int64),
                                   fdf["funding_rate"].astype(float)))
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
        fb = {int(ft): fr for ft, fr in fcache[sym].items()
              if lo <= ft <= hi}
        trade = {"side": int(r.side), "qty": float(r.qty_filled),
                 "entry_ref": float(r.close), "r_dist": float(r.r_dist),
                 "decision_ts": int(r.t), "atr_entry": float(r.atr),
                 "atr_t4_close_ms": s.t4 + P.BAR_4H_MS,
                 "atr_values": s.atr, "exposure_by_boundary": expo,
                 "funding_by_time": fb,
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
    n_funding = 0
    while True:
        a = action_fn(env, obs)
        acts[ACTIONS[a]] = acts.get(ACTIONS[a], 0) + 1
        obs, reward, term, trunc, _ = env.step(a)
        total += float(reward)
        if term or trunc:
            n_funding = sum(1 for e in env.engine.events
                            if e["kind"] == "funding")
            return total, acts, n_funding


def main() -> None:  # pragma: no cover — official reporting run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--equity-ledger", required=True)
    ap.add_argument("--sb3-dir", required=True,
                    help="dir with the RETRAINED (funding-corrected) "
                         "manifest + seed zips")
    ap.add_argument("--old-manifest", required=True,
                    help="the superseded no-funding arm_f_sb3_manifest"
                         ".json (history; read-only)")
    ap.add_argument("--old-report", required=True,
                    help="the superseded arm_f_statistics_report_v2.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(os.path.join(args.sb3_dir, "arm_f_sb3_manifest.json")) as f:
        man = json.load(f)
    with open(args.old_manifest) as f:
        old_man = json.load(f)
    with open(args.old_report) as f:
        old_rep = json.load(f)

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
    n_funding_eps = sum(1 for tr, _b, _s, _se in eps
                        if tr["funding_by_time"])
    print(f"validation episodes: {len(eps)} "
          f"({n_funding_eps} with funding rates)", flush=True)

    # exact conventional baseline, funding-corrected
    base_rewards, base_acts = [], {}
    base_funding_events = 0
    for trade, bars, _sym, series in eps:
        mgr = ConventionalManager(series)
        r, acts, nf = run_episode(lambda env, _o: mgr.action(env),
                                  trade, bars)
        base_rewards.append(r)
        base_funding_events += nf
        for k, v in acts.items():
            base_acts[k] = base_acts.get(k, 0) + v
    baseline = float(np.mean(base_rewards))
    print(f"EXACT conventional baseline (funding-corrected): "
          f"{baseline:.5f} funding events {base_funding_events}",
          flush=True)
    if base_funding_events == 0:
        raise SystemExit("STOP: zero funding events across all baseline "
                         "episodes — funding is not flowing (D72 guard)")

    from stable_baselines3 import PPO
    per_seed = []
    for rrec in man["seed_results"]:
        model = PPO.load(os.path.join(
            args.sb3_dir, f"arm_f_sb3_seed{rrec['seed']}.zip"),
            device="cpu")
        vals = []
        for trade, bars, _sym, _s in eps:
            r, _a, _nf = run_episode(
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
            "convergence": rrec["convergence"],
            "beats_exact_conventional_baseline":
                rrec["validation_mean_reward"] > baseline,
            "margin_vs_baseline":
                rrec["validation_mean_reward"] - baseline})
        print(f"seed {rrec['seed']}: {rrec['validation_mean_reward']:.5f}"
              f" vs baseline {baseline:.5f} -> "
              f"{'WIN' if per_seed[-1]['beats_exact_conventional_baseline'] else 'LOSS'}",
              flush=True)

    vals = np.array([p["validation_mean_reward"] for p in per_seed])
    n_beat = int(sum(1 for p in per_seed
                     if p["beats_exact_conventional_baseline"]))
    n_nonconv = sum(1 for p in per_seed
                    if p["convergence"].get("non_converged"))
    old_by_seed = {r["seed"]: r["validation_mean_reward"]
                   for r in old_man["seed_results"]}
    report = {
        "preregistrations": ["PREREGISTRATION_ARM_F_SB3.md (+ D72 "
                             "funding amendment)",
                             "PREREGISTRATION_ARM_F_BASELINE.md"],
        "correction": ("D72: episodes carry frozen funding rates; the "
                       "policy family was RETRAINED (all 10 official "
                       "seeds) and the exact conventional baseline "
                       "re-evaluated, both net of funding"),
        "baseline": {
            "definition": ("EXACT frozen Arm A conventional manager "
                           "(trailing-channel then time exit, ArmARunner "
                           "order), episodes WITH funding"),
            "parity_proof": "tests/test_arm_f_baseline_parity.py",
            "mean_validation_reward": baseline,
            "action_distribution": base_acts,
            "n_funding_events": int(base_funding_events)},
        "per_seed": per_seed,
        "statistics": {
            "mean_validation_reward": float(vals.mean()),
            "median_validation_reward": float(np.median(vals)),
            "iqr_validation_reward": float(np.percentile(vals, 75)
                                           - np.percentile(vals, 25)),
            "variance_validation_reward": float(vals.var(ddof=1)),
            "best_seed": int(per_seed[int(np.argmax(vals))]["seed"]),
            "worst_seed": int(per_seed[int(np.argmin(vals))]["seed"]),
            "n_non_converged": int(n_nonconv)},
        "wins_losses": {"wins": n_beat, "losses": len(per_seed) - n_beat,
                        "pct_seeds_beating_exact_baseline":
                            100.0 * n_beat / len(per_seed)},
        "selection": {"selected_seed": man["selected_seed"],
                      "rule": man["selection_rule"]},
        "old_vs_corrected": {
            "superseded_no_funding_selected_seed":
                old_man["selected_seed"],
            "superseded_no_funding_baseline":
                old_rep["baseline"]["mean_validation_reward"],
            "superseded_no_funding_wins_losses":
                old_rep["wins_losses"],
            "per_seed_delta": [
                {"seed": p["seed"],
                 "old_no_funding": old_by_seed.get(p["seed"]),
                 "corrected": p["validation_mean_reward"],
                 "delta": (p["validation_mean_reward"]
                           - old_by_seed.get(p["seed"]))
                 if old_by_seed.get(p["seed"]) is not None else None}
                for p in per_seed],
            "note": ("old values are from policies trained AND evaluated "
                     "without funding — preserved as superseded history, "
                     "not comparable like-for-like to the corrected "
                     "family beyond direction and magnitude")},
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"baseline": baseline,
                      "wins_losses": report["wins_losses"],
                      "selected_seed": man["selected_seed"]}, indent=2))
    print("report:", args.out, "sha256:",
          hashlib.sha256(open(args.out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
