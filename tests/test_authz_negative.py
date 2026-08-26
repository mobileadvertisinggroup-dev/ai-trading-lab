"""Constitutional-prototype NEGATIVE tests (review verdict §7): an
authorization file with merely nonempty or fabricated hashes can never
grant holdout access — at the read layer and at the unseal gate."""
import json
import os
import subprocess

import numpy as np
import pytest

from lab import protocol as P
from lab.data import lake as L
from lab.data.access import GuardedLake, HoldoutAccessError
from lab.data.authz import verify_authorization
from lab.data.unseal import UnsealRefused, evaluate_holdout

H4 = P.BAR_4H_MS
Q, END = 100 * H4, 130 * H4


@pytest.fixture
def guarded(tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    (manifests / "partition_meta.json").write_text(json.dumps(
        {"quarantine_start_ms": Q, "holdout_start_ms": Q,
         "holdout_end_ms": END}))
    df_cols = {"open_time": np.array([0], dtype=np.int64), "open": [1.0],
               "high": [1.0], "low": [1.0], "close": [1.0],
               "volume": [1.0], "quote_volume": [1.0]}
    import pandas as pd
    L.write_parquet(pd.DataFrame(df_cols),
                    str(tmp_path / "lake" / "klines15m" / "A" / "m.parquet"))
    return {"lake": str(tmp_path / "lake"), "manifests": str(manifests),
            "tmp": tmp_path}


def fabricated_auth(manifests):
    auth = {"protocol_sha256": "a" * 64, "git_commit": "b" * 40,
            "dataset_manifest_sha256": "c" * 64,
            "dataset_manifest_file": "lake_manifest_raw-v1.json",
            "model_manifest_sha256": "d" * 64,
            "model_manifest_file": "model_manifest.json",
            "integrity_manifest_sha256": "e" * 64,
            "external_root_hash": "f" * 64,
            "user_authorization_utc": "2026-08-25T00:00:00Z"}
    with open(os.path.join(manifests, "checkpoint2_authorization.json"),
              "w") as f:
        json.dump(auth, f)


def test_fabricated_nonempty_hashes_never_grant_read_access(guarded):
    fabricated_auth(guarded["manifests"])
    ok, failures = verify_authorization(guarded["manifests"])
    assert not ok and len(failures) >= 4      # every hash check fails
    gl = GuardedLake(guarded["lake"], guarded["manifests"])
    with pytest.raises(HoldoutAccessError):
        gl.read_klines("A", Q, END)
    # the refusal is audited
    audit = open(os.path.join(guarded["manifests"],
                              "access_audit.jsonl")).read()
    assert "REFUSED" in audit


def test_fabricated_auth_never_grants_evaluation(guarded, tmp_path):
    fabricated_auth(guarded["manifests"])
    artifact = tmp_path / "holdout.tar.age"
    artifact.write_bytes(b"not-a-real-artifact")
    with pytest.raises(UnsealRefused) as exc:
        evaluate_holdout(str(artifact), guarded["manifests"],
                         lambda d: {}, str(tmp_path / "r.json"),
                         out_dir=str(tmp_path / "out"),
                         repo_root=str(guarded["tmp"]),
                         identity_provider=lambda: "never-reached")
    msg = str(exc.value)
    assert "refused" in msg.lower()
    assert "recorded in the audit log" in msg


def test_even_correct_current_values_fail_without_locked_manifest(tmp_path, guarded):
    """An attacker copying CURRENT protocol hash + HEAD still fails: the
    integrity manifest is not locked and no external root is approved."""
    import hashlib
    root = os.getcwd()                        # the real repo
    proto = hashlib.sha256(
        open(os.path.join(root, "EXPERIMENT_PROTOCOL.md"), "rb").read()
    ).hexdigest()
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    manifests = guarded["manifests"]
    # name real files for dataset/model manifests with correct hashes
    for name in ("lake_manifest_raw-v1.json", "model_manifest.json"):
        p = os.path.join(manifests, name)
        open(p, "w").write("{}")
    dm = hashlib.sha256(b"{}").hexdigest()
    auth = {"protocol_sha256": proto, "git_commit": head,
            "dataset_manifest_sha256": dm,
            "dataset_manifest_file": "lake_manifest_raw-v1.json",
            "model_manifest_sha256": dm,
            "model_manifest_file": "model_manifest.json",
            "integrity_manifest_sha256": "e" * 64,   # nothing is locked
            "external_root_hash": "f" * 64,          # nothing approved
            "user_authorization_utc": "2026-08-25T00:00:00Z"}
    with open(os.path.join(manifests, "checkpoint2_authorization.json"),
              "w") as f:
        json.dump(auth, f)
    ok, failures = verify_authorization(manifests, repo_root=root)
    assert not ok
    joined = " ".join(failures)
    assert "integrity_manifest" in joined and "external_root" in joined


def test_evaluation_refuses_fabricated_auth_before_anything_else(guarded):
    fabricated_auth(guarded["manifests"])
    with pytest.raises(UnsealRefused, match="authorization gate refused"):
        evaluate_holdout("x.age", guarded["manifests"], lambda d: {},
                         "/dev/null",
                         out_dir=os.path.join(str(guarded["tmp"]), "elsewhere"),
                         repo_root=str(guarded["tmp"]),
                         identity_provider=lambda: "never-reached")
