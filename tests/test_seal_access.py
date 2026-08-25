"""Development tests: sealing split correctness + GuardedLake refusal layer.

These development tests prototype what the LOCKED constitutional
holdout-refusal tests (spec §15) will assert; the constitutional versions are
created and hash-locked before the shakedown.
"""
import io
import json
import os
import tarfile

import numpy as np
import pandas as pd
import pytest
import pyrage

from lab import protocol as P
from lab.data import lake as L
from lab.data import seal as S
from lab.data.access import GuardedLake, HoldoutAccessError

H4 = P.BAR_4H_MS
Q = 100 * H4          # quarantine boundary
END = 130 * H4        # holdout end


def make_klines(start_ms, n_bars):
    t = np.arange(start_ms, start_ms + n_bars * P.BAR_15M_MS, P.BAR_15M_MS,
                  dtype=np.int64)
    return pd.DataFrame({
        "open_time": t, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
        "volume": 10.0, "quote_volume": 15.0})


def make_funding(start_ms, n):
    t = np.arange(start_ms, start_ms + n * P.FUNDING_INTERVAL_MS,
                  P.FUNDING_INTERVAL_MS, dtype=np.int64)
    return pd.DataFrame({"funding_time": t, "funding_rate": 0.0001})


@pytest.fixture
def sealed_env(tmp_path):
    staging = tmp_path / "staging"
    plain = tmp_path / "lake"
    manifests = tmp_path / "manifests"
    manifests.mkdir()

    # staged raw data straddling the quarantine boundary
    df = make_klines(Q - 50 * P.BAR_15M_MS, 200)
    L.write_parquet(df, str(staging / "klines15m" / "AAAUSDT" / "2025-01.parquet"))
    L.write_parquet(make_funding(Q - 10 * P.FUNDING_INTERVAL_MS, 30),
                    str(staging / "funding" / "AAAUSDT.parquet"))

    ident = pyrage.x25519.Identity.generate()
    meta = S.seal_lake(str(staging), str(plain), Q, str(ident.to_public()),
                       str(tmp_path / "holdout-v1.tar.age"))
    S.write_seal_metadata(meta, str(manifests))

    partition_meta = {"quarantine_start_ms": Q, "holdout_start_ms": Q,
                      "holdout_end_ms": END}
    (manifests / "partition_meta.json").write_text(json.dumps(partition_meta))
    return {"plain": str(plain), "manifests": str(manifests),
            "identity": ident, "artifact": str(tmp_path / "holdout-v1.tar.age"),
            "meta": meta}


def test_seal_splits_exactly_at_boundary(sealed_env):
    gl = GuardedLake(sealed_env["plain"], sealed_env["manifests"])
    df = gl.read_klines("AAAUSDT", 0, Q - 1)
    assert len(df) == 50
    assert df.open_time.max() < Q
    # plaintext lake contains NOTHING at/after Q, on disk, anywhere
    for _rel, ap in L.iter_lake_files(sealed_env["plain"]):
        raw = L.read_parquet(ap)
        tcol = "open_time" if "open_time" in raw else "funding_time"
        assert (raw[tcol] < Q).all()


def test_sealed_artifact_decrypts_to_exact_holdout_rows(sealed_env):
    encrypted = open(sealed_env["artifact"], "rb").read()
    tar_bytes = pyrage.decrypt(encrypted, [sealed_env["identity"]])
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        names = tar.getnames()
        assert "klines15m/AAAUSDT/2025-01.parquet" in names
        blob = tar.extractfile("klines15m/AAAUSDT/2025-01.parquet").read()
    assert L.sha256_bytes(blob) == sealed_env["meta"]["sealed_files"][0]["sha256"]
    # decrypting with a WRONG identity fails
    with pytest.raises(Exception):
        pyrage.decrypt(encrypted, [pyrage.x25519.Identity.generate()])


def test_refusals_cover_all_spec_cases(sealed_env):
    gl = GuardedLake(sealed_env["plain"], sealed_env["manifests"])
    cases = [
        ("exact range", lambda: gl.read_klines("AAAUSDT", Q, END)),
        ("partial overlap", lambda: gl.read_klines("AAAUSDT", Q - H4, Q + H4)),
        ("single timestamp", lambda: gl.read_klines("AAAUSDT", Q + 5 * H4, Q + 5 * H4)),
        ("alternate symbol", lambda: gl.read_klines("ZZZUSDT", Q, Q + H4)),
        ("funding", lambda: gl.read_funding("AAAUSDT", Q, END)),
        ("universe/metadata", lambda: gl.universe_info(Q + H4)),
    ]
    for name, fn in cases:
        with pytest.raises(HoldoutAccessError):
            fn()

    # allowed reads still work after refusals
    assert len(gl.read_klines("AAAUSDT", 0, Q - 1)) == 50

    # every refusal is in the hash-chained audit log
    audit = [json.loads(l) for l in
             open(os.path.join(sealed_env["manifests"], "access_audit.jsonl"))]
    refused = [e for e in audit if e["decision"] == "REFUSED"]
    assert len(refused) == len(cases)
    prev = "0" * 64
    import hashlib
    for e in audit:
        assert e["prev"] == prev
        body = {k: e[k] for k in ("ts_utc", "action", "detail", "decision", "prev")}
        expect = hashlib.sha256(
            (prev + json.dumps(body, sort_keys=True, separators=(",", ":")))
            .encode()).hexdigest()
        assert e["hash"] == expect
        prev = e["hash"]


def test_incomplete_authorization_still_refuses(sealed_env):
    auth_path = os.path.join(sealed_env["manifests"],
                             "checkpoint2_authorization.json")
    with open(auth_path, "w") as f:
        json.dump({"protocol_sha256": "x", "git_commit": "y"}, f)  # incomplete
    gl = GuardedLake(sealed_env["plain"], sealed_env["manifests"])
    with pytest.raises(HoldoutAccessError):
        gl.read_klines("AAAUSDT", Q, END)

    # consumed holdout refuses even with all fields present
    full = {k: "filled" for k in
            ("protocol_sha256", "git_commit", "dataset_manifest_sha256",
             "model_manifest_sha256", "integrity_manifest_sha256",
             "external_root_hash", "user_authorization_utc")}
    full["consumed"] = True
    with open(auth_path, "w") as f:
        json.dump(full, f)
    gl2 = GuardedLake(sealed_env["plain"], sealed_env["manifests"])
    with pytest.raises(HoldoutAccessError):
        gl2.read_klines("AAAUSDT", Q, END)


def test_manifest_roundtrip(tmp_path):
    L.write_parquet(make_klines(0, 10), str(tmp_path / "klines15m" / "A" / "m.parquet"))
    m = L.build_manifest(str(tmp_path), "raw-v1")
    assert L.verify_manifest(str(tmp_path), m) == []
    # tamper -> detected
    files = list(L.iter_lake_files(str(tmp_path)))
    with open(files[0][1], "ab") as f:
        f.write(b"x")
    assert L.verify_manifest(str(tmp_path), m) != []
