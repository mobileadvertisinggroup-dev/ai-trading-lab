# PRE-REGISTRATION — dependence-aware learnability rerun (blocker 5)

Committed BEFORE the block-permutation rerun executes or any of its
results are viewed. Everything below is fixed now; deviations require a
documented amendment.

## Retraction (directed)
The label-permutation p-values in `learnability_report.json` (v1: Arm B
AUC perm p = 0.42, Arm C IC perm p = 0.67) are **RETRACTED as
dependence-blind**: i.i.d. label shuffling ignores the overlap and
clustering structure of trade labels (many candidates share a decision
boundary; info intervals overlap across boundaries), so those p-values
overstate the effective sample size. The v1 report file is preserved
unmodified as history; the replacement is `learnability_report_v2.json`.

## Dependence horizon and block definition (fixed before the rerun)
- Maximum label dependence horizon: MAX_HOLD_BARS_4H = 42 4h bars
  (7 days) holding + 7-day embargo.
- **Block = one contiguous 28-calendar-day window of decision
  boundaries** (4x the 7-day horizon), windows anchored at the first
  train (resp. validation) boundary and tiled without overlap. A label
  belongs to the block containing its decision boundary t. The final
  partial window is its own block.

## Null scheme: block permutation (labels move as boundary groups)
- Unique boundaries of the TRAIN split are ordered b_1..b_U; labels are
  grouped by boundary; boundary groups are grouped into the 28-day
  blocks above.
- One permutation = a uniformly random shuffle of BLOCK ORDER
  (seeded), with boundary groups riding inside their blocks in original
  order. The shuffled sequence of label groups is laid back onto the
  original ordered boundary slots: slot u receives the label group at
  position u of the permuted sequence.
- Within a slot, the trade of within-boundary rank r (deterministic
  symbol order) receives the label of element `r mod |incoming group|`
  of the incoming group. This preserves within-boundary clustering and
  intra-block serial dependence while breaking feature-label alignment
  at block scale.
- Permutations: **200**, seed **20260827**, deterministic. Models refit
  per permutation with the SAME frozen draft hyperparameters as v1.
- p-value: two-sided as in v1 — fraction of permutations whose
  |stat − center| >= |observed − center| (center: 0.5 for AUC, 0 for
  IC); reported with the +1/(N+1) worst-case convention as
  `p_upper = (count + 1) / (N + 1)`.

## Confidence intervals (fixed)
- 95% CIs for validation AUC and rank IC by **circular moving-block
  bootstrap over VALIDATION boundaries** (same 28-day block definition,
  blocks resampled with replacement to the observed block count),
  scores from the single observed model (no refitting), **1000**
  resamples, seed **20260828**; percentile CIs.

## Reported sample-structure diagnostics (all mechanical)
Nominal n per split; unique boundaries per split; labels-per-boundary
mean/median/max; fraction of label PAIRS with overlapping
[info_interval_lo, info_interval_hi]; mean number of concurrently open
info intervals; intra-boundary ICC of the binary target (ANOVA
estimator); design effect DE = 1 + (m_bar − 1)·ICC at (a) boundary level
and (b) 28-day-block level; **ESS = n / DE, with the BLOCK-level (more
conservative) figure THE reported ESS**.

## Minimum useful effect + power (fixed)
- MUE (pre-registered): validation AUC deviation **0.05** (AUC 0.55) and
  |rank IC| **0.05** — below these, a supervised edge is not useful to
  the competition even if real.
- Approximate power at the MUE: with c = the null distribution's 95th
  percentile of |stat − center| and s = the block-bootstrap standard
  error of the observed statistic, power ≈ P(N(MUE, s²) > c). Labeled
  APPROXIMATE (normal-theory) in the report.

## Frozen INSUFFICIENT-LEARNABLE-VARIATION rule (applies at Checkpoint 2)
Declare **INSUFFICIENT LEARNABLE VARIATION** for the supervised arms iff
ALL of: (a) block-permutation p_upper >= 0.05 for BOTH validation AUC
and rank IC; (b) the 95% block-bootstrap CI for AUC contains 0.5 AND the
CI for IC contains 0; (c) approximate power at the MUE >= 0.60 for both
statistics. If (a) and (b) hold but (c) fails, the verdict is instead
**UNDERPOWERED — NO EVIDENCE EITHER WAY**. This rule is frozen now and
cannot change after viewing Checkpoint-2 data.

## Interim conclusion (directed, stands until independent adjudication)
"NO DEMONSTRATED LEARNABILITY; statistical significance not
adjudicated." The rerun reports statistics; it does not self-adjudicate.

## Amendment A1 (2026-08-27, provenance directive)
- Official execution runs under lab/tools/provenance_run.py from a
  clean, detached git worktree at a single recorded commit (automatic
  provenance manifest; outputs outside the checkout). A run launched
  earlier from the mutable working tree is preserved as a PROFILE
  cross-check only. No statistical procedure changes.
