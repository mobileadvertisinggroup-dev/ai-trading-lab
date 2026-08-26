"""Step 11: finalize and hash the constitutional (integrity) test suite.

The lock is a MANIFEST: the sha256 of every test file, golden fixture,
governing document, and frozen-constant module, plus the enumerated
constitutional properties, hashed into a single integrity-manifest hash
recorded in build_state.json and data/manifests/integrity_manifest.json.
After the lock, ANY change to a locked file is a material change under
spec §16 (documented amendment + review; never silent).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import time

GOVERNED = [
    "EXPERIMENT_PROTOCOL.md", "SIMULATOR_SEMANTICS.md", "RISK_POLICY.md",
    "DATA_DICTIONARY.md", "HOLDOUT_POLICY.md", "INTEGRITY_TEST_POLICY.md",
    "SPEC_FINAL-1.2.1.md", "lab/protocol.py",
]

CONSTITUTIONAL_PROPERTIES = [
    "exact-equality differential gate vs the Independent Reference Ledger "
    "(first-divergence adjudication; 1e-9 diagnostic only)",
    "golden fixtures G01-G12 (layer-1 Decimal-quantize exact + 1e-8 bound)",
    "property-based accounting invariants incl. randomized differential "
    "fuzzing",
    "holdout refusal at the read layer for exact/partial/point/funding/"
    "universe queries (GuardedLake)",
    "authorization strictness: fabricated or merely nonempty hashes never "
    "grant access (read layer AND unseal gate)",
    "one-time holdout gate: manifest-bound artifact, atomic single opening, "
    "tmpfs-only, FAILED_CLOSED on every post-claim failure, permanent "
    "second-opening block, corrupt chain fails closed",
    "deliberate-leak battery: label-in-features, off-dictionary column, "
    "purge violation, post-t feature, holdout contamination all fail loudly",
    "no-lookahead feature proof: mutating every post-t bar leaves all 28 "
    "features bit-identical",
    "G-shadow identity through entry",
    "synchronized-round invalidation: any arm failure voids the round for "
    "every arm",
    "risk-governor pauses/limits incl. trailing-window drawdown release",
    "forced_delist_close conformance with bounded deferral logging",
]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args()
    root = args.repo_root

    files = sorted(
        glob.glob(os.path.join(root, "tests", "**", "*.py"), recursive=True)
        + glob.glob(os.path.join(root, "fixtures", "golden", "**", "*"),
                    recursive=True)
        + [os.path.join(root, g) for g in GOVERNED])
    entries = [{"path": os.path.relpath(p, root), "sha256": sha256_file(p)}
               for p in files if os.path.isfile(p)]
    manifest = {
        "locked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "constitutional_properties": CONSTITUTIONAL_PROPERTIES,
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

    out = os.path.join(root, "data", "manifests", "integrity_manifest.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)

    bs_path = os.path.join(root, "build_state.json")
    with open(bs_path) as f:
        bs = json.load(f)
    bs["integrity_manifest_hash"] = mhash
    with open(bs_path, "w") as f:
        json.dump(bs, f, indent=1)
        f.write("\n")
    print(f"LOCKED: {len(entries)} files; integrity_manifest_hash={mhash}")


if __name__ == "__main__":  # pragma: no cover
    main()
