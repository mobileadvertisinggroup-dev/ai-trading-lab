"""B/C TRAIN-only selection + corrected Arm E utility — executes
PREREGISTRATION_BC_TRAIN_SELECTION.md and
PREREGISTRATION_ARM_E_UTILITY_V2.md verbatim (D61 blockers B and C).

The invalidated validation-based B/C selections and the invalidated
single-path M3 selection remain preserved unmodified in
bce_finalization.json; this tool never reads their selected values. No
booster is refit. Grids, constraints, tie rules, seeds, and formulas
are exactly the pre-registered ones.
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
from lab.models.pipelines import validate_columns
from lab.tools.finalize_bce import e_bucket

B_GRID = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
C_GRID = (1, 2, 3, 5, 10)
E_MAPPINGS = ("M1", "M2", "M3", "M4")
SUPPORT_FRACTION_NUM, SUPPORT_FRACTION_DEN = 50, 750   # scaled per split
E_BOOT_N = 1000
E_BOOT_SEED = 20260830
BLOCK_DAYS = 28
MS_PER_YEAR = 365.25 * 24 * 3600 * 1000


def support_min(n_split: int) -> int:
    return math.ceil(SUPPORT_FRACTION_NUM * n_split / SUPPORT_FRACTION_DEN)


def sortino_per_trade(r: np.ndarray) -> float:
    dd = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    if dd == 0.0:
        return 0.0 if float(np.mean(r)) <= 0 else 1e6
    return float(np.mean(r) / dd)


def max_drawdown(r: np.ndarray) -> float:
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    return float(np.max(peak - cum)) if len(r) else 0.0


def circular_block_sequences(u: int, l_block: int, n_resamples: int,
                             seed: int) -> list[np.ndarray]:
    """Pre-registered circular moving-block draws over boundary indices
    0..u-1: uniformly random circular starts, L consecutive each,
    concatenated to exactly u indices. Shared across paired series."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_resamples):
        idx = []
        while len(idx) < u:
            s = int(rng.integers(0, u))
            idx.extend(((s + k) % u) for k in range(l_block))
        out.append(np.array(idx[:u], dtype=np.int64))
    return out


def main() -> None:  # pragma: no cover — official run
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.models_dir,
                                   "bc_train_selection.json")

    feats = pd.read_parquet(
        os.path.join(args.ledgers_dir, "features_arm_a.parquet"))
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    df = feats.merge(labels[["t", "symbol", "net_r"]], on=["t", "symbol"],
                     how="left", validate="1:1")
    fcols = sorted(c for c in df.columns
                   if c[:1] == "F" and c[1:3].isdigit())
    validate_columns(fcols)
    tr = df[df.split == "train"].sort_values(["t", "symbol"],
                                             kind="mergesort")
    va = df[df.split == "validation"].sort_values(["t", "symbol"],
                                                  kind="mergesort")
    Xtr = tr[fcols].to_numpy(np.float64)
    Xva = va[fcols].to_numpy(np.float64)
    ytr = tr.net_r.to_numpy(float)
    yva = va.net_r.to_numpy(float)

    bB = lgb.Booster(model_file=os.path.join(args.models_dir, "arm_b.txt"))
    bC = lgb.Booster(model_file=os.path.join(args.models_dir, "arm_c.txt"))
    bE = lgb.Booster(model_file=os.path.join(args.models_dir, "arm_e.txt"))

    # ---- Arm B: TRAIN-only threshold selection (blocker B) --------------
    prob_tr = bB.predict(Xtr)
    prob_va = bB.predict(Xva)
    minb = support_min(len(tr))
    b_rows = []
    for th in B_GRID:
        acc = prob_tr >= th
        n = int(acc.sum())
        b_rows.append({"threshold": th, "train_n_accepted": n,
                       "selectable": n >= minb,
                       "train_accepted_mean_net_r":
                           float(ytr[acc].mean()) if n else None})
    sel = [r for r in b_rows if r["selectable"]]
    if sel:
        best = max(sel, key=lambda r: (r["train_accepted_mean_net_r"],
                                       -r["threshold"]))
        b_th, b_verdict = best["threshold"], "SELECTED (train-only)"
    else:
        b_th, b_verdict = B_GRID[0], ("ARM B INSUFFICIENT SUPPORT — "
                                      "honest negative")
    accv = prob_va >= b_th
    b_validation = {"threshold_applied_once": b_th,
                    "n_accepted": int(accv.sum()),
                    "accept_rate": float(accv.mean()),
                    "accepted_mean_net_r":
                        float(yva[accv].mean()) if accv.any() else None,
                    "rejected_mean_net_r":
                        float(yva[~accv].mean()) if (~accv).any() else None}

    # ---- Arm C: TRAIN-only top-K selection (blocker B) ------------------
    def topk_mask(frame, scores, k):
        f = frame.reset_index(drop=True).copy()
        f["score"] = scores
        mask = np.zeros(len(f), bool)
        for _, grp in f.groupby("t"):
            g = grp.sort_values(["score", "symbol"],
                                ascending=[False, True], kind="mergesort")
            mask[g.index[:k]] = True
        return mask

    cs_tr = bC.predict(Xtr)
    cs_va = bC.predict(Xva)
    minc = support_min(len(tr))
    c_rows = []
    for K in C_GRID:
        m = topk_mask(tr, cs_tr, K)
        n = int(m.sum())
        c_rows.append({"top_k": K, "train_n_selected": n,
                       "selectable": n >= minc,
                       "train_selected_mean_net_r":
                           float(ytr[m].mean()) if n else None})
    selc = [r for r in c_rows if r["selectable"]]
    bestc = max(selc, key=lambda r: (r["train_selected_mean_net_r"],
                                     -r["top_k"]))
    c_k = bestc["top_k"]
    mv = topk_mask(va, cs_va, c_k)
    c_validation = {"top_k_applied_once": c_k,
                    "n_selected": int(mv.sum()),
                    "selected_mean_net_r": float(yva[mv].mean())}

    # ---- Arm E: corrected frozen utility (blocker C) --------------------
    e_va = bE.predict(Xva)
    e_tr = bE.predict(Xtr)
    q = {"q25": float(np.quantile(e_tr, 0.25)),
         "q50": float(np.quantile(e_tr, 0.50)),
         "q75": float(np.quantile(e_tr, 0.75)),
         "q90": float(np.quantile(e_tr, 0.90))}
    saved = np.load(os.path.join(args.models_dir,
                                 "arm_e_cuts.npz"))["cuts"]
    assert np.allclose(saved, [q["q25"], q["q50"], q["q75"]])

    va_r = va.reset_index(drop=True)
    tva = va_r.t.to_numpy(np.int64)
    ub = np.unique(tva)
    rows_by_b = [np.where(tva == b)[0] for b in ub]
    span_days = (int(ub[-1]) - int(ub[0])) / 86_400_000
    l_block = math.ceil(len(ub) * BLOCK_DAYS / span_days)
    seqs = circular_block_sequences(len(ub), l_block, E_BOOT_N,
                                    E_BOOT_SEED)
    t_years = (int(ub[-1]) - int(ub[0]) + P.BAR_4H_MS) / MS_PER_YEAR
    lam = len(va_r) / t_years

    def dd95_boot(r: np.ndarray) -> float:
        # one MAX drawdown per paired resample; upper 95% bound
        mdds = []
        for seq in seqs:
            path = np.concatenate([r[rows_by_b[j]] for j in seq])
            mdds.append(max_drawdown(path))
        return float(np.quantile(np.array(mdds), 0.95))

    rA = 1.0 * yva
    ddA = dd95_boot(rA)
    e_rows = []
    for m in E_MAPPINGS:
        bk = e_bucket(e_va, m, q)
        r = bk * yva
        s_ann = sortino_per_trade(r) * math.sqrt(lam)
        ddE = dd95_boot(r)
        u = s_ann - 2.0 * max(0.0, (ddE - ddA) / max(ddA, 0.01))
        e_rows.append({"mapping": m,
                       "sortino_per_trade": sortino_per_trade(r),
                       "sortino_annualized": s_ann,
                       "dd95_bootstrap_upper95": ddE,
                       "utility_UE": u,
                       "bucket_counts": {str(b): int((bk == b).sum())
                                         for b in sorted(set(bk))},
                       "mean_sized_r": float(r.mean())})
    beste = max(e_rows, key=lambda r: (r["utility_UE"],
                                       -E_MAPPINGS.index(r["mapping"])))

    report = {
        "preregistrations": ["PREREGISTRATION_BC_TRAIN_SELECTION.md",
                             "PREREGISTRATION_ARM_E_UTILITY_V2.md"],
        "invalidated_history_preserved":
            "bce_finalization.json (validation-selected B/C; "
            "single-path-M3) — never consumed here",
        "arm_b": {"train_grid": b_rows, "support_min": minb,
                  "selected_threshold": b_th, "verdict": b_verdict,
                  "validation_applied_once": b_validation,
                  "in_sample_caveat": ("TRAIN probabilities are "
                                       "in-sample for the frozen "
                                       "booster (SPEC §10 mandates the "
                                       "split, not unbiasedness)")},
        "arm_c": {"train_grid": c_rows, "support_min": minc,
                  "selected_top_k": c_k, "verdict":
                      "SELECTED (train-only)",
                  "validation_applied_once": c_validation},
        "arm_e": {"grid": e_rows,
                  "selected_mapping": beste["mapping"],
                  "rule": "highest U_E; ties -> earliest of M1..M4",
                  "dd95_arm_a_reference": ddA,
                  "annualization": {"t_years": t_years,
                                    "trades_per_year": lam,
                                    "method": "S_per_trade * sqrt(lam) "
                                              "(pre-registered, openly "
                                              "approximate under "
                                              "overlap)"},
                  "bootstrap": {"n": E_BOOT_N, "seed": E_BOOT_SEED,
                                "unit": "circular moving-block over "
                                        "validation boundaries",
                                "n_boundaries": len(ub),
                                "block_len_boundaries": l_block,
                                "paired": True},
                  "train_pred_quantiles": q},
    }
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"B": {"selected": b_th, "verdict": b_verdict,
                            "val": b_validation},
                      "C": {"selected": c_k, "val": c_validation},
                      "E": {"selected": beste["mapping"],
                            "U_E": beste["utility_UE"]}}, indent=2))
    print("report:", out, "sha256:",
          hashlib.sha256(open(out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
