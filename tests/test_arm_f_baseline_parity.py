"""D63 blocker 2 — parity proof: the in-episode ConventionalManager
reproduces the OFFICIAL frozen Arm A management outcomes exactly, for
each exit class (trailing exit, time exit, stop hit, target hit).

The official side is ArmARunner itself on synthetic markets; the replay
side is TradeManagementEnv driven by ConventionalManager on the
identical bars, quantities, and costs. Realized economics and closure
timing must match bit-for-bit.
"""
import numpy as np

from lab import protocol as P
from lab.arms.arm_a import ArmARunner, ArrayProvider, tier_costs
from lab.arms.indicators import SymbolSeries
from lab.tools.report_arm_f_v2 import ConventionalManager

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)
HIST = 96
WIGGLE = 1.0        # ATR ~ 2 -> r_dist ~ 4: stop ~ fill-4, target ~ fill+12


def build(levels_4h):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + WIGGLE,
            "low": lv - WIGGLE, "close": lv.copy()}


def scenarios():
    up = [100.0 + 0.02 * i for i in range(HIST)]   # rising staircase
    # every scenario keeps ONE stable 4h bar after the breakout signal
    # bar so the entry FILLS ~106 before the engineered move happens
    # TRAIL: climb to 116 (high 117 < target ~118.8), then drop to 104 —
    # above the ~102.3 stop, below the risen 20-bar exit channel (105.5)
    trail = (up + [106.0, 106.0] + [106.0 + 0.5 * i for i in range(1, 21)]
             + [104.0, 104.0, 104.0])
    # TIME: gentle staircase for > MAX_HOLD bars (never trips the
    # channel, stop, or target)
    time_ = up + [106.0, 106.0] + [106.5 + 0.01 * i
                                   for i in range(P.MAX_HOLD_BARS_4H + 4)]
    # STOP: entry fills ~106, then a plunge through the protective stop
    stop = up + [106.0, 106.0, 92.0, 92.0, 92.0]
    # TARGET: entry fills ~106, then a surge through +3R
    target = up + [106.0, 106.0, 122.0, 122.0, 122.0]
    return {"TRLUSDT": trail, "TIMUSDT": time_, "STPUSDT": stop,
            "TGTUSDT": target}


def test_conventional_manager_reproduces_official_arm_a_outcomes():
    scen = scenarios()
    n4 = max(len(v) for v in scen.values())
    data = {s: build(v + [v[-1]] * (n4 - len(v))) for s, v in scen.items()}
    prov = ArrayProvider({s: {k: a.copy() for k, a in d.items()}
                          for s, d in data.items()})
    runner = ArmARunner(prov, 1_000_000.0,
                        universe_fn=lambda t: sorted(scen))
    end = T0 + (n4 * 16 - 1) * B15
    runner.run(T0, end)

    closed = [p for p in runner.engine.positions.values() if p.closed]
    reasons = {p.close_reason for p in closed}
    # every exit class must actually occur in the official run
    assert {"trailing_exit", "time_exit", "stop", "target"} <= reasons, \
        reasons
    close_t = {e["pos_id"]: e["t"] for e in runner.engine.events
               if e["kind"] == "position_closed"}

    checked = 0
    for p in closed:
        d = data[p.symbol]
        series = SymbolSeries(d["open_time"], d["open"], d["high"],
                              d["low"], d["close"])
        lo = p.decision_ts + B15
        hi = close_t[p.pos_id] + H4
        m = (d["open_time"] >= lo) & (d["open_time"] <= hi)
        bars = list(zip(d["open_time"][m], d["open"][m], d["high"][m],
                        d["low"][m], d["close"][m]))
        rank = sorted(scen).index(p.symbol)
        c = tier_costs(rank)
        trade = {"side": p.side, "qty": p.qty, "entry_ref": 0.0,
                 "r_dist": p.r_dist, "decision_ts": p.decision_ts,
                 "atr_entry": p.r_dist / P.STOP_ATR_MULT,
                 "costs": {"hs": c.half_spread, "slip": c.slippage,
                           "fee": c.fee}}
        from lab.arms.rl_env import TradeManagementEnv
        env = TradeManagementEnv(trade, bars)
        env.reset(seed=0)
        mgr = ConventionalManager(series)
        while True:
            a = mgr.action(env)
            _o, _r, term, trunc, _i = env.step(a)
            if term or trunc:
                break
        ep = env.engine.positions[1]
        assert ep.closed
        assert ep.entry_fill == p.entry_fill, p.symbol
        assert ep.realized_pnl == p.realized_pnl, \
            (p.symbol, p.close_reason, ep.realized_pnl, p.realized_pnl)
        assert ep.fees_paid == p.fees_paid, p.symbol
        env_close_t = [e["t"] for e in env.engine.events
                       if e["kind"] == "position_closed"]
        assert env_close_t == [close_t[p.pos_id]], \
            (p.symbol, p.close_reason)
        checked += 1
    assert checked >= 4