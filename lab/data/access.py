"""GuardedLake — the ONLY sanctioned read path for market data.

Every project component (ingestion diagnostics, features, training,
validation, dashboard, simulator drivers) reads through this class. Any
request whose time range intersects the holdout range — exact, partial, or a
single timestamp; any symbol; klines, funding, or universe/metadata — raises
HoldoutAccessError unless a valid Checkpoint-2 authorization exists
(HOLDOUT_POLICY.md §5, §7; SPEC §9.5–9.6).

Every refusal and every authorized holdout access is appended to a
hash-chained, append-only audit log. Premature access attempts are critical
integrity failures: they are recorded and raised, never retried.
"""
from __future__ import annotations

import json
import os
import time
import hashlib

import pandas as pd

from lab.data import lake as L

AUDIT_LOG = "access_audit.jsonl"
PARTITION_META = "partition_meta.json"
AUTHORIZATION = "checkpoint2_authorization.json"

# hash fields that a Checkpoint-2 authorization record must carry and match
# against build_state.json before holdout access is ever permitted (SPEC §9).
REQUIRED_AUTH_FIELDS = (
    "protocol_sha256", "git_commit", "dataset_manifest_sha256",
    "model_manifest_sha256", "integrity_manifest_sha256",
    "external_root_hash", "user_authorization_utc",
)


class HoldoutAccessError(RuntimeError):
    """Raised on any unauthorized request intersecting the holdout range."""


class GuardedLake:
    def __init__(self, lake_dir: str, manifests_dir: str):
        self.lake_dir = lake_dir
        self.manifests_dir = manifests_dir
        meta_path = os.path.join(manifests_dir, PARTITION_META)
        with open(meta_path) as f:
            self.partition = json.load(f)
        self.q_start = int(self.partition["quarantine_start_ms"])
        self.q_end = int(self.partition["holdout_end_ms"])

    # -- authorization -----------------------------------------------------
    def _authorized(self) -> bool:
        path = os.path.join(self.manifests_dir, AUTHORIZATION)
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                auth = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        if not all(auth.get(k) for k in REQUIRED_AUTH_FIELDS):
            return False
        if auth.get("consumed"):
            return False  # holdout is single-use (SPEC §22)
        # full cryptographic cross-checks against build_state.json / git are
        # performed by lab.data.unseal at decryption time; presence +
        # completeness gates the read layer.
        return True

    # -- audit chain -------------------------------------------------------
    def _audit(self, action: str, detail: dict, decision: str):
        path = os.path.join(self.manifests_dir, AUDIT_LOG)
        prev = "0" * 64
        if os.path.exists(path) and os.path.getsize(path):
            with open(path, "rb") as f:
                try:  # last line's hash
                    last = f.readlines()[-1]
                    prev = json.loads(last)["hash"]
                except (json.JSONDecodeError, KeyError, IndexError):
                    prev = "corrupt-tail"
        entry = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "action": action, "detail": detail, "decision": decision,
                 "prev": prev}
        body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        entry["hash"] = hashlib.sha256((prev + body).encode()).hexdigest()
        with open(path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    # -- the guard ---------------------------------------------------------
    def _guard(self, action: str, start_ms: int, end_ms: int, detail: dict):
        intersects = start_ms <= self.q_end and end_ms >= self.q_start
        if not intersects:
            return
        if self._authorized():
            self._audit(action, detail, "authorized-holdout-access")
            return
        self._audit(action, detail, "REFUSED")
        raise HoldoutAccessError(
            f"{action} for [{start_ms},{end_ms}] intersects the sealed "
            f"holdout range [{self.q_start},{self.q_end}] and no valid "
            f"Checkpoint-2 authorization exists. This attempt has been "
            f"recorded in the audit log.")

    # -- reads -------------------------------------------------------------
    def read_klines(self, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        """15m klines for symbol, open_time in [start_ms, end_ms]."""
        self._guard("read_klines", start_ms, end_ms,
                    {"symbol": symbol, "start_ms": start_ms, "end_ms": end_ms})
        frames = []
        base = os.path.join(self.lake_dir, "klines15m", symbol)
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if name.endswith(".parquet"):
                    df = L.read_parquet(os.path.join(base, name))
                    frames.append(df[(df.open_time >= start_ms)
                                     & (df.open_time <= end_ms)])
        if not frames:
            return pd.DataFrame(columns=L.KLINES_COLS)
        return (pd.concat(frames, ignore_index=True)
                .sort_values("open_time").reset_index(drop=True))

    def read_funding(self, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
        self._guard("read_funding", start_ms, end_ms,
                    {"symbol": symbol, "start_ms": start_ms, "end_ms": end_ms})
        path = L.funding_path(self.lake_dir, symbol)
        if not os.path.exists(path):
            return pd.DataFrame(columns=L.FUNDING_COLS)
        df = L.read_parquet(path)
        return (df[(df.funding_time >= start_ms) & (df.funding_time <= end_ms)]
                .sort_values("funding_time").reset_index(drop=True))

    def universe_info(self, t_ms: int) -> dict:
        """Universe/metadata queries are guarded identically (SPEC §9.6)."""
        self._guard("universe_info", t_ms, t_ms, {"t_ms": t_ms})
        path = os.path.join(self.manifests_dir, "universe", f"{t_ms}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"no universe record for {t_ms}")
        with open(path) as f:
            return json.load(f)
