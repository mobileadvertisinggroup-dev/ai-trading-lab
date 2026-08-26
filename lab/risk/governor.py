"""External deterministic risk governor — RISK_POLICY.md / SPEC FINAL-1.2 §14.

Wraps every arm, including Arm A. Pure state machine: no model may bypass
it, it can restrict but never increase risk, and every decision is recorded.
"""
from __future__ import annotations

from dataclasses import dataclass

DAY_MS = 24 * 60 * 60 * 1000


@dataclass(frozen=True)
class RiskLimits:
    max_risk_per_trade: float = 0.010      # fraction of equity
    max_gross_exposure: float = 1.50       # x equity
    max_directional_exposure: float = 1.20  # x equity, per direction
    max_positions: int = 10
    daily_loss_limit: float = 0.03         # fraction of day-start equity
    drawdown_limit: float = 0.25           # from trailing-window peak equity
    drawdown_window_days: int = 90         # RISK_POLICY v2 (D46): trailing
    # peak window. v1 measured from the ALL-TIME peak, which made the pause
    # an absorbing state: entries blocked -> equity flat -> drawdown never
    # recovers -> permanent halt (observed on the official Arm A run:
    # frozen for 9,220 of 9,848 rounds after 2021-03-05). A crash still
    # pauses immediately; the pause horizon is now bounded by the window.
    min_notional: float = 50.0


@dataclass(frozen=True)
class EntryRequest:
    t: int
    symbol: str
    side: int              # +1 / -1
    qty: float
    price: float           # entry reference price
    stop_distance: float   # price distance to the protective stop (> 0)
    data_complete: bool = True
    has_protective_stop: bool = True


@dataclass(frozen=True)
class PortfolioState:
    equity: float
    gross_exposure: float
    long_exposure: float
    short_exposure: float
    n_positions: int


class RiskGovernor:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self.emergency_pause = False
        self.integrity_pause = False
        self._day: int | None = None
        self._day_start_equity: float | None = None
        self._day_peaks: dict[int, float] = {}   # day -> max observed equity
        self.events: list[dict] = []       # append-only decision ledger

    # ------------------------------------------------------------ state
    def observe(self, t: int, equity: float,
                positions_with_stop: bool = True):
        """Feed an equity snapshot (call at least once per decision round)."""
        day = t // DAY_MS
        if day != self._day:
            self._day = day
            self._day_start_equity = equity
        self._day_peaks[day] = max(self._day_peaks.get(day, equity), equity)
        cutoff = day - self.limits.drawdown_window_days
        for d in [d for d in self._day_peaks if d < cutoff]:
            del self._day_peaks[d]
        if not positions_with_stop:
            self.integrity_pause = True
            self._rec(t, "integrity_failure",
                      reason="open position without protective stop")

    def _rec(self, t, kind, **kw):
        self.events.append({"t": int(t), "kind": f"governor_{kind}", **kw})

    # ------------------------------------------------------ entry checks
    def _paused_reason(self, state: PortfolioState) -> str | None:
        if self.emergency_pause:
            return "emergency_pause"
        if self.integrity_pause:
            return "integrity_pause"
        if self._day_start_equity is not None and self._day_start_equity > 0:
            day_loss = (self._day_start_equity - state.equity) \
                / self._day_start_equity
            if day_loss >= self.limits.daily_loss_limit:
                return "daily_loss_limit"
        if self._day_peaks:
            peak = max(self._day_peaks.values())    # trailing-window peak
            if peak > 0:
                dd = (peak - state.equity) / peak
                if dd >= self.limits.drawdown_limit:
                    return "drawdown_limit"
        return None

    def check_entry(self, req: EntryRequest,
                    state: PortfolioState) -> tuple[str, float, str]:
        """Returns (decision, allowed_qty, reason).

        decision: "approve" | "restrict" | "reject". allowed_qty <= req.qty
        always (the governor never increases risk)."""
        L = self.limits

        def reject(reason):
            self._rec(req.t, "reject", symbol=req.symbol, reason=reason,
                      qty=req.qty)
            return "reject", 0.0, reason

        if not req.data_complete:
            return reject("missing_data_fail_safe")
        if not req.has_protective_stop or req.stop_distance <= 0:
            return reject("no_protective_stop")
        paused = self._paused_reason(state)
        if paused:
            return reject(paused)
        if state.equity <= 0:
            return reject("non_positive_equity")
        if state.n_positions >= L.max_positions:
            return reject("max_positions")

        # tightest qty satisfying every size-based limit
        qty_cap = req.qty
        # risk per trade
        max_risk_qty = (L.max_risk_per_trade * state.equity) / req.stop_distance
        qty_cap = min(qty_cap, max_risk_qty)
        # gross exposure headroom
        gross_room = L.max_gross_exposure * state.equity - state.gross_exposure
        qty_cap = min(qty_cap, max(0.0, gross_room) / req.price)
        # directional exposure headroom
        dir_used = (state.long_exposure if req.side > 0
                    else state.short_exposure)
        dir_room = L.max_directional_exposure * state.equity - dir_used
        qty_cap = min(qty_cap, max(0.0, dir_room) / req.price)

        if qty_cap * req.price < L.min_notional:
            return reject("insufficient_capacity")
        if qty_cap >= req.qty:
            self._rec(req.t, "approve", symbol=req.symbol, qty=req.qty)
            return "approve", req.qty, "ok"
        self._rec(req.t, "restrict", symbol=req.symbol, qty_requested=req.qty,
                  qty_allowed=qty_cap)
        return "restrict", qty_cap, "restricted_to_fit_limits"

    # -------------------------------------------------- management checks
    RISK_REDUCING = {"hold", "reduce_25", "reduce_50", "close",
                     "tighten_stop", "move_stop_breakeven"}

    def check_action(self, t: int, action: str) -> bool:
        """Only risk-reducing management actions pass. The engine enforces
        the same invariants independently (defense in depth)."""
        if self.emergency_pause and action not in ("close", "reduce_25",
                                                   "reduce_50", "hold"):
            self._rec(t, "action_reject", action=action,
                      reason="emergency_pause")
            return False
        if action in self.RISK_REDUCING:
            self._rec(t, "action_approve", action=action)
            return True
        self._rec(t, "action_reject", action=action,
                  reason="not_risk_reducing")
        return False
