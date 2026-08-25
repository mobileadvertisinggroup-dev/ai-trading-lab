"""Seven-arm orchestrator scaffold tests (spec §3, §23)."""
import numpy as np
import pytest

from lab import protocol as P
from lab.arms.arm_a import ArrayProvider
from lab.orchestration.competition import ARMS, Competition

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)
HIST = 96


def build_symbol(levels_4h, wiggle=0.1):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
            "low": lv - wiggle, "close": lv.copy()}


def make_comp(**kw):
    levels = [100.0] * HIST + [105.0, 105.0] + [108.0] * 3
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"], **kw)
    end = T0 + (len(levels) * 16 - 1) * B15
    return comp, T0, end


def test_all_seven_arms_trade_identical_candidates_with_stubs():
    comp, start, end = make_comp()
    comp.run(start, end)
    # candidate equality BY CONSTRUCTION: one shared ledger; every arm's
    # fills reference exactly those (t, symbol) pairs
    cand_keys = {(c["t"], c["symbol"]) for c in comp.candidates}
    assert cand_keys
    for a in ARMS:
        opens = [e for e in comp.arms[a].engine.events
                 if e["kind"] == "fill_open"]
        assert opens, a
        assert {(e["decision_ts"], e["symbol"]) for e in opens} <= cand_keys
    # with permissive stubs, A/B/C/E/F fills are identical in qty and time
    ref = [(e["t"], e["qty"], e["price"]) for e in
           comp.arms["A"].engine.events if e["kind"] == "fill_open"]
    for a in ("B", "C", "E", "F"):
        got = [(e["t"], e["qty"], e["price"]) for e in
               comp.arms[a].engine.events if e["kind"] == "fill_open"]
        assert got == ref, a
    assert comp.coordinator.counts()["invalid"] == 0


def test_g_shadow_identity_through_entry():
    comp, start, end = make_comp()
    comp.run(start, end)
    g_opens = [(e["t"], e["symbol"], e["qty"], e["price"], e["stop"])
               for e in comp.arms["G"].engine.events
               if e["kind"] == "fill_open"]
    s_opens = [(e["t"], e["symbol"], e["qty"], e["price"], e["stop"])
               for e in comp.shadow.engine.events
               if e["kind"] == "fill_open"]
    assert g_opens and g_opens == s_opens     # constitutional prototype


def test_arm_e_bucket_scales_size():
    class HalfSizer:
        version = "half"
        def bucket(self, cand, features):
            return 0.50
    comp, start, end = make_comp(sizer_model=HalfSizer())
    comp.run(start, end)
    qa = [e["qty"] for e in comp.arms["A"].engine.events
          if e["kind"] == "fill_open"]
    qe = [e["qty"] for e in comp.arms["E"].engine.events
          if e["kind"] == "fill_open"]
    assert qe and qe[0] == pytest.approx(0.5 * qa[0])


def test_arm_d_and_g_block_on_regime():
    class BlockLongs:
        version = "block-longs"
        def classify(self, t):
            return {"regime": "downtrend", "multiplier": {1: 0.0, -1: 1.0},
                    "model_version": self.version}
    comp, start, end = make_comp(regime_model=BlockLongs())
    comp.run(start, end)
    # the breakout is long -> D and G open nothing; A still trades
    assert [e for e in comp.arms["A"].engine.events if e["kind"] == "fill_open"]
    assert not [e for e in comp.arms["D"].engine.events if e["kind"] == "fill_open"]
    assert not [e for e in comp.arms["G"].engine.events if e["kind"] == "fill_open"]
    d_recs = [d for d in comp.arms["D"].decisions if "d_multiplier" in d]
    assert d_recs and all(d["d_multiplier"] == 0.0 for d in d_recs)


def test_arm_b_filter_rejection_recorded_not_traded():
    class RejectAll:
        version = "reject-all"
        def accept(self, cand, features):
            return False, 0.01
    comp, start, end = make_comp(filter_model=RejectAll())
    comp.run(start, end)
    assert not [e for e in comp.arms["B"].engine.events
                if e["kind"] == "fill_open"]
    recs = comp.arms["B"].decisions
    assert recs and all(r["accepted"] is False and "probability" in r
                        and r["model_version"] == "reject-all" for r in recs)


def test_failing_arm_invalidates_round_for_everyone():
    class ExplodingSizer:
        version = "boom"
        def bucket(self, cand, features):
            raise RuntimeError("model unavailable")
    comp, start, end = make_comp(sizer_model=ExplodingSizer())
    comp.run(start, end)
    # every round with candidates failed -> nobody ever opened anything
    for a in ARMS:
        assert not [e for e in comp.arms[a].engine.events
                    if e["kind"] == "fill_open"], a
    counts = comp.coordinator.counts()
    assert counts["invalid"] >= 1
    assert comp.candidates == []              # invalid rounds record nothing
    failed = [r for r in comp.coordinator.records if not r["valid"]]
    assert all("model unavailable" in (list(r["reasons"].values()) or [""])[0]
               for r in failed if r["reasons"])
