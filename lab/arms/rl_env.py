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

Observation (float32): built EXCLUSIVELY by the canonical
lab.arms.observation.build_observation (schema obs-v2, adjudication
blocker 2) — training/inference parity is structural. Episode trades
carry the entry-decision ATR (from the candidate ledger), the frozen
Wilder ATR series over completed 4h bars, and the RECORDED official
Arm-A portfolio-exposure fraction per boundary; the schema module
defines every dimension's provenance, units, clipping, and missing-data
rule.

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
from lab.arms.observation import (OBS_DIM, OBS_SCHEMA_HASH,
                                  OBS_SCHEMA_VERSION, ObsInputs,
                                  atr_at_or_before, build_observation)
from lab.sim.engine import Bar, Costs, Engine

ACTIONS = ("hold", "reduce_25", "reduce_50", "close", "tighten_stop",
           "move_stop_breakeven")
TURNOVER_FREE_ACTIONS = 2
TURNOVER_PENALTY = 0.05
INVALID_PENALTY = 0.02
DRAWDOWN_PENALTY = 0.25
DRAWDOWN_FREE_R = 1.0


class TradeManagementEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, trade: dict, bars: list[tuple[int, float, float, float, float]],
                 portfolio_exposure: float = 0.0):
        """trade: {side, qty, entry_ref, r_dist, costs:{hs,slip,fee},
        atr_entry (REQUIRED, candidate-ledger ATR at the entry decision),
        atr_t4_close_ms + atr_values (optional frozen ATR series over
        completed 4h bars; absent -> the obs-v2 missing rule carries
        atr_entry, ratio 1.0), exposure_by_boundary (optional dict
        boundary_ms -> recorded Arm-A exposure FRACTION; absent boundary ->
        most recent recorded <= t; none -> 0.0, flagged in info)}.
        bars: chronological 15m bars [(t,o,h,l,c), ...]; bars[0] is the
        entry bar. Management decisions are offered every BARS_PER_STEP
        bars (= one 4h boundary), matching SIMULATOR_SEMANTICS §4."""
        super().__init__()
        self.trade = trade
        self.bars = [Bar(int(t), float(o), float(h), float(l), float(c))
                     for t, o, h, l, c in bars]
        if not self.bars:
            raise ValueError("bars required")
        if "atr_entry" not in trade or not trade["atr_entry"] > 0:
            raise ValueError("trade.atr_entry (entry-decision ATR) required")
        self.portfolio_exposure = float(portfolio_exposure)
        # D72: frozen per-episode funding rates {funding_time_ms: rate}
        # for the episode symbol, sourced from the verified lake at
        # episode build time. A funding boundary with no recorded rate
        # stays absent — the engine's frozen missing-funding rule emits
        # a loud funding_missing event; nothing is silently filled.
        self._funding = {int(k): float(v) for k, v in
                         (trade.get("funding_by_time") or {}).items()}
        self._prev_close: dict[str, float] = {}
        self._atr_t = np.asarray(trade.get("atr_t4_close_ms", []),
                                 dtype=np.int64)
        self._atr_v = np.asarray(trade.get("atr_values", []), dtype=float)
        self._expo = dict(trade.get("exposure_by_boundary", {}))
        self._expo_keys = np.array(sorted(self._expo), dtype=np.int64)
        self.exposure_recorded = bool(self._expo)
        self.obs_schema = {"version": OBS_SCHEMA_VERSION,
                           "hash": OBS_SCHEMA_HASH}
        self.action_space = spaces.Discrete(len(ACTIONS))
        self.observation_space = spaces.Box(-np.inf, np.inf, (OBS_DIM,),
                                            dtype=np.float32)
        self._steps_per_decision = P.BAR_4H_MS // P.BAR_15M_MS

    # ------------------------------------------------------------ helpers
    def _process_bar(self, b: Bar):
        """One engine bar with the frozen funding map and previous-close
        mark — identical semantics to the official ArmARunner (D72):
        funding transfers hit cash and the position's funding_paid, so
        the terminal reward reflects the policy's ACTUAL holding
        duration and reductions."""
        f = {}
        if b.open_time % P.FUNDING_INTERVAL_MS == 0:
            rate = self._funding.get(int(b.open_time))
            if rate is not None:
                f = {"X": rate}
        self.engine.process_bar_time(b.open_time, {"X": b}, funding=f,
                                     prev_close=dict(self._prev_close))
        self._prev_close["X"] = b.close

    def _exposure_at(self, t: int) -> float:
        if not self.exposure_recorded:
            return 0.0             # documented no-recorded-exposure rule
        i = int(np.searchsorted(self._expo_keys, t, side="right")) - 1
        if i < 0:
            return 0.0
        return float(self._expo[int(self._expo_keys[i])])

    def obs_inputs(self) -> ObsInputs | None:
        """The decision-time state record handed to the CANONICAL builder.
        Exposed publicly so the parity test can compare it field-by-field
        with the orchestrator's construction."""
        p = self.engine.positions.get(1)
        if p is None or p.closed:
            return None
        # the decision BOUNDARY this observation serves: the next 15m
        # timestamp after the last processed bar (obs-v2 parity)
        t_dec = self.bars[self._i].open_time + P.BAR_15M_MS
        atr_entry = float(self.trade["atr_entry"])
        atr_now = (atr_at_or_before(self._atr_t, self._atr_v, t_dec,
                                    atr_entry)
                   if len(self._atr_t) else atr_entry)
        return ObsInputs(
            side=p.side, entry_fill=p.entry_fill, r_dist=p.r_dist,
            mark=p.last_mark, mfe_price=p.mfe, mae_price=p.mae,
            stop=p.stop, target=p.target, qty=p.qty, open_qty=p.open_qty,
            bars_held_4h=max(0, (t_dec - p.decision_ts) // P.BAR_4H_MS),
            atr_now=atr_now, atr_entry=atr_entry,
            gross_exposure=self._exposure_at(t_dec), equity=1.0)

    def _obs(self):
        x = self.obs_inputs()
        if x is None:
            return np.zeros(OBS_DIM, dtype=np.float32)
        return build_observation(x)

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
            r_dist=float(t["r_dist"]),
            # obs-v2: bars_held is measured from the entry DECISION
            # boundary (identical to the orchestrator), supplied by the
            # episode; default (entry bar - 15m) reproduces production
            decision_ts=int(t.get("decision_ts",
                                  self.bars[0].open_time - P.BAR_15M_MS)),
            costs=Costs(c["hs"], c["slip"], c["fee"]),
            stop_offset=float(t["r_dist"]),
            target_offset=P.TARGET_R_MULT * float(t["r_dist"]))
        self._prev_close = {}
        self._process_bar(self.bars[0])
        self._i = 0
        # obs-v2 parity: decisions align with 4h BOUNDARIES exactly as in
        # the orchestrator (state = bars processed through boundary-15m);
        # advance so the first decision serves the first boundary
        n = len(self.bars)
        while (self._i + 1 < n
               and self.bars[self._i + 1].open_time % P.BAR_4H_MS != 0):
            self._i += 1
            self._process_bar(self.bars[self._i])
            if self.engine.positions[1].closed:
                break
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

        # advance to the state immediately before the NEXT 4h boundary
        # (bars processed through boundary-15m) — identical decision
        # timing to the orchestrator (obs-v2 parity)
        n = len(self.bars)
        while self._i + 1 < n:
            self._i += 1
            b = self.bars[self._i]
            self._process_bar(b)
            p = self.engine.positions[1]
            if p.closed:
                break
            nxt = self._i + 1
            if nxt < n and self.bars[nxt].open_time % P.BAR_4H_MS == 0:
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
