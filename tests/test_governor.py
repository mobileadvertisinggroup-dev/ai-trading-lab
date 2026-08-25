"""Risk governor tests (RISK_POLICY.md / SPEC FINAL-1.2 §14) + the deferred
golden fixtures G09 (portfolio loss-limit rejection) and G10 (invalid RL
action), each with hand-derived expectations PENDING INDEPENDENT REVIEW."""
import json
import os

import pytest

from lab.risk.governor import (EntryRequest, PortfolioState, RiskGovernor,
                               RiskLimits, DAY_MS)
from lab.sim.engine import Bar, Costs, Engine

T0 = 1_699_977_600_000          # UTC-day + 4h aligned


def flat_state(equity=10_000.0, **kw):
    d = {"equity": equity, "gross_exposure": 0.0, "long_exposure": 0.0,
         "short_exposure": 0.0, "n_positions": 0}
    d.update(kw)
    return PortfolioState(**d)


def req(**kw):
    d = {"t": T0, "symbol": "A", "side": 1, "qty": 10.0, "price": 100.0,
         "stop_distance": 5.0}
    d.update(kw)
    return EntryRequest(**d)


def test_approve_within_all_limits():
    g = RiskGovernor()
    g.observe(T0, 10_000)
    # risk 10*5=50 = 0.5% of equity, notional 1000 -> approve unchanged
    assert g.check_entry(req(), flat_state()) == ("approve", 10.0, "ok")


def test_risk_per_trade_restriction_never_increases():
    g = RiskGovernor()
    g.observe(T0, 10_000)
    # requested risk 40*5 = 200 = 2% > 1% cap -> qty restricted to 20
    dec, qty, _ = g.check_entry(req(qty=40.0), flat_state())
    assert dec == "restrict" and qty == pytest.approx(20.0)
    # a tiny request is never scaled UP
    dec, qty, _ = g.check_entry(req(qty=1.0), flat_state())
    assert (dec, qty) == ("approve", 1.0)


def test_exposure_and_directional_caps():
    g = RiskGovernor()
    g.observe(T0, 10_000)
    # gross room: 15000-14000=1000 -> qty capped at 10; directional room
    # (long): 12000-9000=3000 not binding
    dec, qty, _ = g.check_entry(
        req(qty=50.0, stop_distance=0.2),
        flat_state(gross_exposure=14_000, long_exposure=9_000,
                   short_exposure=5_000, n_positions=3))
    assert dec == "restrict" and qty == pytest.approx(10.0)
    # directional at exactly min notional: room 50 -> restrict to 0.5
    dec, qty, _ = g.check_entry(
        req(qty=50.0), flat_state(gross_exposure=11_950,
                                  long_exposure=11_950, n_positions=2))
    assert dec == "restrict" and qty == pytest.approx(0.5)
    # below min notional: room 40 < 50 USDT -> reject
    dec, qty, reason = g.check_entry(
        req(qty=50.0), flat_state(gross_exposure=11_960,
                                  long_exposure=11_960, n_positions=2))
    assert dec == "reject" and reason == "insufficient_capacity"


def test_daily_loss_limit_pauses_new_entries_until_next_day():
    g = RiskGovernor()
    g.observe(T0, 10_000)                      # day start
    st = flat_state(equity=9_690)              # -3.1% on the day
    dec, _, reason = g.check_entry(req(t=T0 + 3600_000), st)
    assert (dec, reason) == ("reject", "daily_loss_limit")
    # next UTC day resets the anchor
    g.observe(T0 + DAY_MS, 9_690)
    dec, _, _ = g.check_entry(req(t=T0 + DAY_MS + 60_000),
                              flat_state(equity=9_690))
    assert dec == "approve"


def test_drawdown_limit_and_emergency_and_integrity_pauses():
    g = RiskGovernor()
    g.observe(T0, 10_000)                      # peak
    g.observe(T0 + DAY_MS, 7_400)              # fresh day: no daily-loss trip
    dec, _, reason = g.check_entry(req(t=T0 + DAY_MS + 60_000),
                                   flat_state(equity=7_400))
    assert (dec, reason) == ("reject", "drawdown_limit")   # -26% from peak

    g2 = RiskGovernor()
    g2.observe(T0, 10_000)
    g2.emergency_pause = True
    assert g2.check_entry(req(), flat_state())[0] == "reject"
    assert g2.check_action(T0, "close")        # risk-reducing still allowed
    assert not g2.check_action(T0, "tighten_stop")  # paused: only reductions

    g3 = RiskGovernor()
    g3.observe(T0, 10_000, positions_with_stop=False)   # integrity failure
    dec, _, reason = g3.check_entry(req(), flat_state())
    assert (dec, reason) == ("reject", "integrity_pause")


def test_missing_data_fail_safe_and_stop_requirement():
    g = RiskGovernor()
    g.observe(T0, 10_000)
    assert g.check_entry(req(data_complete=False), flat_state())[2] == \
        "missing_data_fail_safe"
    assert g.check_entry(req(has_protective_stop=False), flat_state())[2] == \
        "no_protective_stop"
    assert g.check_entry(req(stop_distance=0.0), flat_state())[2] == \
        "no_protective_stop"


def test_only_risk_reducing_actions_pass():
    g = RiskGovernor()
    for a in ("hold", "reduce_25", "reduce_50", "close", "tighten_stop",
              "move_stop_breakeven"):
        assert g.check_action(T0, a)
    for a in ("widen_stop", "increase", "remove_protection", "open"):
        assert not g.check_action(T0, a)
    # every decision recorded
    assert len(g.events) == 10


def test_every_decision_is_recorded():
    g = RiskGovernor()
    g.observe(T0, 10_000)
    g.check_entry(req(), flat_state())
    g.check_entry(req(qty=40.0), flat_state())
    g.check_entry(req(data_complete=False), flat_state())
    kinds = [e["kind"] for e in g.events]
    assert kinds == ["governor_approve", "governor_restrict",
                     "governor_reject"]


# ------------------------------------------------- deferred golden fixtures

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures",
                          "golden")


def test_golden_G09_daily_loss_limit_rejection():
    path = os.path.join(GOLDEN_DIR, "G09_loss_limit_rejection.json")
    with open(path) as f:
        g = json.load(f)
    s = g["scenario"]
    gov = RiskGovernor()
    gov.observe(s["day_start_t"], s["day_start_equity"])
    dec, qty, reason = gov.check_entry(
        EntryRequest(**s["entry_request"]), PortfolioState(**s["state"]))
    assert [dec, qty, reason] == g["expected"]["decision"]
    assert g["review_status"] == "PENDING INDEPENDENT REVIEW"


def test_golden_G10_invalid_rl_action():
    path = os.path.join(GOLDEN_DIR, "G10_invalid_rl_action.json")
    with open(path) as f:
        g = json.load(f)
    s = g["scenario"]
    e = Engine(s["starting_cash"])
    e.submit_entry("A", 1, s["qty"], stop=s["stop"], target=s["target"],
                   r_dist=s["r_dist"], decision_ts=T0,
                   costs=Costs(0.0, 0.0, 0.0))
    e.process_bar_time(T0, {"A": Bar(T0, s["px"], s["px"] + 0.1,
                                     s["px"] - 0.1, s["px"])})
    cash_before, stop_before = e.cash, e.positions[1].stop
    for action, new_stop in s["invalid_actions"]:
        assert not e.apply_management_action(T0, 1, action,
                                             new_stop=new_stop)
    # invariant: invalid actions changed NOTHING
    assert e.cash == cash_before == g["expected"]["cash_unchanged"]
    assert e.positions[1].stop == stop_before == g["expected"]["stop_unchanged"]
    assert e.positions[1].open_qty == s["qty"]
    n_invalid = sum(1 for ev in e.events if ev["kind"] == "invalid_action")
    assert n_invalid == len(s["invalid_actions"])
    assert g["review_status"] == "PENDING INDEPENDENT REVIEW"


def test_golden_G11_partial_exit_then_breakeven():
    path = os.path.join(GOLDEN_DIR, "G11_partial_exit_breakeven.json")
    with open(path) as f:
        g = json.load(f)
    s = g["scenario"]
    e = Engine(s["starting_cash"])
    bars = {int(r[0]): Bar(int(r[0]), *r[1:5]) for r in s["bars"]}
    first_t = min(bars)
    e.submit_entry("A", 1, s["qty"], stop=0.0, target=0.0,
                   r_dist=s["stop_offset"], decision_ts=first_t,
                   costs=Costs(0.0, 0.0, 0.0),
                   stop_offset=s["stop_offset"],
                   target_offset=s["target_offset"])
    actions = {}
    for t, a in s["actions"]:
        actions.setdefault(int(t), []).append(a)
    for t in sorted(bars):
        for a in actions.get(t, []):
            assert e.apply_management_action(t, 1, a)
            if a == "move_stop_breakeven":
                assert e.positions[1].stop == g["expected"]["stop_after_breakeven"]
        e.process_bar_time(t, {"A": bars[t]})
    assert e.cash == pytest.approx(g["expected"]["final_cash"])
    closes = [ev for ev in e.events if ev["kind"] == "fill_close"]
    assert len(closes) == len(g["expected"]["closes"])
    for got, want in zip(closes, g["expected"]["closes"]):
        assert got["t"] == want["t"]
        assert got["qty"] == pytest.approx(want["qty"])
        assert got["price"] == pytest.approx(want["price"])
        assert got["pnl"] == pytest.approx(want["pnl"])
        assert got["reason"] == want["reason"]
    assert g["review_status"] == "PENDING INDEPENDENT REVIEW"
