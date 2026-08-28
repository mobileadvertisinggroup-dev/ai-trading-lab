"""Arm F required reporting (D61 blocker E) — NO retraining.

From the ten PRESERVED official SB3 artifacts, computes every
SPEC-required statistic: mean/median/IQR/variance of validation reward,
best and worst seed, the percentage of seeds beating Arm A conventional
management under the EXACT same episodes and terminal reward definition
(baseline = hold at every decision; the env enforces the frozen
stop/target/episode-end backstops — the same reward function scores
both), convergence count and per-seed status, the selected seed's
status, and complete action distributions from the deterministic
evaluation passes. The frozen selection rule is re-applied and must
still select the preserved seed; the tool REFUSES to change it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np
import pandas as pd

from lab import protocol as P
from lab.arms.rl_env import ACTIONS, TradeManagementEnv
from lab.data.access import GuardedLake
from lab.tools.train_arm_f_sb3 import build_episodes_v2


def episode_stats(model, episodes, action_counts):
    total = []
    for trade, bars in episodes:
        env = TradeManagementEnv(trade, bars)
        obs, _ = env.reset(seed=0)
        ep = 0.0
        while True:
            if model is None:
                a = 0                                    # hold baseline
            else:
                a, _s = model.predict(obs, deterministic=True)
                a = int(a)
            action_counts[ACTIONS[a]] = action_counts.get(ACTIONS[a],
                                                          0) + 1
            obs, reward, term, trunc, _ = env.step(a)
            ep += float(reward)
            if term or trunc:
                break
        total.append(ep)
    return float(np.mean(total))


def main() -> None:  # pragma: no cover — official reporting run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--equity-ledger", required=True)
    ap.add_argument("--sb3-dir", required=True)
    ap.add_argument("--shakedown-observability", required=True,
                    help="SHAKEDOWN_INVALID_rl_observability.json of the "
                         "replacement shakedown (for the action-collapse "
                         "statement)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.sb3_dir,
                                   "arm_f_statistics_report.json")

    with open(os.path.join(args.sb3_dir, "arm_f_sb3_manifest.json")) as f:
        man = json.load(f)
    seed_results = man["seed_results"]
    vals = {r["seed"]: r["validation_mean_reward"] for r in seed_results}
    conv = {r["seed"]: r["convergence"].get("non_converged")
            for r in seed_results}

    # frozen selection rule re-applied — must match the preserved choice
    best = seed_results[0]
    for r in seed_results[1:]:
        if r["validation_mean_reward"] > best["validation_mean_reward"]:
            best = r
    if best["seed"] != man["selected_seed"]:
        raise SystemExit("frozen rule selects a different seed than the "
                         "preserved artifact — refusing (post-hoc "
                         "selection prohibited)")

    lake = GuardedLake(args.lake, args.manifests_dir)
    q = int(lake.partition["quarantine_start_ms"])
    end_ms = q - P.BAR_15M_MS
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
    ep_va = build_episodes_v2(df[df.split == "validation"], lake, end_ms,
                              expo)
    print(f"validation episodes: {len(ep_va)}", flush=True)

    # baseline: Arm A conventional management = hold at every decision,
    # identical episodes, identical terminal reward definition
    base_actions: dict = {}
    baseline_val = episode_stats(None, ep_va, base_actions)
    print(f"hold-baseline validation mean reward: {baseline_val:.5f}",
          flush=True)

    from stable_baselines3 import PPO
    per_seed = []
    for r in seed_results:
        model = PPO.load(os.path.join(
            args.sb3_dir, f"arm_f_sb3_seed{r['seed']}.zip"), device="cpu")
        acts: dict = {}
        recomputed = episode_stats(model, ep_va, acts)
        per_seed.append({
            "seed": r["seed"],
            "validation_mean_reward": r["validation_mean_reward"],
            "recomputed_validation_mean_reward": recomputed,
            "recomputation_matches":
                abs(recomputed - r["validation_mean_reward"]) < 1e-9,
            "train_mean_reward": r["train_mean_reward"],
            "non_converged": conv[r["seed"]],
            "beats_hold_baseline":
                r["validation_mean_reward"] > baseline_val,
            "validation_action_distribution": acts})
        print(f"seed {r['seed']}: val {r['validation_mean_reward']:.5f} "
              f"recomputed {recomputed:.5f} actions {acts}", flush=True)

    v = np.array([vals[s] for s in sorted(vals)])
    q1, q3 = float(np.percentile(v, 25)), float(np.percentile(v, 75))
    n_beat = sum(1 for p in per_seed if p["beats_hold_baseline"])
    with open(args.shakedown_observability) as f:
        obs = json.load(f)
    shake_actions = {a: obs["per_arm"][a]["executed_action_counts"]
                     for a in obs["per_arm"]}

    report = {
        "directive": "D61 blocker E — reporting only; NO retraining",
        "statistics": {
            "mean_validation_reward": float(v.mean()),
            "median_validation_reward": float(np.median(v)),
            "iqr_validation_reward": {"q1": q1, "q3": q3,
                                      "iqr": q3 - q1},
            "variance_validation_reward": float(v.var(ddof=1)),
            "best_seed": max(vals, key=lambda s: vals[s]),
            "worst_seed": min(vals, key=lambda s: vals[s]),
            "hold_baseline_validation_mean_reward": baseline_val,
            "pct_seeds_beating_arm_a_conventional":
                100.0 * n_beat / len(per_seed),
            "n_seeds_beating_baseline": n_beat,
            "convergence": {
                "n_non_converged": sum(1 for s in conv.values() if s),
                "per_seed": conv,
                "selected_seed": man["selected_seed"],
                "selected_seed_non_converged":
                    conv[man["selected_seed"]]},
            "hold_baseline_action_distribution": base_actions},
        "per_seed": per_seed,
        "replacement_shakedown_executed_actions": shake_actions,
        "explicit_statements": [
            "7/10 seeds were flagged non-converged by the pre-registered "
            "diagnostic",
            "the selected seed 4 was itself flagged non-converged",
            "the selected validation mean reward was approximately "
            "+0.00449",
            "in the replacement shakedown the executed RL actions "
            "collapsed to HOLD and CLOSE only",
            "no RL management edge has been demonstrated",
        ],
        "selection": {"selected_seed": man["selected_seed"],
                      "rule": man["selection_rule"],
                      "rule_still_selects_this_seed": True},
    }
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps(report["statistics"], indent=2))
    print("report:", out, "sha256:",
          hashlib.sha256(open(out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
