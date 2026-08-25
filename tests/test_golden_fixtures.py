"""Golden-fixture gate: three-layer verification (FINAL-1.2 §13).

Layer 1: manually derived expected values (fixtures/golden/*.json,
         PENDING INDEPENDENT REVIEW until a reviewer signs off).
Layer 2: Independent Reference Ledger.
Layer 3: Main simulator.
Each fixture must (a) reconcile between layers 2 and 3 via the differential
harness and (b) match the layer-1 expected values.
"""
import glob
import json
import os

import pytest

from lab.verify.differential import compare, run_sim, normalize_sim

GOLDEN = sorted(glob.glob(os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "golden", "*.json")))


@pytest.mark.parametrize("path", GOLDEN, ids=[os.path.basename(p) for p in GOLDEN])
def test_golden(path):
    with open(path) as f:
        g = json.load(f)
    fx, exp = g["fixture"], g["expected"]
    # fixture JSON round-trip: instruction/bar keys arrive as strings
    fx["funding"] = {s: {int(t): r for t, r in m.items()}
                     for s, m in fx["funding"].items()}

    rep = compare(fx)                       # layers 2 vs 3
    assert rep["match"], rep

    events, cash = run_sim(fx)              # layer 3 vs layer 1
    assert cash == pytest.approx(exp["final_cash"], rel=1e-9, abs=1e-9)
    norm = normalize_sim(events)
    if "opens" in exp:
        assert sum(1 for e in norm if e["kind"] == "open") == exp["opens"]
    for rej in exp.get("rejects", []):
        assert any(e["kind"] == "reject" and e["symbol"] == rej["symbol"]
                   and e["reason"] == rej["reason"] for e in norm)
    if exp.get("close_reason"):
        closes = [e for e in norm if e["kind"] == "close"]
        assert closes[-1]["reason"] == exp["close_reason"]
    if exp.get("ambiguity_recorded"):
        assert any(e["kind"] == "ambiguity" for e in norm)
    if exp.get("insolvency_recorded"):
        assert any(e["kind"] == "insolvency" for e in norm)
    if exp.get("ruined_reject"):
        assert any(e["kind"] == "reject" and e["reason"] == "ruined"
                   for e in norm)
    if "cancel" in exp:
        assert any(e["kind"] == "cancel"
                   and e["symbol"] == exp["cancel"]["symbol"] for e in norm)
    if "exit_deferred_then_filled_at" in exp:
        closes = [e for e in norm if e["kind"] == "close"]
        assert closes and closes[0]["t"] == exp["exit_deferred_then_filled_at"]
    assert g["review_status"] in ("PENDING INDEPENDENT REVIEW", "REVIEWED")
