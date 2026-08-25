"""Content-hashed raw lake: Parquet files + manifest.

Layout (HOLDOUT_POLICY.md §3 — lake bytes live in GitHub Release assets,
never in Git; only the manifest is committed):

    <lake_dir>/klines15m/<SYMBOL>/<YYYY-MM>.parquet
    <lake_dir>/funding/<SYMBOL>.parquet

Klines schema:  open_time(int64 ms), open, high, low, close,
                volume, quote_volume  (float64)
Funding schema: funding_time(int64 ms), funding_rate(float64)

The lake is read-only after ingestion; every file is pinned by sha256 in the
manifest. Writing happens only through this module during ingestion/sealing.
"""
from __future__ import annotations

import hashlib
import json
import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

KLINES_COLS = ["open_time", "open", "high", "low", "close", "volume", "quote_volume"]
FUNDING_COLS = ["funding_time", "funding_rate"]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_parquet(df: pd.DataFrame, path: str) -> str:
    """Write a canonical, deterministic parquet file; returns sha256."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    table = pa.Table.from_pandas(df.reset_index(drop=True), preserve_index=False)
    # no compression-metadata nondeterminism: fixed codec, fixed row group
    pq.write_table(table, path, compression="zstd", row_group_size=65536,
                   store_schema=True)
    return sha256_file(path)


def read_parquet(path: str) -> pd.DataFrame:
    return pq.read_table(path).to_pandas()


def klines_path(lake_dir: str, symbol: str, month: str) -> str:
    return os.path.join(lake_dir, "klines15m", symbol, f"{month}.parquet")


def funding_path(lake_dir: str, symbol: str) -> str:
    return os.path.join(lake_dir, "funding", f"{symbol}.parquet")


def iter_lake_files(lake_dir: str):
    """Yield (relpath, abspath) of every parquet file in the lake."""
    for root, _dirs, files in os.walk(lake_dir):
        for name in sorted(files):
            if name.endswith(".parquet"):
                ap = os.path.join(root, name)
                yield os.path.relpath(ap, lake_dir), ap


def build_manifest(lake_dir: str, version: str, extra: dict | None = None) -> dict:
    files = []
    for rel, ap in iter_lake_files(lake_dir):
        files.append({"path": rel, "bytes": os.path.getsize(ap),
                      "sha256": sha256_file(ap)})
    manifest = {"version": version, "files": files}
    if extra:
        manifest.update(extra)
    body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest["manifest_sha256"] = sha256_bytes(body)
    return manifest


def verify_manifest(lake_dir: str, manifest: dict) -> list[str]:
    """Return list of problems (empty == verified)."""
    problems = []
    for entry in manifest["files"]:
        ap = os.path.join(lake_dir, entry["path"])
        if not os.path.exists(ap):
            problems.append(f"missing: {entry['path']}")
        elif sha256_file(ap) != entry["sha256"]:
            problems.append(f"hash mismatch: {entry['path']}")
    return problems
