"""One-time holdout evaluation gate (delta review correction B).

Builds a GENUINELY valid authorization environment — a real temp git repo,
correct recomputed hashes, a real age-sealed artifact — so the success path
exercises the entire gate, then proves every required refusal:
wrong artifact, renamed artifact, wrong hash, second opening, cleanup on
evaluator success AND failure, pre-existing output dir, no residue on
either path, corrupted chain blocks access.
"""
import hashlib
import json
import multiprocessing
import os
import shutil
import subprocess
import tarfile
import io
import uuid

import pytest
import pyrage

from lab.data import holdout_ledger as HL
from lab.data.authz import verify_authorization
from lab.data.unseal import UnsealRefused, evaluate_holdout

ART_NAME = "holdout-raw-v1.tar.age"


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


@pytest.fixture
def env(tmp_path):
    """A complete, VALID gate environment."""
    root = tmp_path / "repo"
    manifests = root / "data" / "manifests"
    manifests.mkdir(parents=True)
    (root / "EXPERIMENT_PROTOCOL.md").write_text("frozen protocol\n")

    # a real sealed artifact: tar with one file, encrypted to a test identity
    ident = pyrage.x25519.Identity.generate()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        blob = b"holdout-rows-simulated"
        info = tarfile.TarInfo("klines15m/AAAUSDT/x.parquet")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
    artifact = tmp_path / ART_NAME
    artifact.write_bytes(pyrage.encrypt(buf.getvalue(), [ident.to_public()]))

    # dataset manifest names + hashes the artifact; model manifest exists
    dm = {"version": "raw-v1", "holdout_artifact": ART_NAME,
          "holdout_artifact_sha256": sha(str(artifact))}
    dm_path = manifests / "lake_manifest_raw-v1.json"
    dm_path.write_text(json.dumps(dm, sort_keys=True))
    mm_path = manifests / "model_manifest.json"
    mm_path.write_text("{}")

    # build_state with a "locked" integrity manifest + approved root
    (root / "build_state.json").write_text(json.dumps(
        {"integrity_manifest_hash": "i" * 64,
         "approved_external_root_hash": "r" * 64}))

    # real git repo so HEAD verification is genuine
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "x"], cwd=root, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()

    auth = {"protocol_sha256": hashlib.sha256(
                b"frozen protocol\n").hexdigest(),
            "git_commit": head,
            "dataset_manifest_sha256": sha(str(dm_path)),
            "dataset_manifest_file": "lake_manifest_raw-v1.json",
            "model_manifest_sha256": sha(str(mm_path)),
            "model_manifest_file": "model_manifest.json",
            "integrity_manifest_sha256": "i" * 64,
            "external_root_hash": "r" * 64,
            "user_authorization_utc": "2026-08-26T00:00:00Z"}
    (manifests / "checkpoint2_authorization.json").write_text(
        json.dumps(auth, sort_keys=True))

    return {"root": str(root), "manifests": str(manifests),
            "artifact": str(artifact), "identity": ident,
            "tmp": tmp_path,
            "provide": lambda: str(ident)}


def dummy_evaluator(decrypted_dir):
    files = sorted(os.path.relpath(os.path.join(r, f), decrypted_dir)
                   for r, _, fs in os.walk(decrypted_dir) for f in fs)
    return {"verdict": "DUMMY-EVALUATION-ONLY", "n_files": len(files),
            "files": files}


def shm_dir():
    """A fresh, not-yet-created path on VERIFIED tmpfs (final review §2)."""
    return f"/dev/shm/akra-test-{uuid.uuid4().hex}"


def run_gate(env, artifact=None, out_dir=None):
    out_dir = out_dir or shm_dir()
    results = str(env["tmp"] / "results.json")
    return evaluate_holdout(artifact or env["artifact"], env["manifests"],
                            dummy_evaluator, results, out_dir=out_dir,
                            repo_root=env["root"],
                            identity_provider=env["provide"]), out_dir, results


def events(env):
    return [e["event"] for e in HL.read_events(env["manifests"])]


def test_success_path_evaluates_wipes_and_consumes(env):
    ok, failures = verify_authorization(env["manifests"], env["root"])
    assert ok, failures
    results, out_dir, results_path = run_gate(env)
    assert results["verdict"] == "DUMMY-EVALUATION-ONLY"
    assert results["n_files"] == 1
    # cleanup executed after evaluator SUCCESS; nothing remains
    assert not os.path.exists(out_dir)
    assert json.load(open(results_path))["n_files"] == 1
    assert events(env) == ["OPENING_STARTED", "CONSUMED"]
    # consumption comes from the LEDGER: the auth JSON was NOT rewritten
    auth = json.load(open(os.path.join(env["manifests"],
                                       "checkpoint2_authorization.json")))
    assert "consumed" not in auth


def test_second_opening_refused_after_success(env):
    run_gate(env)
    with pytest.raises(UnsealRefused, match="consumed|opening"):
        run_gate(env, out_dir=shm_dir())
    # and the read-layer verifier now refuses too
    ok, failures = verify_authorization(env["manifests"], env["root"])
    assert not ok and any("ledger" in f for f in failures)


def test_wrong_artifact_correctly_encrypted_is_refused(env):
    # correctly encrypted to the SAME identity, but different content —
    # and therefore a different hash than the approved manifest records
    other = env["tmp"] / ART_NAME
    other_dir = env["tmp"] / "elsewhere"
    other_dir.mkdir()
    other = other_dir / ART_NAME
    other.write_bytes(pyrage.encrypt(b"different-bytes",
                                     [env["identity"].to_public()]))
    with pytest.raises(UnsealRefused, match="sha256"):
        run_gate(env, artifact=str(other))
    assert events(env) == []                    # refused BEFORE opening


def test_renamed_artifact_is_refused(env):
    renamed = env["tmp"] / "holdout-renamed.tar.age"
    shutil.copy(env["artifact"], renamed)
    with pytest.raises(UnsealRefused, match="filename"):
        run_gate(env, artifact=str(renamed))
    assert events(env) == []


def test_tampered_artifact_wrong_hash_refused(env):
    with open(env["artifact"], "ab") as f:
        f.write(b"x")
    with pytest.raises(UnsealRefused, match="sha256"):
        run_gate(env)
    assert events(env) == []


def test_cleanup_and_failed_closed_after_evaluator_failure(env):
    out_dir = shm_dir()
    results = str(env["tmp"] / "r.json")

    def exploding_evaluator(d):
        assert os.path.exists(d)               # decrypted material existed
        raise RuntimeError("evaluator crashed")

    with pytest.raises(RuntimeError, match="evaluator crashed"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         exploding_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"])
    # cleanup executed after evaluator FAILURE; nothing remains
    assert not os.path.exists(out_dir)
    assert events(env) == ["OPENING_STARTED", "FAILED_CLOSED"]
    # PERMANENT block: no self-authorized recovery in this experiment
    # version (final narrow review §3)
    with pytest.raises(UnsealRefused, match="permanently blocked"):
        run_gate(env, out_dir=shm_dir())


def test_recovery_is_not_self_authorizing(env):
    # application code cannot create RECOVERY_AUTHORIZED at all...
    with pytest.raises(ValueError, match="RECOVERY_AUTHORIZED"):
        HL.append_event(env["manifests"], "RECOVERY_AUTHORIZED",
                        {"adjudication": "self-serve attempt"})
    # ...nor OPENING_STARTED outside the atomic claim
    with pytest.raises(ValueError, match="claim_opening"):
        HL.append_event(env["manifests"], "OPENING_STARTED", {})
    # and even if the string were present, opening_permitted ignores it:
    # (simulate by writing a correctly-CHAINED rogue event directly)
    HL._append_locked(env["manifests"], "OPENING_STARTED", {"rogue": True})
    HL._append_locked(env["manifests"], "RECOVERY_AUTHORIZED",
                      {"rogue": True})
    permitted, why = HL.opening_permitted(env["manifests"])
    assert not permitted and "permanently blocked" in why


def test_disk_backed_output_directory_refused(env):
    # fresh, nonexistent, outside the repo — but DISK-backed: refused
    disk_dir = str(env["tmp"] / "fresh-disk-dir")
    assert not os.path.exists(disk_dir)
    with pytest.raises(UnsealRefused, match="memory-backed"):
        run_gate(env, out_dir=disk_dir)
    assert events(env) == []                   # refused BEFORE the claim


def test_identity_failure_after_claim_is_failed_closed(env):
    def bad_identity():
        raise RuntimeError("user aborted identity entry")
    out_dir = shm_dir()
    with pytest.raises(RuntimeError, match="user aborted"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, str(env["tmp"] / "r.json"),
                         out_dir=out_dir, repo_root=env["root"],
                         identity_provider=bad_identity)
    assert events(env) == ["OPENING_STARTED", "FAILED_CLOSED"]
    assert not os.path.exists(out_dir)


def _claim_worker(args):
    manifests, barrier_ignored = args
    try:
        HL.claim_opening(manifests, {"proc": os.getpid()})
        return "opened"
    except HL.OpeningRefused:
        return "refused"


def test_concurrent_claims_exactly_one_opens(env):
    with multiprocessing.Pool(2) as pool:
        outcomes = pool.map(_claim_worker,
                            [(env["manifests"], None)] * 2)
    assert sorted(outcomes) == ["opened", "refused"]
    evs = events(env)
    assert evs.count("OPENING_STARTED") == 1


def test_preexisting_output_directory_refused(env):
    out_dir = shm_dir()
    os.makedirs(out_dir)
    try:
        with pytest.raises(UnsealRefused, match="already exists"):
            run_gate(env, out_dir=out_dir)
        assert events(env) == []
    finally:
        os.rmdir(out_dir)


def test_output_inside_project_tree_refused(env):
    with pytest.raises(UnsealRefused, match="project tree"):
        run_gate(env, out_dir=os.path.join(env["root"], "lake", "sneak"))


def test_corrupted_chain_blocks_all_access(env):
    run_gate(env)                               # produce a real chain
    path = os.path.join(env["manifests"], "holdout_state.jsonl")
    lines = open(path).read().splitlines()
    e = json.loads(lines[-1])
    e["event"] = "RECOVERY_AUTHORIZED"          # tamper without re-chaining
    lines[-1] = json.dumps(e, sort_keys=True)
    open(path, "w").write("\n".join(lines) + "\n")
    with pytest.raises(HL.LedgerCorrupt):
        HL.read_events(env["manifests"])
    ok, failures = verify_authorization(env["manifests"], env["root"])
    assert not ok and any("corrupt" in f for f in failures)
    with pytest.raises(UnsealRefused, match="corrupt|ledger"):
        run_gate(env, out_dir=shm_dir())
