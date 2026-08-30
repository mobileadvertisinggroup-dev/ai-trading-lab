"""Constitutional integrity manifest v7 (D78 blocker 1).

Explicit v1 → … → v6 → v7 lineage; every predecessor preserved
byte-unmodified; the APPROVED scientific root V6 is untouched. v7
exists because the successful V6 dress rehearsal executed a
holdout_evaluator.py carrying the D76 flat-funding-layout correction,
which post-dates the v6 lock: an authorization must never be bound to
a manifest that does not describe the evaluator actually executing
the holdout. v7 therefore EXTENDS the census with the one-time gate
and frozen-evaluator sources themselves, and reason-keys exactly the
post-v6 changes. Undocumented locked-file changes refuse, as always.
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
from lab.tools.lock_integrity_v6 import PROPERTIES_V6

# D78: the gate/evaluator sources the Checkpoint-2 opening actually
# executes join the locked census — future changes to any of them
# refuse without a decision-keyed reason.
GATE_SOURCES_V7 = [
    "lab/tools/holdout_evaluator.py",
    "lab/data/unseal.py",
    "lab/data/authz.py",
    "lab/data/frozen_inputs.py",
    "lab/data/preflight.py",
    "lab/data/holdout_ledger.py",
    "lab/data/access.py",
]

_GATE_ADD_REASON = (
    "ADDED TO CENSUS (D78 blocker 1): the constitutional manifest must "
    "describe the evaluator/gate actually executing the holdout; from "
    "v7 the one-time gate and frozen-evaluator sources are locked and "
    "any future change refuses without a decision-keyed reason.")

CHANGE_REASONS_V7 = {
    "tests/test_holdout_evaluator_units.py":
        "MODIFIED (D76 defect fix, post-v6 lock; pre-recorded in "
        "POST_CHECKPOINT2_LINEAGE_PROPOSAL.md at change time): the "
        "fixture's synthetic funding layout corrected to the REAL flat "
        "seal layout (funding/SYMBOL.parquet) and a regression added "
        "proving the overlay reader finds flat funding files. The "
        "nested-only fixture had masked the frozen-evaluator defect "
        "that the V6 dress rehearsal's funding activity guard caught "
        "by FAILING CLOSED in its isolated environment.",
    "lab/tools/holdout_evaluator.py":
        _GATE_ADD_REASON + " Carries the D76 flat-layout overlay-"
        "reader correction: _read_overlay reads both the nested kline "
        "layout (klines15m/SYM/YYYY-MM.parquet) and the FLAT funding "
        "layout (funding/SYM.parquet) the seal preserves — without it, "
        "every overlay funding file was silently invisible and the "
        "activity guard failed the rehearsal closed.",
    "lab/data/unseal.py": _GATE_ADD_REASON,
    "lab/data/authz.py": _GATE_ADD_REASON,
    "lab/data/frozen_inputs.py": _GATE_ADD_REASON,
    "lab/data/preflight.py": _GATE_ADD_REASON,
    "lab/data/holdout_ledger.py": _GATE_ADD_REASON,
    "lab/data/access.py": _GATE_ADD_REASON,
}

PROPERTIES_V7 = PROPERTIES_V6 + [
    "the locked census includes the one-time gate and frozen-evaluator "
    "sources actually executing the holdout (holdout_evaluator, unseal, "
    "authz, frozen_inputs, preflight, holdout_ledger, access)",
    "the overlay reader handles the seal's exact lake-relative layouts "
    "— nested klines and FLAT funding — pinned by regression; a "
    "layout miss cannot be silent (the funding activity guard fails "
    "closed on all-zero funding)",
]


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    v6_path = os.path.join(root, "data", "manifests",
                           "integrity_manifest_v6.json")
    with open(v6_path) as f:
        v6 = json.load(f)
    v6_hash = v6["integrity_manifest_hash"]
    v6_by_path = {e["path"]: e["sha256_v6"] for e in v6["files"]
                  if e.get("sha256_v6") is not None}

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED_V3]
        + [os.path.join(root, g) for g in GATE_SOURCES_V7])
    now = {os.path.relpath(p, root): sha256_file(p)
           for p in files if os.path.isfile(p)}

    entries, undocumented = [], []
    for path in sorted(set(now) | set(v6_by_path)):
        old, new = v6_by_path.get(path), now.get(path)
        status = ("unchanged" if old == new else
                  "added" if old is None else
                  "removed" if new is None else "modified")
        e = {"path": path, "sha256_v6": old, "sha256_v7": new,
             "status": status}
        if status != "unchanged":
            reason = CHANGE_REASONS_V7.get(path)
            if reason is None:
                undocumented.append((status, path))
            e["reason"] = reason
        entries.append(e)
    if undocumented:
        raise SystemExit("UNDOCUMENTED locked-file changes — refusing "
                         f"manifest v7: {undocumented}")

    manifest = {
        "version": 7,
        "predecessors": v6["predecessors"] + [
            {"path": "data/manifests/integrity_manifest_v6.json",
             "integrity_manifest_hash": v6_hash,
             "status": "HISTORICAL — replacement Checkpoint 1 V6 "
                       "APPROVED (D76); the approved scientific root V6 "
                       "is preserved UNCHANGED; v7 is a holdout-loader/"
                       "readiness lineage correction only (D78), not a "
                       "scientific replacement"}],
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": PROPERTIES_V7,
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
                       "integrity_manifest_v7.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash_v6_approved_science"] = v6_hash
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1, sort_keys=True)
        f.write("\n")
    counts: dict = {}
    for e in entries:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"LOCK v7: {counts}; v6={v6_hash}")
    print(f"integrity_manifest_hash_v7={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
