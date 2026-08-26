"""Steps 1-2 of the pre-Checkpoint-1 assignment (review decision 2026-08-26):
verify the downloaded plaintext lake and mechanically reproduce the frozen
partition from it.

What is verified (all mechanical, exact):
  1. every lake file's sha256 against the git-pinned dataset manifest
     (lab_manifest_raw-v1.json) — count and content;
  2. ZERO readable holdout rows: every klines open_time and every funding
     funding_time is strictly below quarantine_start_ms;
  3. round validity recomputed from the plaintext lake matches
     round_validity.json EXACTLY for every pre-quarantine boundary;
  4. the eligible-interval START rule (60-day / 95%-valid, protocol §6)
     reproduces the recorded train_start_ms from plaintext data alone;
  5. the partition arithmetic (protocol §7) recomputed over the recorded
     eligible interval reproduces n_boundaries / i_t / i_v /
     quarantine_start_ms and every recorded segment timestamp.

HONEST SCOPE: the eligible-interval END and holdout-side round validity
depend on sealed holdout data and are NOT reproducible from the plaintext
lake — by design (HOLDOUT_POLICY §1). They are pinned by the recorded
partition metadata and the sealed artifact's hash instead. Nothing here
touches the encrypted artifact.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pyarrow.parquet as pq

from lab import protocol as P
from lab.data import lake as L
from lab.data import partition as PT


def verify(lake_dir: str, manifests_dir: str, release_version: str) -> dict:
    report: dict = {"release_version": release_version, "checks": {}}

    # -- 1. manifest verification
    with open(os.path.join(manifests_dir,
                           f"lake_manifest_{release_version}.json")) as f:
        manifest = json.load(f)
    problems = L.verify_manifest(lake_dir, manifest)
    if problems:
        raise SystemExit("manifest verification FAILED:\n  "
                         + "\n  ".join(problems[:20]))
    report["checks"]["manifest_files_verified"] = len(manifest["files"])

    with open(os.path.join(manifests_dir, "partition_meta.json")) as f:
        part = json.load(f)
    q = part["quarantine_start_ms"]

    # -- 2. zero readable holdout rows + build calendars in one pass
    cals: dict[str, PT.SymbolCalendar] = {}
    btc_map: dict[int, int] = {}
    n_rows = 0
    kbase = os.path.join(lake_dir, "klines15m")
    for symbol in sorted(os.listdir(kbase)):
        sdir = os.path.join(kbase, symbol)
        times, qvs = [], []
        for name in sorted(os.listdir(sdir)):
            t = pq.read_table(os.path.join(sdir, name),
                              columns=["open_time", "quote_volume"])
            times.append(t["open_time"].to_numpy())
            qvs.append(t["quote_volume"].to_numpy())
        ts = np.concatenate(times)
        n_rows += len(ts)
        if ts.max() >= q:
            raise SystemExit(f"HOLDOUT LEAK: {symbol} has readable klines at "
                             f"{int(ts.max())} >= quarantine {q}")
        cals[symbol] = PT.build_symbol_calendar(symbol, ts,
                                                np.concatenate(qvs))
        if symbol == P.CONTEXT_SYMBOL:
            g4 = (ts // P.BAR_4H_MS) * P.BAR_4H_MS
            u, c = np.unique(g4, return_counts=True)
            btc_map = {int(k): int(v) for k, v in zip(u, c)}
    fbase = os.path.join(lake_dir, "funding")
    n_frows = 0
    for name in sorted(os.listdir(fbase)):
        ft = pq.read_table(os.path.join(fbase, name),
                           columns=["funding_time"])["funding_time"].to_numpy()
        n_frows += len(ft)
        if len(ft) and ft.max() >= q:
            raise SystemExit(f"HOLDOUT LEAK: funding {name} at "
                             f"{int(ft.max())} >= quarantine {q}")
    report["checks"]["zero_readable_holdout_rows"] = True
    report["checks"]["klines_rows_scanned"] = int(n_rows)
    report["checks"]["funding_rows_scanned"] = int(n_frows)
    report["checks"]["n_symbols"] = len(cals)

    # -- 3. recomputed pre-quarantine round validity == round_validity.json
    with open(os.path.join(manifests_dir, "round_validity.json")) as f:
        recorded = {int(k): bool(v) for k, v in json.load(f).items()}
    bounds = np.array(sorted(recorded), dtype=np.int64)
    validity = PT.round_validity_fast(bounds, cals, btc_map)
    mismatches = [int(t) for t in bounds
                  if bool(validity.loc[int(t)]) != recorded[int(t)]]
    if mismatches:
        raise SystemExit(f"round-validity mismatch at {len(mismatches)} "
                         f"boundaries; first: {mismatches[:5]}")
    report["checks"]["round_validity_boundaries_matched"] = len(bounds)

    # -- 4. eligible-interval START rule reproduces train_start_ms
    #    (END is holdout-side; pinned by recorded metadata, not recomputable)
    window_ms = P.INTERVAL_START_WINDOW_DAYS * PT.DAY_MS
    ts_arr = validity.index.to_numpy(dtype=np.int64)
    flags = validity.to_numpy(dtype=bool)
    start_found = None
    for i in range(len(ts_arr)):
        if not flags[i]:
            continue
        t0 = ts_arr[i]
        in_win = (ts_arr >= t0) & (ts_arr <= t0 + window_ms)
        if in_win.sum() and flags[in_win].mean() >= P.INTERVAL_START_VALID_FRACTION:
            start_found = int(t0)
            break
    if start_found != part["train_start_ms"]:
        raise SystemExit(f"interval START mismatch: recomputed {start_found} "
                         f"!= recorded {part['train_start_ms']}")
    report["checks"]["interval_start_reproduced"] = start_found

    # -- 5. partition arithmetic over the recorded interval
    recomputed = PT.compute_partition(part["train_start_ms"],
                                      part["holdout_end_ms"])
    diffs = {k: (recomputed[k], part[k]) for k in recomputed
             if part.get(k) != recomputed[k]}
    if diffs:
        raise SystemExit(f"partition arithmetic mismatch: {diffs}")
    report["checks"]["partition_arithmetic_reproduced"] = {
        k: recomputed[k] for k in ("n_boundaries", "i_t", "i_v",
                                   "quarantine_start_ms")}
    report["verdict"] = "VERIFIED"
    return report


def main() -> None:  # pragma: no cover — operational tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--release-version", default="raw-v1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    report = verify(args.lake, args.manifests_dir, args.release_version)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)


if __name__ == "__main__":  # pragma: no cover
    main()
