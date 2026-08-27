"""THE canonical Arm-F observation builder — adjudication blocker 2.

One builder, consumed by BOTH the training environment
(lab.arms.rl_env.TradeManagementEnv) and orchestrator inference
(lab.orchestration.competition._rl_management). Training/inference parity
is therefore structural: both sides construct an ObsInputs record and call
build_observation(); the parity test (tests/test_observation_parity.py)
proves the two call sites produce bit-identical vectors for the same
underlying state.

SCHEMA v2 — every dimension has a decision-time definition, provenance,
units, clipping rule, and missing-data behavior. NO future information may
enter: every input is a function of completed bars at/before the decision
boundary t and of the position's own engine-tracked state at t.

 # | name                | definition (at decision boundary t)          | units | clip      | missing rule
---+---------------------+----------------------------------------------+-------+-----------+---------------------------
 0 | unrealized_r        | side*(mark - entry_fill)/r_dist              | R     | [-10,10]  | mark = last 15m close <= t (engine last_mark); position exists by construction
 1 | time_frac           | bars_held_4h / MAX_HOLD_BARS_4H              | frac  | [0,1]     | none possible
 2 | mfe_r               | engine MFE (price) / r_dist                  | R     | [0,10]    | 0.0 before first bar
 3 | mae_r               | -engine MAE (price) / r_dist                 | R     | [0,10]    | 0.0 before first bar
 4 | vol_ratio           | ATR28(t)/ATR28(entry decision)               | ratio | [0.1,10]  | ATR(t) = most recent DEFINED Wilder ATR on completed 4h bars <= t; if none since entry, carry atr_entry (ratio 1.0); atr_entry comes from the candidate ledger (always defined - entries require finite ATR)
 5 | giveback_r          | mfe_r - unrealized_r (retracement from best) | R     | [0,20]    | derived from 0 and 2
 6 | dist_stop_r         | side*(mark - stop)/r_dist                    | R     | [0,10]    | stop always exists (protocol; governor integrity pause otherwise)
 7 | dist_target_r       | side*(target - mark)/r_dist                  | R     | [-10,10]  | target always exists (protocol)
 8 | remaining_frac      | open_qty / qty                               | frac  | [0,1]     | none possible
 9 | exposure_frac       | gross_exposure / equity of the OWNING       | frac  | [0,5]     | training episodes: the RECORDED Arm-A official-run exposure fraction at t (exposure ledger); inference: the arm's own engine at t; equity<=0 -> 5.0 (max, conservative)
   |                     | account at t                                 |       |           |

Provenance: mark/MFE/MAE/stop/target/qty from the engine's Position
(updated only by processed bars <= t); ATR from the frozen Wilder ATR
series over completed 4h bars (lab.arms.indicators); exposure from the
owning account's engine (inference) or the official Arm-A exposure ledger
(training). Non-finite intermediate values are clipped to the nearest
bound after the per-dimension rule — never silently propagated as NaN.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from lab import protocol as P

OBS_DIM = 10
OBS_SCHEMA_VERSION = "obs-v2"
_SCHEMA_SPEC = (
    "0:unrealized_r[-10,10];1:time_frac[0,1];2:mfe_r[0,10];3:mae_r[0,10];"
    "4:vol_ratio[0.1,10];5:giveback_r[0,20];6:dist_stop_r[0,10];"
    "7:dist_target_r[-10,10];8:remaining_frac[0,1];9:exposure_frac[0,5];"
    "mark=last15mclose<=t;atr=wilder28_completed4h<=t;"
    "exposure=own_account|recorded_armA")
OBS_SCHEMA_HASH = hashlib.sha256(
    (OBS_SCHEMA_VERSION + "|" + _SCHEMA_SPEC).encode()).hexdigest()


@dataclass(frozen=True)
class ObsInputs:
    """Decision-time state, identical in meaning at both call sites."""
    side: int
    entry_fill: float
    r_dist: float
    mark: float            # last 15m close at/before t (engine last_mark)
    mfe_price: float       # engine Position.mfe (price terms, >= 0)
    mae_price: float       # engine Position.mae (price terms, <= 0)
    stop: float
    target: float
    qty: float
    open_qty: float
    bars_held_4h: int
    atr_now: float         # most recent defined ATR28 <= t (see rule)
    atr_entry: float       # candidate-ledger ATR at the entry decision
    gross_exposure: float  # owning account at t (or recorded Arm-A value)
    equity: float


def _clip(v: float, lo: float, hi: float) -> float:
    """Non-finite guard (documented): +inf -> hi; -inf and NaN -> lo.
    Dimension-level missing-data rules are applied UPSTREAM; a non-finite
    value reaching here is a defensive floor, never a silent NaN."""
    if not np.isfinite(v):
        v = hi if v == float("inf") else lo
    return float(min(hi, max(lo, v)))


def build_observation(x: ObsInputs) -> np.ndarray:
    r = x.r_dist
    unreal = x.side * (x.mark - x.entry_fill) / r
    mfe_r = x.mfe_price / r
    obs = np.array([
        _clip(unreal, -10.0, 10.0),
        _clip(x.bars_held_4h / P.MAX_HOLD_BARS_4H, 0.0, 1.0),
        _clip(mfe_r, 0.0, 10.0),
        _clip(-x.mae_price / r, 0.0, 10.0),
        _clip((x.atr_now / x.atr_entry) if x.atr_entry > 0 else 1.0,
              0.1, 10.0),
        _clip(mfe_r - unreal, 0.0, 20.0),
        _clip(x.side * (x.mark - x.stop) / r, 0.0, 10.0),
        _clip(x.side * (x.target - x.mark) / r, -10.0, 10.0),
        _clip(x.open_qty / x.qty if x.qty > 0 else 0.0, 0.0, 1.0),
        _clip(x.gross_exposure / x.equity if x.equity > 0 else 5.0,
              0.0, 5.0),
    ], dtype=np.float32)
    return obs


def atr_at_or_before(atr_t4_close_ms: np.ndarray, atr_values: np.ndarray,
                     t_ms: int, fallback: float) -> float:
    """Most recent DEFINED ATR whose 4h bar CLOSED at/before t (no future
    information); `fallback` (the entry-decision ATR) when none exists."""
    idx = np.searchsorted(atr_t4_close_ms, t_ms, side="right") - 1
    while idx >= 0:
        v = atr_values[idx]
        if np.isfinite(v) and v > 0:
            return float(v)
        idx -= 1
    return float(fallback)
