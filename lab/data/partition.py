"""Mechanical universe / round-validity / eligible-interval / partition logic.

Pure functions of availability calendars — no favorable-appearance choices
anywhere (SPEC §7, protocol §4, §6, §7). Everything operates on *pre-computed
calendars* so the same code runs identically inside the sealing pipeline
(mechanical pass-through) and on the plaintext lake.

Calendar format (one pandas DataFrame per symbol), indexed by UTC calendar
date (as pandas Timestamp, midnight UTC):
    bars_present : int   number of existing 15m bars that day (0..96)
    qvol         : float daily quote volume; NaN when undefined
                   (defined only if bars_present >= DAILY_QVOL_MIN_BARS)
Plus per-symbol metadata: first_bar_ms (int), last_bar_ms (int).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from lab import protocol as P

DAY_MS = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class SymbolCalendar:
    symbol: str
    daily: pd.DataFrame          # index: date (midnight UTC), cols: bars_present, qvol
    first_bar_ms: int
    last_bar_ms: int


def build_symbol_calendar(symbol: str, open_times_ms: np.ndarray,
                          quote_volumes: np.ndarray) -> SymbolCalendar:
    """Build the daily availability/volume calendar from raw 15m bar data."""
    if len(open_times_ms) == 0:
        empty = pd.DataFrame(columns=["bars_present", "qvol"])
        return SymbolCalendar(symbol, empty, -1, -1)
    days = (open_times_ms // DAY_MS) * DAY_MS
    df = pd.DataFrame({"day": days, "qv": quote_volumes})
    g = df.groupby("day")["qv"].agg(bars_present="count", qvol="sum")
    g.loc[g["bars_present"] < P.DAILY_QVOL_MIN_BARS, "qvol"] = np.nan
    g.index = pd.to_datetime(g.index, unit="ms", utc=True)
    return SymbolCalendar(symbol, g,
                          int(open_times_ms.min()), int(open_times_ms.max()))


def liquidity_median(cal: SymbolCalendar, t_ms: int) -> float:
    """Median daily qvol over the trailing 30 calendar days strictly before t.

    NaN (ineligible) unless >= UNIVERSE_MIN_DEFINED_DAYS days are defined.
    """
    day_t = (t_ms // DAY_MS) * DAY_MS
    lo = pd.to_datetime(day_t - P.UNIVERSE_TRAILING_DAYS * DAY_MS, unit="ms", utc=True)
    hi = pd.to_datetime(day_t - DAY_MS, unit="ms", utc=True)
    window = cal.daily.loc[lo:hi, "qvol"].dropna()
    if len(window) < P.UNIVERSE_MIN_DEFINED_DAYS:
        return float("nan")
    return float(window.median())


def completeness(cal: SymbolCalendar, t_ms: int) -> float:
    """Share of expected 15m bars over the trailing 30 days strictly before t."""
    day_t = (t_ms // DAY_MS) * DAY_MS
    lo = pd.to_datetime(day_t - P.UNIVERSE_TRAILING_DAYS * DAY_MS, unit="ms", utc=True)
    hi = pd.to_datetime(day_t - DAY_MS, unit="ms", utc=True)
    present = int(cal.daily.loc[lo:hi, "bars_present"].sum())
    expected = P.UNIVERSE_TRAILING_DAYS * P.BARS_15M_PER_DAY
    return present / expected


def is_eligible(cal: SymbolCalendar, t_ms: int) -> tuple[bool, float]:
    """Protocol §4 eligibility at decision timestamp t. Returns (ok, liq_median)."""
    if cal.first_bar_ms < 0:
        return False, float("nan")
    if cal.first_bar_ms > t_ms - P.UNIVERSE_MIN_HISTORY_DAYS * DAY_MS:
        return False, float("nan")
    if cal.last_bar_ms < t_ms - P.TRADABLE_LOOKBACK_MS:      # delisted/halted
        return False, float("nan")
    med = liquidity_median(cal, t_ms)
    if not np.isfinite(med) or med < P.UNIVERSE_MIN_MEDIAN_DAILY_QVOL_USDT:
        return False, med
    if completeness(cal, t_ms) < P.UNIVERSE_MIN_COMPLETENESS:
        return False, med
    return True, med


def universe_at(t_ms: int, calendars: dict[str, SymbolCalendar]) -> list[str]:
    """U(t): top-N eligible symbols by liquidity median desc, ties lexicographic."""
    if not P.is_four_hour_boundary(t_ms):
        raise ValueError(f"{t_ms} is not a 4h boundary")
    rows = []
    for sym in sorted(calendars):
        ok, med = is_eligible(calendars[sym], t_ms)
        if ok:
            rows.append((sym, med))
    rows.sort(key=lambda r: (-r[1], r[0]))
    return [sym for sym, _ in rows[: P.UNIVERSE_TOP_N]]


def btc_4h_bar_complete(cal: SymbolCalendar, t_ms: int, bars_15m_by_4h: dict[int, int]) -> bool:
    """True iff the context-symbol 4h bar closing at t has all 16 15m bars."""
    return bars_15m_by_4h.get(t_ms - P.BAR_4H_MS, 0) == P.BARS_15M_PER_4H


def round_validity(boundaries_ms: np.ndarray,
                   calendars: dict[str, SymbolCalendar],
                   btc_bars_15m_by_4h: dict[int, int]) -> pd.Series:
    """Protocol §6: valid round iff BTC 4h bar complete AND >= 30 eligible symbols."""
    flags = {}
    for t in boundaries_ms:
        t = int(t)
        if not btc_4h_bar_complete(calendars.get(P.CONTEXT_SYMBOL), t, btc_bars_15m_by_4h):
            flags[t] = False
            continue
        n = 0
        for sym in calendars:
            ok, _ = is_eligible(calendars[sym], t)
            if ok:
                n += 1
                if n >= P.VALID_ROUND_MIN_ELIGIBLE:
                    break
        flags[t] = n >= P.VALID_ROUND_MIN_ELIGIBLE
    return pd.Series(flags).sort_index()


def eligible_interval(validity: pd.Series, ingestion_freeze_ms: int) -> tuple[int, int]:
    """Protocol §6: (start_ms, end_ms) of the eligible continuous interval.

    start = earliest valid boundary T0 with >= 95% of boundaries in
    [T0, T0+60d] valid; end = last valid boundary <= freeze - 48h.
    Raises if no qualifying interval exists (honest failure, never invented).
    """
    v = validity.sort_index()
    ts = v.index.to_numpy(dtype=np.int64)
    flags = v.to_numpy(dtype=bool)

    end_cut = ingestion_freeze_ms - P.INTERVAL_END_BUFFER_MS
    valid_ts = ts[flags & (ts <= end_cut)]
    if len(valid_ts) == 0:
        raise RuntimeError("no valid rounds before freeze buffer")
    end_ms = int(valid_ts.max())

    window_ms = P.INTERVAL_START_WINDOW_DAYS * DAY_MS
    for i in range(len(ts)):
        if not flags[i]:
            continue
        t0 = ts[i]
        if t0 > end_ms:
            break
        in_win = (ts >= t0) & (ts <= t0 + window_ms)
        if in_win.sum() == 0:
            continue
        if flags[in_win].mean() >= P.INTERVAL_START_VALID_FRACTION:
            return int(t0), end_ms
    raise RuntimeError("no start boundary satisfies the 60-day 95%-valid rule")


def all_boundaries(start_ms: int, end_ms: int) -> np.ndarray:
    """All 4h boundaries in [start_ms, end_ms], inclusive."""
    if start_ms % P.BAR_4H_MS or end_ms % P.BAR_4H_MS:
        raise ValueError("interval endpoints must be 4h boundaries")
    return np.arange(start_ms, end_ms + 1, P.BAR_4H_MS, dtype=np.int64)


def compute_partition(start_ms: int, end_ms: int) -> dict:
    """Protocol §7 partition over ALL boundaries in the eligible interval.

    Returns non-outcome partition metadata only (timestamps and counts).
    """
    b = all_boundaries(start_ms, end_ms)
    n = len(b)
    i_t, i_v = P.partition_indices(n)
    return {
        "n_boundaries": n,
        "train_start_ms": int(b[0]),
        "train_end_ms": int(b[i_t - 1]),
        "validation_start_ms": int(b[i_t]),
        "validation_end_ms": int(b[i_v - 1]),
        "holdout_start_ms": int(b[i_v]),
        "holdout_end_ms": int(b[n - 1]),
        "i_t": i_t,
        "i_v": i_v,
        # quarantine boundary for RAW data = decision timestamp of first
        # holdout round (protocol §7): all 15m rows with open_time >= this
        # are sealed.
        "quarantine_start_ms": int(b[i_v]),
    }
