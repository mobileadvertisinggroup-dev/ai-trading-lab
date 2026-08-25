"""Tests: Arm D regime model + Arm F RL environment (data-free scaffolding)."""
import numpy as np
import pytest

from lab import protocol as P
from lab.arms.regime import (MIN_HISTORY, MULTIPLIERS, RegimeModel,
                             SMA_FAST, SMA_SLOW)
from lab.arms.rl_env import ACTIONS, TradeManagementEnv

H4 = P.BAR_4H_MS
B15 = P.BAR_15M_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)


def series(closes):
    t = np.arange(T0, T0 + len(closes) * H4, H4, dtype=np.int64)
    return t, np.asarray(closes, float)


def boundary(i):
    return T0 + (i + 1) * H4          # bar i closes at this boundary


# ------------------------------------------------------------- regime

def test_regime_classifies_all_four_states():
    n = MIN_HISTORY + 50
    up = np.linspace(100, 200, n)                       # steady rise
    m = RegimeModel(*series(up))
    rec = m.classify(boundary(n - 1))
    assert rec["regime"] == "uptrend"
    assert rec["multiplier"] == MULTIPLIERS["uptrend"]

    # geometric decline: constant log-steps, so vol stays flat
    down = 200.0 * (100.0 / 200.0) ** (np.arange(n) / (n - 1))
    assert RegimeModel(*series(down)).classify(boundary(n - 1))["regime"] \
        == "downtrend"

    # strict alternation: SMA fast == SMA slow == 100, so neither trend
    # condition holds strictly -> sideways; constant vol -> not stress
    flat = 100 + 0.5 * ((-1.0) ** np.arange(n))
    assert RegimeModel(*series(flat)).classify(boundary(n - 1))["regime"] \
        == "sideways"

    # calm history then violent swings -> stress
    calm = list(100 + 0.2 * np.sin(np.arange(n) / 5.0))
    wild = calm + [100 * (1 + (0.10 if i % 2 else -0.10))
                   for i in range(25)]
    rec = RegimeModel(*series(wild)).classify(boundary(len(wild) - 1))
    assert rec["regime"] == "stress"
    assert rec["multiplier"] == {1: 0.5, -1: 0.5}


def test_regime_insufficient_history_is_conservative():
    n = SMA_FAST + 5                                    # < MIN_HISTORY
    rec = RegimeModel(*series(np.linspace(100, 150, n))).classify(boundary(n - 1))
    assert rec["regime"] == "stress" and rec["insufficient_history"]


def test_regime_is_point_in_time():
    """Adding future bars never changes a past classification."""
    n = MIN_HISTORY + 60
    closes = list(100 + np.cumsum(np.sin(np.arange(n) / 3.0)))
    t_eval = boundary(MIN_HISTORY + 20)
    a = RegimeModel(*series(closes)).classify(t_eval)
    b = RegimeModel(*series(closes + [500.0] * 50)).classify(t_eval)
    assert a == b


def test_regime_record_preserves_spec_fields():
    n = MIN_HISTORY + 10
    rec = RegimeModel(*series(np.linspace(100, 160, n))).classify(boundary(n - 1))
    assert {"regime", "inputs", "multiplier", "model_version"} <= set(rec)
    assert set(rec["inputs"]) == {"close", "sma_fast", "sma_slow",
                                  "rvol_20", "rvol_q90_trailing"}


# ------------------------------------------------------------- RL env

def make_bars(levels_15m):
    return [(T0 + i * B15, lv, lv + 0.1, lv - 0.1, lv)
            for i, lv in enumerate(levels_15m)]


TRADE = {"side": 1, "qty": 10.0, "entry_ref": 100.0, "r_dist": 5.0,
         "costs": {"hs": 0.0, "slip": 0.0, "fee": 0.0}}


def test_env_hold_to_episode_end_reward_is_net_r():
    bars = make_bars([100.0] * 20 + [104.0] * 20)
    env = TradeManagementEnv(TRADE, bars)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (10,)
    total = 0.0
    terminated = False
    while not terminated:
        obs, r, terminated, trunc, info = env.step(0)   # hold
        total += r
    # closed at final close 104: net R = 10*(104-100)/(10*5) = 0.8
    assert total == pytest.approx(0.8)
    assert info["invalid_actions"] == 0


def test_env_close_action_realizes_and_terminates():
    bars = make_bars([100.0] * 40)
    env = TradeManagementEnv(TRADE, bars)
    env.reset(seed=0)
    obs, r, terminated, _, _ = env.step(ACTIONS.index("close"))
    assert terminated
    assert r == pytest.approx(0.0)          # flat exit, cost-free

    # stop-out path: bar touches the stop (95) without gapping through
    # (open 95.05 > stop): fill exactly at 95 -> -1R; the 0.1 wiggle puts
    # MAE at 5.05 = 1.01R, so drawdown penalty = 0.25 * 0.01
    bars2 = make_bars([100.0] * 17 + [95.05] * 5)
    env2 = TradeManagementEnv(TRADE, bars2)
    env2.reset(seed=0)
    total, term2 = 0.0, False
    while not term2:
        _, r2, term2, _, _ = env2.step(0)
        total += r2
    assert env2.engine.positions[1].close_reason == "stop"
    assert total == pytest.approx(-1.0 - 0.25 * 0.01)


def test_env_invalid_actions_penalized_not_executed():
    bars = make_bars([100.0] * 40)
    env = TradeManagementEnv(TRADE, bars)
    env.reset(seed=0)
    # breakeven at entry price is not yet protective -> invalid
    _, _, terminated, _, info = env.step(ACTIONS.index("move_stop_breakeven"))
    stop_after = env.engine.positions[1].stop
    assert stop_after == pytest.approx(95.0)            # unchanged
    assert info["invalid_actions"] == 1
    # penalty shows up in the terminal reward
    while not terminated:
        _, r, terminated, _, _ = env.step(0)
    assert r == pytest.approx(0.0 - 0.02)


def test_env_deterministic_replay():
    bars = make_bars([100 + (i * 3 % 7) * 0.5 for i in range(64)])
    def run():
        env = TradeManagementEnv(TRADE, bars)
        env.reset(seed=123)
        rs, terminated = [], False
        i = 0
        while not terminated:
            _, r, terminated, _, _ = env.step([0, 4, 1, 0][i % 4])
            rs.append(r)
            i += 1
        return rs, env.engine.events
    a, b = run(), run()
    assert a[0] == b[0] and a[1] == b[1]


def test_env_tighten_stop_moves_toward_mark_only():
    bars = make_bars([100.0] * 17 + [103.0] * 30)
    env = TradeManagementEnv(TRADE, bars)
    env.reset(seed=0)
    env.step(0)                             # advance; mark now 103
    p = env.engine.positions[1]
    stop_before = p.stop
    env.step(ACTIONS.index("tighten_stop"))
    assert stop_before < env.engine.positions[1].stop < 103.0
