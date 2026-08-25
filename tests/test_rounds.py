"""Synchronized-round coordinator tests + golden fixture G12 (spec §23)."""
import json
import os

import pytest

from lab.orchestration.rounds import RoundCoordinator, RoundError

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "fixtures", "golden",
                      "G12_synchronized_round_failure.json")


def test_golden_G12_synchronized_round_failure():
    with open(GOLDEN) as f:
        g = json.load(f)
    s = g["scenario"]
    rc = RoundCoordinator(s["arms"])
    validity = []
    for rnd in s["rounds"]:
        t = int(rnd["t"])
        rc.begin_round(t)
        for arm, ok in rnd["reports"].items():
            rc.report(t, arm, ok,
                      reason=rnd.get("fail_reason", {}).get(arm))
        validity.append(rc.finalize(t))
        assert rc.is_valid(t) == validity[-1]
    assert validity == g["expected"]["validity"]
    assert rc.counts() == g["expected"]["counts"]
    assert rc.records[1]["failed_arms"] == g["expected"]["round2_failed_arms"]
    assert rc.records[1]["reasons"] == {"B": "model_call_timeout"}
    assert rc.records[2]["failed_arms"] == g["expected"]["round3_failed_arms"]
    assert rc.records[2]["missing_reports"] == \
        g["expected"]["round3_missing_reports"]
    # backfill / reopen attempts raise, always
    if g["expected"]["backfill_raises"]:
        for rnd in s["rounds"]:
            with pytest.raises(RoundError):
                rc.begin_round(int(rnd["t"]))
    assert g["review_status"] == "PENDING INDEPENDENT REVIEW"


def test_round_protocol_misuse_raises():
    rc = RoundCoordinator(["A", "B"])
    with pytest.raises(RoundError):
        rc.report(1, "A", True)            # round not open
    rc.begin_round(1)
    with pytest.raises(RoundError):
        rc.begin_round(1)                  # double open
    rc.report(1, "A", True)
    with pytest.raises(RoundError):
        rc.report(1, "A", True)            # double report
    with pytest.raises(RoundError):
        rc.report(1, "Z", True)            # unknown arm
    assert rc.finalize(1) is False         # B missing -> invalid
    with pytest.raises(RoundError):
        rc.finalize(1)                     # already finalized
    with pytest.raises(RoundError):
        rc.is_valid(2)                     # never finalized
