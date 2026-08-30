"""Constitutional integrity manifest v5 (D72 closure).

Explicit v1 → v2 → v3 → v4 → v5 lineage; every predecessor preserved
byte-unmodified. v4 remains the APPROVED-then-SUPERSEDED-for-CP2-
eligibility historical record (D66 approval, D72 adjudication). Census
identical to v4's (tests/**, fixtures/golden/**, governed docs);
every changed/added locked file must carry a decision-keyed reason or
the lock REFUSES. Adds the D72 funding constitutional properties and
the D69 gate properties.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import time

from lab.tools.lock_integrity import sha256_file
from lab.tools.lock_integrity_v3 import GOVERNED_V3
from lab.tools.lock_integrity_v4 import PROPERTIES_V4

CHANGE_REASONS_V5 = {
    "tests/test_checkpoint2_readiness.py":
        "ADDED (D67, post-v4-approval readiness) then MODIFIED (D69 "
        "blocker 2): frozen-statistics correctness and gate-refusal "
        "tests; gate calls updated for the required model_dir/sb3_dir "
        "parameters. Openly recorded in FAILCLOSED_VERIFICATION.md, "
        "D67/D69, and the readiness lineage proposal at creation time.",
    "tests/test_holdout_gate.py":
        "MODIFIED (D69 blockers 2+5): valid-environment fixture carries "
        "the frozen-input manifest, staged model/sb3 dirs, and the "
        "frozen recipient; identity failure proven to refuse BEFORE the "
        "claim; wrong-but-valid key proven refused against the frozen "
        "recipient.",
    "tests/test_authz_negative.py":
        "MODIFIED (D69 blocker 2): gate calls updated for the new "
        "required parameters; fabricated authorizations now also fail "
        "the frozen-inputs requirement.",
    "tests/test_gate_fault_injection.py":
        "ADDED (D69 blocker 5): fault-injection battery at identity "
        "validation, decryption, extraction, evaluator, serialization, "
        "cleanup, publication, and ledger-append; pre-claim faults "
        "proven unspent, post-claim faults FAILED_CLOSED with no "
        "success representation.",
    "tests/test_holdout_evaluator_units.py":
        "ADDED (D69 blockers 1+3) then MODIFIED (D72 A.4): synthetic "
        "union-loader tests + hand-computed tests for every "
        "pre-registered quantity; the funding_net unit test corrected "
        "from the nonexistent 'amount' field to the engine's real "
        "'paid' field together with the collector it tests.",
    "tests/test_funding_constitutional.py":
        "ADDED (D72 blocker A.6): the ten-item constitutional funding "
        "battery — long/short x positive/negative rates with exact "
        "equity identities, reduction-aware charging, close-before vs "
        "hold-through boundaries, exact ArmARunner event-stream "
        "equality, synchronized rollback of funding mutations, both G "
        "diagnostics' independent funding, reporting-field "
        "reconciliation, the loud missing-funding rule, and the "
        "all-zero-funding activity guard.",
}

PROPERTIES_V5 = PROPERTIES_V4 + [
    "funding is applied in EVERY engine of the seven-arm orchestrator "
    "and both G diagnostics with exact ArmARunner/engine semantics "
    "(transfer = rate x open_qty x mark x side at 8h boundaries), and "
    "in the RL trade-management environment per the policy's actual "
    "holding and reductions",
    "missing funding is LOUD (funding_missing events, never imputed); "
    "the activity guard stops any mechanically implausible all-zero "
    "funding over an active multi-month window",
    "funding reporting reconciles exactly: event transfers == "
    "per-position funding_paid == the equity impact",
    "one-time gate: every frozen input hash-verified against the single "
    "authorized frozen-input manifest BEFORE the atomic claim; identity "
    "verified against the frozen recipient pre-claim; bounded-chunk "
    "wipe; results published atomically only after verified cleanup; "
    "no success representation on cleanup/publication/ledger failure",
]


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    v4_path = os.path.join(root, "data", "manifests",
                           "integrity_manifest_v4.json")
    with open(v4_path) as f:
        v4 = json.load(f)
    v4_hash = v4["integrity_manifest_hash"]
    v4_by_path = {e["path"]: e["sha256_v4"] for e in v4["files"]
                  if e.get("sha256_v4") is not None}

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED_V3])
    now = {os.path.relpath(p, root): sha256_file(p)
           for p in files if os.path.isfile(p)}

    entries, undocumented = [], []
    for path in sorted(set(now) | set(v4_by_path)):
        old, new = v4_by_path.get(path), now.get(path)
        status = ("unchanged" if old == new else
                  "added" if old is None else
                  "removed" if new is None else "modified")
        e = {"path": path, "sha256_v4": old, "sha256_v5": new,
             "status": status}
        if status != "unchanged":
            reason = CHANGE_REASONS_V5.get(path)
            if reason is None:
                undocumented.append((status, path))
            e["reason"] = reason
        entries.append(e)
    if undocumented:
        raise SystemExit("UNDOCUMENTED locked-file changes — refusing "
                         f"manifest v5: {undocumented}")

    manifest = {
        "version": 5,
        "predecessors": v4["predecessors"] + [
            {"path": "data/manifests/integrity_manifest_v4.json",
             "integrity_manifest_hash": v4_hash,
             "status": "HISTORICAL — Checkpoint 1 v4 APPROVED (D66), "
                       "then SUPERSEDED FOR CHECKPOINT-2 ELIGIBILITY by "
                       "the adjudicated funding defect (D72); preserved "
                       "unmodified"}],
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": PROPERTIES_V5,
        "files": entries,
        "material_change_rule": (
            "spec §16: any post-lock change to a listed file requires a "
            "documented amendment, review, and retraining assessment; "
            "never silent."),
    }
    body = json.dumps(manifest, sort_keys=True,
                      separators=(",", ":")).encode()
    mhash = hashlib.sha256(body).hexdigest()
    manifest["integrity_manifest_hash"] = mhash

    out = os.path.join(root, "data", "manifests",
                       "integrity_manifest_v5.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash_v4_superseded_for_cp2"] = v4_hash
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1, sort_keys=True)
        f.write("\n")
    counts: dict = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"LOCK v5: {counts}; v4={v4_hash}")
    print(f"integrity_manifest_hash_v5={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
