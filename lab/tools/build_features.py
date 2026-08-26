"""Steps 4-5 of the pre-Checkpoint-1 assignment: build and freeze the
F01-F28 decision-time features for every candidate in the official Arm A
ledger, and apply the variable-horizon purge/embargo split.

Inputs: the verified lake (via GuardedLake, reads bounded strictly below
the quarantine boundary) + the OFFICIAL candidate and label ledgers.
Context features are computed point-in-time exactly per DATA_DICTIONARY:
  F21 breadth_sma20     fraction of U(t) symbols with close > their SMA(20)
  F22 round_side_count  same-side candidates in the same round (incl. self)
  F23 regime_code       Arm D regime at t (0 up, 1 down, 2 sideways, 3 stress)
  F24 log_liq           log10 of the §4 ranking metric at (symbol, t)
  F25/F26               funding last / mean of prior 9 events before t

Output: features_arm_a.parquet (one row per candidate, keyed (t, symbol),
carrying the purge/embargo split assignment), plus a manifest with hashes.
No lookahead: everything derives from information strictly before t (the
property is enforced by tests/test_features.py on the builder itself).
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
from lab.arms.indicators import SymbolSeries
from lab.arms.regime import RegimeModel
from lab.data import partition as PT
from lab.data.access import GuardedLake
from lab.features.build import FEATURE_SET_VERSION, FeatureSeries, \
    build_features
from lab.labels.purge import chronological_split

REGIME_CODE = {"uptrend": 0, "downtrend": 1, "sideways": 2, "stress": 3}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:  # pragma: no cover — official operational run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--ledgers-dir", required=True)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    out_dir = args.out_dir or args.ledgers_dir

    lake = GuardedLake(args.lake, args.manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    end = q - P.BAR_15M_MS

    cands = pd.read_parquet(
        os.path.join(args.ledgers_dir, "candidates_arm_a.parquet"))
    labels = pd.read_parquet(
        os.path.join(args.ledgers_dir, "labels_arm_a.parquet"))
    print(f"candidates: {len(cands)}; labels: {len(labels)}", flush=True)

    symbols = sorted(os.listdir(os.path.join(args.lake, "klines15m")))
    need = sorted(set(cands["symbol"]))          # feature series needed
    print(f"symbols in ledger: {len(need)} of {len(symbols)}", flush=True)

    # -- load bars (all symbols: breadth needs every universe member) ------
    t0 = time.time()
    fs: dict[str, FeatureSeries] = {}
    cals: dict[str, PT.SymbolCalendar] = {}
    funding: dict[str, pd.DataFrame] = {}
    btc_arrays = None
    for sym in symbols:
        df = lake.read_klines(sym, 0, end)
        ot = df["open_time"].to_numpy(np.int64)
        ss = SymbolSeries(ot, df["open"].to_numpy(float),
                          df["high"].to_numpy(float),
                          df["low"].to_numpy(float),
                          df["close"].to_numpy(float))
        fs[sym] = FeatureSeries(ss.t4, ss.close4, ss.hh_entry, ss.ll_entry,
                                ss.hh_exit, ss.ll_exit)
        cals[sym] = PT.build_symbol_calendar(
            sym, ot, df["quote_volume"].to_numpy(float))
        if sym in need:
            funding[sym] = lake.read_funding(sym, 0, end)
        if sym == P.CONTEXT_SYMBOL:
            btc_arrays = (ss.t4, ss.close4)
    print(f"series loaded ({time.time() - t0:.0f}s)", flush=True)

    regime = RegimeModel(*btc_arrays)
    btc_fs = fs[P.CONTEXT_SYMBOL]

    # -- eligibility over the candidate rounds (same code as partition) ---
    rounds = np.array(sorted(set(cands["t"].astype(np.int64))),
                      dtype=np.int64)
    liq = np.full((len(rounds), len(symbols)), np.nan)
    for j, sym in enumerate(symbols):
        liq[:, j] = PT.eligibility_series(cals[sym], rounds).to_numpy()
    ridx = {int(t): i for i, t in enumerate(rounds)}
    sym_arr = np.array(symbols)
    sym_col = {s: j for j, s in enumerate(symbols)}

    def universe_at(t: int) -> list[str]:
        row = liq[ridx[int(t)]]
        ok = np.isfinite(row)
        order = np.lexsort((sym_arr[ok], -row[ok]))
        return list(sym_arr[ok][order][: P.UNIVERSE_TOP_N])

    # breadth per round: fraction of U(t) with close > SMA20 at t
    breadth: dict[int, float] = {}
    regime_code: dict[int, int] = {}
    for t in rounds:
        t = int(t)
        uni = universe_at(t)
        vals = []
        for s in uni:
            i = fs[s].index_at(t)
            if i is not None and np.isfinite(fs[s].sma20[i]):
                vals.append(1.0 if fs[s].close[i] > fs[s].sma20[i] else 0.0)
        breadth[t] = float(np.mean(vals)) if vals else float("nan")
        regime_code[t] = REGIME_CODE[regime.classify(t)["regime"]]

    # round_side_count from the ledger itself (same-side, same round)
    side_count = cands.groupby(["t", "side"])["symbol"].transform("count")

    # funding context per (symbol, t)
    def funding_ctx(sym: str, t: int) -> tuple[float, float]:
        fdf = funding.get(sym)
        if fdf is None or fdf.empty:
            return float("nan"), float("nan")
        prior = fdf[fdf["funding_time"] < t]["funding_rate"]
        if prior.empty:
            return float("nan"), float("nan")
        last9 = prior.tail(P.FUNDING_MEAN_EVENTS) \
            if hasattr(P, "FUNDING_MEAN_EVENTS") else prior.tail(9)
        return float(prior.iloc[-1]), float(last9.mean())

    rows = []
    t0 = time.time()
    for k, cand in enumerate(cands.to_dict("records")):
        t, sym = int(cand["t"]), cand["symbol"]
        f_last, f_mean = funding_ctx(sym, t)
        ctx = {"breadth_sma20": breadth[t],
               "round_side_count": int(side_count.iloc[k]),
               "regime_code": regime_code[t],
               "liq_median": float(liq[ridx[t]][sym_col[sym]])
               if np.isfinite(liq[ridx[t]][sym_col[sym]]) else None,
               "funding_last": f_last, "funding_mean_3d": f_mean}
        f = build_features(cand, fs[sym], btc_fs, ctx)
        f["t"], f["symbol"] = t, sym
        rows.append(f)
    print(f"features built for {len(rows)} candidates "
          f"({time.time() - t0:.0f}s)", flush=True)

    fdf = pd.DataFrame(rows)

    # -- purge/embargo split assignment (step 4) ---------------------------
    lab_records = labels.to_dict("records")
    for r in lab_records:
        lo, hi = r.pop("info_interval_lo"), r.pop("info_interval_hi")
        r["info_interval"] = (None if pd.isna(lo)
                              else (int(lo), int(hi)))
        if pd.isna(r.get("net_r")):
            r["net_r"] = None
        if isinstance(r.get("exclusion"), float) and pd.isna(r["exclusion"]):
            r["exclusion"] = None
    split = chronological_split(lab_records,
                                int(part["validation_start_ms"]), q)
    assign = {}
    for name, exs in split.items():
        for ex in exs:
            assign[(int(ex["t"]), ex["symbol"])] = name
    fdf["split"] = [assign.get((int(r.t), r.symbol), "unassigned")
                    for r in fdf.itertuples()]
    counts = fdf["split"].value_counts().to_dict()
    print("split counts:", counts, flush=True)

    path = os.path.join(out_dir, "features_arm_a.parquet")
    fdf.to_parquet(path, index=False)
    manifest = {
        "feature_set_version": FEATURE_SET_VERSION,
        "n_rows": len(fdf),
        "split_counts": counts,
        "regime_model_version": regime.version,
        "artifact": {"path": path, "sha256": sha256_file(path)},
        "source_candidates_sha256": sha256_file(
            os.path.join(args.ledgers_dir, "candidates_arm_a.parquet")),
        "source_labels_sha256": sha256_file(
            os.path.join(args.ledgers_dir, "labels_arm_a.parquet")),
    }
    mpath = os.path.join(out_dir, "features_manifest.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print("manifest:", mpath, flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
