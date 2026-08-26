"""Holdout state ledger — append-only, hash-chained (delta review corr. B,
hardened per the final narrow review, 2026-08-26).

Consumption of the one-time holdout evaluation is established HERE, by
chained events, never by rewriting a mutable JSON file. Events:

  OPENING_STARTED   — the controlled evaluation began. Created ONLY by the
                      atomic claim_opening() (OS file lock + chain verify +
                      no-prior-opening check + fsync); append_event refuses
                      it.
  CONSUMED          — evaluation completed; holdout permanently consumed.
  FAILED_CLOSED     — evaluation failed; decrypted material wiped; the
                      holdout remains closed.

RECOVERY IS NOT SELF-AUTHORIZING (final narrow review §3): no application
function may create a RECOVERY_AUTHORIZED event, and opening_permitted
does NOT honor one even if the string appears in the ledger. For this
experiment version, ANY prior OPENING_STARTED permanently blocks another
opening, whether the first attempt succeeded or failed. Recovery would
require a future versioned, explicitly user-approved integrity procedure
with preserved hashes and external approval evidence — which does not
exist yet.

A corrupted chain (broken hash link, malformed row) BLOCKS all holdout
access — fail closed, never open.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time

LEDGER = "holdout_state.jsonl"
LOCKFILE = "holdout_state.lock"

# events ordinary appends may create; OPENING_STARTED only via
# claim_opening(); RECOVERY_AUTHORIZED never (no procedure exists)
_APPENDABLE = frozenset({"CONSUMED", "FAILED_CLOSED"})


class LedgerCorrupt(RuntimeError):
    pass


def _chain_hash(prev: str, entry_body: dict) -> str:
    body = json.dumps(entry_body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + body).encode()).hexdigest()


def read_events(manifests_dir: str) -> list[dict]:
    """Read and VERIFY the chain. Raises LedgerCorrupt on any break."""
    path = os.path.join(manifests_dir, LEDGER)
    if not os.path.exists(path):
        return []
    events = []
    prev = "0" * 64
    with open(path) as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerCorrupt(f"row {i}: malformed JSON") from exc
            body = {k: e[k] for k in e if k != "hash"}
            if e.get("prev") != prev:
                raise LedgerCorrupt(f"row {i}: broken chain link")
            if e.get("hash") != _chain_hash(prev, body):
                raise LedgerCorrupt(f"row {i}: hash mismatch")
            events.append(e)
            prev = e["hash"]
    return events


class _LedgerLock:
    """Exclusive OS file lock serializing every ledger mutation."""

    def __init__(self, manifests_dir: str):
        self._path = os.path.join(manifests_dir, LOCKFILE)

    def __enter__(self):
        self._f = open(self._path, "a+")
        fcntl.flock(self._f.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._f.fileno(), fcntl.LOCK_UN)
        self._f.close()


def _append_locked(manifests_dir: str, event: str, detail: dict) -> dict:
    """Append under an already-held lock: verify chain, write, flush, fsync."""
    events = read_events(manifests_dir)          # verifies chain first
    prev = events[-1]["hash"] if events else "0" * 64
    body = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event, "detail": detail, "prev": prev}
    body["hash"] = _chain_hash(prev, {k: body[k] for k in body if k != "hash"})
    with open(os.path.join(manifests_dir, LEDGER), "a") as f:
        f.write(json.dumps(body, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return body


def append_event(manifests_dir: str, event: str, detail: dict) -> dict:
    """Ordinary append: CONSUMED / FAILED_CLOSED only. OPENING_STARTED is
    created solely by the atomic claim_opening(); RECOVERY_AUTHORIZED can
    never be created by application code (final narrow review §3)."""
    if event not in _APPENDABLE:
        raise ValueError(
            f"event {event!r} may not be appended by application code: "
            f"OPENING_STARTED only via claim_opening(); RECOVERY_AUTHORIZED "
            f"requires a future versioned, user-approved integrity "
            f"procedure that does not exist")
    with _LedgerLock(manifests_dir):
        return _append_locked(manifests_dir, event, detail)


class OpeningRefused(RuntimeError):
    pass


def claim_opening(manifests_dir: str, detail: dict) -> dict:
    """ATOMIC single-opening claim (final narrow review §4): under an
    exclusive OS file lock — verify the complete chain, confirm no previous
    opening exists, append OPENING_STARTED with flush+fsync. Exactly one of
    any set of concurrent claimants succeeds."""
    with _LedgerLock(manifests_dir):
        permitted, why = opening_permitted(manifests_dir)   # raises on corrupt
        if not permitted:
            raise OpeningRefused(why)
        return _append_locked(manifests_dir, "OPENING_STARTED", detail)


def opening_permitted(manifests_dir: str) -> tuple[bool, str]:
    """(permitted, reason). Fail closed on corruption. ANY prior
    OPENING_STARTED (or CONSUMED) permanently refuses — a
    RECOVERY_AUTHORIZED string in the ledger is NOT honored (final narrow
    review §3: recovery requires a future versioned, explicitly
    user-approved integrity procedure that does not exist yet)."""
    try:
        events = read_events(manifests_dir)
    except LedgerCorrupt as e:
        return False, f"state ledger corrupt — access blocked: {e}"
    for e in events:
        if e["event"] == "CONSUMED":
            return False, "holdout permanently consumed (single-use)"
        if e["event"] == "OPENING_STARTED":
            return False, ("a prior opening exists — permanently blocked; "
                           "no self-authorized recovery is possible in this "
                           "experiment version")
    return True, "no prior opening"
