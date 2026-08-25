# RISK_POLICY — AKRA AI TRADING LAB

The external deterministic risk governor (SPEC_FINAL-1.2.md §14). It sits
OUTSIDE every model and every arm — including Arm A — and is enforced by
`lab/risk/governor.py`. No AI model may bypass it; it can restrict any
action but can never increase risk; a failed AI arm is never silently
replaced by Arm A. Every governor decision (approve / restrict / reject)
is recorded with its reason.

Status: numeric limits set 2026-08-25 (decision D15); FROZEN no later than
the constitutional lock. Changing any limit after freezing is a material
change (spec §16).

## Numeric limits (per arm account)

| Limit | Value | Note |
|---|---|---|
| Maximum risk per trade | 1.0% of current equity | risk = qty × stop distance. Ceiling above Arm A's own 0.75% sizing — the governor is a wall, not a sizer. |
| Maximum gross exposure | 150% of equity | equal to the protocol §2.6 strategy limit; governor enforces it independently. |
| Maximum leverage | 1.5× | identical to gross exposure in this account model (collateralized notional). |
| Maximum correlated exposure | 120% of equity per direction | all USDT-perps are treated as one correlated class; cap applies to the sum of long notionals and, separately, short notionals. |
| Maximum concurrent positions | 10 | equal to protocol §2.6. |
| Daily loss limit | 3% of UTC-day-start equity | breached → no new entries until the next UTC day; open-position protection continues. |
| Portfolio drawdown safety limit | 25% from peak equity | while exceeded → no new entries; protective management continues. |
| Valid protective order | always | every open position must carry a stop; a position observed without one is a critical integrity failure (recorded; emergency pause). |
| Emergency pause | manual flag | while set → no new entries. |
| Missing-data fail-safe | no new trade | any missing/invalid required input at decision time → the entry is refused, never guessed. |

## Semantics

1. The governor evaluates every proposed ENTRY with: proposed qty, entry
   reference price, stop distance, current equity, current gross/directional
   exposure, open-position count, UTC-day realized start equity, peak
   equity, and a data-completeness flag supplied by the caller.
2. It may (a) approve, (b) restrict — reduce qty to the largest size
   satisfying every limit (never increase), or (c) reject. Reductions that
   fall below the protocol minimum notional become rejections.
3. Management actions pass through `check_action`: only risk-reducing
   actions (reduce / close / tighten / breakeven) are permitted; anything
   else is rejected. The engine independently enforces the same invariants —
   defense in depth, not substitution.
4. Pauses (daily-loss, drawdown, emergency, integrity) block NEW entries
   only. Stops, targets, and risk-reducing management always continue.
5. Governor decisions are appended to the arm's event ledger as
   `governor_*` records; an entry blocked by the governor is an external
   restriction (relevant to Arm E rule 6: it is not the sizing model
   choosing zero).
