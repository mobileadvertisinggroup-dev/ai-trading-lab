"""Full-size surrogate DRESS REHEARSAL of the one-time gate
(D69 blocker 4 + closure).

Runs the EXACT production entry point — `python -m lab.data.unseal`,
interactive TTY identity entry and all — against a SURROGATE artifact
built exclusively from NON-HOLDOUT rows (the validation span
[validation_start, quarantine)), encrypted to an EPHEMERAL age keypair
generated inside this process and discarded at exit. Everything runs in
an isolated temporary manifests directory with its own fresh state
ledger, so the rehearsal claims only ITS OWN surrogate opening.

WHAT THIS NEVER DOES:
  - never reads, copies, decrypts, or hashes the real
    holdout-raw-v1.tar.age;
  - never touches the real data/manifests/ ledger, authorization slot,
    or manifests (the real opening count stays ZERO — verified at the
    end against a pre-run snapshot);
  - never uses, requests, or stores the key holder's private key — the
    identity is an ephemeral keypair that exists only in this process.

The surrogate authorization record lives ONLY in the temporary
rehearsal manifests directory; data/manifests/checkpoint2_authorization
.json is never created.

Outputs:
  - data/manifests/checkpoint2_resource_profile.json — measured peak
    RSS, tmpfs high-water, runtime, sizes; consumed by the resource
    preflight (lab.data.preflight) when the real gate runs;
  - readiness/DRESS_REHEARSAL_EVIDENCE.json — the full rehearsal
    record: surrogate window, artifact hash, ledger events, checks.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

import pyrage

from lab.data import lake as L
from lab.data.seal import _df_to_parquet_bytes, _time_column_for
from lab.tools.make_frozen_inputs import (MANIFEST_FILES, MODEL_DIR_FILES,
                                          REPO_FILES, sb3_dir_files)

SURROGATE_ARTIFACT = "surrogate-nonholdout-v1.tar.age"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_surrogate_artifact(lake_dir: str, vs: int, q: int,
                             recipient, artifact_path: str,
                             workdir: str) -> dict:
    """Tar every lake file's rows in [vs, q) (NON-holdout validation
    rows) in the exact lake-relative layout, then age-encrypt to the
    ephemeral recipient via the streaming API."""
    tar_path = os.path.join(workdir, "surrogate.tar")
    n_files = rows = 0
    with tarfile.open(tar_path, "w") as tar:
        for rel, ap in L.iter_lake_files(lake_dir):
            tcol = _time_column_for(rel)
            df = L.read_parquet(ap)
            part = df[(df[tcol] >= vs) & (df[tcol] < q)]
            if not len(part):
                continue
            blob = _df_to_parquet_bytes(part)
            info = tarfile.TarInfo(name=rel)
            info.size = len(blob)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(blob))
            n_files += 1
            rows += int(len(part))
            del df, part, blob
    with open(tar_path, "rb") as src, open(artifact_path, "wb") as dst:
        pyrage.encrypt_io(src, dst, [recipient])
    tar_size = os.path.getsize(tar_path)
    os.unlink(tar_path)                     # non-holdout, but tidy
    return {"n_files": n_files, "rows": rows, "tar_bytes": tar_size,
            "artifact_bytes": os.path.getsize(artifact_path),
            "artifact_sha256": sha256_file(artifact_path)}


def build_surrogate_manifests(mdir: str, repo_root: str, part: dict,
                              vs: int, q: int, artifact_path: str,
                              pubkey: str, model_dir: str,
                              sb3_dir: str) -> None:
    os.makedirs(mdir)
    spart = dict(part)
    spart.update({"quarantine_start_ms": vs, "holdout_start_ms": vs,
                  "holdout_end_ms": q,
                  "surrogate": "validation-span rehearsal — NON-holdout"})
    with open(os.path.join(mdir, "partition_meta.json"), "w") as f:
        json.dump(spart, f, sort_keys=True)
    dm = {"version": "surrogate-rehearsal-v1",
          "holdout_artifact": os.path.basename(artifact_path),
          "holdout_artifact_sha256": sha256_file(artifact_path)}
    with open(os.path.join(mdir, "lake_manifest_raw-v1.json"), "w") as f:
        json.dump(dm, f, sort_keys=True)
    # D76: the bound model manifest (funding-corrected v5) — copied
    # byte-identical from the real gate location
    shutil.copy(os.path.join(repo_root, "data", "manifests",
                             "model_manifest_v5.json"),
                os.path.join(mdir, "model_manifest_v5.json"))
    with open(os.path.join(mdir, "holdout_recipient.txt"), "w") as f:
        f.write(pubkey + "\n")

    fi = {"purpose": "surrogate rehearsal frozen-input manifest",
          "repo_files": {n: sha256_file(os.path.join(repo_root, n))
                         for n in REPO_FILES},
          "manifest_files": {n: sha256_file(os.path.join(mdir, n))
                             for n in MANIFEST_FILES},
          "model_dir_files": {n: sha256_file(os.path.join(model_dir, n))
                              for n in MODEL_DIR_FILES},
          "sb3_dir_files": {n: sha256_file(os.path.join(sb3_dir, n))
                            for n in sb3_dir_files(sb3_dir)}}
    with open(os.path.join(mdir, "checkpoint2_frozen_inputs.json"),
              "w") as f:
        json.dump(fi, f, sort_keys=True)

    head = subprocess.run(["git", "-C", repo_root, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    with open(os.path.join(repo_root, "build_state.json")) as f:
        bs = json.load(f)
    auth = {
        "NOTE": ("SURROGATE rehearsal authorization — lives ONLY in the "
                 "temporary rehearsal manifests dir; authorizes NOTHING "
                 "outside it; the real authorization slot was not "
                 "created"),
        "protocol_sha256": sha256_file(
            os.path.join(repo_root, "EXPERIMENT_PROTOCOL.md")),
        "git_commit": head,
        "dataset_manifest_file": "lake_manifest_raw-v1.json",
        "dataset_manifest_sha256": sha256_file(
            os.path.join(mdir, "lake_manifest_raw-v1.json")),
        "model_manifest_file": "model_manifest_v5.json",
        "model_manifest_sha256": sha256_file(
            os.path.join(mdir, "model_manifest_v5.json")),
        "integrity_manifest_sha256": bs["integrity_manifest_hash"],
        "external_root_hash": bs["approved_external_root_hash"],
        "frozen_inputs_manifest_file": "checkpoint2_frozen_inputs.json",
        "frozen_inputs_manifest_sha256": sha256_file(
            os.path.join(mdir, "checkpoint2_frozen_inputs.json")),
        "user_authorization_utc": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(mdir, "checkpoint2_authorization.json"),
              "w") as f:
        json.dump(auth, f, sort_keys=True)


def stage_dir(src: str, names: list[str], dst: str) -> None:
    os.makedirs(dst)
    for n in names:
        shutil.copy(os.path.join(src, n), os.path.join(dst, n))


def drive_gate_under_pty(cmd: list[str], secret_line: str,
                         out_dir_probe) -> dict:
    """Fork the EXACT production CLI onto a pty, answer the identity
    prompt with the EPHEMERAL secret, and sample peak RSS + tmpfs
    high-water until exit."""
    pid, fd = pty.fork()
    if pid == 0:                                   # child == the gate
        os.execvp(cmd[0], cmd)
    transcript = b""
    sent = False
    peak_rss = tmpfs_hw = 0
    t0 = time.time()
    exit_status = None
    try:
        while True:
            r, _, _ = select.select([fd], [], [], 0.5)
            if r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    chunk = b""
                if chunk:
                    transcript += chunk
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.flush()
            if not sent and b"AGE-SECRET-KEY line" in transcript:
                os.write(fd, (secret_line + "\n").encode())
                sent = True
            try:
                with open(f"/proc/{pid}/status") as f:
                    for line in f:
                        if line.startswith("VmHWM:"):
                            peak_rss = max(peak_rss,
                                           int(line.split()[1]) * 1024)
            except OSError:
                pass
            tmpfs_hw = max(tmpfs_hw, out_dir_probe(pid))
            done, status = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                exit_status = status
                break
    finally:
        os.close(fd)
    return {"identity_prompt_answered": sent,
            "exit_status": int(exit_status),
            "exit_ok": os.WIFEXITED(exit_status)
            and os.WEXITSTATUS(exit_status) == 0,
            "runtime_seconds": round(time.time() - t0, 1),
            "peak_rss_bytes": peak_rss,
            "tmpfs_high_water_bytes": tmpfs_hw,
            "transcript_tail": transcript[-2000:].decode("utf-8",
                                                         "replace")}


def du_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for n in files:
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    return total


def main() -> None:  # pragma: no cover — rehearsal driver
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--lake", required=True,
                    help="verified pre-holdout lake (rows < quarantine)")
    ap.add_argument("--workdir", required=True,
                    help="scratch dir for artifact/manifests/results")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo_root)
    real_manifests = os.path.join(repo, "data", "manifests")

    # snapshot of the REAL ledger state (must be unchanged at the end)
    real_ledger = os.path.join(real_manifests, "holdout_state.jsonl")
    ledger_before = (sha256_file(real_ledger)
                     if os.path.exists(real_ledger) else "ABSENT")
    real_artifact_untouched = "never opened, never read"

    with open(os.path.join(real_manifests, "partition_meta.json")) as f:
        part = json.load(f)
    vs = int(part["validation_start_ms"])
    q = int(part["quarantine_start_ms"])

    os.makedirs(args.workdir, exist_ok=True)
    work = tempfile.mkdtemp(prefix="rehearsal-", dir=args.workdir)

    # 1. EPHEMERAL identity — generated here, never written to disk
    ident = pyrage.x25519.Identity.generate()
    pubkey = str(ident.to_public())

    # 2. surrogate artifact from NON-holdout validation rows
    artifact = os.path.join(work, SURROGATE_ARTIFACT)
    print(f"[rehearsal] building surrogate artifact from [{vs}, {q}) …",
          flush=True)
    art_meta = build_surrogate_artifact(args.lake, vs, q,
                                        ident.to_public(), artifact, work)
    print(f"[rehearsal] artifact: {art_meta['artifact_bytes']:,} bytes, "
          f"{art_meta['n_files']} files, {art_meta['rows']:,} rows",
          flush=True)

    # 3. staged frozen model dirs (strict census)
    model_dir = os.path.join(work, "models")
    sb3_dir = os.path.join(work, "models_sb3")
    stage_dir(os.path.join(repo, "data", "models"), MODEL_DIR_FILES,
              model_dir)
    src_sb3 = os.path.join(repo, "data", "models_sb3")
    stage_dir(src_sb3, sb3_dir_files(src_sb3), sb3_dir)

    # 4. isolated surrogate manifests dir (own fresh ledger)
    mdir = os.path.join(work, "manifests")
    build_surrogate_manifests(mdir, repo, part, vs, q, artifact, pubkey,
                              model_dir, sb3_dir)

    # 5. the EXACT production entry point, on a pty
    results_path = os.path.join(work, "surrogate_results.json")
    cmd = [sys.executable, "-m", "lab.data.unseal",
           "--artifact", artifact, "--manifests-dir", mdir,
           "--pre-lake", args.lake, "--model-dir", model_dir,
           "--sb3-dir", sb3_dir, "--results", results_path,
           "--repo-root", repo]
    print("[rehearsal] driving production gate under pty …", flush=True)
    probe = lambda pid: du_bytes(f"/dev/shm/akra-holdout-eval-{pid}")  # noqa: E731
    run = drive_gate_under_pty(cmd, str(ident), probe)
    del ident                                   # ephemeral key discarded

    # 6. surrogate ledger events + REAL environment untouched
    with open(os.path.join(mdir, "holdout_state.jsonl")) as f:
        surrogate_events = [json.loads(l)["event"] for l in f]
    ledger_after = (sha256_file(real_ledger)
                    if os.path.exists(real_ledger) else "ABSENT")
    results_ok = os.path.exists(results_path)
    results_bytes = os.path.getsize(results_path) if results_ok else 0

    profile = {
        "purpose": ("measured surrogate resource profile for the "
                    "pre-claim resource preflight (D69 blocker 4)"),
        "surrogate_window_ms": [vs, q],
        "ciphertext_bytes": art_meta["artifact_bytes"],
        "decrypted_tar_bytes": art_meta["tar_bytes"],
        "peak_rss_bytes": run["peak_rss_bytes"],
        "tmpfs_high_water_bytes": run["tmpfs_high_water_bytes"],
        "runtime_seconds": run["runtime_seconds"],
        "results_bytes": results_bytes,
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime()),
        "entry_point": "python -m lab.data.unseal (production CLI, pty)",
    }
    evidence = {
        "artifact": art_meta, "run": run,
        "surrogate_ledger_events": surrogate_events,
        "results_written": results_ok, "results_bytes": results_bytes,
        "real_ledger_sha_before": ledger_before,
        "real_ledger_sha_after": ledger_after,
        "real_ledger_unchanged": ledger_before == ledger_after,
        "real_artifact": real_artifact_untouched,
        "real_authorization_created": os.path.exists(
            os.path.join(real_manifests, "checkpoint2_authorization.json")),
        "ephemeral_key": ("generated in-process, used once on the pty, "
                          "discarded; the key holder's key was never "
                          "requested"),
        "profile": profile,
        "workdir": work,
    }
    with open(os.path.join(args.workdir,
                           "DRESS_REHEARSAL_EVIDENCE.json"), "w") as f:
        json.dump(evidence, f, indent=2, sort_keys=True)
    ok = (run["exit_ok"] and results_ok
          and surrogate_events == ["OPENING_STARTED", "CONSUMED"]
          and ledger_before == ledger_after
          and not evidence["real_authorization_created"])
    print(f"[rehearsal] {'SUCCESS' if ok else 'FAILED'}: "
          f"events={surrogate_events} rss={run['peak_rss_bytes']:,} "
          f"tmpfs={run['tmpfs_high_water_bytes']:,} "
          f"t={run['runtime_seconds']}s real_ledger_unchanged="
          f"{ledger_before == ledger_after}", flush=True)
    if ok:
        with open(os.path.join(real_manifests,
                               "checkpoint2_resource_profile.json"),
                  "w") as f:
            json.dump(profile, f, indent=2, sort_keys=True)
        print("[rehearsal] wrote data/manifests/"
              "checkpoint2_resource_profile.json", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":  # pragma: no cover
    main()
