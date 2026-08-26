"""Golden-fixture gate: three-layer verification (FINAL-1.2 §13).

Layer 1: manually derived CANONICAL DECIMAL expected values
         (fixtures/golden/*.json).
Layer 2: Independent Reference Ledger.
Layer 3: Main simulator.
Each fixture must (a) reconcile between layers 2 and 3 via the differential
harness (EXACT equality) and (b) match the layer-1 canonical value under
the LAYER-1 COMPARISON RULE (reviewer-mandated, 2026-08-25): the
implementation's final cash, rounded via Decimal ROUND_HALF_EVEN to the
6 decimal places of the hand derivation, must equal the canonical decimal
EXACTLY, and the raw absolute difference must not exceed 1e-8. A broad
pytest.approx is never used for layer 1 — it hid the G03 v1 defect where a
binary float artifact had been stored as the expected value.
"""
import glob
import json
import os
from decimal import Decimal, ROUND_HALF_EVEN

import pytest

from lab.verify.differential import compare, run_sim, normalize_sim

LAYER1_DECIMALS = 6
LAYER1_ABS_BOUND = 1e-8


def assert_layer1_cash(cash: float, canonical: float, exp: dict):
    rule = exp.get("layer1_comparison", {})
    decimals = int(rule.get("decimals", LAYER1_DECIMALS))
    bound = float(rule.get("abs_bound", LAYER1_ABS_BOUND))
    q = Decimal(1).scaleb(-decimals)
    got = Decimal(repr(cash)).quantize(q, rounding=ROUND_HALF_EVEN)
    want = Decimal(repr(canonical)).quantize(q, rounding=ROUND_HALF_EVEN)
    assert got == want, (f"layer-1 mismatch: implementation {cash!r} "
                         f"rounds to {got}, canonical is {want}")
    assert abs(cash - canonical) <= bound, (
        f"layer-1 raw difference {abs(cash - canonical)!r} exceeds "
        f"documented bound {bound!r}")

def _is_engine_fixture(path):
    with open(path) as f:
        return "fixture" in json.load(f)    # component fixtures use "scenario"


GOLDEN = sorted(p for p in glob.glob(os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "golden", "*.json"))
    if _is_engine_fixture(p))               # component fixtures: own tests


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
    assert_layer1_cash(cash, exp["final_cash"], exp)
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
    assert g["review_status"] == "REVIEWED"
