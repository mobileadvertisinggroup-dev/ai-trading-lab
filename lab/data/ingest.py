"""Ingestion: Binance USDT-M perpetual history → staged lake → seal → publish.

Runs on GitHub Actions runners (open egress); the dev container cannot reach
exchange endpoints (BUILD_STATE D3). Everything network-touching lives here;
parsers are pure functions with local tests. Operating rules: HOLDOUT_POLICY.md
§6 — paper-only, metadata-only logging near the holdout range, no raw data to
Git.

Source layout (data.binance.vision, public, no auth):
  data/futures/um/monthly/klines/<SYM>/15m/<SYM>-15m-<YYYY-MM>.zip
  data/futures/um/daily/klines/<SYM>/15m/<SYM>-15m-<YYYY-MM-DD>.zip
  data/futures/um/monthly/fundingRate/<SYM>/<SYM>-fundingRate-<YYYY-MM>.zip
Each with a sibling .CHECKSUM (sha256). Bucket listing is S3 XML with
marker pagination. Delisted symbols remain listed → survivorship-free
coverage to the extent the archive provides it (audited, protocol §8).

NOTE (shakedown item S-ING-1): CSV column layouts are asserted defensively
below; the first Actions run uses --probe to confirm real headers before any
full ingestion. Never guess silently — mismatches raise.
"""
from __future__ import annotations

import argparse
import calendar as _cal
import datetime as dt
import io
import json
import logging
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import numpy as np
import pandas as pd

from lab import protocol as P
from lab.data import lake as L
from lab.data import partition as PT
from lab.data import seal as SL

log = logging.getLogger("lab.ingest")

VISION = "https://data.binance.vision"
# Bucket LISTING must hit the S3 endpoint itself — data.binance.vision
# serves the website HTML for query URLs (probe run 1 finding, 2026-08-26).
VISION_LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
S3NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

# Probe run 2 (2026-08-26) measured 0.68s/symbol-month sequential => ~9.3h
# for 824 symbols x ~60 months, over the 5.8h job budget. Acquisition is
# therefore CONCURRENT within the single ingestion job (downloads are
# independent per symbol and network-bound). Multi-job sharding was
# rejected: PC-1 (SPEC §9.3a / HOLDOUT_POLICY §4a) forbids holdout-range
# staging from ever leaving the runner as an artifact, so acquisition must
# complete inside one RUNNER_TEMP lifetime. Any symbol failure still fails
# the whole run — a partial dataset is never published (verdict §5.5).
ACQ_WORKERS = int(os.environ.get("AKRA_ACQ_WORKERS", "12"))

KLINE_COLS_RAW = ["open_time", "open", "high", "low", "close", "volume",
                  "close_time", "quote_volume", "count", "taker_buy_volume",
                  "taker_buy_quote_volume", "ignore"]


# ---------------------------------------------------------------- pure parsers

def normalize_epoch_ms(values: np.ndarray) -> np.ndarray:
    """Binance archives switched some datasets to microseconds; normalize to ms."""
    v = values.astype(np.int64, copy=True)
    micros = v > 100_000_000_000_000  # > year 5138 in ms => microseconds
    v[micros] //= 1000
    return v


def parse_kline_csv(raw: bytes) -> pd.DataFrame:
    """Parse a Binance futures kline CSV (with or without header row)."""
    first = raw.split(b"\n", 1)[0]
    has_header = first.startswith(b"open_time")
    df = pd.read_csv(io.BytesIO(raw), header=0 if has_header else None)
    if df.shape[1] != len(KLINE_COLS_RAW):
        raise ValueError(f"unexpected kline column count {df.shape[1]}")
    df.columns = KLINE_COLS_RAW
    out = pd.DataFrame({
        "open_time": normalize_epoch_ms(df["open_time"].to_numpy()),
        "open": df["open"].astype(np.float64),
        "high": df["high"].astype(np.float64),
        "low": df["low"].astype(np.float64),
        "close": df["close"].astype(np.float64),
        "volume": df["volume"].astype(np.float64),
        "quote_volume": df["quote_volume"].astype(np.float64),
    })
    if (out["open_time"] % P.BAR_15M_MS).any():
        raise ValueError("open_time not aligned to 15m grid")
    return out.sort_values("open_time").reset_index(drop=True)


def parse_funding_csv(raw: bytes) -> pd.DataFrame:
    """Parse a Binance fundingRate CSV. Known layouts:
       calc_time,funding_interval_hours,last_funding_rate  (headered)
    Any other layout raises (S-ING-1: verify via --probe, then extend
    explicitly — never guess silently)."""
    first = raw.split(b"\n", 1)[0].decode("utf-8", "replace").strip().lower()
    df = pd.read_csv(io.BytesIO(raw))
    cols = [c.strip().lower() for c in df.columns]
    df.columns = cols
    time_col = next((c for c in cols if "calc_time" in c or "fundingtime" in c
                     or c == "funding_time"), None)
    rate_col = next((c for c in cols if "funding_rate" in c or "fundingrate" in c
                     or "last_funding_rate" in c), None)
    if time_col is None or rate_col is None:
        raise ValueError(f"unrecognized funding CSV header: {first!r}")
    out = pd.DataFrame({
        "funding_time": normalize_epoch_ms(df[time_col].to_numpy(dtype=np.int64)),
        "funding_rate": df[rate_col].astype(np.float64),
    })
    return out.sort_values("funding_time").reset_index(drop=True)


def parse_s3_listing(xml_bytes: bytes) -> tuple[list[str], list[str], bool, str]:
    """Return (common_prefixes, keys, truncated, next_marker)."""
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as e:
        raise RuntimeError(
            f"listing response is not S3 XML ({e}); first bytes: "
            f"{xml_bytes[:160]!r}") from e
    prefixes = [el.findtext(f"{S3NS}Prefix") for el in root.iter(f"{S3NS}CommonPrefixes")]
    keys = [el.findtext(f"{S3NS}Key") for el in root.iter(f"{S3NS}Contents")]
    truncated = (root.findtext(f"{S3NS}IsTruncated") or "false") == "true"
    next_marker = root.findtext(f"{S3NS}NextMarker") or (keys[-1] if keys and truncated else "")
    return prefixes, keys, truncated, next_marker


def months_between(start: dt.date, end: dt.date) -> list[str]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


# ---------------------------------------------------------------- networking

def _get(url: str, retries: int = 4, timeout: int = 60) -> bytes:
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers={"User-Agent": "akra-ai-trading-lab/ingest"})
            with urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 — retry then re-raise honestly
            if attempt == retries or "404" in str(e):
                raise
            log.warning("GET %s failed (%s); retry in %.0fs", url, e, delay)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _get_zip_csv(url: str, verify_checksum: bool = True) -> bytes | None:
    """Download <url>, verify sibling .CHECKSUM, return inner CSV bytes.
    Returns None on 404 (month genuinely absent)."""
    try:
        blob = _get(url)
    except Exception as e:  # noqa: BLE001
        if "404" in str(e):
            return None
        raise
    if verify_checksum:
        try:
            want = _get(url + ".CHECKSUM").split()[0].decode()
            got = L.sha256_bytes(blob)
            if got != want:
                raise RuntimeError(f"checksum mismatch for {url}: {got} != {want}")
        except Exception as e:  # noqa: BLE001
            if "404" not in str(e):
                raise
            log.warning("no CHECKSUM for %s; recording unverified", url)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if len(names) != 1:
            raise RuntimeError(f"unexpected zip contents {names} in {url}")
        return z.read(names[0])


REGISTRY_PATH = "data/manifests/exclusion_registry_v1.json"


def load_exclusion_registry(path: str = REGISTRY_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def classify_symbol(symbol: str, registry: dict) -> dict:
    """Deterministic point-in-time classification against the versioned
    registry (review verdict §6). Returns the record preserved in the
    dataset manifest."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    for cat, spec in registry["categories"].items():
        if base in spec.get("bases", ()):
            return {"symbol": symbol, "included": False, "category": cat,
                    "rule": "base-list"}
        pat = spec.get("pattern")
        if pat and re.search(pat, base):
            return {"symbol": symbol, "included": False, "category": cat,
                    "rule": f"pattern:{pat}"}
    return {"symbol": symbol, "included": True, "category": None,
            "rule": None}


def list_perp_symbols(registry: dict | None = None,
                      classifications_out: list | None = None) -> list[str]:
    """All USDT-quoted symbols present in the um monthly klines archive —
    including delisted ones (survivorship-free to archive coverage) —
    filtered by the versioned exclusion registry. Every discovered symbol's
    classification is appended to classifications_out (dataset-manifest
    record)."""
    registry = registry or load_exclusion_registry()
    prefix = "data/futures/um/monthly/klines/"
    url = f"{VISION_LIST}?delimiter=/&prefix={prefix}"
    symbols, marker = [], ""
    while True:
        u = url + (f"&marker={marker}" if marker else "")
        prefixes, _keys, truncated, marker = parse_s3_listing(_get(u))
        for pfx in prefixes:
            sym = pfx[len(prefix):].strip("/")
            if sym.endswith("USDT") and re.fullmatch(r"[A-Z0-9]+", sym):
                symbols.append(sym)
        if not truncated:
            break
    included = []
    for sym in sorted(set(symbols)):
        rec = classify_symbol(sym, registry)
        if classifications_out is not None:
            classifications_out.append(rec)
        if rec["included"]:
            included.append(sym)
    return included


def download_symbol(symbol: str, start: dt.date, end: dt.date,
                    staging_dir: str) -> dict:
    """Download one symbol's 15m klines + funding into the staging lake."""
    stats = {"symbol": symbol, "months": 0, "rows": 0, "funding_rows": 0}
    for month in months_between(start, end):
        url = (f"{VISION}/data/futures/um/monthly/klines/{symbol}/15m/"
               f"{symbol}-15m-{month}.zip")
        csv = _get_zip_csv(url)
        dfs = []
        if csv is not None:
            dfs.append(parse_kline_csv(csv))
        else:
            # month absent as monthly file; try daily files (current month or
            # partial listing months)
            y, m = map(int, month.split("-"))
            for day in range(1, _cal.monthrange(y, m)[1] + 1):
                d = dt.date(y, m, day)
                if d > end:
                    break
                du = (f"{VISION}/data/futures/um/daily/klines/{symbol}/15m/"
                      f"{symbol}-15m-{d.isoformat()}.zip")
                dcsv = _get_zip_csv(du)
                if dcsv is not None:
                    dfs.append(parse_kline_csv(dcsv))
        if dfs:
            df = pd.concat(dfs, ignore_index=True).drop_duplicates("open_time")
            L.write_parquet(df, L.klines_path(staging_dir, symbol, month))
            stats["months"] += 1
            stats["rows"] += len(df)

    fdfs = []
    for month in months_between(start, end):
        fu = (f"{VISION}/data/futures/um/monthly/fundingRate/{symbol}/"
              f"{symbol}-fundingRate-{month}.zip")
        fcsv = _get_zip_csv(fu)
        if fcsv is not None:
            fdfs.append(parse_funding_csv(fcsv))
    if fdfs:
        f = pd.concat(fdfs, ignore_index=True).drop_duplicates("funding_time")
        L.write_parquet(f, L.funding_path(staging_dir, symbol))
        stats["funding_rows"] = len(f)
    return stats


# ---------------------------------------------------------------- calendars

def calendars_from_staging(staging_dir: str) -> tuple[dict, dict]:
    """Build symbol calendars + BTC 15m-per-4h map from the staged lake."""
    cals: dict[str, PT.SymbolCalendar] = {}
    btc_map: dict[int, int] = {}
    base = os.path.join(staging_dir, "klines15m")
    for symbol in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        times, qvs = [], []
        sdir = os.path.join(base, symbol)
        for name in sorted(os.listdir(sdir)):
            df = L.read_parquet(os.path.join(sdir, name))
            times.append(df["open_time"].to_numpy(np.int64))
            qvs.append(df["quote_volume"].to_numpy(np.float64))
        t = np.concatenate(times) if times else np.array([], dtype=np.int64)
        q = np.concatenate(qvs) if qvs else np.array([])
        cals[symbol] = PT.build_symbol_calendar(symbol, t, q)
        if symbol == P.CONTEXT_SYMBOL:
            g4 = (t // P.BAR_4H_MS) * P.BAR_4H_MS
            u, c = np.unique(g4, return_counts=True)
            btc_map = {int(k): int(v) for k, v in zip(u, c)}
    return cals, btc_map


# ---------------------------------------------------------------- orchestrator

def run_ingestion(out_dir: str, manifests_dir: str, recipient_path: str,
                  history_start: str, freeze_utc: str | None,
                  release_version: str) -> dict:
    """Full Phase-2 pipeline: download → calendars → interval → partition →
    seal → plaintext lake + encrypted artifact + manifests."""
    with open(recipient_path) as f:
        recipient = f.read().strip()
    if not recipient.startswith("age1"):
        raise RuntimeError(
            "data/manifests/holdout_recipient.txt must contain the user's "
            "age public key (age1...). Refusing to ingest without a real "
            "recipient — the holdout could not be sealed. (HOLDOUT_POLICY §4)")

    freeze_ms = (int(pd.Timestamp(freeze_utc).timestamp() * 1000)
                 if freeze_utc else int(time.time() * 1000))
    start = dt.date.fromisoformat(history_start)
    end = dt.datetime.fromtimestamp(freeze_ms / 1000, dt.timezone.utc).date()

    staging = os.path.join(out_dir, "staging")
    plain = os.path.join(out_dir, "lake")
    os.makedirs(staging, exist_ok=True)
    os.makedirs(plain, exist_ok=True)

    registry = load_exclusion_registry()
    classifications: list[dict] = []
    symbols = list_perp_symbols(registry, classifications)
    log.info("discovered %d included USDT perp symbols (%d classified, "
             "registry %s)", len(symbols), len(classifications),
             registry["registry_version"])
    # Concurrent acquisition (see ACQ_WORKERS note): symbols are fully
    # independent (distinct staging paths, pure parsers); fut.result()
    # re-raises any worker failure so the run fails rather than publishing
    # a partial dataset.
    done = 0
    with ThreadPoolExecutor(max_workers=ACQ_WORKERS) as pool:
        futs = {pool.submit(download_symbol, sym, start, end, staging): sym
                for sym in symbols}
        for fut in as_completed(futs):
            st = fut.result()
            done += 1
            log.info("[%d/%d] %s months=%d rows=%d funding=%d",
                     done, len(symbols), st["symbol"], st["months"],
                     st["rows"], st["funding_rows"])

    cals, btc_map = calendars_from_staging(staging)
    if P.CONTEXT_SYMBOL not in cals or cals[P.CONTEXT_SYMBOL].first_bar_ms < 0:
        raise RuntimeError("context symbol data missing — cannot proceed")

    first = min(c.first_bar_ms for c in cals.values() if c.first_bar_ms >= 0)
    bounds = PT.all_boundaries(P.four_hour_floor(first) + P.BAR_4H_MS,
                               P.four_hour_floor(freeze_ms))
    validity = PT.round_validity_fast(bounds, cals, btc_map)
    start_ms, end_ms = PT.eligible_interval(validity, freeze_ms)
    part = PT.compute_partition(start_ms, end_ms)
    part["ingestion_freeze_ms"] = freeze_ms
    part["release_version"] = release_version
    log.info("eligible interval: %s .. %s, %d boundaries (train %d / val %d / holdout %d)",
             pd.Timestamp(start_ms, unit="ms", tz="UTC"),
             pd.Timestamp(end_ms, unit="ms", tz="UTC"),
             part["n_boundaries"], part["i_t"], part["i_v"] - part["i_t"],
             part["n_boundaries"] - part["i_v"])

    # ---- SEAL (mechanical pass-through; metadata-only logging inside) ----
    artifact = os.path.join(out_dir, f"holdout-{release_version}.tar.age")
    seal_meta = SL.seal_lake(staging, plain, part["quarantine_start_ms"],
                             recipient, artifact)
    SL.write_seal_metadata(seal_meta, manifests_dir)

    # drop everything outside the eligible interval from the plaintext lake?
    # No: pre-interval data is legitimately needed for warm-up (indicators,
    # trailing-liquidity windows). Only the holdout side is restricted.

    os.makedirs(manifests_dir, exist_ok=True)
    with open(os.path.join(manifests_dir, "partition_meta.json"), "w") as f:
        json.dump(part, f, indent=2, sort_keys=True)
    validity_rec = {str(int(k)): bool(v) for k, v in validity.items()
                    if int(k) < part["quarantine_start_ms"]}  # holdout-side validity is sealed metadata
    with open(os.path.join(manifests_dir, "round_validity.json"), "w") as f:
        json.dump(validity_rec, f, sort_keys=True)
    manifest = L.build_manifest(plain, release_version, extra={
        "holdout_artifact": os.path.basename(artifact),
        "holdout_artifact_sha256": seal_meta["artifact_sha256"],
        "exclusion_registry_version": registry["registry_version"],
        "exclusion_registry_sha256": L.sha256_file(REGISTRY_PATH),
        "symbol_classifications": classifications,
    })
    with open(os.path.join(manifests_dir, f"lake_manifest_{release_version}.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return {"partition": part, "manifest_sha256": manifest["manifest_sha256"],
            "artifact_sha256": seal_meta["artifact_sha256"],
            "n_symbols": len(symbols)}


def probe() -> None:
    """S-ING-1: print real headers/latency of ONE old, pre-2023 (guaranteed
    non-holdout) sample so parser assumptions are confirmed before ingestion."""
    k = _get_zip_csv(f"{VISION}/data/futures/um/monthly/klines/BTCUSDT/15m/"
                     f"BTCUSDT-15m-2021-01.zip")
    f = _get_zip_csv(f"{VISION}/data/futures/um/monthly/fundingRate/BTCUSDT/"
                     f"BTCUSDT-fundingRate-2021-01.zip")
    print("kline first line:", k.split(b"\n", 1)[0][:200])
    print("kline parsed rows:", len(parse_kline_csv(k)))
    print("funding first line:", f.split(b"\n", 1)[0][:200])
    print("funding parsed rows:", len(parse_funding_csv(f)))
    syms = list_perp_symbols()
    print("archive symbols (included):", len(syms), "first:", syms[:5],
          "last:", syms[-5:])
    # measured chunking plan (verdict §5.5): time a representative batch and
    # project the full acquisition against the Actions timeout; NEVER
    # publish a partial dataset as complete — if the projection exceeds the
    # budget, ingestion is redesigned, not truncated. Probe run 2 measured
    # 0.68s/symbol-month SEQUENTIAL (~9.3h > 5.8h budget), so acquisition
    # is now concurrent (ACQ_WORKERS); this measures the REAL concurrent
    # throughput on a 2022 (guaranteed non-holdout) batch.
    batch = [f"{VISION}/data/futures/um/monthly/klines/BTCUSDT/15m/"
             f"BTCUSDT-15m-2022-{m:02d}.zip" for m in range(1, 13)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=ACQ_WORKERS) as pool:
        for fut in [pool.submit(_get_zip_csv, u) for u in batch]:
            fut.result()
    per_month_eff = (time.time() - t0) / len(batch)
    est_months = len(syms) * 60          # ~5 years average history
    hours = per_month_eff * est_months / 3600
    print(f"timing: {per_month_eff:.3f}s per symbol-month effective with "
          f"{ACQ_WORKERS} workers ({len(batch)}-month measured batch); "
          f"projected ~{hours:.1f}h for {len(syms)} symbols x ~60 months "
          f"(budget: 5.8h job timeout)")
    print("PROJECTION-OK" if hours <= 5.8 else "PROJECTION-EXCEEDS-BUDGET")


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format='{"t":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}')
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--out-dir", default="work")
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--recipient", default="data/manifests/holdout_recipient.txt")
    ap.add_argument("--history-start", default="2020-01-01")
    ap.add_argument("--freeze-utc", default=None)
    ap.add_argument("--release-version", default="raw-v1")
    args = ap.parse_args()
    if args.probe:
        probe()
        return
    result = run_ingestion(args.out_dir, args.manifests_dir, args.recipient,
                           args.history_start, args.freeze_utc,
                           args.release_version)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
