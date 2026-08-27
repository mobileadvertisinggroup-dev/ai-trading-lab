"""Constitutional integrity manifest v2 — directed by the independent
Checkpoint-1 adjudication (D52 constitutional-lineage requirement).

The v1 manifest (integrity_manifest.json, hash c423f782…) is PRESERVED
UNMODIFIED as the historical NOT-APPROVED lock. This tool produces
integrity_manifest_v2.json: the same file census (tests/**,
fixtures/golden/**, governed documents + frozen-constant module) with,
for EVERY path, its v1 hash, v2 hash, and status
(unchanged/modified/added/removed) — and, for every non-unchanged path,
the documented reason keyed to a BUILD_STATE decision. An altered or
added locked file with NO registered reason fails the run: nothing
changes silently.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import time

from lab.tools.lock_integrity import (CONSTITUTIONAL_PROPERTIES, GOVERNED,
                                      sha256_file)

# every deliberate post-lock change to a locked file, keyed by repo path.
# The adjudication's directed corrections are the ONLY authority cited.
CHANGE_REASONS = {
    "tests/test_observation_parity.py":
        "ADDED (D53, blocker 2): mechanical training/inference observation "
        "parity proof for the canonical obs-v2 builder.",
    "tests/test_transactional_rounds.py":
        "ADDED (D53, blocker 3): zero-effect proof that a late arm failure "
        "rolls the whole round back (control-run equivalence) plus "
        "pre-decision failure rollback.",
    "tests/test_regime_rl.py":
        "MODIFIED (D53, blocker 2): TRADE fixture gained the REQUIRED "
        "atr_entry field of the env v2 constructor contract; no expected "
        "outcome changed.",
    "lab/protocol.py":
        "MODIFIED (D58, comment-only): TRADABLE_LOOKBACK pinned as the "
        "permanent interpretation of 'permanent delisting' (two days "
        "without bars) per the adjudication; no constant value changed.",
    "RISK_POLICY.md":
        "MODIFIED (D58, directed wording correction): the D46 'cannot "
        "increase risk' claim RETRACTED; correct claim recorded "
        "(preserves stated limits while preventing an unintended "
        "absorbing pause); governor's mechanical allowed-qty property "
        "restated precisely.",
}

NEW_CONSTITUTIONAL_PROPERTIES = [
    "canonical obs-v2 observation builder: one builder for training AND "
    "inference; bit-identical parity proven mechanically",
    "transactional synchronized rounds: invalid rounds leave end-state "
    "identical to a never-run round (control-run equivalence); only the "
    "coordinator's centralized invalid-round record survives",
]


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    v1_path = os.path.join(root, "data", "manifests",
                           "integrity_manifest.json")
    with open(v1_path) as f:
        v1 = json.load(f)
    v1_hash = v1["integrity_manifest_hash"]
    v1_by_path = {e["path"]: e["sha256"] for e in v1["files"]}

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED])
    now = {os.path.relpath(p, root): sha256_file(p)
           for p in files if os.path.isfile(p)}

    entries, undocumented = [], []
    for path in sorted(set(now) | set(v1_by_path)):
        old, new = v1_by_path.get(path), now.get(path)
        if old == new:
            status = "unchanged"
        elif old is None:
            status = "added"
        elif new is None:
            status = "removed"
        else:
            status = "modified"
        e = {"path": path, "sha256_v1": old, "sha256_v2": new,
             "status": status}
        if status != "unchanged":
            reason = CHANGE_REASONS.get(path)
            if reason is None:
                undocumented.append((status, path))
            e["reason"] = reason
        entries.append(e)
    if undocumented:
        raise SystemExit("UNDOCUMENTED locked-file changes — refusing to "
                         f"produce manifest v2: {undocumented}")

    manifest = {
        "version": 2,
        "predecessor": {
            "path": "data/manifests/integrity_manifest.json",
            "integrity_manifest_hash": v1_hash,
            "status": ("HISTORICAL — Checkpoint 1 NOT APPROVED by the "
                       "independent adjudication (D52); preserved "
                       "unmodified")},
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": CONSTITUTIONAL_PROPERTIES
        + NEW_CONSTITUTIONAL_PROPERTIES,
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
                       "integrity_manifest_v2.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash_v1_notapproved"] = v1_hash
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1, sort_keys=True)
        f.write("\n")
    counts = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"LOCK v2: {counts}; v1={v1_hash}")
    print(f"integrity_manifest_hash_v2={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
