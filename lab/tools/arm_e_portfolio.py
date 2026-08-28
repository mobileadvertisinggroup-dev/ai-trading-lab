"""Arm E PORTFOLIO utility — executes PREREGISTRATION_ARM_E_PORTFOLIO.md
verbatim (D63 blocker 1).

One full seven-arm orchestrator run per mapping M1–M4 over the OFFICIAL
validation window (fresh 10,000 account; real timing, overlapping
positions, tiered costs, equity-dependent sizing, capacity limits, the
external risk governor, transactional rounds), differing only in Arm
E's frozen bucket mapping. Portfolio quantities come from the 4h equity
TIME SERIES: decimal maximum drawdown, annualized Sortino from 4h
returns, and paired dependence-aware bootstrap DD95 (identical
resampled blocks across M1–M4 and the Arm A reference). Arm A equality
across the four runs is asserted; the per-trade M3 selection stays
invalidated history; no model is refit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time

import numpy as np

from lab import protocol as P
from lab.arms.indicators import SymbolSeries
from lab.arms.regime import RegimeModel
from lab.data import partition as PT
from lab.data.access import GuardedLake
from lab.tools.learnability_v3 import circular_moving_block_sequences
from lab.tools.shakedown import (FeatureContext, FrozenSizer, LakeProvider,
                                 RegimeAdapter, ShakedownCompetition)

E_MAPPINGS = ("M1", "M2", "M3", "M4")
BOOT_N = 1000
BOOT_SEED = 20260901
BLOCK_LEN_4H = 168                     # 28 days of 4h periods
P_YEAR = 365.25 * 6                    # 4h periods per year


def max_drawdown_decimal(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    return float(np.max(1.0 - equity / peak))


def sortino_annualized(r: np.ndarray) -> float:
    dd = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    if dd == 0.0:
        return 0.0 if float(np.mean(r)) <= 0 else 1e6
    return float(np.mean(r) / dd) * math.sqrt(P_YEAR)


def main() -> None:  # pragma: no cover — official run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    lake = GuardedLake(args.lake, args.manifests_dir)
    part = lake.partition
    start = int(part["validation_start_ms"])
    assert start % P.BAR_4H_MS == 0
    end = int(part["quarantine_start_ms"]) - P.BAR_15M_MS

    with open(os.path.join(args.manifests_dir, "round_validity.json")) as f:
        validity = {int(k): bool(v) for k, v in json.load(f).items()}
    with open(os.path.join(args.model_dir,
                           "bc_train_selection.json")) as f:
        quantiles = json.load(f)["arm_e"]["train_pred_quantiles"]

    symbols = sorted(os.listdir(os.path.join(args.lake, "klines15m")))
    print(f"loading {len(symbols)} symbols...", flush=True)
    provider = LakeProvider(lake, symbols, end)
    boundaries = np.array(sorted(validity), dtype=np.int64)
    cals = {s: PT.build_symbol_calendar(
        s, provider._d[s]["open_time"], provider._d[s]["quote_volume"])
        for s in symbols}
    liq = np.full((len(boundaries), len(symbols)), np.nan)
    for j, s in enumerate(symbols):
        liq[:, j] = PT.eligibility_series(cals[s], boundaries).to_numpy()
    bidx = {int(t): i for i, t in enumerate(boundaries)}
    sym_arr = np.array(symbols)
    sym_col = {s: j for j, s in enumerate(symbols)}

    def universe_fn(t):
        i = bidx.get(int(t))
        if i is None:
            return []
        row = liq[i]
        ok = np.isfinite(row)
        order = np.lexsort((sym_arr[ok], -row[ok]))
        return list(sym_arr[ok][order][: P.UNIVERSE_TOP_N])

    d = provider._d[P.CONTEXT_SYMBOL]
    ss = SymbolSeries(d["open_time"], d["open"], d["high"], d["low"],
                      d["close"])
    regime = RegimeModel(ss.t4, ss.close4)
    ctx = FeatureContext(provider, cals, boundaries, liq, sym_col, regime)

    a_ref = None
    curves: dict[str, np.ndarray] = {}
    per_mapping: dict[str, dict] = {}
    for m in E_MAPPINGS:
        t0 = time.time()
        comp = ShakedownCompetition(
            provider, 10_000.0, universe_fn,
            valid_round_fn=lambda t: validity.get(int(t), False),
            sizer_model=FrozenSizer(args.model_dir, ctx, mapping=m,
                                    quantiles=quantiles),
            regime_model=RegimeAdapter(regime),
            feature_ctx=ctx, diagnostics=False)
        comp.run(start, end)
        a_curve = [(r["t"], r["equity"])
                   for r in comp.arms["A"].equity_curve]
        if a_ref is None:
            a_ref = a_curve
            curves["A"] = np.array([e for _t, e in a_curve])
        else:
            assert a_curve == a_ref, \
                "Arm A reference differs across mapping runs — STOP"
        e_curve = comp.arms["E"].equity_curve
        curves[m] = np.array([r["equity"] for r in e_curve])
        per_mapping[m] = {
            "rounds": comp.coordinator.counts(),
            "final_equity": float(curves[m][-1]),
            "n_boundaries": len(e_curve),
            "equity_curve_sha256": hashlib.sha256(json.dumps(
                [[r["t"], r["equity"]] for r in e_curve]).encode())
                .hexdigest(),
        }
        print(f"{m}: final {curves[m][-1]:.2f} "
              f"({time.time() - t0:.0f}s)", flush=True)

    n = {len(v) for v in curves.values()}
    assert len(n) == 1, f"curve lengths differ: {n}"
    rets = {k: v[1:] / v[:-1] - 1.0 for k, v in curves.items()}
    nr = len(next(iter(rets.values())))
    seqs = circular_moving_block_sequences(nr, BLOCK_LEN_4H, BOOT_N,
                                           BOOT_SEED)

    def dd95(r: np.ndarray) -> float:
        mdds = []
        for seq in seqs:                       # paired across all series
            path = np.cumprod(1.0 + r[seq])
            mdds.append(max_drawdown_decimal(path))
        return float(np.quantile(np.array(mdds), 0.95))

    dd95_a = dd95(rets["A"])
    results = []
    for m in E_MAPPINGS:
        r = rets[m]
        s_ann = sortino_annualized(r)
        mdd = max_drawdown_decimal(curves[m])
        d_e = dd95(r)
        u = s_ann - 2.0 * max(0.0, (d_e - dd95_a) / max(dd95_a, 0.01))
        results.append(dict(per_mapping[m], mapping=m,
                            max_drawdown_decimal=mdd,
                            sortino_annualized=s_ann,
                            dd95_decimal=d_e,
                            penalty=2.0 * max(0.0, (d_e - dd95_a)
                                              / max(dd95_a, 0.01)),
                            utility_UE=u))
        print(f"{m}: MDD {mdd:.4f} S_ann {s_ann:.4f} DD95 {d_e:.4f} "
              f"U_E {u:.4f}", flush=True)
    best = max(results, key=lambda x: (x["utility_UE"],
                                       -E_MAPPINGS.index(x["mapping"])))

    report = {
        "preregistration": "PREREGISTRATION_ARM_E_PORTFOLIO.md",
        "invalidated_history": ("per-trade cumulative-R selection in "
                                "bc_train_selection.json arm_e (and the "
                                "earlier single-path variant) — "
                                "preserved, never consumed"),
        "window": {"start_ms": start, "end_ms": end,
                   "n_4h_boundaries": int(list(n)[0])},
        "arm_a_reference": {
            "identical_across_runs": True,
            "max_drawdown_decimal":
                max_drawdown_decimal(curves["A"]),
            "sortino_annualized": sortino_annualized(rets["A"]),
            "dd95_decimal": dd95_a,
            "final_equity": float(curves["A"][-1])},
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED,
                      "block_len_4h": BLOCK_LEN_4H, "paired": True,
                      "unit": "circular moving-block over the 4h return "
                              "series; one max drawdown per resample"},
        "annualization": {"periods_per_year": P_YEAR,
                          "method": "time-series Sortino x sqrt(P_YEAR)"},
        "results": results,
        "selected_mapping": best["mapping"],
        "rule": "highest U_E; ties -> earliest of M1..M4",
    }
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print(json.dumps({"selected": best["mapping"],
                      "U_E": best["utility_UE"],
                      "dd95_a": dd95_a}, indent=2))
    print("report:", args.out, "sha256:",
          hashlib.sha256(open(args.out, "rb").read()).hexdigest())


if __name__ == "__main__":  # pragma: no cover
    main()
