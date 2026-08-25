# SIMULATOR_SEMANTICS — AKRA AI TRADING LAB

The frozen execution-semantics specification (SPEC_FINAL-1.2.md §11, §13).
This document is the *input* both independent implementations build from:

- `lab/sim/` — the main simulator (production).
- `lab/refledger/` — the Independent Reference Ledger (verification only;
  separate package, zero shared accounting/execution/portfolio/fee/stop/
  sizing/P&L code, no imports in either direction — FINAL-1.2 §13).

EXPERIMENT_PROTOCOL.md defines *what* the strategy does; this document
defines *how* execution and accounting work. Every rule here is
deterministic. Where a rule involves judgment, the conservative choice is
specified and the event is recorded.

## 1. Account model

- Linear USDT-margined perpetuals. One account per arm.
- **Cash** changes only through: entry/exit fees, funding transfers, and
  realized P&L at (partial or full) closes. Opening a position transfers no
  principal (collateralized notional).
- **Unrealized P&L** of a position: `side × qty × (mark − entry_fill)`,
  side ∈ {+1 long, −1 short}, mark = latest known 15m close (or the current
  processing price where a rule says so).
- **Equity** = cash + Σ unrealized P&L of open positions.
- **Gross exposure** = Σ qty × mark over open positions.
- All accounting in float64; no rounding until display. Quantities and
  prices are used exactly as computed.

## 2. Orders and fills

Order types: market entry, stop-market (protective stop), take-profit
limit (target), market exit (trailing/time/management/forced closes).

Cost parameters per order (from protocol §5): taker fee `F = 0.05%`,
half-spread `hs`, slippage `slip` (tier-resolved by the caller at decision
time and fixed for the life of the order).

Fill prices (`side` = +1 buy / −1 sell of the *execution*, not the position):

| Fill | Price |
|---|---|
| Market entry (long open / short close-side buy) | `ref × (1 + hs + slip)` |
| Market entry (short open / long close-side sell) | `ref × (1 − hs − slip)` |
| Market exit | same formulas with `ref` = the mandated reference price |
| Forced close (delisting) / stop-market | same, with `slip` doubled |
| Take-profit limit | exactly the target price (limit guarantees price) |

`ref` for market orders = the open of the mandated 15m bar. Taker fee
`F × fill_notional` is charged on **every** fill, including take-profit
limits (conservative). Fees are cash debits at fill time.

## 3. Per-bar processing order

Bars are processed symbol-by-symbol inside one global 15m time step. Within
one 15m bar timestamp, the engine processes, in this exact order:

1. **Funding** (if the bar's open time is a funding timestamp): each open
   position pays/receives `funding_rate × qty × mark`, where mark = the
   close of the 15m bar closing at the funding timestamp (i.e., the
   previous bar's close; if that bar is missing, the current bar's open).
   Sign: long pays when rate > 0, short receives; reversed for rate < 0.
   Missing funding datum → 0 applied, event recorded.
2. **Pending market exits** (queued by trailing/time/management decisions
   from strictly earlier timestamps): filled at this bar's open with market
   costs.
3. **Pending entries** (submitted at this bar's open time by a decision
   round): capacity-checked in submission order (protocol §2.6 ordering),
   then filled at this bar's open. Checks per candidate, in order:
   min-notional, position-count cap, gross-exposure cap (using equity at
   check time and fill-price notional). Failing any check → rejection event
   (reason recorded), no state change.
4. **Protective checks intrabar** for every open position, in position-id
   (creation) order:
   - Stop hit iff `low ≤ stop` (long) / `high ≥ stop` (short).
   - Target hit iff `high ≥ target` (long) / `low ≤ target` (short).
   - Both hit in the same bar → **stop executes, target does not**
     (conservative intrabar-ambiguity rule); an `ambiguity` event is
     recorded with both levels.
   - Stop fill: stop-market with doubled slippage. `ref` = the stop price,
     except **gap-through**: when the bar opens beyond the stop (long:
     open ≤ stop; short: open ≥ stop), `ref` = the bar open — the fill is
     never better than the market's first trade (honest, conservative).
   - Target fill: exactly at the target price, even when the bar opens
     beyond it (conservative: never better than the registered limit).
   - A position opened in step 3 of this same bar is eligible for step 4 in
     this same bar (protection is live immediately).
5. **Insolvency check**: equity (at bar close marks) ≤ 0 — including a
   flat account whose cash went negative through a gap-through loss — →
   every open position is force-closed at this bar's close with market
   costs and doubled slippage, the account is marked ruined, and no future
   entry is ever accepted (ruin protection). Event recorded once.

Steps repeat for each bar in strict chronological order. Determinism:
identical inputs must produce byte-identical event streams (a differential
requirement).

## 4. Management actions (Arm F / RL, and G pipeline)

Applied at 4h decision boundaries only, executing per §3.2 at the next 15m
open. Permitted: hold; reduce 25% / 50% (of *current* qty); close; tighten
stop (strictly toward the mark); move stop to breakeven (entry fill) when
that tightens. Rejected as invalid (event recorded, no state change):
increasing size, widening a stop, removing protection, any action on a
closed position, reductions > open quantity, any action violating the risk
governor. Partial exits realize proportional P&L and fees; remaining
quantity keeps entry price, stop, and target.

## 5. Missing data

- Entry bar missing → candidate cancelled (protocol §2.3), event recorded.
- Bar missing for an open position → no protective evaluation that
  timestamp; next existing bar is evaluated as §3.4 (deferral recorded).
- Permanent delisting with an open position → forced close at last traded
  15m close, doubled slippage (protocol §2.7).
- The engine never invents prices.

## 6. Partition-boundary evaluation rule (BUILD_STATE D9)

An evaluation window (train/validation/…) ends at its last boundary; any
position still open is force-closed for evaluation purposes at the last
pre-boundary 15m close with market costs (event `eval_boundary_close`).
This is an evaluation artifact, recorded as such, and never feeds labels
(labels crossing a boundary are purged per spec §10).

## 7. Ledgers and events (immutability)

The engine emits an append-only event stream; every fill, rejection,
funding transfer, ambiguity, deferral, forced close, invalid action, and
insolvency is an event with its timestamp, position id, and full numeric
detail. Trade lifecycles (entry → partials → close, with fees, funding,
MAE/MFE) are derived from events and immutable once closed. Ledger records
are never rewritten; corrections append.

## 8. Shared semantic subset for the differential gate (FINAL-1.2 §13)

The reference ledger implements §§1–3 and 5 (long/short, multiple
positions, capital competition, sizing enforcement, protective stops,
deterministic exits, fees, cash/equity/exposure accounting,
capacity rejection, insolvency) and must reconcile **exactly** — same
fills, same order, same amounts — with the main simulator on the golden
fixtures. §4 management actions and G-shadow accounting are main-simulator
scope, outside the reference subset (per FINAL-1.2 §13 the subset list).
