"""Steps 7-8: compute profiling, then official training of Arms B/C/E
(LightGBM pipelines) and Arm F (deterministic CEM, >= 10 official seeds),
validated on the purged validation split only. Artifacts are frozen with
hashes into model_manifest.json.

Selection rules are PRE-SPECIFIED here, before any result is seen:
  B threshold: the draft 0.5 (no search in this phase);
  C/E: draft pipelines as-is;
  F: among the official seeds, the policy with the highest MEAN VALIDATION
     reward is frozen as THE Arm F policy; every seed's training history
     and validation score is preserved (no silent discards).

Compute profiling (step 7): before full CEM training, one generation is
timed and the full 10-seed cost projected; the projection and the chosen
hyperparameters are recorded in the manifest. If the projection exceeds
the budget, hyperparameters are reduced AND the reduction is recorded —
never silently.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

from lab import protocol as P
from lab.arms.rl_train import LinearPolicy, evaluate, train_cem
from lab.data.access import GuardedLake
from lab.models.pipelines import FilterPipeline, RankerPipeline, \
    SizerPipeline

OFFICIAL_SEEDS = list(range(1, 11))          # 10 official seeds, fixed
TIME_BUDGET_S = 3 * 3600                     # local training budget


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def examples_from(df: pd.DataFrame, fcols: list[str]) -> list[dict]:
    out = []
    for r in df.itertuples():
        out.append({"t": int(r.t), "symbol": r.symbol,
                    "net_r": float(r.net_r),
                    "info_interval": (int(r.info_interval_lo),
                                      int(r.info_interval_hi)),
                    "features": {c: getattr(r, c) for c in fcols}})
    return out


def build_episodes(df: pd.DataFrame, lake: GuardedLake,
                   end_ms: int) -> list[tuple[dict, list]]:
    """One episode per executed labeled trade: bars from the entry bar
    (first 15m after the decision) through exit + one 4h buffer."""
    episodes = []
    by_symbol: dict[str, pd.DataFrame] = {}
    for r in df.itertuples():
        sym = r.symbol
        if sym not in by_symbol:
            by_symbol[sym] = lake.read_klines(sym, 0, end_ms)
        k = by_symbol[sym]
        lo = int(r.t) + P.BAR_15M_MS
        hi = min(int(r.exit_t) + P.BAR_4H_MS, end_ms)
        w = k[(k.open_time >= lo) & (k.open_time <= hi)]
        if w.empty:
            continue
        tier = 1 if int(r.rank) <= P.TIER1_TOP_N else 2
        trade = {"side": int(r.side), "qty": float(r.qty_filled),
                 "entry_ref": float(r.close), "r_dist": float(r.r_dist),
                 "costs": {"hs": P.HALF_SPREAD[tier],
                           "slip": P.SLIPPAGE[tier], "fee": P.TAKER_FEE}}
        bars = list(zip(w.open_time.astype(int), w.open, w.high, w.low,
                        w.close))
        episodes.append((trade, bars))
    return episodes


def main() -> None:  # pragma: no cover — official training run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    lake = GuardedLake(args.lake, args.manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    val_start = int(part["validation_start_ms"])
    end_ms = q - P.BAR_15M_MS

    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    df = feats.merge(
        labels[["t", "symbol", "net_r", "exit_t", "qty_filled",
                "info_interval_lo", "info_interval_hi"]],
        on=["t", "symbol"], validate="1:1")
    cands = pd.read_parquet(
        os.path.join(args.ledgers_dir, "candidates_arm_a.parquet"))
    df = df.merge(cands[["t", "symbol", "side", "close", "r_dist", "rank",
                         "qty_submitted"]], on=["t", "symbol"],
                  validate="1:1")
    fcols = sorted(c for c in df.columns
                   if c[:1] == "F" and c[1:3].isdigit())
    tr = df[df.split == "train"]
    va = df[df.split == "validation"]
    print(f"train {len(tr)} / validation {len(va)}", flush=True)

    manifest: dict = {"selection_rules": __doc__.split("Selection rules")[1]
                      .split("Compute profiling")[0].strip(),
                      "official_seeds": OFFICIAL_SEEDS}

    # ---- Arms B / C / E (LightGBM drafts, purge-guarded fit) -------------
    ex_tr = examples_from(tr, fcols)
    t0 = time.time()
    armB = FilterPipeline().fit(ex_tr, fcols, val_start)
    armC = RankerPipeline().fit(ex_tr, fcols, val_start)
    armE = SizerPipeline().fit(ex_tr, fcols, val_start)
    print(f"B/C/E fitted ({time.time() - t0:.1f}s)", flush=True)

    Xva = va[fcols]
    bprob = armB.model.predict_proba(Xva.to_numpy(float))[:, 1]
    cscore = armC.model.predict(Xva.to_numpy(float))
    yva = va["net_r"].to_numpy(float)

    def _auc(y, s):
        o = np.argsort(s)
        rk = np.empty(len(s)); rk[o] = np.arange(1, len(s) + 1)
        pos = y > 0
        n1, n0 = int(pos.sum()), int((~pos).sum())
        return float((rk[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)) \
            if n1 and n0 else float("nan")

    manifest["arm_b"] = {
        "version": armB.version, "threshold": armB.threshold,
        "validation_auc": _auc(yva, bprob),
        "validation_accept_rate": float((bprob >= armB.threshold).mean()),
        "accepted_mean_net_r": float(yva[bprob >= armB.threshold].mean())
        if (bprob >= armB.threshold).any() else None,
        "rejected_mean_net_r": float(yva[bprob < armB.threshold].mean())
        if (bprob < armB.threshold).any() else None}
    ra = pd.Series(cscore).rank(); rb = pd.Series(yva).rank()
    manifest["arm_c"] = {
        "version": armC.version,
        "validation_rank_ic": float(np.corrcoef(ra, rb)[0, 1])}
    ebuck = np.array([armE.bucket(None, dict(zip(fcols, row)))
                      for row in Xva.to_numpy(float)])
    manifest["arm_e"] = {
        "version": armE.version,
        "bucket_counts": {str(b): int((ebuck == b).sum())
                          for b in sorted(set(ebuck))},
        "mean_net_r_by_bucket": {str(b): float(yva[ebuck == b].mean())
                                 for b in sorted(set(ebuck))}}

    armB.model.booster_.save_model(os.path.join(args.out_dir, "arm_b.txt"))
    armC.model.booster_.save_model(os.path.join(args.out_dir, "arm_c.txt"))
    armE.model.booster_.save_model(os.path.join(args.out_dir, "arm_e.txt"))
    np.savez(os.path.join(args.out_dir, "arm_e_cuts.npz"), cuts=armE._cuts)

    # ---- Arm F: episodes, profiling, 10-seed CEM -------------------------
    print("building episodes...", flush=True)
    ep_tr = build_episodes(tr, lake, end_ms)
    ep_va = build_episodes(va, lake, end_ms)
    print(f"episodes: train {len(ep_tr)} / validation {len(ep_va)}",
          flush=True)

    hp = dict(generations=20, population=32, episodes_per_gen=128)
    t0 = time.time()
    _ = evaluate(LinearPolicy(np.zeros((11) * 6)),
                 ep_tr[: min(64, len(ep_tr))])
    per_ep = (time.time() - t0) / min(64, len(ep_tr))
    proj = (per_ep * hp["episodes_per_gen"] * hp["population"]
            * hp["generations"] * len(OFFICIAL_SEEDS))
    profile = {"seconds_per_episode": per_ep,
               "projected_total_seconds": proj,
               "budget_seconds": TIME_BUDGET_S,
               "hyperparameters_initial": dict(hp)}
    while proj > TIME_BUDGET_S:
        # reduce, never silently: recorded right here
        if hp["episodes_per_gen"] > 48:
            hp["episodes_per_gen"] = int(hp["episodes_per_gen"] * 0.75)
        elif hp["population"] > 16:
            hp["population"] = int(hp["population"] * 0.75)
        else:
            hp["generations"] = max(8, hp["generations"] - 2)
            if hp["generations"] == 8:
                break
        proj = (per_ep * hp["episodes_per_gen"] * hp["population"]
                * hp["generations"] * len(OFFICIAL_SEEDS))
    profile["hyperparameters_final"] = dict(hp)
    profile["projected_final_seconds"] = proj
    manifest["arm_f_compute_profile"] = profile
    print("compute profile:", json.dumps(profile), flush=True)

    seed_results = []
    for seed in OFFICIAL_SEEDS:
        t0 = time.time()
        res = train_cem(ep_tr, seed, log=lambda m: print(m, flush=True),
                        **hp)
        pol = LinearPolicy(np.array(res["theta"]))
        res["validation_mean_reward"] = evaluate(pol, ep_va)
        res["train_seconds"] = round(time.time() - t0, 1)
        seed_results.append(res)
        print(f"seed {seed}: val reward "
              f"{res['validation_mean_reward']:.4f} "
              f"({res['train_seconds']}s)", flush=True)

    best = max(seed_results, key=lambda r: r["validation_mean_reward"])
    np.savez(os.path.join(args.out_dir, "arm_f_policy.npz"),
             theta=np.array(best["theta"]), seed=best["seed"])
    with open(os.path.join(args.out_dir, "arm_f_seeds.json"), "w") as f:
        json.dump(seed_results, f, indent=1, sort_keys=True)
    manifest["arm_f"] = {
        "algorithm": best["algorithm"],
        "selected_seed": best["seed"],
        "selection_rule": "highest mean validation reward (pre-specified)",
        "validation_rewards_by_seed": {
            str(r["seed"]): r["validation_mean_reward"]
            for r in seed_results},
        "hyperparameters": best["hyperparameters"]}

    # ---- freeze ----------------------------------------------------------
    manifest["artifacts"] = {
        name: {"path": os.path.join(args.out_dir, name),
               "sha256": sha256_file(os.path.join(args.out_dir, name))}
        for name in ("arm_b.txt", "arm_c.txt", "arm_e.txt",
                     "arm_e_cuts.npz", "arm_f_policy.npz",
                     "arm_f_seeds.json")}
    mpath = os.path.join(args.out_dir, "model_manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print("model manifest:", mpath, flush=True)
    print(json.dumps({k: manifest[k] for k in
                      ("arm_b", "arm_c", "arm_e", "arm_f")}, indent=2),
          flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
