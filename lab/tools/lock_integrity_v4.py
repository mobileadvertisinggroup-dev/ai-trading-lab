"""Constitutional integrity manifest v4 (D63 closure).

Explicit v1 → v2 → v3 → v4 lineage; every predecessor preserved
byte-unmodified as NOT-APPROVED history. Census identical to v3's
(tests/**, fixtures/golden/**, governed docs + SPEC amendment); every
changed/added locked file must carry a decision-keyed reason or the
lock REFUSES. Adds the D63 constitutional properties (entry-bar
same-bar cloning semantics; exact-conventional-baseline parity).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import time

from lab.tools.lock_integrity import sha256_file
from lab.tools.lock_integrity_v3 import GOVERNED_V3, PROPERTIES_V3

CHANGE_REASONS_V4 = {
    "tests/test_competition.py":
        "MODIFIED (D63 blocker 3): constitutional tests added — same-bar "
        "STOP after entry and same-bar TARGET after entry clone "
        "identically (both proven to FAIL under the previous cloning "
        "order), plus RL tighten/reduce non-propagation to the matched "
        "clone.",
    "tests/test_arm_f_baseline_parity.py":
        "ADDED (D63 blocker 2): parity proof that the in-episode "
        "ConventionalManager reproduces official ArmARunner outcomes "
        "bit-for-bit for trailing-exit, time-exit, stop-hit, and "
        "target-hit trades.",
}

PROPERTIES_V4 = PROPERTIES_V3 + [
    "G_matched entry-bar semantics: a clone created on the entry bar "
    "experiences the identical same-bar stop/target sweep, mark, and "
    "MFE/MAE updates as G actual (exact engine semantics)",
    "Arm F comparisons use the EXACT frozen Arm A conventional manager "
    "as baseline (trailing then time exit, ArmARunner order), "
    "parity-proven against official outcomes",
]


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    v3_path = os.path.join(root, "data", "manifests",
                           "integrity_manifest_v3.json")
    with open(v3_path) as f:
        v3 = json.load(f)
    v3_hash = v3["integrity_manifest_hash"]
    v3_by_path = {e["path"]: e["sha256_v3"] for e in v3["files"]
                  if e.get("sha256_v3") is not None}

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED_V3])
    now = {os.path.relpath(p, root): sha256_file(p)
           for p in files if os.path.isfile(p)}

    entries, undocumented = [], []
    for path in sorted(set(now) | set(v3_by_path)):
        old, new = v3_by_path.get(path), now.get(path)
        status = ("unchanged" if old == new else
                  "added" if old is None else
                  "removed" if new is None else "modified")
        e = {"path": path, "sha256_v3": old, "sha256_v4": new,
             "status": status}
        if status != "unchanged":
            reason = CHANGE_REASONS_V4.get(path)
            if reason is None:
                undocumented.append((status, path))
            e["reason"] = reason
        entries.append(e)
    if undocumented:
        raise SystemExit("UNDOCUMENTED locked-file changes — refusing "
                         f"manifest v4: {undocumented}")

    manifest = {
        "version": 4,
        "predecessors": v3["predecessors"] + [
            {"path": "data/manifests/integrity_manifest_v3.json",
             "integrity_manifest_hash": v3_hash,
             "status": "HISTORICAL — replacement Checkpoint 1 v3 NOT "
                       "APPROVED (D63); preserved unmodified"}],
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": PROPERTIES_V4,
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
                       "integrity_manifest_v4.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash_v3_notapproved"] = v3_hash
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1, sort_keys=True)
        f.write("\n")
    counts: dict = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"LOCK v4: {counts}; v3={v3_hash}")
    print(f"integrity_manifest_hash_v4={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
