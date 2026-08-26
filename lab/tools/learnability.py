"""Step 6: training/validation learnability diagnostic.

Answers, honestly and mechanically, whether the frozen F01-F28 features
carry ANY exploitable signal about Arm A outcomes — before full ML/RL
training. No hyperparameter search here; the DRAFT LightGBM settings from
lab.models.pipelines are used as-is. All fitting on purged TRAIN only;
reporting on purged VALIDATION. Includes the gap-exclusion effects and
BTC-context sufficiency required by the review directive of 2026-08-26.

Metrics:
  Arm B target (net_r > 0): validation AUC + base rates;
  Arm C target (net_r):     validation Spearman rank IC;
  chance reference:         label-permutation nulls (deterministic seeds,
                            200 permutations) with two-sided p-values.

The diagnostic never claims profitability; it measures learnability only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np
import pandas as pd

import lightgbm as lgb

from lab.models.pipelines import _LGB_DRAFT, validate_columns

N_PERMUTATIONS = 200
SEED = 20260826


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra = (ra - ra.mean()) / (ra.std() or 1.0)
    rb = (rb - rb.mean()) / (rb.std() or 1.0)
    return float((ra * rb).mean())


def auc(y: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    pos = y == 1
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main() -> None:  # pragma: no cover — official diagnostic run
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.ledgers_dir,
                                   "learnability_report.json")

    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    df = feats.merge(labels[["t", "symbol", "net_r", "exclusion"]],
                     on=["t", "symbol"], how="left", validate="1:1")

    fcols = sorted(c for c in df.columns if c[:1] == "F" and c[1:3].isdigit())
    validate_columns(fcols)

    tr = df[(df["split"] == "train")].copy()
    va = df[(df["split"] == "validation")].copy()
    assert tr["net_r"].notna().all() and va["net_r"].notna().all()

    Xtr = tr[fcols].to_numpy(np.float64)
    Xva = va[fcols].to_numpy(np.float64)
    ytr_b = (tr["net_r"] > 0).to_numpy(int)
    yva_b = (va["net_r"] > 0).to_numpy(int)
    ytr_c = tr["net_r"].to_numpy(float)
    yva_c = va["net_r"].to_numpy(float)

    params = dict(_LGB_DRAFT)
    params["random_state"] = SEED
    clf = lgb.LGBMClassifier(**params).fit(Xtr, ytr_b)
    b_auc = auc(yva_b, clf.predict_proba(Xva)[:, 1])
    reg = lgb.LGBMRegressor(**params).fit(Xtr, ytr_c)
    c_ic = spearman(yva_c, reg.predict(Xva))

    # deterministic permutation nulls: shuffle TRAIN labels, refit, score
    rng = np.random.default_rng(SEED)
    null_auc, null_ic = [], []
    for _ in range(N_PERMUTATIONS):
        p = rng.permutation(len(ytr_b))
        c0 = lgb.LGBMClassifier(**params).fit(Xtr, ytr_b[p])
        null_auc.append(auc(yva_b, c0.predict_proba(Xva)[:, 1]))
        r0 = lgb.LGBMRegressor(**params).fit(Xtr, ytr_c[p])
        null_ic.append(spearman(yva_c, r0.predict(Xva)))
    null_auc, null_ic = np.array(null_auc), np.array(null_ic)
    p_auc = float((np.abs(null_auc - 0.5) >= abs(b_auc - 0.5)).mean())
    p_ic = float((np.abs(null_ic) >= abs(c_ic)).mean())

    imp = sorted(zip(fcols, clf.feature_importances_.tolist()),
                 key=lambda kv: -kv[1])[:10]

    gap_path = os.path.join(args.ledgers_dir, "gap_exclusion_report.json")
    with open(gap_path) as f:
        gaps = json.load(f)

    report = {
        "n_train": len(tr), "n_validation": len(va),
        "train_base_rate_pos": float(ytr_b.mean()),
        "validation_base_rate_pos": float(yva_b.mean()),
        "train_mean_net_r": float(ytr_c.mean()),
        "validation_mean_net_r": float(yva_c.mean()),
        "arm_b_validation_auc": b_auc,
        "arm_b_permutation_p": p_auc,
        "arm_c_validation_rank_ic": c_ic,
        "arm_c_permutation_p": p_ic,
        "permutations": N_PERMUTATIONS,
        "null_auc_abs_dev_q95": float(np.quantile(np.abs(null_auc - .5), .95)),
        "null_ic_abs_q95": float(np.quantile(np.abs(null_ic), .95)),
        "top_features_arm_b": imp,
        "gap_effects": {
            "summary": gaps,
            "note": ("All exclusions are mechanical applications of the "
                     "frozen data-quality rules; missing OHLCV is never "
                     "imputed. These exclusions shrink the labeled sample "
                     "and are a stated limitation."),
        },
        "btc_context_sufficiency": gaps["btc_context"],
        "honesty": ("Learnability only — no profitability claim. DRAFT "
                    "hyperparameters, no search. Fit on purged train; "
                    "scored on purged validation; permutation nulls with "
                    "deterministic seeds."),
    }
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    body = open(out, "rb").read()
    print(json.dumps({k: report[k] for k in
                      ("n_train", "n_validation", "arm_b_validation_auc",
                       "arm_b_permutation_p", "arm_c_validation_rank_ic",
                       "arm_c_permutation_p")}, indent=2))
    print("report:", out, "sha256:", hashlib.sha256(body).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
