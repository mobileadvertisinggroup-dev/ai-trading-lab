"""Fault-injection battery for the one-time gate (D69 blocker 5).

Injects a failure at EVERY stage the directive names — identity
validation, decryption, extraction, the evaluator, result
serialization, cleanup, result publication, and the ledger append —
and proves the contract at each:

  pre-claim faults  -> refused, opening NOT spent (no ledger events);
  post-claim faults -> FAILED_CLOSED recorded, decrypted material gone,
                       NO results file published, second opening
                       permanently blocked;
  ledger/publication faults -> success is NEVER represented (results
                       removed, exception raised) even though the
                       evaluation itself succeeded.

Uses the same fully-valid environment as test_holdout_gate (real git
repo, real age-encrypted artifact, frozen-input manifest, recipient
pin) so every injected fault is the ONLY thing wrong.
"""
import json
import os

import pytest
import pyrage

from lab.data import holdout_ledger as HL
from lab.data import unseal as U
from lab.data.unseal import UnsealRefused, evaluate_holdout

from tests.test_holdout_gate import (dummy_evaluator, env,  # noqa: F401
                                     events, shm_dir)


def gate(env, **kw):
    out_dir = kw.pop("out_dir", shm_dir())
    results = str(env["tmp"] / "fi-results.json")
    return evaluate_holdout(
        env["artifact"], env["manifests"],
        kw.pop("evaluator", dummy_evaluator), results,
        out_dir=out_dir, repo_root=env["root"],
        identity_provider=kw.pop("provider", env["provide"]),
        model_dir=env["model_dir"], sb3_dir=env["sb3_dir"]), out_dir, results


def assert_failed_closed(env, out_dir, results):
    assert events(env) == ["OPENING_STARTED", "FAILED_CLOSED"]
    assert not os.path.exists(out_dir)          # decrypted material gone
    assert not os.path.exists(results)          # no results published
    assert not os.path.exists(results + ".tmp")
    with pytest.raises(UnsealRefused, match="permanently blocked"):
        gate(env)


# ------------------------------------------------- pre-claim faults
def test_fault_identity_validation_garbage_line(env):
    with pytest.raises(UnsealRefused, match="NOT spent"):
        gate(env, provider=lambda: "AGE-SECRET-KEY-1GARBAGE")
    assert events(env) == []


def test_fault_identity_wrong_key(env):
    other = pyrage.x25519.Identity.generate()
    with pytest.raises(UnsealRefused, match="frozen holdout recipient"):
        gate(env, provider=lambda: str(other))
    assert events(env) == []


def test_fault_frozen_input_one_byte_mutations_each_class(env):
    """One-byte mutation per artifact class refuses BEFORE
    OPENING_STARTED (D69 blocker 2 negative tests)."""
    mutations = [
        os.path.join(env["root"], "EXPERIMENT_PROTOCOL.md"),   # repo_files
        os.path.join(env["manifests"],
                     "lake_manifest_raw-v1.json"),       # manifest_files
        os.path.join(env["manifests"],
                     "holdout_recipient.txt"),           # frozen recipient
        os.path.join(env["model_dir"], "arm_b.txt"),     # model_dir_files
        os.path.join(env["sb3_dir"],
                     "arm_f_sb3_seed4.zip"),             # sb3_dir_files
    ]
    for path in mutations:
        original = open(path, "rb").read()
        try:
            mutated = bytes([original[0] ^ 1]) + original[1:]
            open(path, "wb").write(mutated)
            with pytest.raises(UnsealRefused) as exc:
                gate(env)
            assert ("frozen-input" in str(exc.value)
                    or "authorization" in str(exc.value)), path
            assert events(env) == [], path       # BEFORE OPENING_STARTED
        finally:
            open(path, "wb").write(original)
    _, _, _ = gate(env)                          # restored env still opens
    assert events(env) == ["OPENING_STARTED", "CONSUMED"]


def test_fault_frozen_input_additional_file_strict_census(env):
    extra = os.path.join(env["model_dir"], "arm_x_smuggled.txt")
    open(extra, "w").write("unpinned")
    try:
        with pytest.raises(UnsealRefused, match="ADDITIONAL"):
            gate(env)
        assert events(env) == []
    finally:
        os.unlink(extra)


def test_fault_frozen_input_symlink_substitution(env):
    real = os.path.join(env["model_dir"], "arm_b.txt")
    aside = os.path.join(str(env["tmp"]), "aside.txt")
    os.rename(real, aside)
    os.symlink(aside, real)                      # same bytes, via symlink
    try:
        with pytest.raises(UnsealRefused, match="symlink|unsafe"):
            gate(env)
        assert events(env) == []
    finally:
        os.unlink(real)
        os.rename(aside, real)


def test_fault_resource_preflight_shortfall(env, monkeypatch):
    import lab.data.preflight as PF
    monkeypatch.setattr(PF, "_meminfo",
                        lambda: {"MemTotal": 1 << 20,
                                 "MemAvailable": 1 << 20})   # 1 MiB
    with pytest.raises(UnsealRefused, match="resource preflight"):
        gate(env)
    assert events(env) == []                     # refused pre-claim


def test_fault_resource_preflight_swap_present(env, monkeypatch):
    import lab.data.preflight as PF
    monkeypatch.setattr(PF, "_swaps",
                        lambda: ["/dev/sda2  partition  8388604  0  -2"])
    with pytest.raises(UnsealRefused, match="resource preflight"):
        gate(env)
    assert events(env) == []                     # refused pre-claim


# ------------------------------------------------ post-claim faults
def test_fault_while_decrypting(env, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("injected decrypt failure")
    monkeypatch.setattr(pyrage, "decrypt_io", boom)
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    with pytest.raises(RuntimeError, match="injected decrypt"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    assert_failed_closed(env, out_dir, results)


def test_fault_while_extracting(env, monkeypatch):
    import tarfile

    def boom(*a, **k):
        raise tarfile.TarError("injected extract failure")
    monkeypatch.setattr(tarfile, "open", boom)
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    with pytest.raises(tarfile.TarError, match="injected extract"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    assert_failed_closed(env, out_dir, results)


def test_fault_in_evaluator(env):
    def exploding(d):
        assert os.path.exists(d)
        raise RuntimeError("injected evaluator failure")
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    with pytest.raises(RuntimeError, match="injected evaluator"):
        evaluate_holdout(env["artifact"], env["manifests"], exploding,
                         results, out_dir=out_dir, repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    assert_failed_closed(env, out_dir, results)


def test_fault_in_result_serialization(env, monkeypatch):
    def boom(results, tmp_path):
        raise OSError("injected serialization failure")
    monkeypatch.setattr(U, "_write_protected_results", boom)
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    with pytest.raises(OSError, match="injected serialization"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    assert_failed_closed(env, out_dir, results)


def test_fault_in_cleanup_never_reports_success(env, monkeypatch):
    real_wipe = U._wipe_and_verify

    def boom(path):
        raise UnsealRefused("injected cleanup failure — FAILED_CLOSED")
    monkeypatch.setattr(U, "_wipe_and_verify", boom)
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    with pytest.raises(UnsealRefused, match="injected cleanup"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    # FAILED_CLOSED with wiped_and_verified FALSE; nothing published
    evs = HL.read_events(env["manifests"])
    assert [e["event"] for e in evs] == ["OPENING_STARTED",
                                         "FAILED_CLOSED"]
    assert evs[-1]["detail"]["wiped_and_verified"] is False
    assert not os.path.exists(results)
    assert not os.path.exists(results + ".tmp")
    real_wipe(out_dir)                           # manual containment
    assert not os.path.exists(out_dir)


def test_fault_in_result_publication(env, monkeypatch):
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    real_replace = os.replace

    def boom(src, dst):
        if dst == results:
            raise OSError("injected publication failure")
        return real_replace(src, dst)
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(UnsealRefused, match="publication failed"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    assert_failed_closed(env, out_dir, results)


def test_fault_in_consumed_ledger_append(env, monkeypatch):
    out_dir, results = shm_dir(), str(env["tmp"] / "fi-results.json")
    real_append = HL.append_event

    def boom(manifests_dir, event, detail):
        raise OSError(f"injected ledger append failure ({event})")
    monkeypatch.setattr(HL, "append_event", boom)
    with pytest.raises(UnsealRefused, match="CONSUMED ledger append"):
        evaluate_holdout(env["artifact"], env["manifests"],
                         dummy_evaluator, results, out_dir=out_dir,
                         repo_root=env["root"],
                         identity_provider=env["provide"],
                         model_dir=env["model_dir"],
                         sb3_dir=env["sb3_dir"])
    # success is NOT represented: published results were removed
    assert not os.path.exists(results)
    assert not os.path.exists(results + ".tmp")
    assert not os.path.exists(out_dir)
    # even without a terminal event, OPENING_STARTED blocks forever
    monkeypatch.setattr(HL, "append_event", real_append)
    assert [e["event"] for e in HL.read_events(env["manifests"])] == \
        ["OPENING_STARTED"]
    with pytest.raises(UnsealRefused, match="permanently blocked"):
        gate(env)


def test_all_faults_leave_audit_or_ledger_trail(env):
    """A refused pre-claim attempt is audit-logged."""
    with pytest.raises(UnsealRefused):
        gate(env, provider=lambda: "AGE-SECRET-KEY-1GARBAGE")
    audit = open(os.path.join(env["manifests"],
                              "access_audit.jsonl")).read()
    assert "identity_validation" in audit and "REFUSED" in audit
