"""Constitutional integrity manifest v6 (D74 closure).

Explicit v1 → … → v5 → v6 lineage; every predecessor preserved
byte-unmodified. v5 is NOT-APPROVED history (D74: G_matched entry-bar
funding ordering blocker). Census identical (tests/**,
fixtures/golden/**, governed docs); every changed/added locked file
must carry a decision-keyed reason or the lock REFUSES. Adds the D74
constitutional property (diagnostic-clone entry-bar funding
exemption).
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
from lab.tools.lock_integrity_v5 import PROPERTIES_V5

CHANGE_REASONS_V6 = {
    "tests/test_funding_constitutional.py":
        "MODIFIED (D74): the staggered entry-boundary regression "
        "battery added — another arm holds X across funding boundary "
        "t, G first fills X at t with X in the shared frozen map, and "
        "G actual AND the matched clone must both record zero entry-"
        "bar funding with identical same-bar semantics and normal "
        "later-boundary reconciliation; plus pre-existing clones "
        "funded normally, entry-bar-only scope, multi-symbol mixed "
        "books, rollback restoring the exemption stamp, and "
        "diagnostics-on/off G-actual byte-identity. Proven to FAIL "
        "under the V5 ordering (readiness/D74_REGRESSION_FAIL_UNDER_"
        "V5.txt) and PASS after the position-level fix.",
}

PROPERTIES_V6 = PROPERTIES_V5 + [
    "diagnostic-clone entry-bar funding exemption: a G_matched clone "
    "pays no funding (and emits no funding_missing) on exactly its "
    "entry bar — identical to the mirrored actual position, which "
    "fills after that bar's funding phase — via the position-level "
    "clone_entry_bar_ms stamp set only by clone_open; later boundaries "
    "charge normally; actual arms A-G are untouched (differential "
    "gate + diagnostics-on/off byte-identity)",
]


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    v5_path = os.path.join(root, "data", "manifests",
                           "integrity_manifest_v5.json")
    with open(v5_path) as f:
        v5 = json.load(f)
    v5_hash = v5["integrity_manifest_hash"]
    v5_by_path = {e["path"]: e["sha256_v5"] for e in v5["files"]
                  if e.get("sha256_v5") is not None}

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED_V3])
    now = {os.path.relpath(p, root): sha256_file(p)
           for p in files if os.path.isfile(p)}

    entries, undocumented = [], []
    for path in sorted(set(now) | set(v5_by_path)):
        old, new = v5_by_path.get(path), now.get(path)
        status = ("unchanged" if old == new else
                  "added" if old is None else
                  "removed" if new is None else "modified")
        e = {"path": path, "sha256_v5": old, "sha256_v6": new,
             "status": status}
        if status != "unchanged":
            reason = CHANGE_REASONS_V6.get(path)
            if reason is None:
                undocumented.append((status, path))
            e["reason"] = reason
        entries.append(e)
    if undocumented:
        raise SystemExit("UNDOCUMENTED locked-file changes — refusing "
                         f"manifest v6: {undocumented}")

    manifest = {
        "version": 6,
        "predecessors": v5["predecessors"] + [
            {"path": "data/manifests/integrity_manifest_v5.json",
             "integrity_manifest_hash": v5_hash,
             "status": "HISTORICAL — replacement Checkpoint 1 v5 NOT "
                       "APPROVED (D74: G_matched entry-bar funding "
                       "ordering blocker); preserved unmodified"}],
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": PROPERTIES_V6,
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
                       "integrity_manifest_v6.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash_v5_notapproved"] = v5_hash
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1, sort_keys=True)
        f.write("\n")
    counts: dict = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"LOCK v6: {counts}; v5={v5_hash}")
    print(f"integrity_manifest_hash_v6={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
