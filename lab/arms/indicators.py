"""Deterministic 4h aggregation and indicators (EXPERIMENT_PROTOCOL.md §1).

Pure numpy; no lookahead by construction: every series value at index i uses
only bars completed at or before bar i, and the Donchian channels exclude the
signal bar itself (prior-n definition).
"""
from __future__ import annotations

import numpy as np

from lab import protocol as P


def aggregate_4h(open_time_ms: np.ndarray, o: np.ndarray, h: np.ndarray,
                 l: np.ndarray, c: np.ndarray):
    """Aggregate 15m bars into complete 4h bars (16/16 15m bars required).

    Returns dict of arrays: open_time (4h bar open, ms), open, high, low,
    close. Incomplete 4h windows are dropped (protocol §1).
    """
    if len(open_time_ms) == 0:
        return {k: np.array([]) for k in ("open_time", "open", "high", "low", "close")}
    order = np.argsort(open_time_ms)
    t, o, h, l, c = (a[order] for a in (open_time_ms, o, h, l, c))
    g = (t // P.BAR_4H_MS) * P.BAR_4H_MS
    uniq, start_idx, counts = np.unique(g, return_index=True, return_counts=True)
    complete = counts == P.BARS_15M_PER_4H
    out_t, out_o, out_h, out_l, out_c = [], [], [], [], []
    for gi, si, ci, ok in zip(uniq, start_idx, counts, complete):
        if not ok:
            continue
        sl = slice(si, si + ci)
        out_t.append(gi)
        out_o.append(o[sl][0])
        out_h.append(h[sl].max())
        out_l.append(l[sl].min())
        out_c.append(c[sl][-1])
    return {"open_time": np.array(out_t, dtype=np.int64),
            "open": np.array(out_o), "high": np.array(out_h),
            "low": np.array(out_l), "close": np.array(out_c)}


def donchian_prior(high: np.ndarray, low: np.ndarray, n: int):
    """HH(n)/LL(n) over the n bars strictly BEFORE each bar (protocol §1).

    hh[i] = max(high[i-n : i]); NaN while fewer than n prior bars exist.
    """
    m = len(high)
    hh = np.full(m, np.nan)
    ll = np.full(m, np.nan)
    for i in range(n, m):
        hh[i] = high[i - n:i].max()
        ll[i] = low[i - n:i].min()
    return hh, ll


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               n: int = P.ATR_PERIOD):
    """Wilder ATR on completed 4h bars; atr[i] uses bars 0..i.

    Seeded with the simple mean of the first n true ranges; NaN until
    >= 3n bars exist (protocol §1: ATR defined only with >= 3n bars).
    """
    m = len(close)
    atr = np.full(m, np.nan)
    if m < 2:
        return atr
    tr = np.empty(m)
    tr[0] = high[0] - low[0]
    for i in range(1, m):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
    if m < n:
        return atr
    val = tr[:n].mean()
    smoothed = np.full(m, np.nan)
    smoothed[n - 1] = val
    for i in range(n, m):
        val = (val * (n - 1) + tr[i]) / n
        smoothed[i] = val
    min_bars = P.ATR_MIN_HISTORY_BARS
    atr[min_bars - 1:] = smoothed[min_bars - 1:]
    return atr


class SymbolSeries:
    """Precomputed per-symbol 4h series with boundary lookup.

    A 4h bar with open_time g "closes at" decision boundary g + 4h; signals
    at boundary t use the bar closing at t (protocol §2.2).
    """

    def __init__(self, open_time_15m: np.ndarray, o, h, l, c):
        bars = aggregate_4h(open_time_15m, o, h, l, c)
        self.t4 = bars["open_time"]
        self.close4 = bars["close"]
        self.hh_entry, self.ll_entry = donchian_prior(
            bars["high"], bars["low"], P.DONCHIAN_ENTRY_BARS)
        self.hh_exit, self.ll_exit = donchian_prior(
            bars["high"], bars["low"], P.DONCHIAN_EXIT_BARS)
        self.atr = wilder_atr(bars["high"], bars["low"], bars["close"])
        # boundary -> index of the bar closing at that boundary
        self._idx = {int(g) + P.BAR_4H_MS: i for i, g in enumerate(self.t4)}

    def at_boundary(self, t_ms: int) -> dict | None:
        """Signal inputs available at decision boundary t, or None if the 4h
        bar closing at t doesn't exist (missing data)."""
        i = self._idx.get(int(t_ms))
        if i is None:
            return None
        return {"close": float(self.close4[i]),
                "hh_entry": float(self.hh_entry[i]),
                "ll_entry": float(self.ll_entry[i]),
                "hh_exit": float(self.hh_exit[i]),
                "ll_exit": float(self.ll_exit[i]),
                "atr": float(self.atr[i])}
