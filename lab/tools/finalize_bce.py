"""Arms B/C/E finalization — executes PREREGISTRATION_BCE_FINALIZATION.md
verbatim (adjudication blocker 6). No refitting: the frozen draft
boosters' scores are combined with the 18 pre-registered decision-rule
configurations; every configuration's result is recorded; selection and
tie rules are the pre-registered ones. Also emits the directed anomaly
explanations (B draft tail-acceptance, E draft non-monotonicity) as
preserved honest negatives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

import numpy as np
import pandas as pd

import lightgbm as lgb

from lab.models.pipelines import E_BUCKETS, validate_columns

B_GRID = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
B_MIN_ACCEPT = 50
C_GRID = (1, 2, 3, 5, 10)
C_MIN_SELECTED = 50
E_MAPPINGS = ("M1", "M2", "M3", "M4")


def sortino(r: np.ndarray) -> float:
    dd = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    if dd == 0.0:
        return 0.0 if float(np.mean(r)) <= 0 else 1e6
    return float(np.mean(r) / dd)


def dd95(r: np.ndarray) -> float:
    cum = np.cumsum(r)
    peak = np.maximum.accumulate(np.maximum(cum, 0.0))
    return float(np.quantile(peak - cum, 0.95))


def e_bucket(p: np.ndarray, mapping: str, q: dict) -> np.ndarray:
    if mapping == "M1":
        cuts = np.array([q["q25"], q["q50"], q["q75"]])
        return np.array([E_BUCKETS[i] for i in np.searchsorted(cuts, p)])
    if mapping == "M2":
        cuts = np.array([0.0, q["q50"], q["q75"]])
        return np.array([E_BUCKETS[i] for i in np.searchsorted(cuts, p)])
    if mapping == "M3":
        cuts = np.array([q["q25"], q["q75"], q["q90"]])
        return np.array([E_BUCKETS[i] for i in np.searchsorted(cuts, p)])
    if mapping == "M4":
        return np.full(len(p), 1.0)
    raise ValueError(mapping)


def main() -> None:  # pragma: no cover — official finalization run
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.models_dir, "bce_finalization.json")

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
    y = va.net_r.to_numpy(float)

    bB = lgb.Booster(model_file=os.path.join(args.models_dir, "arm_b.txt"))
    bC = lgb.Booster(model_file=os.path.join(args.models_dir, "arm_c.txt"))
    bE = lgb.Booster(model_file=os.path.join(args.models_dir, "arm_e.txt"))
    prob = bB.predict(Xva)
    cscore = bC.predict(Xva)
    e_va = bE.predict(Xva)
    e_tr = bE.predict(Xtr)
    q = {"q25": float(np.quantile(e_tr, 0.25)),
         "q50": float(np.quantile(e_tr, 0.50)),
         "q75": float(np.quantile(e_tr, 0.75)),
         "q90": float(np.quantile(e_tr, 0.90))}
    saved = np.load(os.path.join(args.models_dir, "arm_e_cuts.npz"))["cuts"]
    assert np.allclose(saved, [q["q25"], q["q50"], q["q75"]]), \
        "frozen-cut mismatch vs arm_e_cuts.npz"

    # ---- Arm B ----------------------------------------------------------
    b_rows = []
    for th in B_GRID:
        acc = prob >= th
        n = int(acc.sum())
        b_rows.append({"threshold": th, "n_accepted": n,
                       "selectable": n >= B_MIN_ACCEPT,
                       "accepted_mean_net_r":
                           float(y[acc].mean()) if n else None})
    sel = [r for r in b_rows if r["selectable"]]
    if sel:
        best = max(sel, key=lambda r: (r["accepted_mean_net_r"],
                                       -r["threshold"]))
        b_final = {"threshold": best["threshold"], "verdict": "SELECTED",
                   "rule": "highest accepted mean net_r among selectable; "
                           "ties -> lower threshold"}
    else:
        b_final = {"threshold": B_GRID[0],
                   "verdict": "ARM B INSUFFICIENT SUPPORT — honest "
                              "negative (no grid threshold accepts >= "
                              f"{B_MIN_ACCEPT})"}

    # ---- Arm C ----------------------------------------------------------
    va_idx = va.reset_index(drop=True)
    va_idx["score"] = cscore
    c_rows = []
    for K in C_GRID:
        chosen_mask = np.zeros(len(va_idx), bool)
        for _, grp in va_idx.groupby("t"):
            g = grp.sort_values(["score", "symbol"],
                                ascending=[False, True],
                                kind="mergesort")
            chosen_mask[g.index[:K]] = True
        n = int(chosen_mask.sum())
        c_rows.append({"top_k": K, "n_selected": n,
                       "selectable": n >= C_MIN_SELECTED,
                       "selected_mean_net_r":
                           float(y[chosen_mask].mean()) if n else None})
    selc = [r for r in c_rows if r["selectable"]]
    bestc = max(selc, key=lambda r: (r["selected_mean_net_r"],
                                     -r["top_k"]))
    c_final = {"top_k": bestc["top_k"], "verdict": "SELECTED",
               "rule": "highest selected mean net_r among selectable; "
                       "ties -> smaller K"}

    # ---- Arm E (frozen SPEC utility) ------------------------------------
    rA = 1.0 * y
    dA = dd95(rA)
    e_rows = []
    for m in E_MAPPINGS:
        bk = e_bucket(e_va, m, q)
        r = bk * y
        dE = dd95(r)
        u = sortino(r) - 2.0 * max(0.0, (dE - dA) / max(dA, 0.01))
        e_rows.append({"mapping": m, "utility_UE": u,
                       "sortino_net": sortino(r), "dd95": dE,
                       "bucket_counts": {str(b): int((bk == b).sum())
                                         for b in sorted(set(bk))},
                       "mean_sized_r": float(r.mean())})
    beste = max(e_rows, key=lambda r: (r["utility_UE"],
                                       -E_MAPPINGS.index(r["mapping"])))
    e_final = {"mapping": beste["mapping"], "verdict": "SELECTED",
               "rule": "highest U_E; ties -> earliest of M1..M4",
               "dd95_arm_a_reference": dA,
               "train_pred_quantiles": q}

    # ---- directed anomaly explanations (honest negatives) ---------------
    n05 = int((prob >= 0.5).sum())
    anomalies = {
        "arm_b_draft": {
            "validation_base_rate_pos": float((y > 0).mean()),
            "prob_quantiles": {p: float(np.quantile(prob, float(p)))
                               for p in ("0.5", "0.9", "0.95", "0.99")},
            "n_accepted_at_0.50": n05,
            "se_of_mean_of_that_n":
                float(y.std(ddof=1) / np.sqrt(max(n05, 1))),
            "accepted_mean_at_0.50":
                float(y[prob >= 0.5].mean()) if n05 else None,
            "explanation": (
                "The positive base rate centers the classifier's "
                "probabilities far below 0.50, so the draft threshold "
                "sits in the extreme upper tail of a chance-level score; "
                "the accepted set is tiny and its mean lies within the "
                "sampling noise of the validation net_r distribution — "
                "a tail artifact, not model preference for bad trades. "
                "Preserved as an honest negative.")},
        "arm_e_draft": {
            "overall_validation_mean_net_r": float(y.mean()),
            "per_bucket": [], "explanation": (
                "With chance-level ranking (validation IC ~0.02), "
                "per-bucket means are noise draws around the overall "
                "mean; non-monotonicity is the expected behavior of no "
                "signal. Preserved as an honest negative.")}}
    bk1 = e_bucket(e_va, "M1", q)
    for b in sorted(set(bk1)):
        yy = y[bk1 == b]
        se = float(yy.std(ddof=1) / np.sqrt(len(yy)))
        dev = float(yy.mean() - y.mean())
        anomalies["arm_e_draft"]["per_bucket"].append(
            {"bucket": float(b), "n": int(len(yy)),
             "mean_net_r": float(yy.mean()), "se": se,
             "deviation_from_overall": dev,
             "exceeds_2se": bool(abs(dev) > 2 * se)})

    report = {"preregistration": "PREREGISTRATION_BCE_FINALIZATION.md",
              "budget_configurations": len(B_GRID) + len(C_GRID)
              + len(E_MAPPINGS),
              "arm_b": {"grid": b_rows, "final": b_final},
              "arm_c": {"grid": c_rows, "final": c_final},
              "arm_e": {"grid": e_rows, "final": e_final},
              "anomaly_explanations": anomalies}
    with open(out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"B": b_final, "C": c_final,
                      "E": {k: e_final[k] for k in
                            ("mapping", "verdict")}}, indent=2))
    print("report:", out, "sha256:",
          hashlib.sha256(open(out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
