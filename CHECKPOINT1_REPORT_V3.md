# CHECKPOINT 1 — REPLACEMENT REPORT (v3, 2026-08-28)

Supersedes CHECKPOINT1_REPORT_V2.md (preserved as NOT-APPROVED
history, root v2 preserved). Covers the narrow corrections directed by
the independent adjudication of 2026-08-28 (D61, blockers A–F), all
executed under the certified provenance gate (clean detached worktrees,
automatic manifests, lake-input addendum). Paper-only; no holdout
access, no private-key request, no Checkpoint-2 step.

## Blocker A — G-shadow versioned into two diagnostics (D62)
- Adjudicated material-change amendment `SPEC_AMENDMENT_A1_GSHADOW.md`
  (spec file byte-unmodified; amendment is a governed locked document).
- **G actual** now gates entries on its own state only — the previous
  shadow-open suppressor is removed; nothing diagnostic can alter its
  decisions, capacity, or execution.
- **G matched-entry management shadow**: every actual G fill cloned at
  identical timestamp/symbol/side/qty/price/protection (diagnostic-only
  `Engine.clone_open`), conventional management after; over-cap
  excursions recorded explicitly; not a feasible portfolio, not an arm.
- **G feasible conventional counterfactual**: same pre-RL pipeline
  under its own limits; per-candidate decision ledger; divergence fully
  explained, no identity claim after state divergence.
- Constitutional tests added (locked, reason-keyed in manifest v3):
  exact matched-fill identity; fully explained feasible divergence;
  diagnostic inertness (G actual byte-identical with diagnostics
  on/off); explicit over-cap recording. Transactional byte-compare
  covers both diagnostics. SD-GSHADOW and the failed strict result stay
  preserved permanently (data/shakedown_v2/).

## Blocker B — Arms B and C selected from TRAIN only (D62)
- Pre-registered before computation (PREREGISTRATION_BC_TRAIN_
  SELECTION.md); identical grids; support scaled 50/750 → ≥140.
- CERTIFIED result (bc_train_selection.json, sha 0c51af3a…):
  **B threshold 0.50** (train-only; 191 train accepts; in-sample caveat
  recorded). Applied ONCE to validation: 8 accepts (1.07%), accepted
  mean net_r −0.334 — the known honest negative now arrived at by the
  spec-compliant procedure and preserved as such.
  **C top-K = 1** (train-only). Applied ONCE to validation: 443
  selected, mean net_r +0.033.
- The invalidated validation-selected values (B 0.30, C top-3) are
  preserved as INVALID selection history and never consumed.

## Blocker C — Arm E utility corrected to the frozen SPEC formula (D62)
- Prior M3 selection INVALIDATED (single observed path, unannualized);
  preserved as history.
- Pre-registered corrected implementation (PREREGISTRATION_ARM_E_
  UTILITY_V2.md): annualized Sortino after costs (S_per_trade ×
  sqrt(trades/year), openly approximate under overlap; T_years 0.946,
  λ 792.5); DD95 = upper 95% bound of the bootstrap MAXIMUM-drawdown
  distribution (paired circular moving-block draws over validation
  boundaries, 1000 resamples, seed 20260830, one max drawdown per
  resample); exact frozen U_E; the original four mappings only.
- CERTIFIED result: **M3 selected again** — U_E 2.861 (annualized
  Sortino 2.861; DD95_E 45.71 vs DD95_A 95.59, penalty 0). All four
  mappings' full results preserved (M1 2.798, M2 2.114, M4 2.390).

## Blocker D — learnability v3 (D62)
- Pre-registered before execution (PREREGISTRATION_LEARNABILITY_V3.md)
  with mechanical invariance tests committed to the locked suite first.
- Corrections implemented exactly: EXACT-multiset circular-rotation
  permutation (bijection; no modulo duplication/truncation;
  displacement ≥ 28 days both ways; 200 rotations, seed 20260831) and
  a TRUE circular moving-block CI bootstrap (uniform overlapping
  starts, exact boundary count, 1000 resamples, seed 20260832).
- CERTIFIED result (learnability_report_v3.json, sha 62abec01…):
  observed AUC 0.5240 / IC 0.0288 reproduce exactly; p_upper 0.478
  (AUC) and 0.667 (IC); CI95 [0.460, 0.584] and [−0.057, 0.112]; power
  at the MUE 0.283 / 0.048; ESS reported as an APPROXIMATION.
  Qualitative conclusion unchanged and stated verbatim:
  **"NO DEMONSTRATED LEARNABILITY; statistical significance not
  adjudicated"** — and the evidence remains in the UNDERPOWERED branch
  of the frozen IL rule. v1 retracted and v2 not-adjudicated histories
  preserved.

## Blocker E — Arm F required reporting, no retraining (D62)
CERTIFIED report (arm_f_statistics_report.json, sha 6902d7cf…), all
statistics from the ten PRESERVED artifacts (per-seed deterministic
recomputation matches the preserved manifest exactly):
- mean validation reward **−0.00584**; median **−0.00628**; IQR
  [−0.00955, −0.00197] (0.00758); variance 3.81e-05;
- best seed 4 (+0.00449), worst seed 3 (−0.01601);
- Arm A conventional-management baseline (hold on identical episodes,
  identical terminal reward): **+0.04614** — **0/10 seeds beat it**;
- convergence: **7/10 seeds non-converged; the selected seed 4 is
  itself non-converged**; the frozen selection rule re-applied still
  selects seed 4 (preserved, no post-hoc change);
- complete per-seed action distributions recorded; in the v2
  replacement shakedown executed actions collapsed to HOLD/CLOSE only;
- explicit statement: **no RL management edge has been demonstrated.**

## Blocker F — provenance lake addendum (D62)
Every official lake-consuming job now verifies the authoritative
content-addressed lake manifest BEFORE execution (exact on-disk census
against the 13,241 manifest paths + seeded 24-file full-hash sample —
no redundant 1.2 GB re-hash), records the manifest and partition-meta
hashes, binds the quarantine boundary (1752134400000), and records the
zero-readable-holdout statement. A failed verification refuses the run.
Exercised by the Arm F report and v3 shakedown provenance manifests.
This addendum grants no holdout access.

## v3 shakedown (permanently INVALID) — CERTIFIED, ZERO defects
From the clean worktree at a474c65 with the corrected frozen rules
(B 0.50 train-only / C top-1 / E M3 corrected / F SB3 seed 4 canonical
obs-v2): **1,080/1,080 rounds valid; all seven arms decided every
round; zero defects.** Both new constitutional diagnostics PASSED
mechanically: exact matched-fill identity (G_matched clones = G fills;
zero over-cap events at these entry rates), and zero unexplained
feasible divergences (8 G fills / 8 feasible fills, every skip staged).
Full RL observability recorded; dashboard rebuilt and
ledger-reconciled (docs/dashboard_shakedown_v3.html). Note: the
corrected B/C rules are far more restrictive (G: 8 fills vs 328 under
the invalidated rules) — a mechanical consequence of honest train-only
selection, not a performance claim.

## Constitutional lineage and suite
- Integrity manifest **v3** hash **c5cbdf77…** (v1 c423f782… and v2
  2268007d… preserved unmodified as NOT-APPROVED lineage): 40
  unchanged / 3 modified / 2 added, every change reason-keyed to D61;
  generation refuses undocumented changes; independently re-verified.
- Full suite + differential/reference-ledger checks from the clean
  worktree at a474c65: **149/149** (verbatim output preserved, sha
  0a328a44…).
- Root v2 (6958237194…) remains PRESERVED, NOT APPROVED. The v3
  external root hash is in
  `data/manifests/checkpoint1_root_hash_v3.json` with full lineage.

## What is NOT claimed
No profitability; no demonstrated learnability; no RL management edge
(0/10 seeds beat conventional management); B's spec-compliant selection
produces a preserved honest negative; all shakedowns permanently
INVALID for performance conclusions; holdout sealed; paper-only.

## Stop
Work STOPS at replacement Checkpoint 1 (v3). Awaiting independent
adjudication. Prohibitions honored: no private-key request or access;
no holdout decryption or inspection; no Checkpoint-2 authorization; no
official holdout evaluation; no real-money trading; no deletion or
rewriting of prior evidence; no silent protocol, threshold, fixture,
or expected-outcome changes.
