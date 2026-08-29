"""Controlled one-time holdout evaluation — SPEC §9/§22, delta review
corr. B, D69 blockers 2/4/5.

There is NO general-purpose "decrypt and leave a directory" operation.
The single sanctioned path is `evaluate_holdout`. EVERYTHING that can be
checked without the holdout runs BEFORE the atomic claim — a failure
there refuses and the single opening is NOT spent:

  pre-claim (refusal costs nothing):
  1. strict authorization (lab.data.authz — recomputed hashes; fabricated
     values never pass) AND the append-only hash-chained state ledger
     (corrupt chain => fail closed);
  2. exact artifact FILENAME + sha256 from the approved dataset manifest;
  3. frozen-input verification (lab.data.frozen_inputs): ONE manifest,
     itself hash-bound to the authorization record, pins EVERY consumed
     file — protocol, spec + amendments, pre-registrations, dataset/
     partition manifests, the frozen recipient, boosters, cuts,
     selection records, the SB3 manifest + seed ZIP; missing, ADDITIONAL,
     substituted, symlinked, or path-escaping inputs refuse;
  4. output directory: fresh, outside the project tree, on a VERIFIED
     memory-backed filesystem (tmpfs/ramfs via /proc/mounts);
  5. identity: read interactively (TTY, no echo; tests inject a
     provider), parsed, and VERIFIED — the derived public recipient must
     equal the frozen recipient pinned in data/manifests/
     holdout_recipient.txt. A mistyped or wrong key refuses HERE, before
     anything is claimed or decrypted;
  6. resource preflight (lab.data.preflight): ciphertext size, tmpfs
     capacity, available RAM, no-swap requirement, results-directory
     capacity, surrogate-profile-scaled expected peak, conservative
     margin.

  the claim and after:
  7. ATOMIC single-opening claim (OS file lock + chain verify +
     no-prior-opening + fsync) IMMEDIATELY before real decryption;
  8. STREAMING decryption (pyrage.decrypt_io) of the ciphertext into a
     tar file on the verified tmpfs — never a whole-file bytes object —
     then streamed extraction (filter="data"), then the tar is
     overwritten in bounded chunks and deleted before the evaluator runs
     (halves the tmpfs peak);
  9. the frozen evaluator; its returned results are serialized FIRST to
     a protected temp file (mode 0600, fsync) next to the final results
     path;
 10. wipe-and-verify of ALL decrypted material (bounded-chunk zero
     overwrite — never a size-of-file bytes object — then tree removal,
     then absence verification). Cleanup failure => FAILED_CLOSED, the
     temp results are removed, and NO success is represented;
 11. only after VERIFIED cleanup: atomic publication of the results
     (os.replace) and the CONSUMED ledger append. If the CONSUMED append
     fails, the published results are removed again, FAILED_CLOSED is
     recorded where possible, and the run raises — success is never
     represented with a failed ledger;
 12. permanently refuses a second opening after OPENING_STARTED —
     recovery is NOT self-authorizing. Every post-claim failure closes
     with FAILED_CLOSED where possible; even if that append fails, the
     OPENING_STARTED itself keeps the holdout blocked.

Crash states (documented in DATAFLOW_HOLDOUT_OPENING.md): a hard crash
(power loss, SIGKILL) between the claim and cleanup can leave decrypted
material on the tmpfs and no terminal ledger event. The material is
memory-backed — it vanishes on power-off — and manual containment is:
remove the out_dir tree, verify absence, and report; the opening stays
permanently spent either way.
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
import sys
import tarfile

from lab.data import holdout_ledger as HL
from lab.data.authz import AUTHORIZATION, verify_authorization
from lab.data.frozen_inputs import verify_frozen_inputs
from lab.data.preflight import preflight_resources

RECIPIENT_FILE = "holdout_recipient.txt"
WIPE_CHUNK = 1 << 20                    # bounded memory, always


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
    auth_path = os.path.join(manifests_dir, AUTHORIZATION)
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


def _wipe_file(fp: str):
    """Zero-overwrite one file in bounded chunks (never a size-of-file
    bytes object — D69 blocker 5), fsync, then unlink."""
    try:
        size = os.path.getsize(fp)
        zero = b"\0" * WIPE_CHUNK
        with open(fp, "r+b") as f:
            left = size
            while left > 0:
                n = min(left, WIPE_CHUNK)
                f.write(zero[:n])
                left -= n
            f.flush()
            os.fsync(f.fileno())
        os.unlink(fp)
    except OSError:
        pass                            # rmtree + verification follow


def _wipe_and_verify(path: str):
    if os.path.exists(path):
        for root, _dirs, files in os.walk(path):
            for name in files:          # overwrite before unlink
                _wipe_file(os.path.join(root, name))
        shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        raise UnsealRefused("decrypted material could not be verifiably "
                            "destroyed — FAILED_CLOSED")


def _frozen_recipient(manifests_dir: str) -> str:
    with open(os.path.join(manifests_dir, RECIPIENT_FILE)) as f:
        return f.read().strip()


def _write_protected_results(results: dict, tmp_path: str):
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True, default=str)
        f.flush()
        os.fsync(f.fileno())


def evaluate_holdout(artifact_path: str, manifests_dir: str, evaluator,
                     results_path: str, out_dir: str | None = None,
                     repo_root: str | None = None,
                     identity_provider=None, *,
                     model_dir: str, sb3_dir: str) -> dict:
    """The one controlled holdout evaluation. Returns the evaluator's
    results dict (also written to results_path). Single-use."""
    import pyrage

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

    # -- 3. frozen-input verification (D69 blocker 2): every consumed
    # file re-hashed against the ONE authorized frozen-input manifest,
    # itself hash-bound to the authorization record. Strict census.
    root = repo_root or os.path.dirname(os.path.dirname(
        os.path.abspath(manifests_dir)))
    with open(os.path.join(manifests_dir, AUTHORIZATION)) as f:
        auth = json.load(f)
    fi_ok, fi_failures = verify_frozen_inputs(
        manifests_dir, root, model_dir, sb3_dir,
        auth.get("frozen_inputs_manifest_sha256", ""))
    if not fi_ok:
        _refuse(manifests_dir, {"stage": "frozen_inputs",
                                "failures": fi_failures[:20]},
                "frozen-input verification refused:\n  - "
                + "\n  - ".join(fi_failures))

    # -- 4. fresh, memory-backed (tmpfs/ramfs) output only
    out_dir = out_dir or f"/dev/shm/akra-holdout-eval-{os.getpid()}"
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

    # -- 5. identity read + PRE-CLAIM verification against the frozen
    # recipient (D69 blocker 5): a wrong or mistyped key refuses here,
    # while the opening is still unspent.
    try:
        identity_line = (identity_provider or _interactive_identity)()
        try:
            identity = pyrage.x25519.Identity.from_str(identity_line)
        finally:
            del identity_line
        derived = str(identity.to_public())
    except UnsealRefused:
        raise
    except Exception as e:
        _refuse(manifests_dir, {"stage": "identity_validation"},
                f"identity entry/parsing failed before the claim — the "
                f"opening is NOT spent: {e}")
    frozen = _frozen_recipient(manifests_dir)
    if derived != frozen:
        del identity
        _refuse(manifests_dir, {"stage": "identity_validation",
                                "derived_recipient": derived},
                "the entered identity does not correspond to the frozen "
                f"holdout recipient {frozen} — refused BEFORE the claim")

    # -- 6. resource preflight (D69 blocker 4) — non-holdout inputs only
    pf_ok, pf_report = preflight_resources(artifact_path, out_dir,
                                           results_path, manifests_dir)
    if not pf_ok:
        del identity
        _refuse(manifests_dir, {"stage": "resource_preflight",
                                "report": pf_report},
                "resource preflight refused (capacity/RAM/swap/results "
                "margin): "
                + json.dumps(pf_report["checks"], sort_keys=True))

    # -- 7. ATOMIC single-opening claim (lock + chain verify + fsync),
    # immediately before real decryption.
    try:
        HL.claim_opening(manifests_dir,
                         {"artifact": exp_name, "artifact_sha256": exp_sha,
                          "resource_preflight": pf_report["checks"]})
    except HL.OpeningRefused as e:
        _refuse(manifests_dir, {"stage": "claim"}, f"opening refused: {e}")

    # From here the single opening is spent. EVERY failure closes with
    # FAILED_CLOSED where possible; even if that append fails, the
    # OPENING_STARTED itself keeps the holdout blocked.
    tmp_results = results_path + ".tmp"
    tar_path = None
    try:
        os.makedirs(out_dir)
        os.chmod(out_dir, 0o700)

        # -- 8. STREAMING decrypt to tmpfs, stream-extract, wipe the tar
        tar_path = os.path.join(out_dir, "overlay.tar")
        with open(artifact_path, "rb") as src, \
                open(tar_path, "wb") as dst:
            pyrage.decrypt_io(src, dst, [identity])
        del identity
        with tarfile.open(tar_path, mode="r|*") as tar:
            tar.extractall(out_dir, filter="data")
        _wipe_file(tar_path)
        if os.path.exists(tar_path):
            raise UnsealRefused("decrypted tar could not be removed "
                                "before evaluation — FAILED_CLOSED")

        # -- 9. the frozen evaluator; results FIRST to a protected temp
        results = evaluator(out_dir)
        _write_protected_results(results, tmp_results)

        # -- 10. wipe-and-verify BEFORE any success representation
        _wipe_and_verify(out_dir)
    except Exception as e:
        wiped = False
        try:
            _wipe_and_verify(out_dir)
            wiped = True
        finally:
            try:
                if os.path.exists(tmp_results):
                    os.unlink(tmp_results)
            except OSError:
                pass
            try:
                HL.append_event(manifests_dir, "FAILED_CLOSED",
                                {"artifact": exp_name,
                                 "error": str(e)[:300],
                                 "wiped_and_verified": wiped})
            except Exception:
                pass    # OPENING_STARTED still blocks the holdout
        raise

    # -- 11. verified cleanup done: publish atomically, then CONSUMED
    try:
        os.replace(tmp_results, results_path)
    except Exception as e:
        try:
            os.unlink(tmp_results)
        except OSError:
            pass
        try:
            HL.append_event(manifests_dir, "FAILED_CLOSED",
                            {"artifact": exp_name,
                             "error": f"results publication failed: "
                                      f"{str(e)[:200]}",
                             "wiped_and_verified": True})
        except Exception:
            pass
        raise UnsealRefused(
            "atomic results publication failed after cleanup — no "
            f"success is represented: {e}") from e
    try:
        HL.append_event(manifests_dir, "CONSUMED",
                        {"artifact": exp_name, "artifact_sha256": exp_sha,
                         "results_path": results_path,
                         "wiped_and_verified": True})
    except Exception as e:
        try:
            os.unlink(results_path)     # no success representation
        except OSError:
            pass
        try:
            HL.append_event(manifests_dir, "FAILED_CLOSED",
                            {"artifact": exp_name,
                             "error": f"CONSUMED append failed: "
                                      f"{str(e)[:200]}",
                             "wiped_and_verified": True})
        except Exception:
            pass
        raise UnsealRefused(
            "the CONSUMED ledger append failed after cleanup — the "
            "published results were removed and success is NOT "
            f"represented: {e}") from e
    return results


def main():  # pragma: no cover — interactive entry point
    """The ONE sanctioned interactive Checkpoint-2 command (run locally
    by the key holder; the private key is entered on the TTY, verified
    against the frozen recipient BEFORE the claim, and never stored).
    Everything upstream of the evaluator is the fail-closed gate; the
    evaluator is the FROZEN plan of
    PREREGISTRATION_CHECKPOINT2_EVALUATION.md."""
    import argparse

    from lab.tools.holdout_evaluator import make_evaluator

    ap = argparse.ArgumentParser(
        description="One-time Checkpoint-2 holdout evaluation "
                    "(interactive; single use; fail closed)")
    ap.add_argument("--artifact", required=True,
                    help="downloaded holdout-raw-v1.tar.age (basename and "
                         "sha256 are verified against the approved "
                         "dataset manifest before anything opens)")
    ap.add_argument("--manifests-dir", required=True)
    ap.add_argument("--pre-lake", required=True,
                    help="verified pre-holdout lake directory")
    ap.add_argument("--model-dir", required=True,
                    help="staged dir with EXACTLY the frozen B/C/E "
                         "artifacts + selection records (strict census)")
    ap.add_argument("--sb3-dir", required=True,
                    help="staged dir with EXACTLY the frozen SB3 "
                         "manifest + selected-seed ZIP (strict census)")
    ap.add_argument("--results", required=True,
                    help="output path for the results JSON (the only "
                         "thing that leaves the gate)")
    ap.add_argument("--repo-root", default=None,
                    help="repository root for authorization/frozen-input "
                         "verification (default: parent of manifests-dir"
                         "'s parent)")
    args = ap.parse_args()
    evaluator = make_evaluator(args.pre_lake, args.manifests_dir,
                               args.model_dir, args.sb3_dir)
    evaluate_holdout(args.artifact, args.manifests_dir, evaluator,
                     args.results, repo_root=args.repo_root,
                     model_dir=args.model_dir, sb3_dir=args.sb3_dir)
    print("Holdout evaluation complete; the state ledger records "
          f"CONSUMED. Results: {args.results}")


if __name__ == "__main__":  # pragma: no cover
    main()
