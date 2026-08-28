"""Constitutional integrity manifest v3 (D61 constitutional procedure).

Predecessor = integrity manifest v2 (itself NOT APPROVED history, like
v1); both stay byte-unmodified. Census extends the locked set with the
adjudicated governed amendment SPEC_AMENDMENT_A1_GSHADOW.md. Every
changed/added locked file must carry a decision-keyed reason or the
lock REFUSES. The constitutional property list replaces the superseded
single-shadow identity property with the three adjudicated G-diagnostic
properties.
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
from lab.tools.lock_integrity_v2 import NEW_CONSTITUTIONAL_PROPERTIES

GOVERNED_V3 = GOVERNED + ["SPEC_AMENDMENT_A1_GSHADOW.md"]

CHANGE_REASONS_V3 = {
    "tests/test_competition.py":
        "MODIFIED (D61 blocker A, adjudicated amendment): the single "
        "G-shadow strict-identity test is replaced by the three "
        "constitutional diagnostic properties (exact matched-fill "
        "identity; fully explained feasible divergence; diagnostic "
        "inertness) plus explicit over-cap recording.",
    "tests/test_transactional_rounds.py":
        "MODIFIED (D61 blocker A): the transactional byte-compare now "
        "covers BOTH G diagnostics instead of the single shadow.",
    "tests/test_learnability_v3_invariance.py":
        "ADDED (D61 blocker D): pre-registered mechanical invariance "
        "tests for the v3 rotation permutation and TRUE circular "
        "moving-block bootstrap, committed before the v3 run.",
    "SPEC_AMENDMENT_A1_GSHADOW.md":
        "ADDED (D61 blocker A): adjudicated material-change amendment "
        "to the Arm G Shadow Counterfactual section; the spec file "
        "itself stays byte-unmodified.",
    "DATA_DICTIONARY.md":
        "MODIFIED (D61 blocker A): documents the two G diagnostic "
        "ledgers (matched / feasible) and their fields.",
}

PROPERTIES_V3 = [p for p in (CONSTITUTIONAL_PROPERTIES
                             + NEW_CONSTITUTIONAL_PROPERTIES)
                 if p != "G-shadow identity through entry"] + [
    "G matched-entry diagnostic: exact matched-fill identity with G "
    "actual (timestamp, symbol, side, qty, price, initial protection); "
    "over-cap excursions explicitly recorded",
    "G feasible counterfactual: every divergence from G actual is "
    "recorded and explained (decision stages + governor/engine "
    "rejections); no silent divergence",
    "G diagnostics are inert: with diagnostics on vs absent, G actual "
    "and every arm are byte-identical (superseded strict single-shadow "
    "identity preserved as failed history, SD-GSHADOW)",
]


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    v2_path = os.path.join(root, "data", "manifests",
                           "integrity_manifest_v2.json")
    with open(v2_path) as f:
        v2 = json.load(f)
    v2_hash = v2["integrity_manifest_hash"]
    v2_by_path = {e["path"]: e["sha256_v2"] for e in v2["files"]
                  if e["sha256_v2"] is not None}

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED_V3])
    now = {os.path.relpath(p, root): sha256_file(p)
           for p in files if os.path.isfile(p)}

    entries, undocumented = [], []
    for path in sorted(set(now) | set(v2_by_path)):
        old, new = v2_by_path.get(path), now.get(path)
        status = ("unchanged" if old == new else
                  "added" if old is None else
                  "removed" if new is None else "modified")
        e = {"path": path, "sha256_v2": old, "sha256_v3": new,
             "status": status}
        if status != "unchanged":
            reason = CHANGE_REASONS_V3.get(path)
            if reason is None:
                undocumented.append((status, path))
            e["reason"] = reason
        entries.append(e)
    if undocumented:
        raise SystemExit("UNDOCUMENTED locked-file changes — refusing "
                         f"manifest v3: {undocumented}")

    manifest = {
        "version": 3,
        "predecessors": [
            {"path": "data/manifests/integrity_manifest.json",
             "integrity_manifest_hash": v2["predecessor"]
             ["integrity_manifest_hash"],
             "status": "HISTORICAL — NOT APPROVED (v1)"},
            {"path": "data/manifests/integrity_manifest_v2.json",
             "integrity_manifest_hash": v2_hash,
             "status": "HISTORICAL — replacement Checkpoint 1 NOT "
                       "APPROVED (v2, D61); preserved unmodified"},
        ],
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": PROPERTIES_V3,
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
                       "integrity_manifest_v3.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash_v2_notapproved"] = v2_hash
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1, sort_keys=True)
        f.write("\n")
    counts: dict = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"LOCK v3: {counts}; v2={v2_hash}")
    print(f"integrity_manifest_hash_v3={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
