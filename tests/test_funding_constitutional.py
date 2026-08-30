"""D72 blocker A.6 — constitutional funding tests.

Funding is part of the frozen cost model ("after all costs"). These
tests pin, mechanically: sign semantics for long/short with positive/
negative rates; charging on the ACTUAL open quantity after reductions;
close-before vs hold-through a funding boundary; exact equality between
the orchestrator's funding stream and the official ArmARunner's on an
identical scenario; synchronized rollback of funding mutations; both G
diagnostics receiving correct independent funding; reporting-field
reconciliation (events == positions == metric); and the missing-funding
rule staying LOUD (funding_missing events + the activity guard that
stops any implausible all-zero funding window).
"""
import numpy as np
import pytest

from lab import protocol as P
from lab.arms.arm_a import ArmARunner, ArrayProvider
from lab.arms.rl_env import ACTIONS, TradeManagementEnv
from lab.orchestration.competition import Competition
from lab.tools.holdout_evaluator import (funding_activity_guard,
                                         funding_reconciliation,
                                         supporting_metrics)

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
F8 = P.FUNDING_INTERVAL_MS
T0 = (1_700_000_000_000 // F8) * F8          # 8h- (and 4h-) aligned
HIST = 96
RATE = 0.001


def build_symbol(levels_4h, wiggle=0.1):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
            "low": lv - wiggle, "close": lv.copy()}


def scenario(direction=+1, rate=RATE, with_funding=True):
    """One clean breakout (long or short) held across >=2 funding
    boundaries. Returns (provider, start, end)."""
    # one breakout, then a flat plateau at the breakout level: every
    # later boundary close equals the (wiggle-raised) channel extreme,
    # so exactly ONE entry exists — no compounding, and equity deltas
    # between funded and unfunded runs equal the funding transfers
    if direction > 0:
        levels = [100.0] * HIST + [105.0] * 6
    else:
        levels = [100.0] * HIST + [95.0] * 6
    data = {"AAAUSDT": build_symbol(levels)}
    end = T0 + (len(levels) * 16 - 1) * B15
    funding = ({"AAAUSDT": {int(t): rate
                            for t in range(T0, end + 1, F8)}}
               if with_funding else None)
    return ArrayProvider(data, funding=funding), T0, end


def run_comp(direction=+1, rate=RATE, with_funding=True):
    prov, start, end = scenario(direction, rate, with_funding)
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    comp.run(start, end)
    return comp


def funding_events(state):
    return [e for e in state.engine.events if e["kind"] == "funding"]


# ---------------------------------------------- 1-3: sign semantics
def test_long_positive_funding_pays():
    comp = run_comp(+1, RATE)
    st = comp.arms["A"]
    assert sum(1 for e in st.engine.events
               if e["kind"] == "fill_open") == 1     # no compounding
    ev = funding_events(st)
    assert len(ev) >= 2
    assert all(e["paid"] > 0 for e in ev)          # long pays +rate
    # exact equity impact: with-funding equity is lower by exactly sum(paid)
    base = run_comp(+1, RATE, with_funding=False)
    paid = sum(e["paid"] for e in ev)
    assert paid > 0
    diff = (base.arms["A"].engine.equity({"AAAUSDT": 105.0})
            - st.engine.equity({"AAAUSDT": 105.0}))
    assert abs(diff - paid) < 1e-9


def test_short_positive_funding_receives():
    comp = run_comp(-1, RATE)
    ev = funding_events(comp.arms["A"])
    assert len(ev) >= 2
    assert all(e["paid"] < 0 for e in ev)          # short receives +rate
    assert sum(1 for e in comp.arms["A"].engine.events
               if e["kind"] == "fill_open") == 1
    base = run_comp(-1, RATE, with_funding=False)
    paid = sum(e["paid"] for e in ev)
    diff = (base.arms["A"].engine.equity({"AAAUSDT": 95.0})
            - comp.arms["A"].engine.equity({"AAAUSDT": 95.0}))
    assert abs(diff - paid) < 1e-9 and paid < 0


def test_negative_funding_reverses_both_sides():
    lng = run_comp(+1, -RATE)
    assert all(e["paid"] < 0 for e in funding_events(lng.arms["A"]))
    sht = run_comp(-1, -RATE)
    assert all(e["paid"] > 0 for e in funding_events(sht.arms["A"]))


def test_funding_transfer_arithmetic_exact():
    comp = run_comp(+1, RATE)
    for e in funding_events(comp.arms["A"]):
        p = comp.arms["A"].engine.positions[e["pos_id"]]
        assert e["rate"] == RATE
        assert abs(e["paid"] - RATE * e["mark"]
                   * (e["paid"] / (RATE * e["mark"]))) < 1e-12
        # paid = rate * open_qty * mark * side; recover qty and check
        qty = e["paid"] / (RATE * e["mark"] * p.side)
        assert qty > 0


# ------------------------------- 4-5: reductions and close timing (env)
def env_episode(actions_at_decisions, rate=RATE, n4=6):
    """Single-position env episode: entry at T0+15m, flat 100 bars,
    funding boundaries at every 8h multiple; scripted actions."""
    t = np.arange(T0 + B15, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    bars = [(int(x), 100.0, 100.1, 99.9, 100.0) for x in t]
    fb = {int(b): rate for b in range(T0, int(t[-1]) + 1, F8)}
    trade = {"side": +1, "qty": 4.0, "entry_ref": 100.0, "r_dist": 5.0,
             "decision_ts": T0, "atr_entry": 2.5,
             "funding_by_time": fb,
             "costs": {"hs": 0.0, "slip": 0.0, "fee": 0.0}}
    env = TradeManagementEnv(trade, bars)
    obs, _ = env.reset(seed=0)
    k = 0
    while True:
        a = (actions_at_decisions[k] if k < len(actions_at_decisions)
             else ACTIONS.index("hold"))
        k += 1
        obs, reward, term, trunc, _ = env.step(a)
        if term or trunc:
            return env, reward


def test_reduction_before_funding_boundary_charges_open_qty():
    env, _ = env_episode([ACTIONS.index("reduce_50")])
    ev = [e for e in env.engine.events if e["kind"] == "funding"]
    assert ev, "no funding applied in episode"
    # every funding transfer must equal rate x CURRENT open_qty x mark
    for e in ev:
        implied_qty = e["paid"] / (RATE * e["mark"])
        assert abs(implied_qty - 2.0) < 1e-9, \
            "funding charged on pre-reduction quantity"
    full, _ = env_episode([])           # no reduction: charged on 4.0
    ev_full = [e for e in full.engine.events if e["kind"] == "funding"]
    assert abs(ev_full[0]["paid"] / (RATE * ev_full[0]["mark"]) - 4.0) \
        < 1e-9


def test_close_before_vs_after_funding_boundary():
    closed, _ = env_episode([ACTIONS.index("close")])
    held, _ = env_episode([])
    ev_closed = [e for e in closed.engine.events if e["kind"] == "funding"]
    ev_held = [e for e in held.engine.events if e["kind"] == "funding"]
    assert not ev_closed, "closed-before-boundary position paid funding"
    assert ev_held and held.engine.positions[1].funding_paid > 0
    assert closed.engine.positions[1].funding_paid == 0.0


def test_env_reward_reflects_funding():
    _, r_no = env_episode([], rate=0.0)
    _, r_pos = env_episode([], rate=RATE)
    assert r_pos < r_no                 # long pays positive funding


# ------------------------------------ 6: exact equality with ArmARunner
def test_orchestrator_funding_equals_armarunner_exactly():
    prov, start, end = scenario(+1, RATE)
    runner = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    runner.run(start, end)
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    comp.run(start, end)
    key = lambda e: (e["t"], e["symbol"], e["rate"], e["mark"], e["paid"])  # noqa: E731
    r_ev = [key(e) for e in runner.engine.events if e["kind"] == "funding"]
    c_ev = [key(e) for e in comp.arms["A"].engine.events
            if e["kind"] == "funding"]
    assert r_ev, "ArmARunner scenario produced no funding"
    assert r_ev == c_ev


# --------------------------- 7: synchronized rollback after funding
def test_rollback_restores_funding_state_exactly():
    comp = run_comp(+1, RATE)
    st = comp.arms["A"]
    pre_cash = st.engine.cash
    pre_paid = {pid: p.funding_paid
                for pid, p in st.engine.positions.items()}
    pre_events = len(st.engine.events)
    snap = st.snapshot()
    # mutate: one more funding boundary applied directly
    t_next = ((st.engine.events[-1]["t"] // F8) + 1) * F8
    from lab.sim.engine import Bar
    bar = Bar(t_next, 108.0, 108.1, 107.9, 108.0)
    st.engine.process_bar_time(t_next, {"AAAUSDT": bar},
                               funding={"AAAUSDT": RATE},
                               prev_close={"AAAUSDT": 108.0})
    assert st.engine.cash != pre_cash          # funding mutated state
    st.rollback(snap)
    assert st.engine.cash == pre_cash
    assert len(st.engine.events) == pre_events
    assert {pid: p.funding_paid
            for pid, p in st.engine.positions.items()} == pre_paid


# ------------------------- 8: G diagnostics independent correct funding
def test_g_diagnostics_receive_correct_independent_funding():
    comp = run_comp(+1, RATE)
    key = lambda e: (e["t"], e["symbol"], e["rate"], e["mark"], e["paid"])  # noqa: E731
    g_ev = [key(e) for e in comp.arms["G"].engine.events
            if e["kind"] == "funding"]
    m_ev = [key(e) for e in comp.shadow_matched.engine.events
            if e["kind"] == "funding"]
    f_ev = [key(e) for e in comp.shadow_feasible.engine.events
            if e["kind"] == "funding"]
    assert g_ev, "G held no position across a funding boundary"
    # matched diagnostic: identical clone -> identical funding stream,
    # recorded INDEPENDENTLY in its own engine
    assert m_ev == g_ev
    assert comp.shadow_matched.engine is not comp.arms["G"].engine
    # feasible diagnostic: own account, same frozen rates
    assert f_ev and all(e[2] == RATE for e in f_ev)
    rec = funding_reconciliation(comp.shadow_feasible.engine.events,
                                 comp.shadow_feasible.engine.positions)
    assert rec["event_to_equity_reconciled"]


# ------------------------------- 9: reporting-field reconciliation
def test_reporting_field_reconciliation():
    comp = run_comp(+1, RATE)
    st = comp.arms["A"]
    curve = np.array([r["equity"] for r in st.equity_curve])
    m = supporting_metrics(curve, st.engine.events, st.engine.positions)
    rec = funding_reconciliation(st.engine.events, st.engine.positions)
    paid_events = sum(e["paid"] for e in funding_events(st))
    paid_positions = sum(p.funding_paid
                         for p in st.engine.positions.values())
    assert abs(paid_events - paid_positions) < 1e-9
    assert abs(m["funding_net"] - (-paid_events)) < 1e-12
    assert abs(rec["funding_net"] - (-paid_events)) < 1e-12
    assert rec["event_to_equity_reconciled"]
    assert rec["n_applied"] == len(funding_events(st))
    assert rec["by_symbol"]["AAAUSDT"]["applied"] == rec["n_applied"]
    assert rec["by_side"]["long_paid"] > 0


# ------------------------------------- 10: missing funding stays loud
def test_missing_funding_stays_loud():
    comp = run_comp(+1, RATE, with_funding=False)
    st = comp.arms["A"]
    missing = [e for e in st.engine.events
               if e["kind"] == "funding_missing"]
    assert missing, "missing funding was silent"
    assert not funding_events(st)
    rec = funding_reconciliation(st.engine.events, st.engine.positions)
    assert rec["n_missing"] == len(missing) and rec["n_applied"] == 0
    assert rec["by_symbol"]["AAAUSDT"]["missing"] == len(missing)


def test_funding_activity_guard_stops_implausible_zeros():
    # crossings but nothing applied over a multi-month active window
    bad1 = {"n_applied": 0, "n_missing": 400, "n_boundary_crossings": 400,
            "total_paid": 0.0}
    ok, why = funding_activity_guard(bad1, span_days=120,
                                     n_closed_trades=300)
    assert not ok and "ZERO rates applied" in why
    # applied payments summing to exactly zero
    bad2 = {"n_applied": 500, "n_missing": 0, "n_boundary_crossings": 500,
            "total_paid": 0.0}
    ok, why = funding_activity_guard(bad2, 120, 300)
    assert not ok and "exactly 0.0" in why
    # no crossings at all despite months of trading
    bad3 = {"n_applied": 0, "n_missing": 0, "n_boundary_crossings": 0,
            "total_paid": 0.0}
    ok, why = funding_activity_guard(bad3, 120, 300)
    assert not ok and "implausible" in why
    # legitimate active funding passes
    good = {"n_applied": 500, "n_missing": 3, "n_boundary_crossings": 503,
            "total_paid": 12.34}
    ok, _ = funding_activity_guard(good, 120, 300)
    assert ok
    # small windows / few trades are exempt (honest small fixtures)
    ok, _ = funding_activity_guard(bad1, span_days=3, n_closed_trades=2)
    assert ok


# =====================================================================
# D74 — G_matched ENTRY-BAR funding exemption (staggered-entry blocker)
#
# Failure case (V5): at funding boundary t another engine already holds
# X, so the shared frozen map contains X; G actual has no X before t,
# fills a NEW X entry ON t, and pays no entry-bar funding (engine order
# funding -> exits -> entries). The mirrored clone, created before the
# matched engine processes bar t, was ALREADY OPEN at its funding phase
# and paid entry-bar funding G actual did not. The exemption is
# POSITION-LEVEL: clone_open stamps the clone's entry bar, and
# _process_funding skips exactly that bar for exactly that position —
# no symbol-level workaround, no change to any actual arm's behavior.
# =====================================================================
class StaggerFilter:
    """Rejects every candidate at the designated boundaries (delaying
    B's and G's entries onto a later funding boundary); accepts all
    other candidates."""
    version = "stub-stagger"

    def __init__(self, reject_at: set[int]):
        self.reject_at = set(int(t) for t in reject_at)

    def accept(self, cand, features):
        if int(cand["t"]) in self.reject_at:
            return False, 0.0
        return True, 1.0


def staggered_scenario(rate=RATE):
    """AAAUSDT: breakout bar at 4h index 96 (candidate at boundary 97,
    REJECTED for B/G — arm A enters and holds), second breakout bar at
    index 97 (candidate at boundary 98 — an 8h FUNDING boundary since
    T0 is 8h-aligned and 98 is even — ACCEPTED, so G first fills X on a
    funding boundary while A already holds X and the shared map
    contains X)."""
    levels = [100.0] * HIST + [105.0, 110.0, 110.0, 110.0, 110.0, 110.0]
    data = {"AAAUSDT": build_symbol(levels)}
    end = T0 + (len(levels) * 16 - 1) * B15
    t_reject = T0 + 97 * H4                  # first candidate boundary
    t_entry = T0 + 98 * H4                   # G's entry: 8h boundary
    assert t_entry % F8 == 0 and t_reject % F8 != 0
    funding = {"AAAUSDT": {int(t): rate
                           for t in range(T0, end + 1, F8)}}
    prov = ArrayProvider(data, funding=funding)
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"],
                       filter_model=StaggerFilter({t_reject}))
    comp.run(T0, end)
    return comp, t_entry


def _sym_funding(state, sym="AAAUSDT"):
    return [(e["t"], e["symbol"], e["rate"], e["mark"], e["paid"],
             e["pos_id"])
            for e in state.engine.events
            if e["kind"] == "funding" and e["symbol"] == sym]


def test_staggered_entry_bar_funding_exemption_matched_equals_g():
    """THE D74 regression: proven to FAIL under the V5 ordering and to
    PASS with the position-level entry-bar exemption."""
    comp, t_entry = staggered_scenario()
    g, m = comp.arms["G"], comp.shadow_matched
    # G actual entered X exactly at the funding boundary t_entry, while
    # arm A already held X (so the shared map contained X at t_entry)
    g_opens = [e for e in g.engine.events if e["kind"] == "fill_open"]
    assert [e["t"] for e in g_opens] == [t_entry]
    a_funding_at_entry = [e for e in comp.arms["A"].engine.events
                          if e["kind"] == "funding"
                          and e["t"] == t_entry]
    assert a_funding_at_entry, "arm A did not hold X across t_entry"
    # BOTH G actual and the matched clone record ZERO funding at the
    # entry bar for the new position...
    assert [e for e in _sym_funding(g) if e[0] == t_entry] == []
    assert [e for e in _sym_funding(m) if e[0] == t_entry] == []
    # ...and NO funding_missing either (G actual's position did not
    # exist at the funding phase; the clone must behave identically)
    assert not [e for e in m.engine.events
                if e["kind"] == "funding_missing" and e["t"] == t_entry]
    # later funding boundaries reconcile normally and identically
    g_later = [e[:5] for e in _sym_funding(g) if e[0] > t_entry]
    m_later = [e[:5] for e in _sym_funding(m) if e[0] > t_entry]
    assert g_later and g_later == m_later
    # same-bar entry semantics remain identical (fill + protection +
    # position state on the entry bar)
    def fills(st):
        return [(e["t"], e["symbol"], e["side"], e["qty"], e["price"],
                 e["stop"], e["target"]) for e in st.engine.events
                if e["kind"] == "fill_open"]
    assert fills(g) == fills(m)
    gp = [p for p in g.engine.positions.values()][-1]
    mp = [p for p in m.engine.positions.values()][-1]
    assert (gp.mae, gp.mfe, gp.stop, gp.target, gp.open_qty) == \
        (mp.mae, mp.mfe, mp.stop, mp.target, mp.open_qty)
    assert gp.funding_paid == mp.funding_paid
    # full reconciliation still holds in the matched engine
    rec = funding_reconciliation(m.engine.events, m.engine.positions)
    assert rec["event_to_equity_reconciled"]


def test_preexisting_matched_positions_still_funded_normally():
    """A clone held from an EARLIER bar pays funding at later
    boundaries exactly like G actual (exemption is entry-bar only)."""
    comp = run_comp(+1, RATE)          # G and arms enter together
    g_ev = [e[:5] for e in _sym_funding(comp.arms["G"])]
    m_ev = [e[:5] for e in _sym_funding(comp.shadow_matched)]
    assert g_ev and g_ev == m_ev       # every later boundary charged


def test_exemption_is_entry_bar_only():
    comp, t_entry = staggered_scenario()
    m = comp.shadow_matched
    later = [e for e in _sym_funding(m) if e[0] > t_entry]
    assert later, "clone never funded after its entry bar"
    p = m.engine.positions[later[0][5]]
    assert p.funding_paid == sum(e[4] for e in later
                                 if e[5] == later[0][5])
    assert p.funding_paid > 0          # long, positive rate


def test_mixed_preexisting_and_new_clones_multi_symbol():
    """Two symbols: X staggered (G enters at the 8h boundary t_e while
    A holds X), Y entered by everyone earlier. At t_e the matched book
    holds a PRE-EXISTING Y clone (charged) and a NEW X clone (exempt)."""
    x_levels = [100.0] * HIST + [105.0, 110.0, 110.0, 110.0, 110.0,
                                 110.0]
    y_levels = [100.0] * HIST + [105.0, 105.0, 105.0, 105.0, 105.0,
                                 105.0]
    data = {"XXXUSDT": build_symbol(x_levels),
            "YYYUSDT": build_symbol(y_levels)}
    end = T0 + (len(x_levels) * 16 - 1) * B15
    t_reject = T0 + 97 * H4
    t_e = T0 + 98 * H4
    funding = {s: {int(t): RATE for t in range(T0, end + 1, F8)}
               for s in data}

    class RejectXAtFirst:
        version = "stub-reject-x-first"

        def accept(self, cand, features):
            if cand["symbol"] == "XXXUSDT" and int(cand["t"]) == t_reject:
                return False, 0.0
            return True, 1.0

    comp = Competition(ArrayProvider(data, funding=funding), 10_000,
                       universe_fn=lambda t: sorted(data),
                       filter_model=RejectXAtFirst())
    comp.run(T0, end)
    m = comp.shadow_matched
    x_at_te = [e for e in _sym_funding(m, "XXXUSDT") if e[0] == t_e]
    y_at_te = [e for e in _sym_funding(m, "YYYUSDT") if e[0] == t_e]
    assert x_at_te == [], "NEW X clone paid entry-bar funding"
    assert y_at_te, "pre-existing Y clone was not charged at t_e"
    # and G actual agrees on both
    assert [e for e in _sym_funding(comp.arms["G"], "XXXUSDT")
            if e[0] == t_e] == []
    assert [e[:5] for e in _sym_funding(comp.arms["G"], "YYYUSDT")
            if e[0] == t_e] == [e[:5] for e in y_at_te]


def test_rollback_restores_exemption_state_exactly():
    comp, t_entry = staggered_scenario()
    m = comp.shadow_matched
    clone = [p for p in m.engine.positions.values()][-1]
    stamp = clone.clone_entry_bar_ms
    assert stamp == t_entry            # the exemption stamp exists
    pre_paid = {pid: p.funding_paid
                for pid, p in m.engine.positions.items()}
    snap = m.snapshot()
    from lab.sim.engine import Bar
    t_next = ((max(e["t"] for e in m.engine.events) // F8) + 1) * F8
    m.engine.process_bar_time(t_next,
                              {"AAAUSDT": Bar(t_next, 110.0, 110.1,
                                              109.9, 110.0)},
                              funding={"AAAUSDT": RATE},
                              prev_close={"AAAUSDT": 110.0})
    assert {pid: p.funding_paid
            for pid, p in m.engine.positions.items()} != pre_paid
    m.rollback(snap)
    assert {pid: p.funding_paid
            for pid, p in m.engine.positions.items()} == pre_paid
    restored = m.engine.positions[clone.pos_id]
    assert restored.clone_entry_bar_ms == stamp   # stamp survives


def test_diagnostics_on_off_g_actual_byte_identical_staggered():
    """The exemption lives ONLY in diagnostic clones: with diagnostics
    disabled, G actual's ledgers are byte-identical on the exact
    staggered funding scenario."""
    import json as _json

    def run(diag):
        levels = [100.0] * HIST + [105.0, 110.0, 110.0, 110.0, 110.0,
                                   110.0]
        data = {"AAAUSDT": build_symbol(levels)}
        end = T0 + (len(levels) * 16 - 1) * B15
        funding = {"AAAUSDT": {int(t): RATE
                               for t in range(T0, end + 1, F8)}}
        comp = Competition(ArrayProvider(data, funding=funding), 10_000,
                           universe_fn=lambda t: ["AAAUSDT"],
                           filter_model=StaggerFilter({T0 + 97 * H4}),
                           diagnostics=diag)
        comp.run(T0, end)
        return {a: _json.dumps({"events": st.engine.events,
                                "decisions": st.decisions,
                                "equity": st.equity_curve},
                               sort_keys=True, default=float)
                for a, st in comp.arms.items()}

    assert run(True) == run(False)
