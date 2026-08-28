"""Learnability v3 — executes PREREGISTRATION_LEARNABILITY_V3.md
verbatim (D61 blocker D).

Corrects the two v2 implementation defects: the permutation is now an
EXACT-multiset circular rotation of the label vector by whole-boundary
trade counts (a bijection — no modulo duplication/truncation), and the
CI bootstrap is a TRUE circular moving-block bootstrap (uniformly
random circular starts, overlapping blocks). The observed models and
metrics are identical to v1/v2 (same frozen hyperparameters and model
seed — observed AUC/IC must reproduce exactly). v1 stays retracted; v2
stays preserved as not-adjudicated history. ESS is an APPROXIMATION.
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

from lab.models.pipelines import _LGB_DRAFT, validate_columns
from lab.tools.learnability import auc, spearman
from lab.tools.learnability_v2 import (MODEL_SEED, MUE_AUC_DEV, MUE_IC,
                                       design_effect, overlap_stats,
                                       two_sided_p)

PERM_SEED_V3 = 20260831
BOOT_SEED_V3 = 20260832
N_PERMUTATIONS = 200
N_BOOTSTRAP = 1000
BLOCK_DAYS = 28
D28_MS = 28 * 24 * 3600 * 1000
BLOCK_MS = D28_MS


def eligible_rotation_boundaries(ub: np.ndarray) -> np.ndarray:
    """Pre-registered eligibility: new-start boundary b_{j+1} displaced
    from b_1 by >= 28 days and <= span − 28 days."""
    span = int(ub[-1]) - int(ub[0])
    d = ub - ub[0]
    return np.where((d >= D28_MS) & (d <= span - D28_MS))[0]


def rotate_labels(y: np.ndarray, ts: np.ndarray,
                  j: int) -> np.ndarray:
    """EXACT-multiset circular rotation by the total trade count of the
    first j boundaries (rows MUST be sorted (t, symbol) upstream)."""
    ub, counts = np.unique(ts, return_counts=True)
    s = int(np.cumsum(counts)[j - 1]) if j > 0 else 0
    return np.concatenate([y[s:], y[:s]])


def draw_rotations(ts: np.ndarray, n: int, seed: int) -> list[int]:
    ub = np.unique(ts)
    elig = eligible_rotation_boundaries(ub)
    if len(elig) == 0:
        raise SystemExit("no eligible rotation offsets — adjudication "
                         "required")
    rng = np.random.default_rng(seed)
    return [int(rng.choice(elig)) for _ in range(n)]


def circular_moving_block_sequences(u: int, l_block: int, n: int,
                                    seed: int) -> list[np.ndarray]:
    """TRUE circular moving-block draws: every start position allowed
    (overlapping blocks), L consecutive with wrap, concatenated and
    truncated to exactly u indices."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        idx: list[int] = []
        while len(idx) < u:
            s = int(rng.integers(0, u))
            idx.extend(((s + k) % u) for k in range(l_block))
        out.append(np.array(idx[:u], dtype=np.int64))
    return out


def main() -> None:  # pragma: no cover — official diagnostic run
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.ledgers_dir,
                                   "learnability_report_v3.json")

    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    df = feats.merge(
        labels[["t", "symbol", "net_r", "info_interval_lo",
                "info_interval_hi"]],
        on=["t", "symbol"], how="left", validate="1:1")
    fcols = sorted(c for c in df.columns
                   if c[:1] == "F" and c[1:3].isdigit())
    validate_columns(fcols)
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

    # ---- v3 permutation null: exact-multiset circular rotation ----------
    rots = draw_rotations(ttr, N_PERMUTATIONS, PERM_SEED_V3)
    null_auc, null_ic = [], []
    for i, j in enumerate(rots):
        yp = rotate_labels(ytr_c, ttr, j)
        assert len(yp) == len(ytr_c)
        c0 = lgb.LGBMClassifier(**params).fit(Xtr, (yp > 0).astype(int))
        null_auc.append(auc(yva_b, c0.predict_proba(Xva)[:, 1]))
        r0 = lgb.LGBMRegressor(**params).fit(Xtr, yp)
        null_ic.append(spearman(yva_c, r0.predict(Xva)))
        if (i + 1) % 25 == 0:
            print(f"rotation {i + 1}/{N_PERMUTATIONS}", flush=True)
    null_auc = np.array(null_auc)
    null_ic = np.array(null_ic)
    p_auc = two_sided_p(null_auc, obs_auc, 0.5)
    p_ic = two_sided_p(null_ic, obs_ic, 0.0)

    # ---- v3 TRUE circular moving-block bootstrap ------------------------
    ub = np.unique(tva)
    rows_by_b = [np.where(tva == b)[0] for b in ub]
    span_days = (int(ub[-1]) - int(ub[0])) / 86_400_000
    l_block = math.ceil(len(ub) * BLOCK_DAYS / span_days)
    seqs = circular_moving_block_sequences(len(ub), l_block, N_BOOTSTRAP,
                                           BOOT_SEED_V3)
    boot_auc, boot_ic, boot_rows = [], [], []
    for seq in seqs:
        rows = np.concatenate([rows_by_b[j] for j in seq])
        boot_rows.append(len(rows))
        boot_auc.append(auc(yva_b[rows], score_b[rows]))
        boot_ic.append(spearman(yva_c[rows], score_c[rows]))
    boot_auc = np.array(boot_auc, float)
    boot_ic = np.array(boot_ic, float)
    ci = lambda a: [float(np.nanquantile(a, .025)),
                    float(np.nanquantile(a, .975))]
    se_auc = float(np.nanstd(boot_auc))
    se_ic = float(np.nanstd(boot_ic))

    def approx_power(null, center, se, mue):
        c = float(np.quantile(np.abs(null - center), 0.95))
        if se <= 0:
            return float(mue > c)
        z = (c - mue) / se
        return float(1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))

    def split_diag(d, ts):
        y = (d.net_r.to_numpy(float) > 0).astype(float)
        per_b = d.groupby("t").size()
        blocks = ((ts - ts.min()) // BLOCK_MS).astype(np.int64)
        return {"nominal_n": len(d),
                "unique_boundaries": int(d.t.nunique()),
                "labels_per_boundary": {"mean": float(per_b.mean()),
                                        "median": float(per_b.median()),
                                        "max": int(per_b.max())},
                "overlap": overlap_stats(
                    d.info_interval_lo.to_numpy(np.int64),
                    d.info_interval_hi.to_numpy(np.int64), np.unique(ts)),
                "de_boundary_level": design_effect(y, ts),
                "de_block_level": design_effect(y, blocks)}
    diag_tr = split_diag(tr, ttr)
    diag_va = split_diag(va, tva)
    for d in (diag_tr, diag_va):
        d["ess_reported_APPROXIMATION"] = d["de_block_level"]["ess"]

    report = {
        "procedure_version": 3,
        "preregistration": "PREREGISTRATION_LEARNABILITY_V3.md",
        "history": {"v1": "RETRACTED (dependence-blind)",
                    "v2": "preserved, quantitative procedure NOT "
                          "adjudicated (fixed-block bootstrap; modulo "
                          "assignment)"},
        "seeds": {"model": MODEL_SEED, "permutation": PERM_SEED_V3,
                  "bootstrap": BOOT_SEED_V3},
        "observed": {"validation_auc": obs_auc,
                     "validation_rank_ic": obs_ic},
        "rotation_permutation": {
            "n_permutations": N_PERMUTATIONS,
            "eligible_offsets": int(len(
                eligible_rotation_boundaries(np.unique(ttr)))),
            "auc": p_auc, "rank_ic": p_ic,
            "null_auc_abs_dev_q95":
                float(np.quantile(np.abs(null_auc - 0.5), 0.95)),
            "null_ic_abs_q95":
                float(np.quantile(np.abs(null_ic), 0.95))},
        "circular_moving_block_bootstrap": {
            "n_resamples": N_BOOTSTRAP,
            "n_boundaries": int(len(ub)),
            "block_len_boundaries": int(l_block),
            "resampled_rows": {"min": int(np.min(boot_rows)),
                               "mean": float(np.mean(boot_rows)),
                               "max": int(np.max(boot_rows))},
            "auc_ci95": ci(boot_auc), "auc_se": se_auc,
            "rank_ic_ci95": ci(boot_ic), "rank_ic_se": se_ic},
        "power_at_mue": {
            "mue": {"auc_deviation": MUE_AUC_DEV, "abs_rank_ic": MUE_IC},
            "method": "APPROXIMATE normal-theory (pre-registered)",
            "auc": approx_power(null_auc, 0.5, se_auc, MUE_AUC_DEV),
            "rank_ic": approx_power(null_ic, 0.0, se_ic, MUE_IC)},
        "structure": {"train": diag_tr, "validation": diag_va},
        "frozen_il_rule": "unchanged (PREREGISTRATION_LEARNABILITY_"
                          "BLOCKS.md; applies at Checkpoint 2)",
        "interim_conclusion": ("NO DEMONSTRATED LEARNABILITY; "
                               "statistical significance not "
                               "adjudicated"),
    }
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"observed": report["observed"],
                      "auc_p_upper": p_auc["p_upper"],
                      "ic_p_upper": p_ic["p_upper"],
                      "auc_ci95":
                          report["circular_moving_block_bootstrap"]
                          ["auc_ci95"],
                      "ic_ci95":
                          report["circular_moving_block_bootstrap"]
                          ["rank_ic_ci95"],
                      "power": report["power_at_mue"]}, indent=2))
    print("report:", out, "sha256:",
          hashlib.sha256(open(out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
