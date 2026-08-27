"""Dependence-aware learnability rerun — executes
PREREGISTRATION_LEARNABILITY_BLOCKS.md verbatim (adjudication blocker 5).

The v1 i.i.d. label-permutation p-values are RETRACTED as dependence-
blind (v1 report preserved unmodified). This rerun keeps the SAME
observed models and metrics as v1 (identical draft hyperparameters and
model seed) and replaces only the statistical assessment: block
permutation null, block-bootstrap CIs, sample-structure diagnostics,
ESS, and approximate power at the pre-registered minimum useful effect.
It reports; it does not self-adjudicate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os

import numpy as np
import pandas as pd

import lightgbm as lgb

from lab import protocol as P
from lab.models.pipelines import _LGB_DRAFT, validate_columns
from lab.tools.learnability import auc, spearman

MODEL_SEED = 20260826          # identical to v1 -> identical observed stats
PERM_SEED = 20260827           # pre-registered
BOOT_SEED = 20260828           # pre-registered
N_PERMUTATIONS = 200           # pre-registered
N_BOOTSTRAP = 1000             # pre-registered
BLOCK_MS = 28 * 24 * 3600 * 1000   # 28 calendar days, pre-registered
MUE_AUC_DEV = 0.05             # pre-registered minimum useful effect
MUE_IC = 0.05


# ------------------------------------------------------------ structure
def block_ids(ts: np.ndarray, anchor: int) -> np.ndarray:
    return ((ts - anchor) // BLOCK_MS).astype(np.int64)


def icc_anova(y: np.ndarray, groups: np.ndarray) -> float:
    """One-way ANOVA ICC(1) over cluster labels; y may be binary."""
    df = pd.DataFrame({"y": y, "g": groups})
    k = df.g.nunique()
    n = len(df)
    if k < 2 or n <= k:
        return 0.0
    gm = df.y.mean()
    agg = df.groupby("g")["y"].agg(["mean", "count"])
    ssb = float((agg["count"] * (agg["mean"] - gm) ** 2).sum())
    ssw = float(((df.y - df.g.map(agg["mean"])) ** 2).sum())
    msb = ssb / (k - 1)
    msw = ssw / (n - k)
    m0 = (n - float((agg["count"] ** 2).sum()) / n) / (k - 1)
    denom = msb + (m0 - 1) * msw
    return float((msb - msw) / denom) if denom > 0 else 0.0


def design_effect(y: np.ndarray, groups: np.ndarray) -> dict:
    icc = icc_anova(y, groups)
    k = len(np.unique(groups))
    m_bar = len(y) / k
    de = max(1.0, 1.0 + (m_bar - 1.0) * icc)
    return {"icc": icc, "n_clusters": k, "mean_cluster_size": m_bar,
            "design_effect": de, "ess": len(y) / de}


def overlap_stats(lo: np.ndarray, hi: np.ndarray,
                  boundaries: np.ndarray) -> dict:
    n = len(lo)
    pairs = 0
    chunk = 512
    for i in range(0, n, chunk):
        li, hii = lo[i:i + chunk, None], hi[i:i + chunk, None]
        ov = (li <= hi[None, :]) & (lo[None, :] <= hii)
        pairs += int(ov.sum()) - ov.shape[0]        # remove self-pairs
    # every unordered pair was counted twice (once per ordered direction)
    total_unordered = pairs // 2
    concurrent = [int(((lo <= t) & (hi >= t)).sum()) for t in boundaries]
    return {"n_labels": n,
            "overlapping_pair_fraction":
                total_unordered / (n * (n - 1) / 2) if n > 1 else 0.0,
            "mean_concurrent_open_intervals": float(np.mean(concurrent)),
            "max_concurrent_open_intervals": int(np.max(concurrent))}


# ---------------------------------------------------------- permutation
def permuted_labels(net_r: np.ndarray, ts: np.ndarray,
                    rng: np.random.Generator) -> np.ndarray:
    """One pre-registered block permutation of net_r (rows MUST be sorted
    by (t, symbol) upstream): shuffle 28-day BLOCK order, boundary groups
    ride inside blocks, lay groups back onto the original boundary slots,
    within-slot assignment by rank r -> incoming[r % len(incoming)]."""
    ub, inv = np.unique(ts, return_inverse=True)
    groups = [net_r[inv == u] for u in range(len(ub))]
    bids = block_ids(ub, int(ub[0]))
    blocks: list[list[int]] = []
    for b in np.unique(bids):
        blocks.append([int(i) for i in np.where(bids == b)[0]])
    order = rng.permutation(len(blocks))
    seq = [g for bi in order for g in (groups[i] for i in blocks[bi])]
    out = np.empty_like(net_r)
    for u in range(len(ub)):
        rows = np.where(inv == u)[0]
        inc = seq[u]
        out[rows] = inc[np.arange(len(rows)) % len(inc)]
    return out


def two_sided_p(null: np.ndarray, observed: float, center: float) -> dict:
    count = int((np.abs(null - center) >= abs(observed - center)).sum())
    return {"count_ge": count, "n": len(null),
            "p_raw": count / len(null),
            "p_upper": (count + 1) / (len(null) + 1)}


def approx_power(null: np.ndarray, center: float, se: float,
                 mue_dev: float) -> float:
    """Pre-registered normal-theory approximation: c = null 95th
    percentile of |stat-center|; power ~ P(N(mue_dev, se^2) > c)."""
    c = float(np.quantile(np.abs(null - center), 0.95))
    if se <= 0:
        return float(mue_dev > c)
    z = (c - mue_dev) / se
    return float(1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))


def main() -> None:  # pragma: no cover — official diagnostic run
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.ledgers_dir,
                                   "learnability_report_v2.json")

    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    df = feats.merge(
        labels[["t", "symbol", "net_r", "info_interval_lo",
                "info_interval_hi"]],
        on=["t", "symbol"], how="left", validate="1:1")
    fcols = sorted(c for c in df.columns if c[:1] == "F" and c[1:3].isdigit())
    validate_columns(fcols)
    # deterministic (t, symbol) order — the pre-registered within-boundary
    # rank order for the permutation scheme
    tr = df[df.split == "train"].sort_values(
        ["t", "symbol"], kind="mergesort").reset_index(drop=True)
    va = df[df.split == "validation"].sort_values(
        ["t", "symbol"], kind="mergesort").reset_index(drop=True)

    Xtr = tr[fcols].to_numpy(np.float64)
    Xva = va[fcols].to_numpy(np.float64)
    ytr_c = tr.net_r.to_numpy(float)
    yva_c = va.net_r.to_numpy(float)
    yva_b = (yva_c > 0).astype(int)
    ttr = tr.t.to_numpy(np.int64)
    tva = va.t.to_numpy(np.int64)

    params = dict(_LGB_DRAFT)
    params["random_state"] = MODEL_SEED
    clf = lgb.LGBMClassifier(**params).fit(Xtr, (ytr_c > 0).astype(int))
    score_b = clf.predict_proba(Xva)[:, 1]
    obs_auc = auc(yva_b, score_b)
    reg = lgb.LGBMRegressor(**params).fit(Xtr, ytr_c)
    score_c = reg.predict(Xva)
    obs_ic = spearman(yva_c, score_c)
    print(f"observed: AUC {obs_auc:.4f} IC {obs_ic:.4f}", flush=True)

    # ---- pre-registered block permutation null --------------------------
    rng = np.random.default_rng(PERM_SEED)
    null_auc, null_ic = [], []
    for i in range(N_PERMUTATIONS):
        yp = permuted_labels(ytr_c, ttr, rng)
        c0 = lgb.LGBMClassifier(**params).fit(Xtr, (yp > 0).astype(int))
        null_auc.append(auc(yva_b, c0.predict_proba(Xva)[:, 1]))
        r0 = lgb.LGBMRegressor(**params).fit(Xtr, yp)
        null_ic.append(spearman(yva_c, r0.predict(Xva)))
        if (i + 1) % 25 == 0:
            print(f"permutation {i + 1}/{N_PERMUTATIONS}", flush=True)
    null_auc = np.array(null_auc)
    null_ic = np.array(null_ic)
    p_auc = two_sided_p(null_auc, obs_auc, 0.5)
    p_ic = two_sided_p(null_ic, obs_ic, 0.0)

    # ---- pre-registered validation block bootstrap ----------------------
    rngb = np.random.default_rng(BOOT_SEED)
    vb = block_ids(tva, int(tva.min()))
    ub = np.unique(vb)
    rows_by_block = [np.where(vb == b)[0] for b in ub]
    boot_auc, boot_ic = [], []
    for _ in range(N_BOOTSTRAP):
        pick = rngb.integers(0, len(ub), size=len(ub))
        rows = np.concatenate([rows_by_block[j] for j in pick])
        boot_auc.append(auc(yva_b[rows], score_b[rows]))
        boot_ic.append(spearman(yva_c[rows], score_c[rows]))
    boot_auc = np.array(boot_auc, float)
    boot_ic = np.array(boot_ic, float)
    ci = lambda a: [float(np.nanquantile(a, .025)),
                    float(np.nanquantile(a, .975))]
    se_auc = float(np.nanstd(boot_auc))
    se_ic = float(np.nanstd(boot_ic))

    # ---- structure diagnostics ------------------------------------------
    def split_diag(d, ts):
        y = (d.net_r.to_numpy(float) > 0).astype(float)
        per_b = d.groupby("t").size()
        return {
            "nominal_n": len(d),
            "unique_boundaries": int(d.t.nunique()),
            "labels_per_boundary": {"mean": float(per_b.mean()),
                                    "median": float(per_b.median()),
                                    "max": int(per_b.max())},
            "overlap": overlap_stats(
                d.info_interval_lo.to_numpy(np.int64),
                d.info_interval_hi.to_numpy(np.int64),
                np.unique(ts)),
            "de_boundary_level": design_effect(y, ts),
            "de_block_level": design_effect(
                y, block_ids(ts, int(ts.min()))),
        }
    diag_tr = split_diag(tr, ttr)
    diag_va = split_diag(va, tva)
    for d in (diag_tr, diag_va):
        d["ess_reported"] = d["de_block_level"]["ess"]   # pre-registered

    report = {
        "preregistration": "PREREGISTRATION_LEARNABILITY_BLOCKS.md",
        "retraction": ("v1 label-permutation p-values (AUC p=0.42, IC "
                       "p=0.67) RETRACTED as dependence-blind; v1 report "
                       "preserved unmodified as learnability_report.json"),
        "block_definition_ms": BLOCK_MS,
        "seeds": {"model": MODEL_SEED, "permutation": PERM_SEED,
                  "bootstrap": BOOT_SEED},
        "observed": {"validation_auc": obs_auc,
                     "validation_rank_ic": obs_ic},
        "block_permutation": {
            "n_permutations": N_PERMUTATIONS,
            "auc": p_auc, "rank_ic": p_ic,
            "null_auc_abs_dev_q95":
                float(np.quantile(np.abs(null_auc - 0.5), 0.95)),
            "null_ic_abs_q95": float(np.quantile(np.abs(null_ic), 0.95))},
        "block_bootstrap": {
            "n_resamples": N_BOOTSTRAP,
            "auc_ci95": ci(boot_auc), "auc_se": se_auc,
            "rank_ic_ci95": ci(boot_ic), "rank_ic_se": se_ic},
        "power_at_mue": {
            "mue": {"auc_deviation": MUE_AUC_DEV, "abs_rank_ic": MUE_IC},
            "method": "APPROXIMATE normal-theory (pre-registered)",
            "auc": approx_power(null_auc, 0.5, se_auc, MUE_AUC_DEV),
            "rank_ic": approx_power(null_ic, 0.0, se_ic, MUE_IC)},
        "structure": {"train": diag_tr, "validation": diag_va},
        "frozen_il_rule": ("See PREREGISTRATION_LEARNABILITY_BLOCKS.md — "
                           "frozen before Checkpoint 2"),
        "interim_conclusion": ("NO DEMONSTRATED LEARNABILITY; statistical "
                               "significance not adjudicated"),
    }
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    body = open(out, "rb").read()
    print(json.dumps({"observed": report["observed"],
                      "auc_p_upper": p_auc["p_upper"],
                      "ic_p_upper": p_ic["p_upper"],
                      "auc_ci95": report["block_bootstrap"]["auc_ci95"],
                      "ic_ci95": report["block_bootstrap"]["rank_ic_ci95"],
                      "power": report["power_at_mue"]}, indent=2))
    print("report:", out, "sha256:", hashlib.sha256(body).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
