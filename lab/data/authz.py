"""Checkpoint-2 authorization verification — SPEC §9 / review verdict §7.

The ONLY code that decides whether holdout access is authorized. Used by
both the read layer (GuardedLake) and the sanctioned unseal command. Every
required hash is verified against the CURRENT, independently recomputed
value — an authorization file containing merely nonempty or fabricated
hashes can never grant access (constitutional negative test).

Verified, all required to match EXACTLY:
  protocol_sha256            == sha256(EXPERIMENT_PROTOCOL.md) now
  git_commit                 == `git rev-parse HEAD` now
  dataset_manifest_sha256    == sha256 of the named dataset manifest file
  model_manifest_sha256      == sha256 of the named model manifest file
  integrity_manifest_sha256  == build_state.json integrity_manifest_hash
  external_root_hash         == build_state.json approved_external_root_hash
plus: user_authorization_utc present, consumed is false.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

AUTHORIZATION = "checkpoint2_authorization.json"


def _sha256(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_authorization(manifests_dir: str,
                         repo_root: str | None = None) -> tuple[bool, list[str]]:
    """Returns (authorized, failures). failures is empty iff authorized."""
    root = repo_root or os.path.dirname(os.path.dirname(
        os.path.abspath(manifests_dir)))
    failures: list[str] = []
    path = os.path.join(manifests_dir, AUTHORIZATION)
    if not os.path.exists(path):
        return False, ["no authorization record"]
    try:
        with open(path) as f:
            auth = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return False, [f"unreadable authorization record: {e}"]

    if auth.get("consumed"):
        # legacy input-record flag only; the LEDGER below is authoritative
        failures.append("authorization record marked consumed")
    if not auth.get("user_authorization_utc"):
        failures.append("missing user_authorization_utc")

    # protocol hash — recomputed now
    proto = _sha256(os.path.join(root, "EXPERIMENT_PROTOCOL.md"))
    if not proto or auth.get("protocol_sha256") != proto:
        failures.append("protocol_sha256 does not match the current "
                        "EXPERIMENT_PROTOCOL.md")

    # git commit — current HEAD
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        head = None
    if not head or auth.get("git_commit") != head:
        failures.append("git_commit does not match current HEAD")

    # dataset + model manifests — hashes of the NAMED files
    for key, file_key in (("dataset_manifest_sha256", "dataset_manifest_file"),
                          ("model_manifest_sha256", "model_manifest_file")):
        fname = auth.get(file_key)
        digest = _sha256(os.path.join(manifests_dir, fname)) if fname else None
        if not digest or auth.get(key) != digest:
            failures.append(f"{key} does not match the named manifest file")

    # integrity manifest + externally preserved root — from build_state.json
    try:
        with open(os.path.join(root, "build_state.json")) as f:
            bs = json.load(f)
    except (OSError, json.JSONDecodeError):
        bs = {}
    integ = bs.get("integrity_manifest_hash")
    if not integ or auth.get("integrity_manifest_sha256") != integ:
        failures.append("integrity_manifest_sha256 does not match the "
                        "locked constitutional manifest (or none is locked)")
    root_hash = bs.get("approved_external_root_hash")
    if not root_hash or auth.get("external_root_hash") != root_hash:
        failures.append("external_root_hash does not match the most "
                        "recently approved externally preserved root")

    # holdout state ledger (delta review corr. B): consumption is
    # established by the append-only hash-chained ledger, never by the
    # (mutable) authorization JSON; a corrupt chain blocks access.
    from lab.data import holdout_ledger as HL
    try:
        permitted, why = HL.opening_permitted(manifests_dir)
        if not permitted:
            failures.append(f"holdout state ledger: {why}")
    except HL.LedgerCorrupt as e:
        failures.append(f"holdout state ledger corrupt — access blocked: {e}")

    return not failures, failures
