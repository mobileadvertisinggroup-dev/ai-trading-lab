"""Development tests for the main simulator engine (SIMULATOR_SEMANTICS.md).

Golden fixtures with independently reviewed expected values come in Phase 5;
these development tests verify the engine's mechanics against hand-computed
arithmetic at development precision.
"""
import math

import pytest

from lab import protocol as P
from lab.sim.engine import Bar, Costs, Engine

C0 = Costs(half_spread=0.0, slippage=0.0, fee=0.0)      # cost-free
CF = Costs(half_spread=0.001, slippage=0.0005, fee=P.TAKER_FEE)
T0 = 1_000_000_000_000 - (1_000_000_000_000 % P.BAR_4H_MS)
B15 = P.BAR_15M_MS


def bar(t, o, h, l, c):
    return Bar(t, o, h, l, c)


def test_long_wins_exactly_2R_costfree():
    e = Engine(10_000)
    # entry 100, Rdist 5 -> stop 95, target(+3R) 115; exit at +2R via market
    e.submit_entry("A", +1, qty=10, stop=95, target=115, r_dist=5,
                   decision_ts=T0, costs=C0)
    e.process_bar_time(T0, {"A": bar(T0, 100, 101, 99, 100)})
    p = e.positions[1]
    assert p.entry_fill == 100 and not p.closed
    e.submit_exit(1, 1.0, "test_exit")
    e.process_bar_time(T0 + B15, {"A": bar(T0 + B15, 110, 111, 109, 110)})
    assert e.positions[1].closed
    assert e.cash == pytest.approx(10_000 + 10 * 10)   # +2R = +100
    assert e.positions[1].realized_pnl == pytest.approx(100)


def test_short_loses_exactly_1R_on_stop_costfree():
    e = Engine(10_000)
    # short entry 100, Rdist 5 -> stop 105 (a 1R loss when hit)
    e.submit_entry("A", -1, qty=10, stop=105, target=85, r_dist=5,
                   decision_ts=T0, costs=C0)
    e.process_bar_time(T0, {"A": bar(T0, 100, 106, 99, 105)})
    p = e.positions[1]
    assert p.closed and p.close_reason == "stop"
    assert p.realized_pnl == pytest.approx(-50)        # -1R = -0.75%... -5*10
    assert e.cash == pytest.approx(9_950)


def test_costs_make_gross_winner_net_loser():
    e = Engine(10_000)
    e.submit_entry("A", +1, qty=100, stop=95, target=200, r_dist=5,
                   decision_ts=T0, costs=CF)
    e.process_bar_time(T0, {"A": bar(T0, 100, 100.5, 99.9, 100.2)})
    entry_fill = 100 * (1 + 0.0015)
    assert e.positions[1].entry_fill == pytest.approx(entry_fill)
    # price rises 0.2% gross — less than round-trip costs
    e.submit_exit(1, 1.0, "test_exit")
    e.process_bar_time(T0 + B15, {"A": bar(T0 + B15, 100.2, 100.3, 100.1, 100.2)})
    exit_fill = 100.2 * (1 - 0.0015)
    gross = 100 * (100.2 - 100)
    net = (100 * (exit_fill - entry_fill)
           - 100 * entry_fill * P.TAKER_FEE - 100 * exit_fill * P.TAKER_FEE)
    assert gross > 0 > net
    assert e.cash - 10_000 == pytest.approx(net)


def test_intrabar_ambiguity_takes_stop_first():
    e = Engine(10_000)
    e.submit_entry("A", +1, qty=10, stop=95, target=105, r_dist=5,
                   decision_ts=T0, costs=C0)
    # one bar spans both stop and target
    e.process_bar_time(T0, {"A": bar(T0, 100, 106, 94, 100)})
    p = e.positions[1]
    assert p.closed and p.close_reason == "stop"
    assert any(ev["kind"] == "ambiguity" and ev["rule"] == "stop_first"
               for ev in e.events)


def test_stop_market_pays_double_slippage():
    e = Engine(10_000)
    c = Costs(half_spread=0.001, slippage=0.0005, fee=0.0)
    e.submit_entry("A", +1, qty=10, stop=95, target=115, r_dist=5,
                   decision_ts=T0, costs=c)
    e.process_bar_time(T0, {"A": bar(T0, 100, 100, 94, 95)})
    fill_close = [ev for ev in e.events if ev["kind"] == "fill_close"][0]
    assert fill_close["price"] == pytest.approx(95 * (1 - 0.001 - 2 * 0.0005))


def test_capacity_and_count_rejections_change_nothing():
    e = Engine(10_000, max_positions=2, max_gross_exposure=1.5)
    # two positions of 7000 notional each = 14000 <= 15000 cap: OK
    for sym in ("A", "B"):
        e.submit_entry(sym, +1, qty=70, stop=95, target=200, r_dist=5,
                       decision_ts=T0, costs=C0)
    # third: violates BOTH count cap and capacity
    e.submit_entry("C", +1, qty=70, stop=95, target=200, r_dist=5,
                   decision_ts=T0, costs=C0)
    bars = {s: bar(T0, 100, 100, 100, 100) for s in "ABC"}
    cash_before = e.cash
    e.process_bar_time(T0, bars)
    assert len(e.open_positions()) == 2
    rej = [ev for ev in e.events if ev["kind"] == "rejection"]
    assert len(rej) == 1 and rej[0]["symbol"] == "C"
    assert rej[0]["reason"] == "max_positions"
    assert e.cash == cash_before  # cost-free entries; rejection changed nothing

    # exposure-cap rejection (count below cap)
    e2 = Engine(10_000, max_positions=10, max_gross_exposure=1.5)
    e2.submit_entry("A", +1, qty=100, stop=95, target=200, r_dist=5,
                    decision_ts=T0, costs=C0)   # 10k notional
    e2.submit_entry("B", +1, qty=60, stop=95, target=200, r_dist=5,
                    decision_ts=T0, costs=C0)   # +6k > 15k cap
    e2.process_bar_time(T0, {s: bar(T0, 100, 100, 100, 100) for s in "AB"})
    rej2 = [ev for ev in e2.events if ev["kind"] == "rejection"]
    assert len(rej2) == 1 and rej2[0]["reason"] == "capacity"


def test_min_notional_rejection():
    e = Engine(10_000)
    e.submit_entry("A", +1, qty=0.4, stop=95, target=115, r_dist=5,
                   decision_ts=T0, costs=C0)   # 40 USDT < 50
    e.process_bar_time(T0, {"A": bar(T0, 100, 100, 100, 100)})
    assert [ev["reason"] for ev in e.events if ev["kind"] == "rejection"] \
        == ["min_notional"]
    assert not e.open_positions()


def test_partial_exits_and_invalid_actions():
    e = Engine(10_000)
    e.submit_entry("A", +1, qty=8, stop=95, target=115, r_dist=5,
                   decision_ts=T0, costs=C0)
    e.process_bar_time(T0, {"A": bar(T0, 100, 101, 99, 100)})
    assert e.apply_management_action(T0, 1, "reduce_50")
    e.process_bar_time(T0 + B15, {"A": bar(T0 + B15, 102, 103, 101, 102)})
    p = e.positions[1]
    assert p.open_qty == pytest.approx(4)
    assert p.realized_pnl == pytest.approx(4 * 2)
    # partial never exceeds open quantity; qty never negative
    assert e.apply_management_action(T0, 1, "reduce_50")
    e.process_bar_time(T0 + 2 * B15, {"A": bar(T0 + 2 * B15, 102, 102, 102, 102)})
    assert e.positions[1].open_qty == pytest.approx(2)

    # invalid: widening the stop
    assert not e.apply_management_action(T0, 1, "tighten_stop", new_stop=90)
    # invalid: "tighten" past the mark
    assert not e.apply_management_action(T0, 1, "tighten_stop", new_stop=150)
    # valid tighten
    assert e.apply_management_action(T0, 1, "tighten_stop", new_stop=99)
    assert e.positions[1].stop == 99
    # breakeven tighten (entry 100 < mark 102)
    assert e.apply_management_action(T0, 1, "move_stop_breakeven")
    assert e.positions[1].stop == 100
    # unknown + closed-position actions rejected
    assert not e.apply_management_action(T0, 1, "widen_stop")
    assert e.apply_management_action(T0, 1, "close")
    e.process_bar_time(T0 + 3 * B15, {"A": bar(T0 + 3 * B15, 102, 102, 102, 102)})
    assert not e.apply_management_action(T0, 1, "hold")
    invalid = [ev for ev in e.events if ev["kind"] == "invalid_action"]
    assert len(invalid) == 4


def test_funding_transfers_both_directions():
    e = Engine(10_000)
    tf = T0  # T0 is 4h-aligned; ensure funding-aligned
    assert tf % P.FUNDING_INTERVAL_MS == 0
    e.submit_entry("A", +1, qty=10, stop=95, target=115, r_dist=5,
                   decision_ts=tf - B15, costs=C0)
    e.process_bar_time(tf - B15, {"A": bar(tf - B15, 100, 100, 100, 100)})
    # long pays positive funding on the previous close mark
    e.process_bar_time(tf, {"A": bar(tf, 100, 100, 100, 100)},
                       funding={"A": 0.0001}, prev_close={"A": 100})
    assert e.cash == pytest.approx(10_000 - 0.0001 * 10 * 100)
    # short receives positive funding
    e2 = Engine(10_000)
    e2.submit_entry("A", -1, qty=10, stop=115, target=85, r_dist=5,
                    decision_ts=tf - B15, costs=C0)
    e2.process_bar_time(tf - B15, {"A": bar(tf - B15, 100, 100, 100, 100)})
    e2.process_bar_time(tf, {"A": bar(tf, 100, 100, 100, 100)},
                        funding={"A": 0.0001}, prev_close={"A": 100})
    assert e2.cash == pytest.approx(10_000 + 0.0001 * 10 * 100)
    # missing funding datum -> 0 applied + event
    e2.process_bar_time(tf + P.FUNDING_INTERVAL_MS,
                        {"A": bar(tf + P.FUNDING_INTERVAL_MS, 100, 100, 100, 100)},
                        funding={}, prev_close={"A": 100})
    assert any(ev["kind"] == "funding_missing" for ev in e2.events)


def test_insolvency_ruin_protection():
    e = Engine(1_000)
    # full 1.5x capacity: 15 qty @ 100 = 1500 notional on 1000 equity
    e.submit_entry("A", +1, qty=15, stop=50, target=300, r_dist=25,
                   decision_ts=T0, costs=C0)
    e.process_bar_time(T0, {"A": bar(T0, 100, 100, 100, 100)})
    assert e.open_positions()
    # catastrophic gap through the stop: opens at 25 -> gap-through fill at
    # the OPEN (25), never the stop (50): loss 15*(100-25)=1125 > equity
    e.process_bar_time(T0 + B15, {"A": bar(T0 + B15, 25, 30, 20, 22)})
    p = e.positions[1]
    assert p.closed and p.close_reason == "stop"
    fill_ev = [ev for ev in e.events if ev["kind"] == "fill_close"][0]
    assert fill_ev["price"] == pytest.approx(25)       # open, not stop=50
    assert e.cash == pytest.approx(1_000 - 1_125)
    assert e.ruined
    assert any(ev["kind"] == "insolvency" for ev in e.events)
    # ruined accounts never open new risk
    e.submit_entry("B", +1, qty=1, stop=95, target=115, r_dist=5,
                   decision_ts=T0 + 2 * B15, costs=C0)
    e.process_bar_time(T0 + 2 * B15, {"B": bar(T0 + 2 * B15, 100, 100, 100, 100)})
    assert [ev for ev in e.events if ev["kind"] == "rejection"][-1]["reason"] == "ruined"
    assert not e.open_positions()


def test_long_short_symmetry_mirrored_prices():
    """Long on price path p and short on mirrored path 2k-p produce identical
    P&L with identical costs (invariant, FINAL-1.2 §13)."""
    k = 100.0
    path = [(100, 102, 99, 101), (101, 104, 100, 103), (103, 103, 96, 97)]
    mirror = [tuple(2 * k - x for x in (o, l, h, c))  # high/low swap
              for (o, h, l, c) in path]
    eL, eS = Engine(10_000), Engine(10_000)
    eL.submit_entry("A", +1, qty=10, stop=94, target=120, r_dist=3,
                    decision_ts=T0, costs=C0)
    eS.submit_entry("A", -1, qty=10, stop=106, target=80, r_dist=3,
                    decision_ts=T0, costs=C0)
    for i, ((o, h, l, c), (mo, mh, ml, mc)) in enumerate(zip(path, mirror)):
        t = T0 + i * B15
        eL.process_bar_time(t, {"A": bar(t, o, h, l, c)})
        eS.process_bar_time(t, {"A": bar(t, mo, mh, ml, mc)})
    eL.submit_exit(1, 1.0, "x")
    eS.submit_exit(1, 1.0, "x")
    t = T0 + 3 * B15
    eL.process_bar_time(t, {"A": bar(t, 97, 97, 97, 97)})
    eS.process_bar_time(t, {"A": bar(t, 103, 103, 103, 103)})
    assert eL.cash == pytest.approx(eS.cash)


def test_determinism_identical_inputs_identical_event_stream():
    def run():
        e = Engine(10_000)
        e.submit_entry("A", +1, qty=10, stop=95, target=110, r_dist=5,
                       decision_ts=T0, costs=CF)
        e.submit_entry("B", -1, qty=5, stop=210, target=170, r_dist=5,
                       decision_ts=T0, costs=CF)
        for i in range(20):
            t = T0 + i * B15
            px = 100 + (i * 7 % 13) - 6
            e.process_bar_time(t, {
                "A": bar(t, px, px + 2, px - 2, px + 1),
                "B": bar(t, 2 * px, 2 * px + 3, 2 * px - 3, 2 * px - 1)},
                funding={"A": 0.0001, "B": -0.0002} if t % P.FUNDING_INTERVAL_MS == 0 else {},
                prev_close={"A": 100, "B": 200})
        return e.events
    assert run() == run()


def test_eval_boundary_force_close():
    e = Engine(10_000)
    e.submit_entry("A", +1, qty=10, stop=90, target=130, r_dist=5,
                   decision_ts=T0, costs=C0)
    e.process_bar_time(T0, {"A": bar(T0, 100, 101, 99, 100)})
    e.force_close_all(T0 + B15, {"A": 104.0}, "eval_boundary_close")
    p = e.positions[1]
    assert p.closed and p.close_reason == "eval_boundary_close"
    assert e.cash == pytest.approx(10_000 + 40)
