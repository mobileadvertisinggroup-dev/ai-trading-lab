"""Arm A runner — executes EXPERIMENT_PROTOCOL.md §2 on the simulator engine.

Deterministic orchestration: at every valid 4h boundary it evaluates
trailing/time exits for open positions, generates breakout candidates over
U(t) in liquidity-rank order, sizes them, and submits to lab.sim.engine.
Between boundaries it feeds every 15m bar to the engine for stop/target
enforcement and funding.

Emits the CANDIDATE LEDGER: one record per candidate with all decision-time
inputs (spec §4 label reproducibility; Arms B/C/E consume exactly these
events). Candidate records never contain post-decision information.

Market data arrives through a provider interface so the same runner serves
synthetic dev tests, the shakedown, and lake-backed official runs (which use
GuardedLake underneath — never raw paths).
"""
from __future__ import annotations

import numpy as np

from lab import protocol as P
from lab.arms.indicators import SymbolSeries
from lab.sim.engine import Bar, Costs, Engine


class MarketProvider:
    """Interface. bars_15m(symbol) -> dict of numpy arrays
    (open_time, open, high, low, close); funding(symbol) -> dict ts->rate;
    symbols() -> list; universe ranking inputs are supplied per-run."""

    def symbols(self) -> list[str]:
        raise NotImplementedError

    def bars_15m(self, symbol: str) -> dict:
        raise NotImplementedError

    def funding(self, symbol: str) -> dict[int, float]:
        return {}


class ArrayProvider(MarketProvider):
    """In-memory provider for tests and fixtures."""

    def __init__(self, data: dict[str, dict], funding: dict[str, dict] | None = None):
        self._data = data
        self._funding = funding or {}

    def symbols(self):
        return sorted(self._data)

    def bars_15m(self, symbol):
        return self._data[symbol]

    def funding(self, symbol):
        return self._funding.get(symbol, {})


def tier_costs(rank: int) -> Costs:
    """Protocol §5: tier 1 = top TIER1_TOP_N of U(t) by rank (0-based)."""
    tier = 1 if rank < P.TIER1_TOP_N else 2
    return Costs(half_spread=P.HALF_SPREAD[tier], slippage=P.SLIPPAGE[tier])


class ArmARunner:
    def __init__(self, provider: MarketProvider, starting_cash: float,
                 universe_fn, valid_round_fn=None):
        """universe_fn(t_ms) -> ordered list of symbols (rank order, §4).
        valid_round_fn(t_ms) -> bool; None = all boundaries valid."""
        self.provider = provider
        self.engine = Engine(starting_cash)
        self.universe_fn = universe_fn
        self.valid_round_fn = valid_round_fn or (lambda t: True)
        self.candidates: list[dict] = []       # the candidate ledger
        self.equity_curve: list[dict] = []
        self._series: dict[str, SymbolSeries] = {}
        self._bars15: dict[str, dict] = {}
        self._bar_index: dict[str, dict[int, int]] = {}
        for sym in provider.symbols():
            d = provider.bars_15m(sym)
            self._bars15[sym] = d
            self._series[sym] = SymbolSeries(d["open_time"], d["open"],
                                             d["high"], d["low"], d["close"])
            self._bar_index[sym] = {int(t): i
                                    for i, t in enumerate(d["open_time"])}
        self._last_close: dict[str, float] = {}

    # ---------------------------------------------------------------- bars
    def _bars_at(self, t: int) -> dict[str, Bar]:
        out = {}
        for sym, idx in self._bar_index.items():
            i = idx.get(t)
            if i is not None:
                d = self._bars15[sym]
                out[sym] = Bar(t, float(d["open"][i]), float(d["high"][i]),
                               float(d["low"][i]), float(d["close"][i]))
        return out

    def _marks(self) -> dict[str, float]:
        return dict(self._last_close)

    # ------------------------------------------------------ decision round
    def _boundary_exits(self, t: int):
        """Trailing-channel and time exits (protocol §2.4), queued for the
        next 15m open."""
        for p in self.engine.open_positions():
            sig = self._series[p.symbol].at_boundary(t)
            bars_held = (t - p.decision_ts) // P.BAR_4H_MS
            if sig is not None and np.isfinite(sig["ll_exit"]) and \
                    np.isfinite(sig["hh_exit"]):
                trail = (sig["close"] < sig["ll_exit"] if p.side > 0
                         else sig["close"] > sig["hh_exit"])
                if trail:
                    self.engine.submit_exit(p.pos_id, 1.0, "trailing_exit")
                    continue
            if bars_held >= P.MAX_HOLD_BARS_4H:
                self.engine.submit_exit(p.pos_id, 1.0, "time_exit")

    def _decision_round(self, t: int):
        universe = self.universe_fn(t)
        open_syms = {p.symbol for p in self.engine.open_positions()}
        equity = self.engine.equity(self._marks())
        n_universe = len(universe)
        for rank, sym in enumerate(universe):
            if sym in open_syms:
                continue
            series = self._series.get(sym)
            sig = series.at_boundary(t) if series else None
            if sig is None or not np.isfinite(sig["atr"]) or sig["atr"] <= 0 \
                    or not np.isfinite(sig["hh_entry"]):
                continue                       # missing inputs -> no candidate
            side = 0
            if sig["close"] > sig["hh_entry"]:
                side = +1
            elif sig["close"] < sig["ll_entry"]:
                side = -1
            if side == 0:
                continue
            r_dist = P.STOP_ATR_MULT * sig["atr"]
            qty = (P.RISK_FRACTION * equity) / r_dist
            costs = tier_costs(rank)
            self.candidates.append({
                "t": int(t), "symbol": sym, "side": side,
                "close": sig["close"], "hh_entry": sig["hh_entry"],
                "ll_entry": sig["ll_entry"], "atr": sig["atr"],
                "r_dist": r_dist, "rank": rank + 1,
                "n_eligible": n_universe, "equity": equity,
                "qty_submitted": qty,
            })
            self.engine.submit_entry(
                sym, side, qty, stop=0.0, target=0.0,
                r_dist=r_dist, decision_ts=t, costs=costs,
                max_notional=P.NOTIONAL_CAP_FRACTION * equity,
                stop_offset=r_dist,                       # fill -/+ 2xATR
                target_offset=P.TARGET_R_MULT * r_dist)   # fill +/- 3R

    # ------------------------------------------------------------ main run
    def run(self, start_ms: int, end_ms: int):
        """Iterate all 15m timestamps in [start_ms, end_ms]."""
        if start_ms % P.BAR_4H_MS or end_ms % P.BAR_15M_MS:
            raise ValueError("start must be a 4h boundary; end a 15m boundary")
        t = start_ms
        while t <= end_ms:
            if t % P.BAR_4H_MS == 0 and self.valid_round_fn(t):
                self._boundary_exits(t)
                self._decision_round(t)
            bars = self._bars_at(t)
            funding = {}
            if t % P.FUNDING_INTERVAL_MS == 0:
                for p in self.engine.open_positions():
                    rate = self.provider.funding(p.symbol).get(t)
                    if rate is not None:
                        funding[p.symbol] = rate
            self.engine.process_bar_time(t, bars, funding=funding,
                                         prev_close=self._marks())
            for sym, b in bars.items():
                self._last_close[sym] = b.close
            if t % P.BAR_4H_MS == 0:
                self.equity_curve.append(
                    {"t": t, "equity": self.engine.equity(self._marks())})
            t += P.BAR_15M_MS
        return self.engine
