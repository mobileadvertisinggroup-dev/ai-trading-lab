"""Post-ingestion coverage audit — user directive 2026-08-26 (acceptance
gate for raw-v1 and every later data version; recorded as D40).

Before a data release may be declared scientifically usable, this audit is
performed on the PUBLISHED plaintext lake and preserved (with its hash) in
the dataset manifest. Per symbol it:

  1. records the first and last available 15-minute bar;
  2. records every missing month between those dates;
  3. distinguishes: pre-listing months, post-delisting months, genuinely
     missing archive months while the market was active, the recent months
     handled by the daily fallback, and holdout-sealed months (whose rows
     are in the encrypted artifact, not the readable lake — classified,
     never probed for values);
  4. detects internal 15-minute gaps and reports completeness by symbol
     and month;
  5. verifies AGAINST THE ARCHIVE that restricting the daily fallback to
     the final DAILY_FALLBACK_MONTHS months did not silently discard any
     month in which historical trading data actually existed: every
     internal missing month — and the month just before the first bar and
     just after the last bar — is probed (tiny ranged requests); if the
     archive holds ANY data we lack, the verdict is FAIL_COVERAGE_LOSS;
  6. reports BTC context coverage separately;
  7. is written to data/manifests/coverage_audit_<version>.json and its
     sha256 recorded in the dataset manifest (append-only addendum keys;
     the original manifest_sha256 is preserved unchanged).

FAIL_COVERAGE_LOSS means: the release is NOT accepted for training, the
acquisition rule is corrected, and a NEW data version is produced. An
acquisition failure is never silently treated as the market being
unavailable.
"""
from __future__ import annotations

import argparse
import calendar as _cal
import datetime as dt
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pyarrow.parquet as pq

from lab import protocol as P

BAR = P.BAR_15M_MS


# ------------------------------------------------------------------ months

def month_of(ms: int) -> str:
    d = dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def month_start_ms(month: str) -> int:
    y, m = map(int, month.split("-"))
    return int(dt.datetime(y, m, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)


def next_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    m += 1
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}"


def prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def months_between(a: str, b: str) -> list[str]:
    """Inclusive list of YYYY-MM from a to b."""
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        cur = next_month(cur)
    return out


def months_from_end(month: str, end_month: str) -> int:
    y1, m1 = map(int, month.split("-"))
    y2, m2 = map(int, end_month.split("-"))
    return (y2 - y1) * 12 + (m2 - m1)


def expected_slots(lo_ms: int, hi_ms: int) -> int:
    """Number of 15m grid timestamps t with lo <= t < hi."""
    if hi_ms <= lo_ms:
        return 0
    first = ((lo_ms + BAR - 1) // BAR) * BAR
    if first >= hi_ms:
        return 0
    return (hi_ms - 1 - first) // BAR + 1


# ------------------------------------------------------------------ probing

def make_archive_probe(vision_url: str):
    """Returns probe(symbol, month) -> 'monthly' | 'daily' | 'absent'.
    Existence is checked with tiny ranged GETs (bytes=0-0); 404 = absent.
    Daily existence is sampled on several days spread across the month —
    any hit proves the archive holds data for that month."""
    from urllib.request import Request, urlopen

    def exists(url: str) -> bool:
        try:
            req = Request(url, headers={
                "User-Agent": "akra-ai-trading-lab/audit",
                "Range": "bytes=0-0"})
            with urlopen(req, timeout=30):
                return True
        except Exception as e:  # noqa: BLE001
            if "404" in str(e) or "416" in str(e):
                return "404" not in str(e)
            raise

    def probe(symbol: str, month: str) -> str:
        mu = (f"{vision_url}/data/futures/um/monthly/klines/{symbol}/15m/"
              f"{symbol}-15m-{month}.zip")
        if exists(mu):
            return "monthly"
        y, m = map(int, month.split("-"))
        last_day = _cal.monthrange(y, m)[1]
        for day in sorted({1, 8, 15, 22, last_day}):
            du = (f"{vision_url}/data/futures/um/daily/klines/{symbol}/15m/"
                  f"{symbol}-15m-{y:04d}-{m:02d}-{day:02d}.zip")
            if exists(du):
                return "daily"
        return "absent"

    return probe


# ------------------------------------------------------------------ audit

def _scan_symbol(lake_dir: str, symbol: str) -> dict:
    """Per-month {rows, t_min, t_max} from the symbol's parquet files,
    reading only the open_time column."""
    sdir = os.path.join(lake_dir, "klines15m", symbol)
    months = {}
    for name in sorted(os.listdir(sdir)):
        if not name.endswith(".parquet"):
            continue
        t = pq.read_table(os.path.join(sdir, name),
                          columns=["open_time"])["open_time"].to_pylist()
        if t:
            months[name[:-8]] = {"rows": len(t), "t_min": min(t),
                                 "t_max": max(t)}
    return months


def audit_lake(lake_dir: str, manifests_dir: str, release_version: str,
               daily_fallback_months: int, archive_probe=None,
               probe_workers: int = 12,
               acquisition_start_month: str = "2020-01") -> dict:
    """Full coverage audit. archive_probe(symbol, month) -> 'monthly' |
    'daily' | 'absent'; None skips probing (classification only — NOT
    sufficient to accept a release; the accept path always probes)."""
    with open(os.path.join(manifests_dir, "partition_meta.json")) as f:
        part = json.load(f)
    quarantine_ms = part["quarantine_start_ms"]
    freeze_ms = part["ingestion_freeze_ms"]
    q_month = month_of(quarantine_ms)
    freeze_month = month_of(freeze_ms)

    base = os.path.join(lake_dir, "klines15m")
    symbols = sorted(os.listdir(base)) if os.path.isdir(base) else []

    per_symbol: dict[str, dict] = {}
    probe_requests: list[tuple[str, str, str]] = []  # (symbol, month, why)

    for sym in symbols:
        months = _scan_symbol(lake_dir, sym)
        if not months:
            per_symbol[sym] = {"empty": True}
            continue
        present = sorted(months)
        first_bar = months[present[0]]["t_min"]
        last_bar = months[present[-1]]["t_max"]
        first_m, last_m = month_of(first_bar), month_of(last_bar)

        month_report = {}
        for m in months_between(first_m, last_m):
            lo = max(month_start_ms(m), first_bar)
            hi = min(month_start_ms(next_month(m)), last_bar + BAR,
                     quarantine_ms, freeze_ms)
            exp = expected_slots(lo, hi)
            if m in months:
                rows = months[m]["rows"]
                month_report[m] = {
                    "status": "present", "rows": rows, "expected": exp,
                    "completeness": round(rows / exp, 6) if exp else None}
            else:
                if m >= q_month:
                    cls = "holdout_sealed"
                elif months_from_end(m, freeze_month) < daily_fallback_months:
                    cls = "recent_fallback_window_absent"
                else:
                    cls = "internal_missing_pending_probe"
                    probe_requests.append((sym, m, "internal"))
                month_report[m] = {"status": cls, "expected": exp}

        # head/tail truncation probes (one month before first / after last),
        # skipping months where absence is explained (sealed, fallback, or
        # before the frozen acquisition start — archive data before
        # history_start is excluded by design, not an acquisition failure)
        head_m = prev_month(first_m)
        if head_m >= acquisition_start_month:
            probe_requests.append((sym, head_m, "pre_listing_check"))
        tail_m = next_month(last_m)
        if (tail_m < q_month
                and months_from_end(tail_m, freeze_month)
                >= daily_fallback_months):
            probe_requests.append((sym, tail_m, "post_delisting_check"))

        per_symbol[sym] = {
            "first_bar_ms": first_bar, "last_bar_ms": last_bar,
            "first_month": first_m, "last_month": last_m,
            "months_present": len(months),
            "months": month_report,
            "pre_listing_months_before": first_m,
            "post_delisting_months_after": last_m,
        }

    # ---- archive probes (points 3/5: never treat acquisition failure as
    # market unavailability without checking the archive)
    probes_done: dict[tuple[str, str], str] = {}
    if archive_probe is not None and probe_requests:
        def run(req):
            sym, m, why = req
            return (sym, m, why, archive_probe(sym, m))
        with ThreadPoolExecutor(max_workers=probe_workers) as pool:
            for sym, m, why, res in pool.map(run, probe_requests):
                probes_done[(sym, m)] = res

    coverage_losses = []
    for sym, m, why in probe_requests:
        res = probes_done.get((sym, m))
        if res is None:
            continue
        rep = per_symbol[sym]
        if why == "internal":
            if res == "absent":
                rep["months"][m]["status"] = "archive_empty_market_inactive"
            else:
                rep["months"][m]["status"] = f"COVERAGE_LOSS_archive_has_{res}"
                coverage_losses.append({"symbol": sym, "month": m,
                                        "archive": res, "kind": "internal"})
        elif why == "pre_listing_check" and res != "absent":
            coverage_losses.append({"symbol": sym, "month": m,
                                    "archive": res, "kind": "head_truncated"})
        elif why == "post_delisting_check" and res != "absent":
            coverage_losses.append({"symbol": sym, "month": m,
                                    "archive": res, "kind": "tail_truncated"})

    probed = archive_probe is not None
    audit = {
        "release_version": release_version,
        "generated_utc": dt.datetime.now(dt.timezone.utc)
                           .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "parameters": {
            "daily_fallback_months": daily_fallback_months,
            "quarantine_start_ms": quarantine_ms,
            "ingestion_freeze_ms": freeze_ms,
            "bar_ms": BAR,
            "archive_probed": probed,
            "acquisition_start_month": acquisition_start_month,
        },
        "n_symbols": len(symbols),
        "symbols": per_symbol,
        "btc_context": per_symbol.get(P.CONTEXT_SYMBOL,
                                      {"error": "context symbol missing"}),
        "coverage_losses": coverage_losses,
        "verdict": ("FAIL_COVERAGE_LOSS" if coverage_losses else
                    ("PASS" if probed else "UNVERIFIED_NO_PROBE")),
    }
    return audit


def record_in_manifest(manifests_dir: str, release_version: str) -> dict:
    """Preserve the audit file name, sha256, and verdict inside the dataset
    manifest (directive point 7). Append-only addendum keys: the original
    ingestion-time manifest_sha256 is left untouched as the pin for the
    release assets; manifest_sha256_with_audit hashes the amended body."""
    import hashlib
    audit_name = f"coverage_audit_{release_version}.json"
    audit_path = os.path.join(manifests_dir, audit_name)
    with open(audit_path, "rb") as f:
        audit_bytes = f.read()
    audit_sha = hashlib.sha256(audit_bytes).hexdigest()
    verdict = json.loads(audit_bytes)["verdict"]

    man_path = os.path.join(manifests_dir,
                            f"lake_manifest_{release_version}.json")
    with open(man_path) as f:
        manifest = json.load(f)
    manifest["coverage_audit_file"] = audit_name
    manifest["coverage_audit_sha256"] = audit_sha
    manifest["coverage_audit_verdict"] = verdict
    body = {k: v for k, v in manifest.items()
            if k != "manifest_sha256_with_audit"}
    manifest["manifest_sha256_with_audit"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"))
        .encode()).hexdigest()
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


def main() -> None:  # pragma: no cover — exercised on Actions
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--release-version", required=True)
    ap.add_argument("--no-probe", action="store_true",
                    help="classification only; verdict UNVERIFIED_NO_PROBE "
                         "(never sufficient to accept a release)")
    ap.add_argument("--history-start", default="2020-01-01",
                    help="frozen acquisition start (matches ingest)")
    ap.add_argument("--verify-manifest", action="store_true",
                    help="first verify every lake file against the "
                         "release's git-pinned manifest hashes")
    args = ap.parse_args()
    from lab.data import lake as LK
    from lab.data.ingest import DAILY_FALLBACK_MONTHS, VISION
    if args.verify_manifest:
        with open(os.path.join(
                args.manifests_dir,
                f"lake_manifest_{args.release_version}.json")) as f:
            manifest = json.load(f)
        problems = LK.verify_manifest(args.lake, manifest)
        if problems:
            raise SystemExit("lake fails manifest verification:\n  "
                             + "\n  ".join(problems[:20]))
        print(f"lake verified against manifest "
              f"({len(manifest['files'])} files)")
    probe = None if args.no_probe else make_archive_probe(VISION)
    audit = audit_lake(args.lake, args.manifests_dir, args.release_version,
                       DAILY_FALLBACK_MONTHS, archive_probe=probe,
                       acquisition_start_month=args.history_start[:7])
    out = os.path.join(args.manifests_dir,
                       f"coverage_audit_{args.release_version}.json")
    with open(out, "w") as f:
        json.dump(audit, f, indent=1, sort_keys=True)
    record_in_manifest(args.manifests_dir, args.release_version)
    n_loss = len(audit["coverage_losses"])
    print(f"coverage audit: {audit['n_symbols']} symbols, verdict "
          f"{audit['verdict']}, {n_loss} coverage losses -> {out} "
          f"(hash recorded in dataset manifest)")
    if audit["verdict"] != "PASS":
        raise SystemExit(
            f"AUDIT {audit['verdict']}: the release is NOT accepted for "
            f"training (user directive 2026-08-26). Correct the acquisition "
            f"rule and produce a new data version.")


if __name__ == "__main__":  # pragma: no cover
    main()
