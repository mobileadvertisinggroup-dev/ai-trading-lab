# PRE-REGISTRATION — Arms B/C/E finalization (blocker 6)

Committed BEFORE any of the grid evaluations below are computed or
viewed. Total selection budget: **18 configurations** (9 + 5 + 4), all
evaluated on validation ONLY, every result recorded in the model
manifest, nothing outside this list ever evaluated. Honest-disclosure
note: the DRAFT results (B at threshold 0.50, C at K=10, E mapping M1)
are already known and preserved; the grids, constraints, and tie rules
below are nevertheless fixed ex ante and do not depend on those values.
The frozen draft LightGBM models are NOT refit — only their decision
rules (threshold / K / bucket mapping) are being finalized, exactly as
SPEC §3 allows ("selected using training and validation only, then
frozen before holdout").

## Arm B — accept threshold (9 configurations)
- Grid: {0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70} applied
  to the frozen classifier's validation probabilities.
- Support constraint: a threshold is SELECTABLE only if it accepts
  >= 50 of the 750 validation candidates (protects against tail-noise
  selection — the pathology behind the draft's 1.07% accept rate).
- Selection: among selectable thresholds, the highest mean net_r of
  accepted validation candidates; ties -> LOWER threshold.
- If NO threshold is selectable: freeze the LOWEST grid threshold
  (most inclusive, closest to Arm A behavior) and record verdict
  "ARM B INSUFFICIENT SUPPORT — honest negative".

## Arm C — top-K per round (5 configurations)
- Grid: K in {1, 2, 3, 5, 10} (10 = MAX_CONCURRENT_POSITIONS, the
  draft). Per validation boundary, rank that boundary's candidates by
  the frozen regressor score, select the top K.
- Support constraint: total selected across validation >= 50.
- Selection: among selectable K, highest mean net_r of selected
  candidates; ties -> SMALLER K.

## Arm E — bucket mapping (4 configurations), FROZEN SPEC UTILITY
- Candidate mappings of the frozen regressor's prediction p (cuts from
  TRAIN-prediction quantiles q25/q50/q75/q90, frozen at fit time):
  - M1 (draft): quartiles -> 0.25 / 0.50 / 0.75 / 1.00.
  - M2 (sign-anchored): p < 0 -> 0.25; 0 <= p < q50 -> 0.50;
    q50 <= p < q75 -> 0.75; p >= q75 -> 1.00.
  - M3 (conservative-tail): p < q25 -> 0.25; q25 <= p < q75 -> 0.50;
    q75 <= p < q90 -> 0.75; p >= q90 -> 1.00.
  - M4 (flat control): every candidate -> 1.00 (Arm-A-parity baseline;
    selecting M4 = the honest statement that sizing adds nothing).
- Utility (SPEC §3, frozen): U_E = Sortino_net − 2 × max(0,
  (DD95_E − DD95_A) / max(DD95_A, 0.01)), computed mechanically as:
  validation trades in (t, symbol) order; sized return r_i = bucket_i ×
  net_r_i (R units); Arm A reference r_i^A = 1.0 × net_r_i;
  Sortino_net = mean(r) / sqrt(mean(min(r, 0)^2)) (downside dev 0 ->
  Sortino := 0 if mean <= 0 else 1e6); DD95 = 95th percentile of the
  drawdown series (running peak minus running cumsum) of the
  time-ordered cumulative sum.
- Selection: highest U_E; ties -> earliest mapping in the list order
  M1, M2, M3, M4.

## Anomaly explanations (directed; computed from already-recorded data)
The report accompanying the finalization must quantify, from the
recorded validation ledger and frozen model scores only:
1. Arm B draft anomaly (accept 1.07%, accepted mean −0.334): the
   validation base rate of positives (~0.30) centers the classifier's
   probabilities far below 0.50, so the draft threshold sits in the
   extreme upper tail of a chance-level score (learnability AUC ~0.52
   retracted-p) — acceptance there is a small-n tail artifact; report
   n accepted, the score distribution quantiles, and the standard error
   of an n-of-that-size mean under the validation net_r distribution.
2. Arm E draft anomaly (non-monotone bucket means): with chance-level
   ranking (IC ~0.02), bucket means are draws around the overall
   validation mean; report per-bucket n, SE, and whether observed
   deviations exceed 2×SE.
Both are preserved as honest negatives regardless of what the grids
select.

## Prohibitions
No refitting, no new features, no metric substitution, no evaluation
outside the 18 configurations, no reordering of tie rules after
results are seen. Any deviation requires a documented amendment BEFORE
it is executed.

## Amendment A1 (2026-08-27, provenance directive)
- Official execution runs under lab/tools/provenance_run.py from a
  clean, detached git worktree at a single recorded commit (automatic
  provenance manifest; outputs outside the checkout). The earlier
  same-day evaluation from the mutable working tree is preserved as a
  PROFILE cross-check only; the 18-configuration budget is NOT consumed
  twice — the official run re-executes the identical pre-registered
  grids deterministically (no new configurations are examined).
