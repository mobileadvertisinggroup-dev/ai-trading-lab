"""Generate data/manifests/checkpoint2_frozen_inputs.json (D69 blocker 2).

ONE exact manifest pinning every file the one-time gate + frozen
evaluator consume — governing documents (protocol, spec, amendments,
pre-registrations), dataset/partition manifests, the frozen recipient,
and the exact model artifacts (boosters, cuts, selection records, the
SB3 manifest + selected-seed ZIP). Run ONCE from the committed tree;
the resulting file is committed and its sha256 is carried in the
(future) authorization record as `frozen_inputs_manifest_sha256`.
The gate verifies every pinned hash BEFORE the atomic claim
(lab.data.frozen_inputs.verify_frozen_inputs) and refuses missing,
additional, substituted, symlinked, or path-escaping inputs.

This tool creates NO authorization and touches NO holdout material.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

from lab.data.frozen_inputs import FROZEN_INPUTS

REPO_FILES = [
    "EXPERIMENT_PROTOCOL.md",
    "SPEC_FINAL-1.2.1.md",
    "SPEC_AMENDMENT_A1_GSHADOW.md",
    "PREREGISTRATION_CHECKPOINT2_EVALUATION.md",
    "PREREGISTRATION_LEARNABILITY_BLOCKS.md",
]
MANIFEST_FILES = [
    "lake_manifest_raw-v1.json",
    "partition_meta.json",
    "holdout_recipient.txt",
    "model_manifest_v5.json",       # D76: the bound model manifest
]
MODEL_DIR_FILES = [
    "arm_b.txt", "arm_c.txt", "arm_e.txt", "arm_e_cuts.npz",
    "bc_train_selection.json", "arm_e_portfolio_selection.json",
]


def sb3_dir_files(sb3_dir: str) -> list[str]:
    """The SB3 manifest plus the ZIP of ITS OWN selected seed (D76:
    seed 3 after the funding-corrected retraining) — read from the
    manifest, never hard-coded."""
    with open(os.path.join(sb3_dir, "arm_f_sb3_manifest.json")) as f:
        sel = int(json.load(f)["selected_seed"])
    return ["arm_f_sb3_manifest.json", f"arm_f_sb3_seed{sel}.zip"]


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(repo_root: str, model_dir: str, sb3_dir: str) -> dict:
    manifests_dir = os.path.join(repo_root, "data", "manifests")

    def section(root, names):
        out = {}
        for n in names:
            p = os.path.join(root, n)
            if not os.path.isfile(p) or os.path.islink(p):
                raise SystemExit(f"missing or symlinked input: {p}")
            out[n] = _sha256(p)
        return out

    return {
        "purpose": ("D69 blocker 2 — the single frozen-input manifest "
                    "the one-time Checkpoint-2 gate verifies, hash by "
                    "hash, BEFORE the atomic opening claim"),
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
        "repo_files": section(repo_root, REPO_FILES),
        "manifest_files": section(manifests_dir, MANIFEST_FILES),
        "model_dir_files": section(model_dir, MODEL_DIR_FILES),
        "sb3_dir_files": section(sb3_dir, sb3_dir_files(sb3_dir)),
        "notes": ("model_dir_files / sb3_dir_files are enforced with a "
                  "STRICT census: the staged directories must contain "
                  "exactly these files and nothing else."),
    }


def main() -> None:  # pragma: no cover — governance tool
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--sb3-dir", required=True)
    args = ap.parse_args()
    man = build(args.repo_root, args.model_dir, args.sb3_dir)
    out = os.path.join(args.repo_root, "data", "manifests", FROZEN_INPUTS)
    with open(out, "w") as f:
        json.dump(man, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"wrote {out}\nsha256 {_sha256(out)}")


if __name__ == "__main__":  # pragma: no cover
    main()
