"""Sanctioned holdout unseal command — SPEC §9 / review verdict §7.

The ONLY path by which the encrypted holdout may ever be decrypted.

Gate (all enforced before any decryption): lab.data.authz strict
verification — recomputed protocol hash, current git commit, named dataset
and model manifest hashes, locked integrity-manifest hash, the approved
externally preserved root hash, an explicit Checkpoint-2 authorization
record, and non-consumed status. A record with fabricated or merely
nonempty hashes fails (negative-tested).

Key handling: the private age identity is accepted ONLY through a secure
interactive prompt on a real TTY (getpass, echo off). It is never accepted
via argv, environment, or file path; never written anywhere; held in
memory only for the single decryption.

Output handling: decrypted material is written only to a caller-chosen
directory that must be OUTSIDE the project lake (refused otherwise;
default /dev/shm — RAM-backed, gone at reboot). After the one-time
evaluation the caller wipes it; consumption is recorded immutably in the
authorization record and the hash-chained audit log WITHOUT recording the
key.
"""
from __future__ import annotations

import getpass
import io
import json
import os
import sys
import tarfile
import time

from lab.data.authz import AUTHORIZATION, verify_authorization


class UnsealRefused(RuntimeError):
    pass


def _audit(manifests_dir: str, action: str, detail: dict, decision: str):
    # append to the same hash-chained log the read layer uses
    from lab.data.access import GuardedLake  # local import: audit only
    import hashlib
    path = os.path.join(manifests_dir, "access_audit.jsonl")
    prev = "0" * 64
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, "rb") as f:
            try:
                prev = json.loads(f.readlines()[-1])["hash"]
            except (json.JSONDecodeError, KeyError, IndexError):
                prev = "corrupt-tail"
    entry = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "action": action, "detail": detail, "decision": decision,
             "prev": prev}
    body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    entry["hash"] = hashlib.sha256((prev + body).encode()).hexdigest()
    with open(path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def unseal(artifact_path: str, manifests_dir: str, out_dir: str = "/dev/shm/akra-holdout",
           repo_root: str | None = None) -> str:
    """Decrypt the holdout artifact after the full Checkpoint-2 gate.
    Returns the output directory. Marks the holdout consumed."""
    ok, failures = verify_authorization(manifests_dir, repo_root)
    if not ok:
        _audit(manifests_dir, "unseal", {"artifact": artifact_path,
                                         "failures": failures}, "REFUSED")
        raise UnsealRefused(
            "Checkpoint-2 authorization gate refused decryption:\n  - "
            + "\n  - ".join(failures)
            + "\nThis attempt has been recorded in the audit log.")

    root = repo_root or os.path.dirname(os.path.dirname(
        os.path.abspath(manifests_dir)))
    lake_like = os.path.abspath(os.path.join(root, "lake"))
    if os.path.abspath(out_dir).startswith((lake_like, os.path.abspath(root))):
        _audit(manifests_dir, "unseal", {"out_dir": out_dir},
               "REFUSED")
        raise UnsealRefused("decrypted holdout must never be written into "
                            "the project tree or raw lake (SPEC §9.8)")

    if not sys.stdin.isatty():
        _audit(manifests_dir, "unseal", {}, "REFUSED")
        raise UnsealRefused("the private identity is accepted only through "
                            "secure interactive entry on a TTY (SPEC §9)")
    identity_line = getpass.getpass(
        "Paste the AGE-SECRET-KEY line (input hidden, never stored): ")
    if not identity_line.strip().startswith("AGE-SECRET-KEY-1"):
        _audit(manifests_dir, "unseal", {}, "REFUSED")
        raise UnsealRefused("that is not an age secret identity line")

    import pyrage
    identity = pyrage.x25519.Identity.from_str(identity_line.strip())
    del identity_line
    with open(artifact_path, "rb") as f:
        tar_bytes = pyrage.decrypt(f.read(), [identity])
    del identity

    os.makedirs(out_dir, exist_ok=True)
    os.chmod(out_dir, 0o700)
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        tar.extractall(out_dir, filter="data")
    n_files = sum(len(fs) for _, _, fs in os.walk(out_dir))

    # record consumption immutably — never the key
    auth_path = os.path.join(manifests_dir, AUTHORIZATION)
    with open(auth_path) as f:
        auth = json.load(f)
    auth["consumed"] = True
    auth["consumed_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(auth_path, "w") as f:
        json.dump(auth, f, indent=2, sort_keys=True)
    _audit(manifests_dir, "unseal",
           {"artifact": artifact_path, "out_dir": out_dir,
            "n_files": n_files}, "authorized-holdout-decryption")
    return out_dir


def main():  # pragma: no cover — interactive entry point
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--out-dir", default="/dev/shm/akra-holdout")
    a = ap.parse_args()
    print(unseal(a.artifact, a.manifests_dir, a.out_dir))


if __name__ == "__main__":  # pragma: no cover
    main()
