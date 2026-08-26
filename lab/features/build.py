"""Feature builder — implements DATA_DICTIONARY.md (draft F01–F28).

Every feature is a function of information STRICTLY before the candidate's
decision timestamp t: completed 4h bars, prior funding events, the
point-in-time universe, and the candidate-ledger row itself (whose fields
are all decision-time). No entry fills, no labels, no post-t bars — the
no-lookahead property is asserted by test (mutating every bar at/after t
must leave every feature bit-identical).

The builder stores raw values (hour/dow as integers); one-hot encoding is a
preprocessing step fitted on training rows only (spec §10).
"""
from __future__ import annotations

import math

import numpy as np

from lab import protocol as P

FEATURE_SET_VERSION = "features-v1-draft"

# Canonical training-time column order: the sorted (zero-padded) F-names.
# Model artifacts are fitted on matrices in exactly this order; adapters
# must bind by THIS list, never by booster.feature_name() (which is
# generic Column_N when fitted from bare arrays) — shakedown defect
# SD-FEATNAMES.
FEATURE_NAMES = [
    "F01_side", "F02_atr_pct", "F03_breakout_strength", "F04_channel_width",
    "F05_rank_frac", "F06_n_eligible", "F07_ret_1", "F08_ret_5",
    "F09_ret_20", "F10_ret_60", "F11_rvol_20", "F12_rvol_ratio",
    "F13_trend_sma20", "F14_trend_sma60", "F15_dist_opposite",
    "F16_breakout_run", "F17_btc_ret_5", "F18_btc_ret_20", "F19_btc_ret_60",
    "F20_btc_rvol_20", "F21_breadth_sma20", "F22_round_side_count",
    "F23_regime_code", "F24_log_liq", "F25_funding_last",
    "F26_funding_mean_3d", "F27_hour_slot", "F28_dow",
]


class FeatureSeries:
    """Per-symbol derived arrays over completed 4h bars, indexed by the
    decision boundary at which each bar becomes available (its close)."""

    def __init__(self, t4_open_ms: np.ndarray, close4: np.ndarray,
                 hh_entry: np.ndarray, ll_entry: np.ndarray,
                 hh_exit: np.ndarray, ll_exit: np.ndarray):
        self.close = np.asarray(close4, float)
        self.hh_entry, self.ll_entry = hh_entry, ll_entry
        self.hh_exit, self.ll_exit = hh_exit, ll_exit
        logc = np.log(self.close)
        self.logret1 = np.diff(logc, prepend=np.nan)
        n = len(self.close)
        self.ret = {}
        for w in (1, 5, 20, 60):
            r = np.full(n, np.nan)
            r[w:] = logc[w:] - logc[:-w]
            self.ret[w] = r
        self.rvol20 = _trailing_std(self.logret1, 20)
        self.rvol60 = _trailing_std(self.logret1, 60)
        self.sma20 = _trailing_mean(self.close, 20)
        self.sma60 = _trailing_mean(self.close, 60)
        # F16: consecutive closes beyond the prior-60 channel midpoint
        mid = (self.hh_entry + self.ll_entry) / 2.0
        run = np.zeros(n)
        for i in range(n):
            if not np.isfinite(mid[i]):
                run[i] = 0
            elif self.close[i] > mid[i]:
                run[i] = run[i - 1] + 1 if i and run[i - 1] > 0 else 1
            elif self.close[i] < mid[i]:
                run[i] = run[i - 1] - 1 if i and run[i - 1] < 0 else -1
            else:
                run[i] = 0
        self.run = np.clip(run, -10, 10)
        self._idx = {int(g) + P.BAR_4H_MS: i for i, g in enumerate(
            np.asarray(t4_open_ms, dtype=np.int64))}

    def index_at(self, t_ms: int) -> int | None:
        return self._idx.get(int(t_ms))


def build_features(cand: dict, sym: FeatureSeries, btc: FeatureSeries,
                   context: dict) -> dict:
    """context: breadth_sma20 (float), round_side_count (int),
    regime_code (0..3), liq_median (float), funding_last (float|nan),
    funding_mean_3d (float|nan) — all computed point-in-time by the caller
    (the orchestrator) from pre-t information only."""
    t = int(cand["t"])
    i = sym.index_at(t)
    j = btc.index_at(t)
    if i is None or j is None:
        raise ValueError("candidate timestamp has no completed bar")
    side = int(cand["side"])
    atr = float(cand["atr"])
    close = float(cand["close"])
    breached = cand["hh_entry"] if side > 0 else cand["ll_entry"]
    opposite = sym.ll_exit[i] if side > 0 else sym.hh_exit[i]

    f = {
        "F01_side": side,
        "F02_atr_pct": atr / close,
        "F03_breakout_strength": side * (close - breached) / atr,
        "F04_channel_width": (cand["hh_entry"] - cand["ll_entry"]) / close,
        "F05_rank_frac": (cand["rank"] - 1) / max(1, cand["n_eligible"]),
        "F06_n_eligible": int(cand["n_eligible"]),
        "F07_ret_1": float(sym.ret[1][i]),
        "F08_ret_5": float(sym.ret[5][i]),
        "F09_ret_20": float(sym.ret[20][i]),
        "F10_ret_60": float(sym.ret[60][i]),
        "F11_rvol_20": float(sym.rvol20[i]),
        "F12_rvol_ratio": float(sym.rvol20[i] / sym.rvol60[i])
                          if sym.rvol60[i] else float("nan"),
        "F13_trend_sma20": (close - float(sym.sma20[i])) / atr,
        "F14_trend_sma60": (close - float(sym.sma60[i])) / atr,
        "F15_dist_opposite": side * (close - float(opposite)) / atr,
        "F16_breakout_run": float(side * sym.run[i]),
        "F17_btc_ret_5": float(btc.ret[5][j]),
        "F18_btc_ret_20": float(btc.ret[20][j]),
        "F19_btc_ret_60": float(btc.ret[60][j]),
        "F20_btc_rvol_20": float(btc.rvol20[j]),
        "F21_breadth_sma20": float(context["breadth_sma20"]),
        "F22_round_side_count": int(context["round_side_count"]),
        "F23_regime_code": int(context["regime_code"]),
        "F24_log_liq": math.log10(context["liq_median"])
                       if context.get("liq_median") else float("nan"),
        "F25_funding_last": float(context.get("funding_last", float("nan"))),
        "F26_funding_mean_3d": float(context.get("funding_mean_3d",
                                                 float("nan"))),
        "F27_hour_slot": (t // P.BAR_4H_MS) % 6,
        "F28_dow": (t // (24 * 3600 * 1000) + 4) % 7,   # epoch day 0 = Thu
        "feature_set_version": FEATURE_SET_VERSION,
    }
    return f


def _trailing_std(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n, len(x)):
        w = x[i - n + 1: i + 1]
        if np.isfinite(w).all():
            out[i] = float(np.std(w, ddof=1))
    return out


def _trailing_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out
