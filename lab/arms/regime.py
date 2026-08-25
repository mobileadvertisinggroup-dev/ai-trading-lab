"""Arm D — market-regime model (SPEC FINAL-1.2 §3, Arm D).

Independently defined, deterministic, point-in-time regime classifier over
the BTC context 4h series, plus the frozen multiplier policy. All inputs at
decision timestamp t use completed bars strictly before/at t per protocol
§1 conventions; classifications never change when future data arrives
(tested).

Regimes: uptrend / downtrend / sideways / high-volatility stress.

DRAFT-FROZEN policy (recorded in BUILD_STATE; final freeze at Checkpoint 2):

    regime           long multiplier   short multiplier
    stress                0.50              0.50
    uptrend               1.00              0.00   (counter-trend blocked)
    downtrend             0.00              1.00
    sideways              0.50              0.50

Multiplier semantics per spec: 1.00 permit, 0.50 reduce, 0.00 block.
"""
from __future__ import annotations

import numpy as np

from lab import protocol as P

SMA_FAST = 60          # 4h bars (10 days)
SMA_SLOW = 180         # 4h bars (30 days)
VOL_WINDOW = 20        # bars for realized vol
VOL_HISTORY = 1080     # trailing bars (180 days) for the vol quantile
VOL_QUANTILE = 0.90    # stress when rvol_20 above trailing 90th percentile
MIN_HISTORY = SMA_SLOW + 1

REGIMES = ("uptrend", "downtrend", "sideways", "stress")
MULTIPLIERS = {
    "stress": {+1: 0.50, -1: 0.50},
    "uptrend": {+1: 1.00, -1: 0.00},
    "downtrend": {+1: 0.00, -1: 1.00},
    "sideways": {+1: 0.50, -1: 0.50},
}


class RegimeModel:
    """Point-in-time classifier over the BTC 4h close series."""

    version = "regime-v1-draft"

    def __init__(self, t4_open_ms: np.ndarray, close4: np.ndarray):
        order = np.argsort(t4_open_ms)
        self.t4 = np.asarray(t4_open_ms, dtype=np.int64)[order]
        self.close = np.asarray(close4, dtype=np.float64)[order]
        logret = np.diff(np.log(self.close), prepend=np.nan)
        self.rvol = _trailing_std(logret, VOL_WINDOW)
        # boundary t -> index of the bar closing at t
        self._idx = {int(g) + P.BAR_4H_MS: i for i, g in enumerate(self.t4)}

    def classify(self, t_ms: int) -> dict:
        """Regime at decision boundary t. Returns the spec-required record:
        regime, inputs, per-side action + multiplier, model version.
        Insufficient history -> 'stress' (the conservative fail-safe:
        reduce, never full size on unknown conditions), flagged as such."""
        i = self._idx.get(int(t_ms))
        rec = {"t": int(t_ms), "model_version": self.version}
        if i is None or i + 1 < MIN_HISTORY:
            rec.update({"regime": "stress", "insufficient_history": True,
                        "inputs": {},
                        "multiplier": dict(MULTIPLIERS["stress"])})
            return rec
        c = self.close[: i + 1]
        sma_fast = float(c[-SMA_FAST:].mean())
        sma_slow = float(c[-SMA_SLOW:].mean())
        close = float(c[-1])
        vol = float(self.rvol[i])
        lo = max(0, i + 1 - VOL_HISTORY)
        vol_hist = self.rvol[lo: i + 1]
        vol_hist = vol_hist[np.isfinite(vol_hist)]
        vol_q = float(np.quantile(vol_hist, VOL_QUANTILE)) \
            if len(vol_hist) >= VOL_WINDOW else float("inf")

        if np.isfinite(vol) and vol > vol_q:
            regime = "stress"
        elif close > sma_fast > sma_slow:
            regime = "uptrend"
        elif close < sma_fast < sma_slow:
            regime = "downtrend"
        else:
            regime = "sideways"
        rec.update({
            "regime": regime, "insufficient_history": False,
            "inputs": {"close": close, "sma_fast": sma_fast,
                       "sma_slow": sma_slow, "rvol_20": vol,
                       "rvol_q90_trailing": vol_q},
            "multiplier": dict(MULTIPLIERS[regime]),
        })
        return rec


def _trailing_std(x: np.ndarray, n: int) -> np.ndarray:
    """std of the last n values at each index (ddof=1); NaN when < n."""
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        w = x[i - n + 1: i + 1]
        if np.isfinite(w).all():
            out[i] = float(np.std(w, ddof=1))
    return out
