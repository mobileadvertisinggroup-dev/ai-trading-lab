"""Arm F — RL trade-management environment (SPEC FINAL-1.2 §3, Arm F).

A gymnasium environment in which one episode = the post-entry management of
ONE Arm-A trade. The agent controls management only; entries, initial size,
and initial protection come from the frozen Arm A rules. The environment
replays the trade through a fresh main-simulator Engine, so every action is
subject to the engine's invariants (never widen, never grow) and the risk
governor's action filter.

Determinism: the environment is a pure function of (trade setup, bar
sequence); reset(seed=...) seeds only gymnasium's bookkeeping — nothing in
the dynamics is stochastic. Seeds matter at TRAINING time (SB3), not here.

Action space (Discrete 6): 0 hold, 1 reduce_25, 2 reduce_50, 3 close,
4 tighten_stop (move stop 25% of the distance toward the last mark),
5 move_stop_breakeven.

Observation (float32, spec Arm F list): unrealized R, time-in-trade
fraction, MFE in R, MAE in R, ATR-relative volatility now/entry, momentum
deterioration (close vs entry in R over time), distance to stop in R,
distance to target in R, remaining size fraction, portfolio exposure
fraction (supplied by the caller; 0 for single-trade episodes).

Reward: 0 each intermediate step; at episode end, net realized R
(including fees and funding) minus frozen penalties:
  - 0.05 per executed reduce/close action beyond the first two (turnover)
  - 0.02 per invalid action attempt (risk-violation penalty)
  - 0.25 × max(0, MAE_R − 1.0) (drawdown penalty beyond 1R adverse)
Penalty constants are DRAFT until the pre-training freeze (BUILD_STATE).
"""
from __future__ import annotations

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as e:  # pragma: no cover
    raise ImportError("gymnasium is required for lab.arms.rl_env") from e

from lab import protocol as P
from lab.sim.engine import Bar, Costs, Engine

ACTIONS = ("hold", "reduce_25", "reduce_50", "close", "tighten_stop",
           "move_stop_breakeven")
TURNOVER_FREE_ACTIONS = 2
TURNOVER_PENALTY = 0.05
INVALID_PENALTY = 0.02
DRAWDOWN_PENALTY = 0.25
DRAWDOWN_FREE_R = 1.0
OBS_DIM = 10


class TradeManagementEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, trade: dict, bars: list[tuple[int, float, float, float, float]],
                 portfolio_exposure: float = 0.0):
        """trade: {side, qty, entry_fill?, entry_ref, r_dist, costs:{hs,slip,fee}}
        bars: chronological 15m bars [(t,o,h,l,c), ...]; bars[0] is the entry
        bar. Management decisions are offered every BARS_PER_STEP bars
        (= one 4h boundary), matching SIMULATOR_SEMANTICS §4."""
        super().__init__()
        self.trade = trade
        self.bars = [Bar(int(t), float(o), float(h), float(l), float(c))
                     for t, o, h, l, c in bars]
        if not self.bars:
            raise ValueError("bars required")
        self.portfolio_exposure = float(portfolio_exposure)
        self.action_space = spaces.Discrete(len(ACTIONS))
        self.observation_space = spaces.Box(-np.inf, np.inf, (OBS_DIM,),
                                            dtype=np.float32)
        self._steps_per_decision = P.BAR_4H_MS // P.BAR_15M_MS

    # ------------------------------------------------------------ helpers
    def _obs(self):
        p = self.engine.positions.get(1)
        if p is None or p.closed:
            return np.zeros(OBS_DIM, dtype=np.float32)
        r = self.trade["r_dist"]
        mark = p.last_mark
        unreal_r = p.side * (mark - p.entry_fill) / r
        frac_t = self._i / max(1, len(self.bars) - 1)
        mfe_r = p.mfe / r
        mae_r = -p.mae / r
        vol_ratio = 1.0            # ATR recomputation deferred to training data
        deterioration = unreal_r / max(frac_t, 1e-6)
        dist_stop_r = p.side * (mark - p.stop) / r
        dist_tgt_r = p.side * (p.target - mark) / r
        size_frac = p.open_qty / self.trade["qty"]
        return np.array([unreal_r, frac_t, mfe_r, mae_r, vol_ratio,
                         deterioration, dist_stop_r, dist_tgt_r, size_frac,
                         self.portfolio_exposure], dtype=np.float32)

    def _final_reward(self):
        p = self.engine.positions[1]
        risk = self.trade["qty"] * self.trade["r_dist"]
        net = p.realized_pnl - p.fees_paid - p.funding_paid
        reward = net / risk
        excess_actions = max(0, self._executed_actions - TURNOVER_FREE_ACTIONS)
        reward -= TURNOVER_PENALTY * excess_actions
        reward -= INVALID_PENALTY * self._invalid_actions
        mae_r = -p.mae / self.trade["r_dist"]
        reward -= DRAWDOWN_PENALTY * max(0.0, mae_r - DRAWDOWN_FREE_R)
        return float(reward)

    # ------------------------------------------------------------ gym api
    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        t = self.trade
        self.engine = Engine(1_000_000.0)      # ample cash: management only
        c = t["costs"]
        self.engine.submit_entry(
            "X", int(t["side"]), float(t["qty"]), stop=0.0, target=0.0,
            r_dist=float(t["r_dist"]), decision_ts=self.bars[0].open_time,
            costs=Costs(c["hs"], c["slip"], c["fee"]),
            stop_offset=float(t["r_dist"]),
            target_offset=P.TARGET_R_MULT * float(t["r_dist"]))
        self.engine.process_bar_time(self.bars[0].open_time,
                                     {"X": self.bars[0]})
        self._i = 0
        self._executed_actions = 0
        self._invalid_actions = 0
        return self._obs(), {}

    def step(self, action: int):
        name = ACTIONS[int(action)]
        p = self.engine.positions.get(1)
        t_now = self.bars[self._i].open_time
        if p is not None and not p.closed and name != "hold":
            if name == "tighten_stop":
                new_stop = p.stop + 0.25 * (p.last_mark - p.stop)
                ok = self.engine.apply_management_action(
                    t_now, 1, "tighten_stop", new_stop=new_stop)
            else:
                ok = self.engine.apply_management_action(t_now, 1, name)
            if ok:
                if name in ("reduce_25", "reduce_50", "close"):
                    self._executed_actions += 1
            else:
                self._invalid_actions += 1

        # advance one decision interval (16 x 15m bars) or to the end
        end = min(self._i + self._steps_per_decision, len(self.bars) - 1)
        while self._i < end:
            self._i += 1
            b = self.bars[self._i]
            self.engine.process_bar_time(b.open_time, {"X": b})
            p = self.engine.positions[1]
            if p.closed:
                break

        p = self.engine.positions[1]
        out_of_bars = self._i >= len(self.bars) - 1
        if not p.closed and out_of_bars:
            # episode data exhausted: close at final bar close (time-exit
            # analogue for the episode; recorded by the engine as a close)
            last = self.bars[-1]
            self.engine.force_close_all(last.open_time, {"X": last.close},
                                        "episode_end")
        terminated = self.engine.positions[1].closed
        reward = self._final_reward() if terminated else 0.0
        return self._obs(), reward, terminated, False, {
            "invalid_actions": self._invalid_actions,
            "executed_actions": self._executed_actions}
