"""Frozen-input verification for the one-time holdout evaluation
(D69 blocker 2).

ONE exact frozen-input manifest (data/manifests/
checkpoint2_frozen_inputs.json) pins every file the gate + evaluator
consume: governing documents, dataset/partition manifests, the frozen
recipient, and every model artifact (boosters, cuts, selection records,
the SB3 manifest and seed ZIP). Before the atomic claim the gate:

  - verifies the manifest file's own sha256 against the value carried in
    the authorization record (authz);
  - recomputes and verifies EVERY pinned hash;
  - refuses missing, ADDITIONAL (strict census of the model/sb3 dirs),
    substituted, symlinked, or path-escaping inputs — entries are exact
    basenames only, resolved strictly inside their pinned directory.

Any failure refuses BEFORE OPENING_STARTED — the opening is not spent.
"""
from __future__ import annotations

import hashlib
import json
import os

FROZEN_INPUTS = "checkpoint2_frozen_inputs.json"

# manifest sections -> which root the basenames resolve against
SECTIONS = ("repo_files", "manifest_files", "model_dir_files",
            "sb3_dir_files")
STRICT_CENSUS = ("model_dir_files", "sb3_dir_files")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_join(root: str, name: str) -> str | None:
    """Exact-basename resolution: refuse separators, traversal, and
    symlinks (the file, and escape via resolved path)."""
    if os.sep in name or (os.altsep and os.altsep in name) \
            or name in (".", "..") or name.startswith("~"):
        return None
    p = os.path.join(root, name)
    if os.path.islink(p):
        return None
    rp = os.path.realpath(p)
    if not rp.startswith(os.path.realpath(root) + os.sep):
        return None
    return p


def verify_frozen_inputs(manifests_dir: str, repo_root: str,
                         model_dir: str, sb3_dir: str,
                         expected_manifest_sha256: str
                         ) -> tuple[bool, list[str]]:
    failures: list[str] = []
    mpath = os.path.join(manifests_dir, FROZEN_INPUTS)
    if not os.path.isfile(mpath) or os.path.islink(mpath):
        return False, [f"frozen-input manifest missing or symlinked: "
                       f"{FROZEN_INPUTS}"]
    got = _sha256(mpath)
    if got != expected_manifest_sha256:
        return False, ["frozen-input manifest sha256 "
                       f"{got} != authorized {expected_manifest_sha256}"]
    try:
        with open(mpath) as f:
            man = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return False, [f"unreadable frozen-input manifest: {e}"]

    roots = {"repo_files": repo_root, "manifest_files": manifests_dir,
             "model_dir_files": model_dir, "sb3_dir_files": sb3_dir}
    for section in SECTIONS:
        entries = man.get(section)
        if not isinstance(entries, dict) or not entries:
            failures.append(f"manifest section {section} missing/empty")
            continue
        root = roots[section]
        for name, want in sorted(entries.items()):
            p = _safe_join(root, name)
            if p is None:
                failures.append(f"{section}/{name}: unsafe name or "
                                f"symlink/path escape")
                continue
            if not os.path.isfile(p):
                failures.append(f"{section}/{name}: missing")
                continue
            have = _sha256(p)
            if have != want:
                failures.append(f"{section}/{name}: sha256 {have} != "
                                f"frozen {want}")
        if section in STRICT_CENSUS:
            extra = sorted(set(os.listdir(root)) - set(entries))
            extra = [e for e in extra
                     if os.path.isfile(os.path.join(root, e))]
            if extra:
                failures.append(f"{section}: ADDITIONAL unpinned files "
                                f"present: {extra}")
    return not failures, failures
