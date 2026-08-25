"""Differential gate development tests (FINAL-1.2 §13).

Every fixture runs through BOTH independent implementations and must
reconcile transaction-by-transaction. Together these fixtures exercise the
complete §13 minimum differential subset: long, short, multiple simultaneous
positions, capital competition, position sizing (cap + min notional),
protective stops (incl. gap-through), deterministic exits, fees, cash,
equity, exposure accounting, capacity rejection, and insolvency.
"""
import pytest

from lab import protocol as P
from lab.verify.differential import compare

B15 = P.BAR_15M_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % P.BAR_4H_MS)
CF = {"hs": 0.001, "slip": 0.0005, "fee": 0.0005}
C0 = {"hs": 0.0, "slip": 0.0, "fee": 0.0}
LIM = {"max_positions": 10, "max_gross_exposure": 1.5, "min_notional": 50.0}


def fx_base(bars, instructions, cash=10_000, funding=None, limits=LIM):
    return {"starting_cash": cash, "limits": limits,
            "instructions": instructions, "bars": bars,
            "funding": funding or {},
            "funding_interval_ms": P.FUNDING_INTERVAL_MS,
            "bar_ms": B15}


def series(sym_levels, n):
    """bars dict: each symbol flat at level with 0.1 wiggle, n bars."""
    return {s: [[T0 + i * B15, lv, lv + 0.1, lv - 0.1, lv]
                for i in range(n)] for s, lv in sym_levels.items()}


def assert_match(fx):
    rep = compare(fx)
    assert rep["match"], rep
    return rep


def entry(t, sym, side, qty, stop_off, tgt_off, costs=CF, cap=None):
    return {"t": t, "type": "entry", "symbol": sym, "side": side, "qty": qty,
            "costs": costs, "stop_offset": stop_off, "target_offset": tgt_off,
            "max_notional": cap}


def test_diff_long_target_win():
    bars = {"A": [[T0, 100, 100.2, 99.8, 100],
                  [T0 + B15, 101, 103.5, 100.9, 103],   # through target
                  [T0 + 2 * B15, 103, 103.1, 102.9, 103]]}
    fx = fx_base(bars, [entry(T0, "A", +1, 10, 2.0, 3.0)])
    rep = assert_match(fx)
    assert rep["n"] >= 2


def test_diff_short_stop_loss_and_double_slippage():
    bars = {"A": [[T0, 100, 100.2, 99.8, 100],
                  [T0 + B15, 101, 104.0, 100.9, 103.5]]}  # up through stop
    fx = fx_base(bars, [entry(T0, "A", -1, 10, 2.0, 6.0)])
    assert_match(fx)


def test_diff_costs_flip_gross_winner():
    bars = {"A": [[T0, 100, 100.3, 99.9, 100.2],
                  [T0 + B15, 100.2, 100.4, 100.0, 100.2]]}
    fx = fx_base(bars, [entry(T0, "A", +1, 100, 50.0, 60.0)] +
                 [{"t": T0 + B15, "type": "exit", "pos_id": 1,
                   "reason": "manual", "slip_mult": 1.0}])
    rep = assert_match(fx)
    assert rep["final_cash"] < 10_000            # net loser after costs


def test_diff_overlap_competition_and_rejections():
    bars = series({"A": 100, "B": 200, "C": 50, "D": 80}, 4)
    ins = [
        entry(T0, "A", +1, 70, 5, 10),           # 7000 notional
        entry(T0, "B", -1, 35, 5, 10),           # 7000 notional
        entry(T0, "C", +1, 40, 5, 10),           # 2000 -> capacity reject
        entry(T0 + B15, "D", +1, 0.5, 5, 10),    # 40 -> min_notional reject
        entry(T0 + 2 * B15, "C", +1, 30, 5, 10, cap=900.0),  # cap reduces qty
    ]
    fx = fx_base(bars, ins)
    assert_match(fx)


def test_diff_max_positions_rejection():
    bars = series({f"S{i}": 100 for i in range(5)}, 2)
    lim = dict(LIM, max_positions=3)
    ins = [entry(T0, f"S{i}", +1, 1, 5, 10) for i in range(5)]
    fx = fx_base(bars, ins, limits=lim)
    assert_match(fx)


def test_diff_funding_paid_received_and_missing():
    tf = T0 if T0 % P.FUNDING_INTERVAL_MS == 0 else \
        T0 + (P.FUNDING_INTERVAL_MS - T0 % P.FUNDING_INTERVAL_MS)
    n = (tf - T0) // B15 + 3
    bars = series({"A": 100, "B": 200}, int(n))
    ins = [entry(T0, "A", +1, 10, 50, 60, costs=C0),
           entry(T0, "B", -1, 5, 50, 60, costs=C0)]
    funding = {"A": {tf: 0.0001}}                # B has no datum -> missing
    fx = fx_base(bars, ins, funding=funding)
    assert_match(fx)


def test_diff_intrabar_ambiguity_stop_first():
    bars = {"A": [[T0, 100, 100.1, 99.9, 100],
                  [T0 + B15, 100, 106, 94, 100]]}  # spans stop AND target
    fx = fx_base(bars, [entry(T0, "A", +1, 10, 2.0, 3.0, costs=C0)])
    assert_match(fx)


def test_diff_gap_through_insolvency_and_ruin():
    bars = {"A": [[T0, 100, 100.1, 99.9, 100],
                  [T0 + B15, 25, 30, 20, 22],
                  [T0 + 2 * B15, 22, 22.1, 21.9, 22]],
            "B": [[T0 + 2 * B15, 10, 10.1, 9.9, 10]]}
    ins = [entry(T0, "A", +1, 15, 50.0, 500.0, costs=C0),
           entry(T0 + 2 * B15, "B", +1, 10, 1, 2, costs=C0)]  # ruined reject
    fx = fx_base(bars, ins, cash=1_000)
    assert_match(fx)


def test_diff_missing_bars_cancel_and_deferral():
    bars = {"A": [[T0, 100, 100.1, 99.9, 100],
                  # T0+B15 missing entirely
                  [T0 + 2 * B15, 100, 100.1, 99.9, 100]]}
    ins = [entry(T0, "A", +1, 10, 50, 60, costs=C0),
           entry(T0 + B15, "A", -1, 5, 50, 60, costs=C0),  # missing bar cancel
           {"t": T0 + B15, "type": "exit", "pos_id": 1,
            "reason": "manual", "slip_mult": 1.0}]          # deferred then fills
    fx = fx_base(bars, ins)
    assert_match(fx)


def test_diff_queued_exit_gap_stop_priority():
    bars = {"A": [[T0, 100, 100.1, 99.9, 100],
                  [T0 + B15, 90, 91, 89, 90]]}   # opens below stop 98
    ins = [entry(T0, "A", +1, 10, 2.0, 50.0, costs=CF),
           {"t": T0 + B15, "type": "exit", "pos_id": 1,
            "reason": "trailing_exit", "slip_mult": 1.0}]
    fx = fx_base(bars, ins)
    assert_match(fx)


def test_diff_exit_on_closed_position_dropped():
    bars = {"A": [[T0, 100, 100.1, 99.9, 100],
                  [T0 + B15, 101, 103.5, 100.9, 103],     # target hit
                  [T0 + 2 * B15, 103, 103.1, 102.9, 103]]}
    ins = [entry(T0, "A", +1, 10, 2.0, 3.0, costs=C0),
           {"t": T0 + 2 * B15, "type": "exit", "pos_id": 1,
            "reason": "late", "slip_mult": 1.0}]
    fx = fx_base(bars, ins)
    assert_match(fx)
