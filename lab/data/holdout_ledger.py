"""Holdout state ledger — append-only, hash-chained (delta review corr. B).

Consumption of the one-time holdout evaluation is established HERE, by
chained events, never by rewriting a mutable JSON file. Events:

  OPENING_STARTED   — the controlled evaluation began (gate passed)
  CONSUMED          — evaluation completed; holdout permanently consumed
  FAILED_CLOSED     — evaluation failed; decrypted material wiped; the
                      holdout remains closed and a second opening is
                      refused pending formal adjudication
  RECOVERY_AUTHORIZED — recorded ONLY through a formal integrity
                      adjudication (never by this code path on its own);
                      permits exactly one further opening attempt

A corrupted chain (broken hash link, malformed row) BLOCKS all holdout
access — fail closed, never open.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

LEDGER = "holdout_state.jsonl"


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


def append_event(manifests_dir: str, event: str, detail: dict) -> dict:
    events = read_events(manifests_dir)          # verifies chain first
    prev = events[-1]["hash"] if events else "0" * 64
    body = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event, "detail": detail, "prev": prev}
    body["hash"] = _chain_hash(prev, {k: body[k] for k in body if k != "hash"})
    with open(os.path.join(manifests_dir, LEDGER), "a") as f:
        f.write(json.dumps(body, sort_keys=True) + "\n")
    return body


def opening_permitted(manifests_dir: str) -> tuple[bool, str]:
    """(permitted, reason). Fail closed on corruption. A prior
    OPENING_STARTED/CONSUMED/FAILED_CLOSED refuses unless a LATER
    RECOVERY_AUTHORIZED event (formal adjudication) permits one retry
    that has not itself been used."""
    try:
        events = read_events(manifests_dir)
    except LedgerCorrupt as e:
        return False, f"state ledger corrupt — access blocked: {e}"
    openings = 0
    recoveries = 0
    for e in events:
        if e["event"] == "CONSUMED":
            return False, "holdout permanently consumed (single-use)"
        if e["event"] in ("OPENING_STARTED", "FAILED_CLOSED"):
            if e["event"] == "OPENING_STARTED":
                openings += 1
        elif e["event"] == "RECOVERY_AUTHORIZED":
            recoveries += 1
    if openings == 0:
        return True, "no prior opening"
    if recoveries >= openings:
        return True, "recovery formally authorized"
    return False, ("a prior opening exists; a second opening requires a "
                   "formal integrity adjudication (RECOVERY_AUTHORIZED)")
