# CHECKPOINT 1 — REPLACEMENT REPORT (v4, 2026-08-28)

Supersedes CHECKPOINT1_REPORT_V3.md (preserved; root v3 preserved NOT
APPROVED). Covers the three narrow blockers of the v3 independent
review (D63), executed as D64 under the certified provenance gate. No
data/feature/B–C/PPO retraining occurred; accepted upstream work was
not redone. Paper-only; no holdout access, no key request.

## Blocker 1 — Arm E PORTFOLIO utility (pre-registered; CERTIFIED)
The per-trade cumulative-R "DD95" quantities are invalidated history.
Per PREREGISTRATION_ARM_E_PORTFOLIO.md, each mapping M1–M4 ran through
the ACTUAL validation portfolio simulator — one full seven-arm
orchestrator run per mapping over the official validation window
(fresh 10,000 account; real timing, overlapping positions, tiered
costs, equity-dependent sizing, capacity limits, external governor,
transactional rounds). From the 4h equity time series
(`arm_e_portfolio_selection.json`, sha 94570d6e…):

| mapping | MDD (decimal) | S_ann (time-series) | DD95 (bootstrap upper-95%) | U_E |
|---|---|---|---|---|
| M1 | 0.204 | 0.987 | 0.391 | **0.987** |
| M2 | 0.222 | 0.771 | 0.386 | 0.771 |
| M3 | 0.180 | 0.893 | 0.338 | 0.893 |
| M4 | 0.359 | 0.515 | 0.614 | 0.515 |

DD95_A (reference) = 0.614; **M4's DD95 equals A's exactly — the
built-in consistency check** (flat 1.00 sizing reproduces Arm A).
Paired circular moving-block bootstrap (L=168 4h periods, 1000
resamples, seed 20260901, one max drawdown per resample; identical
drawn blocks across all five series). All DD95_E ≤ DD95_A so every
penalty is 0 and the frozen U_E selects **M1** mechanically. Arm A
equality across the four runs was asserted. The M3 selections (both
per-trade variants) remain preserved invalidated history. No
profitability claim: the underlying ranking signal is chance-level;
M1's higher Sortino is a property of this validation window.

## Blocker 2 — Arm F exact conventional baseline (pre-registered; CERTIFIED)
HOLD was not the frozen Arm A manager; that comparison is invalidated
history (v1 report preserved). Per PREREGISTRATION_ARM_F_BASELINE.md,
the EXACT frozen conventional manager (trailing-channel exit then time
exit, ArmARunner order, identical entries/bars/costs/exit
ordering/terminal reward) was replayed in-episode. **Parity proven
bit-for-bit** against official ArmARunner outcomes for all four exit
classes — trailing exit, time exit, stop hit, target hit — on realized
pnl, fees, entry fill, and closure boundary
(tests/test_arm_f_baseline_parity.py, locked).
Corrected comparison (`arm_f_statistics_report_v2.json`, sha
97f86dc4…): exact baseline mean validation reward **+0.05399** (the
invalidated HOLD proxy was +0.04614 — the true bar is HIGHER).
**Wins/losses: 0 / 10.** Every seed's reward recomputed and matched
the preserved manifest; seed 4 preserved (no independent
artifact-integrity failure). No RL management edge — the corrected
comparison strengthens that conclusion.

## Blocker 3 — G_matched entry-bar semantics (CERTIFIED tests)
The run loop now processes arms first (G fills at the bar open and
receives that bar's protection sweep), mirrors every new G fill into
the matched engine, and only then lets the diagnostic engines process
the SAME bar — a fresh clone therefore experiences the identical
same-bar stop/target sweep, mark, and MFE/MAE updates under exact
engine semantics. Constitutional tests added (locked, reason-keyed in
manifest v4): same-bar STOP after entry and same-bar TARGET after
entry — both **proven to fail under the previous ordering** and to
pass now with identical close time/price/qty/realized economics —
plus RL tighten/reduce non-propagation to the clone, alongside the
existing exact-cloning, inertness, over-cap, and rollback coverage.

## Verification and closure
- **Manifest v4** (`ee518f08…`): explicit v1 → v2 → v3 → v4 lineage,
  all predecessors preserved NOT-APPROVED; 44 unchanged / 1 modified /
  1 added, reason-keyed; independently re-verified (per-file +
  self-hash). New constitutional properties: entry-bar cloning
  semantics; exact-conventional-baseline parity.
- **Suite + differential** from the clean worktree at 4bdecf0:
  **153/153** (verbatim output preserved, sha c3b2abed…).
- **Full INVALID shakedown v4** (CERTIFIED, provenance + lake
  addendum): 1,080/1,080 rounds valid, **ZERO defects**, corrected
  rules wired (B 0.50 / C top-1 / **E M1 portfolio-selected** / F SB3
  seed 4); matched-fill identity exact; zero unexplained feasible
  divergences; full RL observability; dashboard rebuilt and
  ledger-reconciled.
- **Targeted INVALID stress fixture** (CERTIFIED, zero defects,
  `data/stress_fixture_v4/`): in one synthetic run — same-bar stop AND
  target with G/matched bit-agreement; **14 concurrent G_matched
  positions** with explicit `diagnostic_over_cap` recording; **four
  REAL G_feasible capacity divergences** (governor max_positions /
  insufficient_capacity), each explained via the decision ledger;
  executed tighten / reduce / close RL actions. All ledgers exported
  and mechanically reconciled.

## What is NOT claimed
No profitability; no demonstrated learnability; no RL management edge
(0/10 vs the exact conventional baseline); E's M1 selection is frozen
procedure over a chance-level signal, not skill; all shakedowns and
the stress fixture are permanently INVALID for performance
conclusions; holdout sealed; paper-only.

## Stop
Work STOPS at replacement Checkpoint 1 (v4). Awaiting independent
adjudication. Prohibitions honored: no private-key request or access;
no holdout decryption or inspection; no Checkpoint-2 authorization; no
official holdout evaluation; no real-money trading; no deletion or
rewriting of prior evidence; no silent protocol, threshold, fixture,
or expected-outcome changes.
