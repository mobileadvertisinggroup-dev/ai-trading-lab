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


# D61 blocker A: the single G-shadow strict-identity test is REPLACED by
# the two versioned diagnostics' constitutional properties (adjudicated
# amendment; the original strict check's SD-GSHADOW failure is preserved
# permanently in data/shakedown_v2/).

def _fills(state):
    return [(e["t"], e["symbol"], e["side"], e["qty"], e["price"],
             e["stop"], e["target"])
            for e in state.engine.events if e["kind"] == "fill_open"]


def test_g_matched_diagnostic_exact_fill_identity():
    """Constitutional: the matched-entry diagnostic clones EVERY actual
    G fill at the identical timestamp, symbol, side, quantity, price,
    and initial protection."""
    comp, start, end = make_comp()
    comp.run(start, end)
    g = _fills(comp.arms["G"])
    m = _fills(comp.shadow_matched)
    assert g and g == m


def test_g_feasible_divergence_fully_explained():
    """Every candidate the feasible counterfactual did NOT submit has a
    recorded stage in its decision ledger; every submitted-but-unfilled
    entry has a governor rejection or an engine rejection/cancellation
    event — divergence from G actual is fully explained, never silent."""
    comp, start, end = make_comp()
    comp.run(start, end)
    feas = comp.shadow_feasible
    by_key = {}
    for r in feas.decisions:
        by_key.setdefault((r["t"], r["symbol"]), r)
    for c in comp.candidates:
        assert (c["t"], c["symbol"]) in by_key, c
    filled = {(e["decision_ts"], e["symbol"]) for e in feas.engine.events
              if e["kind"] == "fill_open"}
    explained = {"already_open", "filter_rejected", "rank_cut",
                 "regime_blocked"}
    for key, r in by_key.items():
        if key in filled:
            continue
        if r["stage"] == "submitted":
            assert r.get("governor") == "reject" or any(
                e["kind"] in ("rejection", "entry_cancelled")
                and e.get("decision_ts") == key[0]
                and e.get("symbol") == key[1]
                for e in feas.engine.events), r
        else:
            assert r["stage"] in explained, r


def test_diagnostics_change_nothing_about_g_actual():
    """G actual (and every other arm) with diagnostics enabled is
    BYTE-IDENTICAL to a run with no diagnostic ledgers at all —
    decisions, capacity, execution, events, cash, governor streams."""
    on, start, end = make_comp()
    off, _, _ = make_comp(diagnostics=False)
    on.run(start, end)
    off.run(start, end)
    for a in ARMS:
        s1, s2 = on.arms[a], off.arms[a]
        assert s1.engine.events == s2.engine.events, a
        assert s1.engine.cash == s2.engine.cash, a
        assert s1.decisions == s2.decisions, a
        assert s1.rl_decisions == s2.rl_decisions, a
        assert s1.governor.events == s2.governor.events, a
        assert {pid: vars(p) for pid, p in s1.engine.positions.items()} \
            == {pid: vars(p) for pid, p in s2.engine.positions.items()}, a
    assert on.candidates == off.candidates


def _entry_bar_scenario(entry_open, entry_high, entry_low, entry_close):
    """Breakout at boundary HIST+1; the FIRST 15m bar of the next 4h
    period (the entry bar) is customized so same-bar protection fires."""
    levels = [100.0] * HIST + [105.0] + [105.0] * 3
    data = build_symbol(levels)
    i = (HIST + 1) * 16                     # entry bar index
    data["open"][i] = entry_open
    data["high"][i] = entry_high
    data["low"][i] = entry_low
    data["close"][i] = entry_close
    prov = ArrayProvider({"AAAUSDT": data})
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    end = T0 + (len(levels) * 16 - 1) * B15
    comp.run(T0, end)
    return comp


def _entry_and_close(state):
    opens = [e for e in state.engine.events if e["kind"] == "fill_open"]
    closes = [e for e in state.engine.events if e["kind"] == "fill_close"]
    return opens, closes


def test_g_matched_same_bar_stop_after_entry():
    """D63 blocker 3 (constitutional): when G actual's entry bar itself
    hits the protective stop, the matched clone experiences the SAME
    same-bar stop under exact engine semantics — identical close time,
    fill price, and realized economics."""
    comp = _entry_bar_scenario(105.0, 105.2, 100.5, 101.0)
    g_opens, g_closes = _entry_and_close(comp.arms["G"])
    m_opens, m_closes = _entry_and_close(comp.shadow_matched)
    assert g_opens and m_opens
    t_entry = g_opens[0]["t"]
    # G actual stopped out on the entry bar itself
    assert g_closes and g_closes[0]["t"] == t_entry, g_closes[:1]
    # the matched clone did too — identical time, price, quantity
    assert m_closes and m_closes[0]["t"] == t_entry, m_closes[:1]
    for k in ("t", "price", "qty"):
        assert m_closes[0][k] == g_closes[0][k], (k, g_closes[0],
                                                  m_closes[0])
    gp = comp.arms["G"].engine.positions[g_opens[0]["pos_id"]]
    mp = comp.shadow_matched.engine.positions[m_opens[0]["pos_id"]]
    assert mp.closed and gp.closed
    assert mp.realized_pnl == gp.realized_pnl
    assert mp.mae == gp.mae and mp.mfe == gp.mfe


def test_g_matched_same_bar_target_after_entry():
    """Same-bar TARGET on the entry bar clones identically."""
    comp = _entry_bar_scenario(105.0, 108.5, 104.9, 108.0)
    g_opens, g_closes = _entry_and_close(comp.arms["G"])
    m_opens, m_closes = _entry_and_close(comp.shadow_matched)
    assert g_opens and m_opens
    t_entry = g_opens[0]["t"]
    assert g_closes and g_closes[0]["t"] == t_entry
    assert m_closes and m_closes[0]["t"] == t_entry
    for k in ("t", "price", "qty"):
        assert m_closes[0][k] == g_closes[0][k]
    gp = comp.arms["G"].engine.positions[g_opens[0]["pos_id"]]
    mp = comp.shadow_matched.engine.positions[m_opens[0]["pos_id"]]
    assert mp.realized_pnl == gp.realized_pnl


class _TightenReducePolicy:
    """Nontrivial RL management: tighten, then reduce, then hold."""
    version = "test-tighten-reduce"

    def __init__(self):
        self.k = 0

    def action_from_obs(self, obs):
        a = ("tighten_stop", "reduce_25", "hold")[self.k % 3]
        self.k += 1
        return a


def test_g_matched_rl_management_does_not_propagate():
    """Later stop tightening and reductions on G actual must NOT touch
    the matched clone (it manages conventionally) while entry fills stay
    identical — the whole point of matched trade-level attribution."""
    levels = [100.0] * HIST + [105.0, 105.5, 106.0, 106.5, 106.0, 106.5,
                               107.0, 106.5, 106.0]
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels, wiggle=0.4)})
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"],
                       rl_policy=_TightenReducePolicy())
    end = T0 + (len(levels) * 16 - 1) * B15
    comp.run(T0, end)
    assert _fills(comp.arms["G"]) == _fills(comp.shadow_matched)
    g_tight = [e for e in comp.arms["G"].engine.events
               if e["kind"] == "stop_tightened"]
    g_reduce = [e for e in comp.arms["G"].engine.events
                if e["kind"] == "fill_close"
                and e.get("reason") == "rl_reduce_25"]
    assert g_tight and g_reduce, "scenario must exercise RL management"
    m_ev = comp.shadow_matched.engine.events
    assert not [e for e in m_ev if e["kind"] == "stop_tightened"]
    assert not [e for e in m_ev if e["kind"] == "fill_close"
                and str(e.get("reason", "")).startswith("rl_")]
    g_open = [e for e in comp.arms["G"].engine.events
              if e["kind"] == "fill_open"][0]
    mp = comp.shadow_matched.engine.positions[1]
    assert mp.stop == g_open["stop"], "clone keeps the INITIAL protection"


def test_g_matched_over_cap_recorded_explicitly():
    """Cloning past the ten-position cap emits diagnostic_over_cap
    rather than silently rejecting (the matched book is a diagnostic,
    not a feasibility claim)."""
    from lab.sim.engine import Costs, Engine
    eng = Engine(1_000_000.0)
    c = Costs(0.0005, 0.0005)
    for i in range(11):
        eng.clone_open(T0, f"S{i:02d}USDT", 1, 1.0, 100.0, 98.0, 106.0,
                       2.0, T0 - B15, c)
    over = [e for e in eng.events if e["kind"] == "diagnostic_over_cap"]
    assert over and over[-1]["n_open"] == 11 and over[-1]["cap"] == 10
    assert sum(1 for e in eng.events if e["kind"] == "fill_open"
               and e.get("cloned")) == 11


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
