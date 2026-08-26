"""Coverage audit (user directive 2026-08-26, D40): synthetic-lake tests
with an injected archive probe — no network. Proves classification of
pre-listing / post-delisting / internal-missing / fallback-window /
holdout-sealed months, gap completeness, head/tail truncation detection,
the fallback-discard check (point 5), BTC context reporting, manifest
recording, and both verdicts."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from lab import protocol as P
from lab.data import lake as L
from lab.data.audit import audit_lake, expected_slots, record_in_manifest

BAR = P.BAR_15M_MS
MS_2023_01 = 1672531200000        # 2023-01-01T00:00:00Z
MS_2026_01 = 1767225600000        # 2026-01-01T00:00:00Z (quarantine)
MS_2026_03 = 1772323200000        # 2026-03-01T00:00:00Z (freeze)


def write_month(lake, symbol, month, start_ms, n, step=BAR):
    t = start_ms + np.arange(n, dtype=np.int64) * step
    df = pd.DataFrame({"open_time": t, "open": 1.0, "high": 1.0,
                       "low": 1.0, "close": 1.0, "volume": 1.0,
                       "quote_volume": 1.0})
    L.write_parquet(df, L.klines_path(lake, symbol, month))


def month_ms(month):
    return int(pd.Timestamp(month + "-01", tz="UTC").value // 1_000_000)


@pytest.fixture
def env(tmp_path):
    lake = str(tmp_path / "lake")
    manifests = str(tmp_path / "manifests")
    os.makedirs(manifests)
    with open(os.path.join(manifests, "partition_meta.json"), "w") as f:
        json.dump({"quarantine_start_ms": MS_2026_01,
                   "ingestion_freeze_ms": MS_2026_03}, f)
    # BTC context: continuous 2023-01..2023-04 (full months)
    for m in ["2023-01", "2023-02", "2023-03", "2023-04"]:
        n = (month_ms({"2023-01": "2023-02", "2023-02": "2023-03",
                       "2023-03": "2023-04", "2023-04": "2023-05"}[m])
             - month_ms(m)) // BAR
        write_month(lake, P.CONTEXT_SYMBOL, m, month_ms(m), n)
    return {"lake": lake, "manifests": manifests}


def full_month(lake, symbol, month):
    nm = pd.Timestamp(month + "-01", tz="UTC") + pd.offsets.MonthBegin(1)
    n = (int(nm.value // 1_000_000) - month_ms(month)) // BAR
    write_month(lake, symbol, month, month_ms(month), n)


def probe_all_absent(symbol, month):
    return "absent"


def run(env, probe=probe_all_absent, **kw):
    return audit_lake(env["lake"], env["manifests"], "raw-vT", 2,
                      archive_probe=probe,
                      acquisition_start_month="2023-01", **kw)


def test_clean_symbol_passes_with_classifications(env):
    for m in ["2023-02", "2023-03", "2023-04"]:
        full_month(env["lake"], "AAAUSDT", m)
    audit = run(env)
    assert audit["verdict"] == "PASS"
    rep = audit["symbols"]["AAAUSDT"]
    assert rep["first_month"] == "2023-02" and rep["last_month"] == "2023-04"
    assert all(v["status"] == "present" and v["completeness"] == 1.0
               for v in rep["months"].values())
    assert audit["btc_context"]["first_month"] == "2023-01"


def test_internal_missing_month_archive_empty_passes(env):
    full_month(env["lake"], "BBBUSDT", "2023-02")
    full_month(env["lake"], "BBBUSDT", "2023-04")     # 2023-03 missing
    audit = run(env)
    assert audit["verdict"] == "PASS"
    st = audit["symbols"]["BBBUSDT"]["months"]["2023-03"]["status"]
    assert st == "archive_empty_market_inactive"


def test_fallback_discard_is_coverage_loss(env):
    # archive HAS daily data for the internal missing month -> FAIL
    full_month(env["lake"], "CCCUSDT", "2023-02")
    full_month(env["lake"], "CCCUSDT", "2023-04")

    def probe(symbol, month):
        if symbol == "CCCUSDT" and month == "2023-03":
            return "daily"
        return "absent"
    audit = run(env, probe=probe)
    assert audit["verdict"] == "FAIL_COVERAGE_LOSS"
    loss = audit["coverage_losses"]
    assert {"symbol": "CCCUSDT", "month": "2023-03", "archive": "daily",
            "kind": "internal"} in loss
    st = audit["symbols"]["CCCUSDT"]["months"]["2023-03"]["status"]
    assert st == "COVERAGE_LOSS_archive_has_daily"


def test_tail_truncation_detected(env):
    full_month(env["lake"], "DDDUSDT", "2023-02")

    def probe(symbol, month):
        if symbol == "DDDUSDT" and month == "2023-03":
            return "monthly"          # archive continues; our tail stops
        return "absent"
    audit = run(env, probe=probe)
    assert any(l["kind"] == "tail_truncated" and l["symbol"] == "DDDUSDT"
               for l in audit["coverage_losses"])
    assert audit["verdict"] == "FAIL_COVERAGE_LOSS"


def test_head_truncation_detected_but_not_before_history_start(env):
    full_month(env["lake"], "EEEUSDT", "2023-03")

    def probe(symbol, month):
        return "monthly" if (symbol == "EEEUSDT" and month == "2023-02") \
            else "absent"
    audit = run(env, probe=probe)
    assert any(l["kind"] == "head_truncated" for l in audit["coverage_losses"])
    # BTC starts exactly at history start: its head month (2022-12) is
    # before acquisition start and must NOT be probed or flagged
    assert not any(l["symbol"] == P.CONTEXT_SYMBOL
                   for l in audit["coverage_losses"])


def test_holdout_and_fallback_months_classified_not_probed(env):
    # symbol running to the freeze: months >= quarantine are sealed;
    # recent months are fallback window; neither may be probed/flagged
    cur = "2023-02"
    while cur <= "2026-02":
        if cur not in ("2026-01", "2026-02", "2025-12"):
            full_month(env["lake"], "FFFUSDT", cur)
        y, m = map(int, cur.split("-"))
        m += 1
        if m == 13:
            y, m = y + 1, 1
        cur = f"{y:04d}-{m:02d}"
    write_month(env["lake"], "FFFUSDT", "2026-02", month_ms("2026-02"), 10)

    probed = []

    def probe(symbol, month):
        probed.append((symbol, month))
        return "absent"
    audit = run(env, probe=probe)
    rep = audit["symbols"]["FFFUSDT"]["months"]
    assert rep["2026-01"]["status"] == "holdout_sealed"
    assert rep["2025-12"]["status"] == "internal_missing_pending_probe" or \
        rep["2025-12"]["status"] == "archive_empty_market_inactive"
    assert ("FFFUSDT", "2026-01") not in probed
    assert audit["verdict"] == "PASS"


def test_gap_completeness_reported(env):
    # half-missing month: completeness 0.5 reported, but no coverage loss
    # (intra-month gaps are data-quality territory, not acquisition audit)
    nm = month_ms("2023-03")
    n_full = (nm - month_ms("2023-02")) // BAR
    write_month(env["lake"], "GGGUSDT", "2023-02", month_ms("2023-02"),
                n_full // 2, step=2 * BAR)          # every other bar
    audit = run(env)
    rep = audit["symbols"]["GGGUSDT"]["months"]["2023-02"]
    assert rep["status"] == "present"
    assert rep["completeness"] and rep["completeness"] < 0.51


def test_no_probe_is_never_a_pass(env):
    full_month(env["lake"], "HHHUSDT", "2023-02")
    audit = audit_lake(env["lake"], env["manifests"], "raw-vT", 2,
                       archive_probe=None,
                       acquisition_start_month="2023-01")
    assert audit["verdict"] == "UNVERIFIED_NO_PROBE"


def test_record_in_manifest_preserves_original_pin(env, tmp_path):
    full_month(env["lake"], "IIIUSDT", "2023-02")
    audit = run(env)
    with open(os.path.join(env["manifests"],
                           "coverage_audit_raw-vT.json"), "w") as f:
        json.dump(audit, f)
    manifest = L.build_manifest(env["lake"], "raw-vT")
    orig_pin = manifest["manifest_sha256"]
    with open(os.path.join(env["manifests"],
                           "lake_manifest_raw-vT.json"), "w") as f:
        json.dump(manifest, f)
    out = record_in_manifest(env["manifests"], "raw-vT")
    assert out["manifest_sha256"] == orig_pin          # original pin intact
    assert out["coverage_audit_verdict"] == "PASS"
    assert len(out["coverage_audit_sha256"]) == 64
    assert out["manifest_sha256_with_audit"] != orig_pin


def test_expected_slots():
    assert expected_slots(0, 4 * BAR) == 4
    assert expected_slots(1, 4 * BAR) == 3
    assert expected_slots(0, 0) == 0
    assert expected_slots(BAR, BAR) == 0
