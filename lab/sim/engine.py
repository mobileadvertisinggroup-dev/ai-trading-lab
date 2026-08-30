"""Main simulator engine — implements SIMULATOR_SEMANTICS.md exactly.

Strategy-agnostic mechanics: callers (arm runners) compute signals, sizes,
and cost tiers; the engine enforces fills, costs, capacity, protection,
funding, insolvency, and immutable event ledgers. Deterministic: identical
inputs produce identical event streams.

Independence (FINAL-1.2 §13): this package must never import, or be
imported by, lab.refledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lab import protocol as P


@dataclass(frozen=True)
class Bar:
    open_time: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Costs:
    """Per-order cost parameters, tier-resolved by the caller at decision
    time (SIMULATOR_SEMANTICS §2)."""
    half_spread: float
    slippage: float
    fee: float = P.TAKER_FEE


@dataclass
class Position:
    pos_id: int
    symbol: str
    side: int                 # +1 long, -1 short
    qty: float
    entry_fill: float
    entry_time: int
    decision_ts: int
    stop: float
    target: float
    r_dist: float
    costs: Costs
    fees_paid: float = 0.0
    funding_paid: float = 0.0
    realized_pnl: float = 0.0
    last_mark: float = 0.0
    mae: float = 0.0          # max adverse excursion, in price terms
    mfe: float = 0.0          # max favorable excursion
    open_qty: float = 0.0
    closed: bool = False
    close_reason: str | None = None
    # D74: set ONLY by the diagnostic clone_open, never by any actual
    # arm's entry path. A mirrored clone is created BEFORE its engine
    # processes the entry bar (so it is already open at the funding
    # phase), whereas the actual position it mirrors fills AFTER that
    # bar's funding phase and pays nothing. This position-level stamp
    # exempts the clone from funding (and funding_missing) on exactly
    # its entry bar — identical entry-bar semantics to the mirrored
    # actual — and has no effect on later boundaries or on any
    # non-clone position (default None).
    clone_entry_bar_ms: int | None = None

    def __post_init__(self):
        self.open_qty = self.qty
        self.last_mark = self.entry_fill

    def unrealized(self, mark: float) -> float:
        return self.side * self.open_qty * (mark - self.entry_fill)


@dataclass
class _PendingEntry:
    symbol: str
    side: int
    qty: float
    stop: float
    target: float
    r_dist: float
    decision_ts: int
    costs: Costs
    max_notional: float | None = None   # per-position cap; qty reduced at fill
    stop_offset: float | None = None    # anchor at fill: stop = fill -/+ offset
    target_offset: float | None = None  # anchor at fill: target = fill +/- offset


@dataclass
class _PendingExit:
    pos_id: int
    fraction: float           # 1.0 = full close
    reason: str
    slip_mult: float = 1.0


class Engine:
    def __init__(self, starting_cash: float,
                 max_positions: int = P.MAX_CONCURRENT_POSITIONS,
                 max_gross_exposure: float = P.MAX_GROSS_EXPOSURE,
                 min_notional: float = P.MIN_ORDER_NOTIONAL_USDT):
        self.cash = float(starting_cash)
        self.max_positions = max_positions
        self.max_gross_exposure = max_gross_exposure
        self.min_notional = min_notional
        self.positions: dict[int, Position] = {}
        self.ruined = False
        self.events: list[dict] = []      # append-only
        self._next_id = 1
        self._pending_entries: list[_PendingEntry] = []
        self._pending_exits: list[_PendingExit] = []

    # ------------------------------------------------------------- helpers
    def _emit(self, t: int, kind: str, **detail):
        self.events.append({"t": int(t), "kind": kind, **detail})

    def open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if not p.closed]

    def equity(self, marks: dict[str, float]) -> float:
        eq = self.cash
        for p in self.open_positions():
            eq += p.unrealized(marks.get(p.symbol, p.last_mark))
        return eq

    def gross_exposure(self, marks: dict[str, float]) -> float:
        return sum(p.open_qty * marks.get(p.symbol, p.last_mark)
                   for p in self.open_positions())

    def clone_open(self, t: int, symbol: str, side: int, qty: float,
                   fill: float, stop: float, target: float, r_dist: float,
                   decision_ts: int, costs: Costs) -> int:
        """DIAGNOSTIC ONLY (D61 blocker A — G matched-entry management
        shadow): mirror an ACTUAL fill from another account into this
        diagnostic engine at the identical timestamp, symbol, side,
        quantity, fill price, and initial protection. Capacity checks are
        bypassed BY DESIGN — this account is never claimed to be an
        independently feasible portfolio — and an explicit
        `diagnostic_over_cap` event is emitted whenever the mirrored book
        exceeds the position cap. Never called by any official arm
        account; outside SIMULATOR_SEMANTICS entry semantics."""
        fee = qty * fill * costs.fee
        self.cash -= fee
        p = Position(self._next_id, symbol, side, qty, fill, t,
                     decision_ts, stop, target, r_dist, costs,
                     fees_paid=fee, clone_entry_bar_ms=t)
        self.positions[p.pos_id] = p
        self._next_id += 1
        self._emit(t, "fill_open", pos_id=p.pos_id, symbol=symbol,
                   side=side, qty=qty, price=fill, fee=fee, stop=stop,
                   target=target, decision_ts=decision_ts, cloned=True)
        n_open = len(self.open_positions())
        if n_open > self.max_positions:
            self._emit(t, "diagnostic_over_cap", n_open=n_open,
                       cap=self.max_positions)
        return p.pos_id

    @staticmethod
    def _entry_fill_price(ref: float, side: int, c: Costs) -> float:
        return ref * (1 + side * (c.half_spread + c.slippage))

    @staticmethod
    def _exit_fill_price(ref: float, side: int, c: Costs, slip_mult: float) -> float:
        # closing a long sells (adverse = down); closing a short buys (up)
        return ref * (1 - side * (c.half_spread + c.slippage * slip_mult))

    # ------------------------------------------------------- caller inputs
    def submit_entry(self, symbol: str, side: int, qty: float, stop: float,
                     target: float, r_dist: float, decision_ts: int,
                     costs: Costs, max_notional: float | None = None,
                     stop_offset: float | None = None,
                     target_offset: float | None = None) -> None:
        """Queue an entry decided at decision_ts, to fill at that bar's open.
        Submission order == protocol §2.6 processing order. max_notional:
        per-position cap — qty is reduced at fill to fit (protocol §2.5).
        stop_offset/target_offset: protocol §2.4 anchors protection off the
        FILL price — when given, they override stop/target with
        fill -/+ offset at fill time."""
        self._pending_entries.append(_PendingEntry(
            symbol, side, qty, stop, target, r_dist, decision_ts, costs,
            max_notional, stop_offset, target_offset))

    def submit_exit(self, pos_id: int, fraction: float, reason: str,
                    slip_mult: float = 1.0) -> None:
        """Queue a market exit to fill at the next processed bar's open."""
        self._pending_exits.append(_PendingExit(pos_id, fraction, reason,
                                                slip_mult))

    def apply_management_action(self, t: int, pos_id: int, action: str,
                                new_stop: float | None = None) -> bool:
        """SIMULATOR_SEMANTICS §4. Returns True if accepted."""
        p = self.positions.get(pos_id)

        def reject(why):
            self._emit(t, "invalid_action", pos_id=pos_id, action=action,
                       reason=why)
            return False

        if p is None or p.closed:
            return reject("no such open position")
        if action == "hold":
            return True
        if action == "reduce_25":
            self.submit_exit(pos_id, 0.25, "rl_reduce_25")
            return True
        if action == "reduce_50":
            self.submit_exit(pos_id, 0.50, "rl_reduce_50")
            return True
        if action == "close":
            self.submit_exit(pos_id, 1.0, "rl_close")
            return True
        if action == "tighten_stop":
            if new_stop is None:
                return reject("tighten_stop requires new_stop")
            tighter = (new_stop > p.stop) if p.side > 0 else (new_stop < p.stop)
            if not tighter:
                return reject("stop may only tighten")
            # stop must remain protective (on the loss side of the mark)
            if (p.side > 0 and new_stop >= p.last_mark) or \
               (p.side < 0 and new_stop <= p.last_mark):
                return reject("stop must stay on the protective side")
            p.stop = float(new_stop)
            self._emit(t, "stop_tightened", pos_id=pos_id, stop=p.stop)
            return True
        if action == "move_stop_breakeven":
            be = p.entry_fill
            tighter = (be > p.stop) if p.side > 0 else (be < p.stop)
            if not tighter:
                return reject("breakeven would widen the stop")
            if (p.side > 0 and be >= p.last_mark) or \
               (p.side < 0 and be <= p.last_mark):
                return reject("breakeven not yet protective")
            p.stop = be
            self._emit(t, "stop_tightened", pos_id=pos_id, stop=p.stop,
                       breakeven=True)
            return True
        return reject("unknown action")

    # ------------------------------------------------------------ mechanics
    def _fill_close(self, t: int, p: Position, qty: float, fill: float,
                    reason: str):
        fee = qty * fill * p.costs.fee
        pnl = p.side * qty * (fill - p.entry_fill)
        self.cash += pnl - fee
        p.fees_paid += fee
        p.realized_pnl += pnl
        p.open_qty -= qty
        self._emit(t, "fill_close", pos_id=p.pos_id, symbol=p.symbol,
                   qty=qty, price=fill, fee=fee, pnl=pnl, reason=reason,
                   remaining_qty=p.open_qty)
        if p.open_qty <= 1e-12:
            p.open_qty = 0.0
            p.closed = True
            p.close_reason = reason
            self._emit(t, "position_closed", pos_id=p.pos_id,
                       symbol=p.symbol, reason=reason,
                       realized_pnl=p.realized_pnl, fees=p.fees_paid,
                       funding=p.funding_paid, mae=p.mae, mfe=p.mfe)

    def _process_funding(self, t: int, bars: dict[str, Bar],
                         funding: dict[str, float],
                         prev_close: dict[str, float]):
        if t % P.FUNDING_INTERVAL_MS:
            return
        for p in self.open_positions():
            if p.clone_entry_bar_ms == t:
                # D74: a diagnostic clone on its entry bar — the actual
                # position it mirrors filled AFTER this bar's funding
                # phase, so it pays nothing and emits nothing here
                continue
            if p.symbol not in funding:
                self._emit(t, "funding_missing", pos_id=p.pos_id,
                           symbol=p.symbol)
                continue
            rate = funding[p.symbol]
            mark = prev_close.get(p.symbol)
            if mark is None:
                mark = bars[p.symbol].open if p.symbol in bars else p.last_mark
            transfer = rate * p.open_qty * mark * p.side   # long pays +rate
            self.cash -= transfer
            p.funding_paid += transfer
            self._emit(t, "funding", pos_id=p.pos_id, symbol=p.symbol,
                       rate=rate, mark=mark, paid=transfer)

    def _process_pending_exits(self, t: int, bars: dict[str, Bar]):
        remaining = []
        for x in self._pending_exits:
            p = self.positions.get(x.pos_id)
            if p is None or p.closed:
                self._emit(t, "exit_dropped", pos_id=x.pos_id, reason=x.reason)
                continue
            bar = bars.get(p.symbol)
            if bar is None:
                remaining.append(x)      # defer to next existing bar (§5)
                self._emit(t, "exit_deferred", pos_id=x.pos_id,
                           reason=x.reason)
                continue
            gap_stop = (bar.open <= p.stop if p.side > 0
                        else bar.open >= p.stop)
            if gap_stop and x.fraction >= 1.0:
                # protocol §2.4 exit priority: the stop outranks a queued
                # market exit when both trigger at the open (gap-through)
                self._emit(t, "exit_open_gap_stop_priority", pos_id=p.pos_id,
                           queued_reason=x.reason, stop=p.stop, open=bar.open)
                fill = self._exit_fill_price(bar.open, p.side, p.costs,
                                             P.STOP_SLIPPAGE_MULT)
                self._fill_close(t, p, p.open_qty, fill, "stop")
                continue
            qty = p.open_qty * x.fraction
            fill = self._exit_fill_price(bar.open, p.side, p.costs,
                                         x.slip_mult)
            self._fill_close(t, p, qty, fill, x.reason)
        self._pending_exits = remaining

    def _process_pending_entries(self, t: int, bars: dict[str, Bar],
                                 marks: dict[str, float]):
        for e in self._pending_entries:
            if self.ruined:
                self._emit(t, "rejection", symbol=e.symbol, reason="ruined",
                           decision_ts=e.decision_ts)
                continue
            bar = bars.get(e.symbol)
            if bar is None:
                self._emit(t, "entry_cancelled", symbol=e.symbol,
                           reason="missing_bar", decision_ts=e.decision_ts)
                continue
            fill = self._entry_fill_price(bar.open, e.side, e.costs)
            qty = e.qty
            if e.max_notional is not None and qty * fill > e.max_notional:
                qty = e.max_notional / fill     # reduced to fit (§2.5)
            notional = qty * fill
            if notional < self.min_notional:
                self._emit(t, "rejection", symbol=e.symbol,
                           reason="min_notional", notional=notional,
                           decision_ts=e.decision_ts)
                continue
            if len(self.open_positions()) >= self.max_positions:
                self._emit(t, "rejection", symbol=e.symbol,
                           reason="max_positions", decision_ts=e.decision_ts)
                continue
            eq = self.equity(marks)
            if self.gross_exposure(marks) + notional > self.max_gross_exposure * eq:
                self._emit(t, "rejection", symbol=e.symbol,
                           reason="capacity", notional=notional,
                           equity=eq, decision_ts=e.decision_ts)
                continue
            fee = notional * e.costs.fee
            self.cash -= fee
            stop = (fill - e.side * e.stop_offset
                    if e.stop_offset is not None else e.stop)
            target = (fill + e.side * e.target_offset
                      if e.target_offset is not None else e.target)
            p = Position(self._next_id, e.symbol, e.side, qty, fill, t,
                         e.decision_ts, stop, target, e.r_dist, e.costs,
                         fees_paid=fee)
            self.positions[p.pos_id] = p
            self._next_id += 1
            self._emit(t, "fill_open", pos_id=p.pos_id, symbol=p.symbol,
                       side=p.side, qty=p.qty, price=fill, fee=fee,
                       stop=p.stop, target=p.target,
                       decision_ts=e.decision_ts)
        self._pending_entries = []

    def _process_protection(self, t: int, bars: dict[str, Bar]):
        for pos_id in sorted(self.positions):
            p = self.positions[pos_id]
            if p.closed:
                continue
            bar = bars.get(p.symbol)
            if bar is None:
                self._emit(t, "protection_deferred", pos_id=pos_id)
                continue
            # excursion tracking (price terms, favorable positive)
            p.mfe = max(p.mfe, p.side * ((bar.high if p.side > 0 else bar.low)
                                         - p.entry_fill))
            p.mae = min(p.mae, p.side * ((bar.low if p.side > 0 else bar.high)
                                         - p.entry_fill))
            stop_hit = bar.low <= p.stop if p.side > 0 else bar.high >= p.stop
            tgt_hit = bar.high >= p.target if p.side > 0 else bar.low <= p.target
            if stop_hit and tgt_hit:
                self._emit(t, "ambiguity", pos_id=pos_id, stop=p.stop,
                           target=p.target, rule="stop_first")
            if stop_hit:
                # gap-through: a bar opening beyond the stop fills at the
                # open (worse), never at the stop level (SIM_SEMANTICS §3.4)
                ref = (min(p.stop, bar.open) if p.side > 0
                       else max(p.stop, bar.open))
                fill = self._exit_fill_price(ref, p.side, p.costs,
                                             P.STOP_SLIPPAGE_MULT)
                self._fill_close(t, p, p.open_qty, fill, "stop")
            elif tgt_hit:
                self._fill_close(t, p, p.open_qty, p.target, "target")
            else:
                p.last_mark = bar.close

    def _check_insolvency(self, t: int, bars: dict[str, Bar]):
        if self.ruined:
            return
        marks = {p.symbol: (bars[p.symbol].close if p.symbol in bars
                            else p.last_mark) for p in self.open_positions()}
        if self.equity(marks) <= 0:
            self._emit(t, "insolvency", equity=self.equity(marks))
            for p in list(self.open_positions()):
                ref = marks[p.symbol]
                fill = self._exit_fill_price(ref, p.side, p.costs,
                                             P.STOP_SLIPPAGE_MULT)
                self._fill_close(t, p, p.open_qty, fill, "insolvency")
            self.ruined = True

    # ------------------------------------------------------------ main step
    def process_bar_time(self, t: int, bars: dict[str, Bar],
                         funding: dict[str, float] | None = None,
                         prev_close: dict[str, float] | None = None):
        """Process one 15m timestamp (SIMULATOR_SEMANTICS §3 order)."""
        marks = {s: b.open for s, b in bars.items()}
        self._process_funding(t, bars, funding or {}, prev_close or {})
        self._process_pending_exits(t, bars)
        self._process_pending_entries(t, bars, marks)
        self._process_protection(t, bars)
        self._check_insolvency(t, bars)

    def force_close_all(self, t: int, marks: dict[str, float], reason: str,
                        slip_mult: float = 1.0):
        """Evaluation-boundary / delisting closes (§5, §6)."""
        for p in list(self.open_positions()):
            ref = marks.get(p.symbol, p.last_mark)
            fill = self._exit_fill_price(ref, p.side, p.costs, slip_mult)
            self._fill_close(t, p, p.open_qty, fill, reason)

    def force_close(self, t: int, pos_id: int, mark: float, reason: str,
                    slip_mult: float = 1.0):
        """Single-position forced close (protocol §2: forced_delist_close
        at the last traded 15m close, 2x slip per §5). Pending exits for
        the position drop naturally as exit_dropped."""
        p = self.positions.get(pos_id)
        if p is None or p.closed:
            return
        fill = self._exit_fill_price(mark, p.side, p.costs, slip_mult)
        self._fill_close(t, p, p.open_qty, fill, reason)
