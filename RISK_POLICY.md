# RISK_POLICY — AKRA AI TRADING LAB

The external deterministic risk governor (SPEC_FINAL-1.2.md §14). It sits
OUTSIDE every model and every arm — including Arm A — and is enforced by
`lab/risk/governor.py`. No AI model may bypass it; per request it can
only reduce or reject what was proposed (allowed qty ≤ requested qty,
management restricted to risk-reducing actions — a mechanical property
of `check_entry`/`check_action`, distinct from the retracted D46 pause
claim, see changelog); a failed AI arm is never silently
replaced by Arm A. Every governor decision (approve / restrict / reject)
is recorded with its reason.

Status: numeric limits set 2026-08-25 (decision D15), amended to v2 on
2026-08-26 (decision D46, drawdown reference — see changelog); FROZEN no
later than the constitutional lock. Changing any limit after freezing is a
material change (spec §16).

## Numeric limits (per arm account)

| Limit | Value | Note |
|---|---|---|
| Maximum risk per trade | 1.0% of current equity | risk = qty × stop distance. Ceiling above Arm A's own 0.75% sizing — the governor is a wall, not a sizer. |
| Maximum gross exposure | 150% of equity | equal to the protocol §2.6 strategy limit; governor enforces it independently. |
| Maximum leverage | 1.5× | identical to gross exposure in this account model (collateralized notional). |
| Maximum correlated exposure | 120% of equity per direction | all USDT-perps are treated as one correlated class; cap applies to the sum of long notionals and, separately, short notionals. |
| Maximum concurrent positions | 10 | equal to protocol §2.6. |
| Daily loss limit | 3% of UTC-day-start equity | breached → no new entries until the next UTC day; open-position protection continues. |
| Portfolio drawdown safety limit | 25% from the TRAILING 90-DAY peak equity (v2, D46) | while exceeded → no new entries; protective management continues; the pause horizon is bounded by the trailing window. |
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

## Changelog

- **v1 (2026-08-25, D15)**: drawdown measured from the all-time peak.
- **v2 (2026-08-26, D46)**: drawdown measured from the trailing 90-day
  peak. Reason (observed, not hypothetical): on the official Arm A run
  over raw-v1, equity peaked +69% on 2021-02-14, drew down 26.4% in the
  March-2021 crash, and the v1 pause then became an ABSORBING state —
  new entries blocked → equity flat → drawdown never recovers → the
  account stayed frozen for 9,220 of 9,848 pre-holdout rounds (final
  equity a permanent 0.4% below the release level). The policy text
  ("while exceeded → no new entries" — a PAUSE) never intended a
  permanent halt. v2 preserves the crash behavior exactly (a ≥25% fall
  within any 90-day window still blocks entries immediately) and bounds
  the halt horizon: after ~90 flat days the reference peak decays to
  current equity and trading resumes. RETRACTION (independent
  Checkpoint-1 adjudication, D52): the claim originally recorded here —
  that the v2 pause "cannot increase risk" — is WITHDRAWN. Resuming
  entries after ~90 flat days creates additional future exposure
  relative to a permanent halt, so that claim was too strong. The
  correct, adjudicated statement is: **v2 preserves the stated limits
  while preventing an unintended absorbing pause.**
  This is a PRE-LOCK amendment of a draft policy,
  recorded as a material decision for Checkpoint-1 review; the frozen
  EXPERIMENT_PROTOCOL.md is untouched.
