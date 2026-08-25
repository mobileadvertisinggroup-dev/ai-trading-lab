"""Holdout sealing utility — mechanical pass-through, no display.

Implements HOLDOUT_POLICY.md §4 / SPEC §9. Splits every lake file at the
quarantine boundary: rows strictly before Q stay in the plaintext lake;
rows at/after Q stream into a tar that is immediately age-encrypted to the
user's public key. Holdout VALUES are never printed, logged, summarized, or
written to a durable plaintext location; this module logs metadata only
(file names, row counts, hashes).

The transient staging tar lives in a mode-0700 private temp directory and is
shredded (overwritten + deleted) in a finally block. Decrypted holdout data
is never produced here at all — sealing is encrypt-only.
"""
from __future__ import annotations

import io
import json
import logging
import os
import tarfile
import tempfile

import pandas as pd

import pyrage

from lab.data import lake as L

log = logging.getLogger("lab.seal")

TIME_COLUMN = {"klines15m": "open_time", "funding": "funding_time"}


def _time_column_for(relpath: str) -> str:
    top = relpath.split(os.sep, 1)[0]
    try:
        return TIME_COLUMN[top]
    except KeyError:
        raise ValueError(f"unknown lake layer for {relpath!r}") from None


def _df_to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pandas(df.reset_index(drop=True),
                                        preserve_index=False),
                   buf, compression="zstd", row_group_size=65536)
    return buf.getvalue()


def seal_lake(staging_dir: str, plaintext_lake_dir: str,
              quarantine_start_ms: int, recipient_pubkey: str,
              artifact_out_path: str) -> dict:
    """Split staged raw data at Q and seal the holdout side.

    staging_dir: temp lake produced by ingestion (full range, runner-local).
    plaintext_lake_dir: destination for pre-Q rows (the publishable lake).
    Returns non-outcome seal metadata (names / row counts / hashes only).
    """
    recipient = pyrage.x25519.Recipient.from_str(recipient_pubkey.strip())
    sealed_files: list[dict] = []
    kept_files: list[str] = []

    tmpdir = tempfile.mkdtemp(prefix="seal-", dir=os.path.dirname(artifact_out_path) or ".")
    os.chmod(tmpdir, 0o700)
    tar_path = os.path.join(tmpdir, "holdout.tar")
    try:
        with tarfile.open(tar_path, "w") as tar:
            for rel, ap in L.iter_lake_files(staging_dir):
                tcol = _time_column_for(rel)
                df = L.read_parquet(ap)
                before = df[df[tcol] < quarantine_start_ms]
                after = df[df[tcol] >= quarantine_start_ms]
                if len(before):
                    L.write_parquet(before, os.path.join(plaintext_lake_dir, rel))
                    kept_files.append(rel)
                if len(after):
                    blob = _df_to_parquet_bytes(after)
                    info = tarfile.TarInfo(name=rel)
                    info.size = len(blob)
                    info.mtime = 0  # deterministic
                    tar.addfile(info, io.BytesIO(blob))
                    sealed_files.append({"path": rel, "rows": int(len(after)),
                                         "sha256": L.sha256_bytes(blob)})
                    # metadata-only logging — never values (HOLDOUT_POLICY §6.2)
                    log.info("sealed %s rows=%d", rel, len(after))
                del df, before, after

        with open(tar_path, "rb") as f:
            tar_bytes = f.read()
        encrypted = pyrage.encrypt(tar_bytes, [recipient])
        with open(artifact_out_path, "wb") as f:
            f.write(encrypted)
        artifact_sha = L.sha256_file(artifact_out_path)
    finally:
        # shred transient plaintext tar
        if os.path.exists(tar_path):
            size = os.path.getsize(tar_path)
            with open(tar_path, "r+b") as f:
                f.write(b"\0" * size)
            os.remove(tar_path)
        os.rmdir(tmpdir)

    meta = {
        "quarantine_start_ms": int(quarantine_start_ms),
        "recipient": recipient_pubkey.strip(),
        "artifact": os.path.basename(artifact_out_path),
        "artifact_sha256": artifact_sha,
        "sealed_files": sealed_files,
        "n_sealed_files": len(sealed_files),
        "n_plaintext_files": len(kept_files),
    }
    log.info("seal complete: %d files sealed, artifact sha256=%s",
             len(sealed_files), artifact_sha)
    return meta


def write_seal_metadata(meta: dict, manifests_dir: str) -> str:
    os.makedirs(manifests_dir, exist_ok=True)
    path = os.path.join(manifests_dir, "holdout_seal.json")
    with open(path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    return path
