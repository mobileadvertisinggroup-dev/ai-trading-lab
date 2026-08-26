"""Step 3 of the pre-Checkpoint-1 assignment: the OFFICIAL Arm A run over
the verified raw-v1 lake (train + validation only), producing the frozen
ledgers every downstream arm consumes, plus the gap-exclusion accounting
required by the review directive of 2026-08-26.

Data path: GuardedLake ONLY (never raw paths). Every read is bounded above
by quarantine_start_ms - 1, so no request ever intersects the sealed
holdout range. Positions still open at the last readable 15m bar are
force-closed there (decision D9) and their candidates labeled through that
close; those labels carry exclusion=None but the event reason
'holdout_boundary_force_close' marks them in the trade ledger.

Universe construction uses the SAME vectorized eligibility code the
partition/validity computation used (lab.data.partition.eligibility_series),
so U(t) is consistent with the recorded round validity by construction.

Outputs (out_dir):
  candidates_arm_a.parquet      the candidate ledger (decision-time only)
  labels_arm_a.parquet          spec §4 labels incl. exclusion reasons
  events_arm_a.jsonl.gz         full engine event stream
  equity_arm_a.parquet          4h equity curve
  gap_exclusion_report.json     rounds/symbols/candidates excluded by gaps
  ledger_manifest_arm_a.json    sha256 of every artifact + run parameters
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

from lab import protocol as P
from lab.arms.arm_a import ArmARunner, MarketProvider
from lab.data import partition as PT
from lab.data.access import GuardedLake
from lab.labels.labels import build_labels
from lab.labels.purge import chronological_split

STARTING_CASH = 10_000.0     # D45: not spec-numeric; matches every golden
                             # fixture and the governor's min-notional scale


class GuardedProvider(MarketProvider):
    """MarketProvider backed exclusively by GuardedLake reads, bounded
    strictly below the quarantine boundary."""

    def __init__(self, lake: GuardedLake, symbols: list[str], end_ms: int):
        self._lake = lake
        self._symbols = symbols
        self._end = end_ms
        self._bars: dict[str, dict] = {}
        self._funding: dict[str, dict[int, float]] = {}

    def load(self, log_every: int = 100):
        t0 = time.time()
        for i, sym in enumerate(self._symbols):
            df = self._lake.read_klines(sym, 0, self._end)
            self._bars[sym] = {
                "open_time": df["open_time"].to_numpy(np.int64),
                "open": df["open"].to_numpy(np.float64),
                "high": df["high"].to_numpy(np.float64),
                "low": df["low"].to_numpy(np.float64),
                "close": df["close"].to_numpy(np.float64),
                "quote_volume": df["quote_volume"].to_numpy(np.float64),
            }
            fdf = self._lake.read_funding(sym, 0, self._end)
            self._funding[sym] = dict(
                zip(fdf["funding_time"].to_numpy(np.int64),
                    fdf["funding_rate"].to_numpy(np.float64)))
            if (i + 1) % log_every == 0:
                print(f"loaded {i + 1}/{len(self._symbols)} symbols "
                      f"({time.time() - t0:.0f}s)", flush=True)

    def symbols(self):
        return self._symbols

    def bars_15m(self, symbol):
        return self._bars[symbol]

    def funding(self, symbol):
        return self._funding.get(symbol, {})


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
    ap.add_argument("--out-dir", default="data/ledgers")
    ap.add_argument("--profile-rounds", type=int, default=0,
                    help="run only the first N decision rounds (compute "
                         "profiling; output marked PROFILE, never official)")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    lake = GuardedLake(args.lake, args.manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    last_15m = q - P.BAR_15M_MS

    with open(os.path.join(args.manifests_dir, "round_validity.json")) as f:
        validity = {int(k): bool(v) for k, v in json.load(f).items()}
    boundaries = np.array(sorted(validity), dtype=np.int64)

    symbols = sorted(os.listdir(os.path.join(args.lake, "klines15m")))
    print(f"symbols: {len(symbols)}; boundaries: {len(boundaries)}; "
          f"quarantine: {q}", flush=True)

    provider = GuardedProvider(lake, symbols, last_15m)
    provider.load()

    # -- calendars + eligibility (same code path as the partition) --------
    print("building calendars + eligibility...", flush=True)
    t0 = time.time()
    liq = np.full((len(boundaries), len(symbols)), np.nan)
    comp_only_excl = np.zeros(len(boundaries), dtype=np.int64)
    cals = {}
    for j, sym in enumerate(symbols):
        d = provider.bars_15m(sym)
        cal = PT.build_symbol_calendar(sym, d["open_time"], d["quote_volume"])
        cals[sym] = cal
        elig = PT.eligibility_series(cal, boundaries)
        liq[:, j] = elig.to_numpy()
        # completeness-only exclusions: would be eligible except <99% rule
        if cal.first_bar_ms >= 0:
            m = PT.daily_universe_metrics(cal)
            days = pd.to_datetime((boundaries // PT.DAY_MS) * PT.DAY_MS,
                                  unit="ms", utc=True)
            mm = m.reindex(days)
            lm = mm["liq_median"].to_numpy()
            cc = mm["completeness"].to_numpy()
            base_ok = ((cal.first_bar_ms
                        <= boundaries - P.UNIVERSE_MIN_HISTORY_DAYS * PT.DAY_MS)
                       & (cal.last_bar_ms >= boundaries - P.TRADABLE_LOOKBACK_MS)
                       & np.isfinite(lm)
                       & (lm >= P.UNIVERSE_MIN_MEDIAN_DAILY_QVOL_USDT))
            comp_only_excl += (base_ok
                               & (cc < P.UNIVERSE_MIN_COMPLETENESS)).astype(int)
    print(f"eligibility done ({time.time() - t0:.0f}s)", flush=True)

    bidx = {int(t): i for i, t in enumerate(boundaries)}
    sym_arr = np.array(symbols)

    def universe_fn(t: int) -> list[str]:
        i = bidx.get(int(t))
        if i is None:
            return []
        row = liq[i]
        ok = np.isfinite(row)
        order = np.lexsort((sym_arr[ok], -row[ok]))
        return list(sym_arr[ok][order][: P.UNIVERSE_TOP_N])

    def valid_round_fn(t: int) -> bool:
        return validity.get(int(t), False)

    runner = ArmARunner(provider, STARTING_CASH, universe_fn=universe_fn,
                        valid_round_fn=valid_round_fn)

    start = int(part["train_start_ms"])
    end = last_15m
    profile = args.profile_rounds > 0
    if profile:
        # round_validity covers warm-up boundaries before the eligible
        # interval too; profile over rounds AT/after the official start
        run_bounds = boundaries[boundaries >= start]
        end = int(run_bounds[min(args.profile_rounds, len(run_bounds)) - 1])
        end += P.BAR_4H_MS - P.BAR_15M_MS   # finish the last round's bars
    print(f"running Arm A {'PROFILE' if profile else 'OFFICIAL'}: "
          f"{start} .. {end}", flush=True)
    t0 = time.time()
    runner.run(start, end)
    elapsed = time.time() - t0
    print(f"run complete in {elapsed:.0f}s; candidates="
          f"{len(runner.candidates)}; events={len(runner.engine.events)}",
          flush=True)

    # -- D9: force-close positions still open at the last readable bar ----
    still_open = len(runner.engine.open_positions())
    if still_open:
        runner.engine.force_close_all(end, runner._marks(),
                                      "holdout_boundary_force_close")
        print(f"force-closed {still_open} positions at {end} (D9)",
              flush=True)

    # -- labels + purge/embargo accounting (step 3/4 boundary) ------------
    labels = build_labels(runner.candidates, runner.engine.events)
    excl_hist: dict[str, int] = {}
    for ex in labels:
        k = ex["exclusion"] or "labeled"
        excl_hist[k] = excl_hist.get(k, 0) + 1

    # -- gap-exclusion report (review directive) ---------------------------
    btc_incomplete = 0
    too_few_eligible = 0
    d = provider.bars_15m(P.CONTEXT_SYMBOL)
    g4 = (d["open_time"] // P.BAR_4H_MS) * P.BAR_4H_MS
    u, c = np.unique(g4, return_counts=True)
    btc_map = {int(k): int(v) for k, v in zip(u, c)}
    for t in boundaries:
        if validity[int(t)]:
            continue
        if btc_map.get(int(t) - P.BAR_4H_MS, 0) != P.BARS_15M_PER_4H:
            btc_incomplete += 1
        else:
            too_few_eligible += 1
    gap_report = {
        "decision_rounds_pre_holdout": len(boundaries),
        "invalid_rounds_skipped": int((~np.array(
            [validity[int(t)] for t in boundaries])).sum()),
        "invalid_rounds_btc_4h_incomplete": btc_incomplete,
        "invalid_rounds_too_few_eligible": too_few_eligible,
        "symbol_boundary_exclusions_completeness_only":
            int(comp_only_excl.sum()),
        "universe_member_missing_input_skips":
            runner.stats["missing_input_skips"],
        "candidates_total": len(runner.candidates),
        "label_exclusion_histogram": excl_hist,
        "btc_context": {
            "complete_4h_bars": int((c == P.BARS_15M_PER_4H).sum()),
            "incomplete_4h_bars": int((c != P.BARS_15M_PER_4H).sum()),
            "total_4h_bars": int(len(u)),
        },
        "note": ("Invalid rounds are skipped for EVERY arm (synchronized "
                 "rounds); completeness exclusions apply the frozen >=99% "
                 "rule mechanically; missing OHLCV is never filled."),
    }

    split = chronological_split(labels, int(part["validation_start_ms"]), q)
    gap_report["purge_embargo"] = {k: len(v) for k, v in split.items()}

    # -- write artifacts ----------------------------------------------------
    tag = "PROFILE_" if profile else ""
    paths = {}
    cdf = pd.DataFrame(runner.candidates)
    paths["candidates"] = os.path.join(args.out_dir,
                                       f"{tag}candidates_arm_a.parquet")
    cdf.to_parquet(paths["candidates"], index=False)
    ldf = pd.DataFrame([{**e, "info_interval_lo":
                         (e["info_interval"] or (None, None))[0],
                         "info_interval_hi":
                         (e["info_interval"] or (None, None))[1]}
                        for e in labels]).drop(columns=["info_interval"],
                                               errors="ignore")
    paths["labels"] = os.path.join(args.out_dir, f"{tag}labels_arm_a.parquet")
    ldf.to_parquet(paths["labels"], index=False)
    paths["events"] = os.path.join(args.out_dir, f"{tag}events_arm_a.jsonl.gz")
    with gzip.open(paths["events"], "wt") as f:
        for ev in runner.engine.events:
            f.write(json.dumps(ev, sort_keys=True, default=float) + "\n")
    paths["equity"] = os.path.join(args.out_dir, f"{tag}equity_arm_a.parquet")
    pd.DataFrame(runner.equity_curve).to_parquet(paths["equity"], index=False)
    paths["gap_report"] = os.path.join(args.out_dir,
                                       f"{tag}gap_exclusion_report.json")
    with open(paths["gap_report"], "w") as f:
        json.dump(gap_report, f, indent=2, sort_keys=True)

    manifest = {
        "run": "PROFILE (never official)" if profile else "OFFICIAL Arm A",
        "starting_cash": STARTING_CASH,
        "start_ms": start, "end_ms": end,
        "release_version": part.get("release_version"),
        "elapsed_seconds": round(elapsed, 1),
        "n_candidates": len(runner.candidates),
        "n_events": len(runner.engine.events),
        "final_equity": runner.equity_curve[-1]["equity"]
        if runner.equity_curve else None,
        "artifacts": {k: {"path": v, "sha256": sha256_file(v)}
                      for k, v in paths.items()},
    }
    mpath = os.path.join(args.out_dir, f"{tag}ledger_manifest_arm_a.json")
    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in manifest.items()
                      if k != "artifacts"}, indent=2), flush=True)
    print("manifest:", mpath, flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
