"""Phase 4 tests: indicators + end-to-end Arm A runner on synthetic data."""
import numpy as np
import pytest

from lab import protocol as P
from lab.arms import indicators as IND
from lab.arms.arm_a import ArmARunner, ArrayProvider, tier_costs

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)


# --------------------------------------------------------------- indicators

def test_aggregate_4h_completeness_and_ohlc():
    t = np.arange(0, 33 * B15, B15, dtype=np.int64)      # 2 full 4h + 1 bar
    o = np.linspace(100, 132, 33)
    h = o + 1
    l = o - 1
    c = o + 0.5
    bars = IND.aggregate_4h(t, o, h, l, c)
    assert list(bars["open_time"]) == [0, H4]            # third window incomplete
    assert bars["open"][0] == o[0] and bars["close"][0] == c[15]
    assert bars["high"][1] == h[16:32].max()
    assert bars["low"][1] == l[16:32].min()
    # drop one 15m bar from the first window -> that 4h bar disappears
    keep = np.ones(33, bool)
    keep[3] = False
    bars2 = IND.aggregate_4h(t[keep], o[keep], h[keep], l[keep], c[keep])
    assert list(bars2["open_time"]) == [H4]


def test_donchian_prior_excludes_current_bar():
    high = np.array([1, 5, 2, 9, 3], float)
    low = np.array([0, 4, 1, 8, 2], float)
    hh, ll = IND.donchian_prior(high, low, 2)
    assert np.isnan(hh[0]) and np.isnan(hh[1])
    assert hh[2] == 5 and ll[2] == 0
    assert hh[3] == 5 and hh[4] == 9        # bar 3's own high excluded at 3
    assert ll[4] == 1


def test_wilder_atr_constant_range_and_min_history():
    n = P.ATR_PERIOD
    m = 3 * n + 10
    high = np.full(m, 101.0)
    low = np.full(m, 99.0)
    close = np.full(m, 100.0)
    atr = IND.wilder_atr(high, low, close, n)
    assert np.isnan(atr[3 * n - 2])          # undefined before 3n bars
    assert atr[3 * n - 1] == pytest.approx(2.0)
    assert atr[-1] == pytest.approx(2.0)


# ------------------------------------------------------------ synthetic mkt

def build_symbol(levels_4h, wiggle=0.1):
    """15m arrays where 4h bar i sits at levels_4h[i]; each 15m bar has
    high=level+wiggle, low=level-wiggle, open=close=level."""
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
            "low": lv - wiggle, "close": lv.copy()}


HIST = 96      # 4h bars of flat history (>= 3*ATR_PERIOD and > 60)


def test_arm_a_breakout_entry_and_target_exit():
    # flat 100 -> breakout to 105 (candidate) -> 108 (through +3R target)
    levels = [100.0] * HIST + [105.0, 105.0] + [108.0] * 3
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    r = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    end = T0 + (len(levels) * 16 - 1) * B15
    r.run(T0, end)

    # first candidate at the boundary where the 105-bar completed; a second
    # (protocol-correct) candidate fires next boundary: after the target
    # closed the position, close 108 still exceeds HH60 = 105.1
    assert len(r.candidates) == 2
    cand = r.candidates[0]
    t_signal = T0 + (HIST + 1) * H4            # bar HIST closes at this boundary
    assert cand["t"] == t_signal
    assert cand["side"] == +1
    assert cand["close"] == 105.0
    assert cand["hh_entry"] == pytest.approx(100.1)
    assert cand["rank"] == 1 and cand["n_eligible"] == 1
    # candidate contains ONLY decision-time inputs
    assert set(cand) == {"t", "symbol", "side", "close", "hh_entry",
                         "ll_entry", "atr", "r_dist", "rank", "n_eligible",
                         "equity", "qty_submitted"}

    opens = [ev for ev in r.engine.events if ev["kind"] == "fill_open"]
    assert len(opens) == 2
    op = opens[0]
    assert op["t"] == t_signal                  # filled at the boundary bar open
    c1 = tier_costs(0)
    assert op["price"] == pytest.approx(105 * (1 + c1.half_spread + c1.slippage))
    # protection anchored at fill per protocol §2.4
    assert op["stop"] == pytest.approx(op["price"] - cand["r_dist"])
    assert op["target"] == pytest.approx(op["price"] + 3 * cand["r_dist"])
    # sizing: notional cap (15% equity) binds here and qty was reduced to fit
    assert op["qty"] * op["price"] == pytest.approx(
        P.NOTIONAL_CAP_FRACTION * cand["equity"])
    assert op["qty"] < cand["qty_submitted"]

    p = r.engine.positions[1]
    assert p.closed and p.close_reason == "target"
    assert p.realized_pnl == pytest.approx(p.qty * 3 * cand["r_dist"])
    # equity curve recorded at every boundary
    assert len(r.equity_curve) == len(levels)


def test_arm_a_time_exit_after_42_bars():
    hold = P.MAX_HOLD_BARS_4H
    levels = [100.0] * HIST + [105.0] * (hold + 4)
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    r = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    end = T0 + (len(levels) * 16 - 1) * B15
    r.run(T0, end)

    assert len(r.candidates) == 1
    t_entry = r.candidates[0]["t"]
    p = r.engine.positions[1]
    assert p.closed and p.close_reason == "time_exit"
    closes = [ev for ev in r.engine.events if ev["kind"] == "fill_close"]
    assert closes[0]["t"] == t_entry + hold * H4     # exactly 42 bars later
    # while open: no second candidate for the same symbol (no pyramiding)
    assert len([ev for ev in r.engine.events if ev["kind"] == "fill_open"]) == 1


def test_arm_a_short_breakout_and_stop():
    # flat 100 -> breakdown to 95 (short candidate) -> snap back up hits stop
    levels = [100.0] * HIST + [95.0, 95.0] + [99.0] * 2
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    r = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    end = T0 + (len(levels) * 16 - 1) * B15
    r.run(T0, end)
    assert r.candidates[0]["side"] == -1
    assert r.candidates[0]["ll_entry"] == pytest.approx(99.9)
    p = r.engine.positions[1]
    assert p.closed and p.close_reason == "stop"
    assert p.realized_pnl < 0


def test_arm_a_invalid_rounds_produce_no_candidates():
    levels = [100.0] * HIST + [105.0] * 4
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    r = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"],
                   valid_round_fn=lambda t: False)
    end = T0 + (len(levels) * 16 - 1) * B15
    r.run(T0, end)
    assert r.candidates == []
    assert not r.engine.events


def test_arm_a_missing_indicator_inputs_no_candidate():
    # too little history: ATR undefined -> breakout ignored
    levels = [100.0] * 30 + [105.0] * 2
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    r = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    end = T0 + (len(levels) * 16 - 1) * B15
    r.run(T0, end)
    assert r.candidates == []
