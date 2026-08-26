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
from lab.risk.governor import EntryRequest, PortfolioState, RiskGovernor
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
                 universe_fn, valid_round_fn=None, governor=None):
        """universe_fn(t_ms) -> ordered list of symbols (rank order, §4).
        valid_round_fn(t_ms) -> bool; None = all boundaries valid.
        governor: external risk governor (SPEC §14); every arm gets one —
        pass an instance to share state, None for a fresh default."""
        self.provider = provider
        self.engine = Engine(starting_cash)
        self.universe_fn = universe_fn
        self.valid_round_fn = valid_round_fn or (lambda t: True)
        self.governor = governor or RiskGovernor()
        self.candidates: list[dict] = []       # the candidate ledger
        self.equity_curve: list[dict] = []
        # gap accounting (review directive 2026-08-26): universe members
        # producing NO candidate because signal inputs are missing at the
        # boundary (absent 4h bar / non-finite ATR or channel from gaps).
        self.stats = {"missing_input_skips": 0}
        self._series: dict[str, SymbolSeries] = {}
        self._bars15: dict[str, dict] = {}
        # run() iterates t monotonically, so per-symbol cursors replace the
        # timestamp->index dicts (identical behavior, O(1) memory — the
        # dicts were ~35M entries on the real lake).
        self._cursor: dict[str, int] = {}
        for sym in provider.symbols():
            d = provider.bars_15m(sym)
            self._bars15[sym] = d
            self._series[sym] = SymbolSeries(d["open_time"], d["open"],
                                             d["high"], d["low"], d["close"])
            self._cursor[sym] = 0
        self._last_close: dict[str, float] = {}

    # ---------------------------------------------------------------- bars
    def _bars_at(self, t: int) -> dict[str, Bar]:
        out = {}
        for sym, d in self._bars15.items():
            ot = d["open_time"]
            i = self._cursor[sym]
            n = len(ot)
            while i < n and ot[i] < t:
                i += 1
            self._cursor[sym] = i
            if i < n and ot[i] == t:
                out[sym] = Bar(t, float(d["open"][i]), float(d["high"][i]),
                               float(d["low"][i]), float(d["close"][i]))
        return out

    def _marks(self) -> dict[str, float]:
        return dict(self._last_close)

    # ------------------------------------------------------ decision round
    def _boundary_exits(self, t: int):
        """Trailing-channel and time exits (protocol §2.4), queued for the
        next 15m open. Delisted/permanently-halted symbols (no bar within
        the frozen §4 tradability lookback) are force-closed at the last
        traded 15m close with 2x slip — protocol §2 `forced_delist_close`.
        Detection is point-in-time: only the ABSENCE of recent bars is
        used, never future knowledge."""
        for p in self.engine.open_positions():
            d = self._bars15.get(p.symbol)
            if d is None:
                continue
            ot = d["open_time"]
            i = self._cursor.get(p.symbol, 0)
            n = len(ot)
            # last bar strictly before t (cursor sits at the first bar
            # >= previous step's timestamp)
            while i < n and ot[i] < t:
                i += 1
            last_seen = int(ot[i - 1]) if i > 0 else None
            if last_seen is not None and \
                    last_seen < t - P.TRADABLE_LOOKBACK_MS:
                self.engine.force_close(
                    t, p.pos_id, self._last_close.get(p.symbol, p.last_mark),
                    "forced_delist_close", slip_mult=P.STOP_SLIPPAGE_MULT)
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

    def _portfolio_state(self, equity: float) -> PortfolioState:
        marks = self._marks()
        long_x = short_x = 0.0
        for p in self.engine.open_positions():
            notional = p.open_qty * marks.get(p.symbol, p.last_mark)
            if p.side > 0:
                long_x += notional
            else:
                short_x += notional
        return PortfolioState(equity=equity, gross_exposure=long_x + short_x,
                              long_exposure=long_x, short_exposure=short_x,
                              n_positions=len(self.engine.open_positions()))

    def _decision_round(self, t: int):
        universe = self.universe_fn(t)
        open_syms = {p.symbol for p in self.engine.open_positions()}
        equity = self.engine.equity(self._marks())
        self.governor.observe(
            t, equity,
            positions_with_stop=all(p.stop is not None and p.stop > 0
                                    for p in self.engine.open_positions()))
        n_universe = len(universe)
        for rank, sym in enumerate(universe):
            if sym in open_syms:
                continue
            series = self._series.get(sym)
            sig = series.at_boundary(t) if series else None
            if sig is None or not np.isfinite(sig["atr"]) or sig["atr"] <= 0 \
                    or not np.isfinite(sig["hh_entry"]):
                self.stats["missing_input_skips"] += 1
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
            # external risk governor (SPEC §14): approve / restrict / reject.
            # Uses the signal close as the pre-trade reference price; the
            # engine's own caps re-check at the actual fill.
            decision, allowed_qty, gov_reason = self.governor.check_entry(
                EntryRequest(t=t, symbol=sym, side=side, qty=qty,
                             price=sig["close"], stop_distance=r_dist),
                self._portfolio_state(equity))
            self.candidates.append({
                "t": int(t), "symbol": sym, "side": side,
                "close": sig["close"], "hh_entry": sig["hh_entry"],
                "ll_entry": sig["ll_entry"], "atr": sig["atr"],
                "r_dist": r_dist, "rank": rank + 1,
                "n_eligible": n_universe, "equity": equity,
                "qty_submitted": qty,
                "governor": decision, "governor_reason": gov_reason,
            })
            if decision == "reject":
                continue        # external restriction, recorded — never bypassed
            self.engine.submit_entry(
                sym, side, allowed_qty, stop=0.0, target=0.0,
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
