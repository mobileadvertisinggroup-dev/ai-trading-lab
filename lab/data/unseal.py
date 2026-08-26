"""Controlled one-time holdout evaluation — SPEC §9/§22, delta review corr. B.

There is NO general-purpose "decrypt and leave a directory" operation.
The single sanctioned path is `evaluate_holdout`, which:

  1. verifies every authorization/hash gate (lab.data.authz — strict,
     recomputed values; fabricated hashes never pass) AND the append-only
     hash-chained holdout state ledger (corrupt chain => fail closed);
  2. resolves the exact expected holdout artifact FILENAME and SHA-256 from
     the approved dataset manifest and refuses any supplied artifact whose
     basename or recomputed hash differs;
  3. atomically CLAIMS the single opening (OS file lock + chain verify +
     no-prior-opening + fsync via holdout_ledger.claim_opening — two
     concurrent attempts cannot both open);
  4. accepts the private identity only via secure interactive TTY entry
     (tests inject an identity provider; the gate itself is unchanged);
  5. decrypts ONLY into a fresh directory on a VERIFIED memory-backed
     filesystem (tmpfs/ramfs — checked against /proc/mounts; disk-backed
     paths are refused even outside the repository; pre-existing
     directories are refused; never inside the project tree);
  6. runs the exact frozen holdout evaluator (a deterministic dummy until
     the real frozen evaluator exists — the gate is NOT
     implementation-complete until that evaluator is plugged in here);
  7. exports only the evaluator's returned result ledgers/reports;
  8. wipes decrypted material in a finally block on success or failure and
     VERIFIES its absence (verification failure => FAILED_CLOSED + raise);
  9. records CONSUMED (success) or FAILED_CLOSED (failure) in the chained
     ledger — consumption is established by the LEDGER, never by rewriting
     the authorization JSON (which remains an input record only);
 10. permanently refuses a second opening after OPENING_STARTED —
     recovery is NOT self-authorizing; it would require a future
     versioned, explicitly user-approved integrity procedure (final
     narrow review §3). Every exception after the claim — including
     identity-entry or identity-parsing failure — is closed with
     FAILED_CLOSED where possible; even if that append fails, the
     OPENING_STARTED itself keeps the holdout blocked.
"""
from __future__ import annotations

import getpass
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile

from lab.data import holdout_ledger as HL
from lab.data.authz import verify_authorization


class UnsealRefused(RuntimeError):
    pass


def _audit_refusal(manifests_dir: str, detail: dict):
    """Premature/invalid attempts are immutably logged (SPEC §9.6) into
    the same hash-chained access audit log the read layer uses."""
    import time
    path = os.path.join(manifests_dir, "access_audit.jsonl")
    prev = "0" * 64
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, "rb") as f:
            try:
                prev = json.loads(f.readlines()[-1])["hash"]
            except (json.JSONDecodeError, KeyError, IndexError):
                prev = "corrupt-tail"
    entry = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "action": "holdout_evaluation", "detail": detail,
             "decision": "REFUSED", "prev": prev}
    body = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    entry["hash"] = hashlib.sha256((prev + body).encode()).hexdigest()
    with open(path, "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _refuse(manifests_dir: str, detail: dict, message: str):
    _audit_refusal(manifests_dir, detail)
    raise UnsealRefused(message + "\nThis attempt has been recorded in the "
                        "audit log.")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _interactive_identity() -> str:
    if not sys.stdin.isatty():
        raise UnsealRefused("the private identity is accepted only through "
                            "secure interactive entry on a TTY (SPEC §9)")
    line = getpass.getpass(
        "Paste the AGE-SECRET-KEY line (input hidden, never stored): ")
    if not line.strip().startswith("AGE-SECRET-KEY-1"):
        raise UnsealRefused("that is not an age secret identity line")
    return line.strip()


def _expected_artifact(manifests_dir: str) -> tuple[str, str]:
    """(filename, sha256) of the holdout artifact named inside the APPROVED
    dataset manifest (the one the authorization record names and hashes)."""
    auth_path = os.path.join(manifests_dir, "checkpoint2_authorization.json")
    with open(auth_path) as f:
        auth = json.load(f)
    manifest_path = os.path.join(manifests_dir, auth["dataset_manifest_file"])
    with open(manifest_path) as f:
        manifest = json.load(f)
    name = manifest.get("holdout_artifact")
    digest = manifest.get("holdout_artifact_sha256")
    if not name or not digest:
        raise UnsealRefused("the approved dataset manifest does not name a "
                            "holdout artifact — nothing may be decrypted")
    return name, digest


MEMORY_FSTYPES = {"tmpfs", "ramfs"}


def _is_memory_backed(path: str) -> bool:
    """True iff path resides on a verified memory-backed filesystem.
    Resolves the deepest EXISTING ancestor, then matches the longest
    mount-point prefix in /proc/mounts and checks its fstype."""
    p = os.path.realpath(path)
    while not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent
    best_len, best_type = -1, None
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mnt, fstype = parts[1], parts[2]
                mnt_dec = mnt.encode().decode("unicode_escape")
                if (p == mnt_dec or p.startswith(mnt_dec.rstrip("/") + "/")
                        or mnt_dec == "/"):
                    if len(mnt_dec) > best_len:
                        best_len, best_type = len(mnt_dec), fstype
    except OSError:
        return False
    return best_type in MEMORY_FSTYPES


def _wipe_and_verify(path: str):
    if os.path.exists(path):
        for root, _dirs, files in os.walk(path):
            for name in files:            # overwrite before unlink
                fp = os.path.join(root, name)
                try:
                    size = os.path.getsize(fp)
                    with open(fp, "r+b") as f:
                        f.write(b"\0" * size)
                except OSError:
                    pass
        shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        raise UnsealRefused("decrypted material could not be verifiably "
                            "destroyed — FAILED_CLOSED")


def evaluate_holdout(artifact_path: str, manifests_dir: str, evaluator,
                     results_path: str, out_dir: str | None = None,
                     repo_root: str | None = None,
                     identity_provider=None) -> dict:
    """The one controlled holdout evaluation. Returns the evaluator's
    results dict (also written to results_path). Single-use."""
    # -- 1. authorization gate (strict) + state ledger (fail closed)
    ok, failures = verify_authorization(manifests_dir, repo_root)
    if not ok:
        _refuse(manifests_dir, {"stage": "authorization",
                                "failures": failures},
                "authorization gate refused:\n  - "
                + "\n  - ".join(failures))
    permitted, why = HL.opening_permitted(manifests_dir)
    if not permitted:
        _refuse(manifests_dir, {"stage": "opening"},
                f"opening refused: {why}")

    # -- 2. exact artifact identity from the approved dataset manifest
    exp_name, exp_sha = _expected_artifact(manifests_dir)
    if os.path.basename(artifact_path) != exp_name:
        _refuse(manifests_dir, {"stage": "artifact_identity",
                                "supplied": os.path.basename(artifact_path)},
                f"artifact filename {os.path.basename(artifact_path)!r} does "
                f"not match the manifest-named holdout artifact {exp_name!r}")
    got_sha = _sha256_file(artifact_path)
    if got_sha != exp_sha:
        _refuse(manifests_dir, {"stage": "artifact_hash", "got": got_sha},
                f"artifact sha256 {got_sha} does not match the approved "
                f"dataset manifest's {exp_sha}")

    # -- 5. fresh, memory-backed (tmpfs/ramfs) output only
    out_dir = out_dir or f"/dev/shm/akra-holdout-eval-{os.getpid()}"
    root = repo_root or os.path.dirname(os.path.dirname(
        os.path.abspath(manifests_dir)))
    if os.path.abspath(out_dir).startswith(os.path.abspath(root)):
        _refuse(manifests_dir, {"stage": "out_dir", "out_dir": out_dir},
                "decrypted holdout must never be written into the project "
                "tree (SPEC §9.8)")
    if os.path.exists(out_dir):
        _refuse(manifests_dir, {"stage": "out_dir", "out_dir": out_dir},
                f"output directory {out_dir!r} already exists — a fresh "
                f"protected directory is required")
    if not _is_memory_backed(out_dir):
        _refuse(manifests_dir, {"stage": "out_dir", "out_dir": out_dir},
                f"output directory {out_dir!r} is not on a verified "
                f"memory-backed filesystem (tmpfs/ramfs) — disk-backed "
                f"paths are refused (final narrow review §2)")

    # -- 3. ATOMIC single-opening claim (lock + chain verify + fsync)
    try:
        HL.claim_opening(manifests_dir,
                         {"artifact": exp_name, "artifact_sha256": exp_sha})
    except HL.OpeningRefused as e:
        _refuse(manifests_dir, {"stage": "claim"}, f"opening refused: {e}")

    # From here the single opening is spent. EVERY failure — including
    # identity entry/parsing — closes with FAILED_CLOSED where possible;
    # even if that append fails, OPENING_STARTED keeps the holdout blocked.
    try:
        # -- 4. identity via interactive TTY (tests inject a provider)
        identity_line = (identity_provider or _interactive_identity)()
        try:
            import pyrage
            identity = pyrage.x25519.Identity.from_str(identity_line)
        finally:
            del identity_line

        with open(artifact_path, "rb") as f:
            tar_bytes = pyrage.decrypt(f.read(), [identity])
        del identity
        os.makedirs(out_dir)
        os.chmod(out_dir, 0o700)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
            tar.extractall(out_dir, filter="data")
        del tar_bytes

        # -- 6./7. the frozen evaluator; only its results leave this scope
        results = evaluator(out_dir)
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, sort_keys=True, default=str)
    except Exception as e:
        try:
            _wipe_and_verify(out_dir)                   # -- 8. (failure)
            wiped = True
        finally:
            try:
                HL.append_event(manifests_dir, "FAILED_CLOSED",
                                {"artifact": exp_name,
                                 "error": str(e)[:300],
                                 "wiped_and_verified": True})   # -- 9.
            except Exception:
                pass    # OPENING_STARTED still blocks the holdout
        raise
    _wipe_and_verify(out_dir)                           # -- 8. (success)
    HL.append_event(manifests_dir, "CONSUMED",
                    {"artifact": exp_name, "artifact_sha256": exp_sha,
                     "results_path": results_path,
                     "wiped_and_verified": True})       # -- 9.
    return results


def main():  # pragma: no cover — interactive entry point
    raise SystemExit(
        "The holdout gate is not implementation-complete: the real frozen "
        "holdout evaluator does not exist yet. When it does, it is plugged "
        "into evaluate_holdout() and invoked from here — never a bare "
        "decrypt. (Delta review correction B.)")


if __name__ == "__main__":  # pragma: no cover
    main()
