# PRE-REGISTRATION — Arms B/C TRAIN-only selection (D61 blocker B)

Committed BEFORE any TRAIN-grid value is computed or viewed. Corrects
the invalidated validation-based selection (preserved as INVALID
history in `data/models/bce_finalization.json`); SPEC §10 requires
thresholds fitted using TRAINING data only. The frozen draft boosters
are NOT refit (their training inputs and preprocessing are unchanged).

## What is already known (honest disclosure)
The validation grid results from the invalidated procedure are known
and preserved. The TRAIN-side grid values below have NEVER been
computed. The grids are IDENTICAL to the invalidated pre-registration —
no expansion, no tuning, no reordering of tie rules.

## Arm B — accept threshold (TRAIN only)
- Grid (unchanged): {0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65,
  0.70}, applied to the frozen classifier's probabilities on the purged
  TRAIN split (n = 2,089). These are in-sample probabilities of the
  model on its own training data — recorded as an honest caveat; SPEC
  §10 mandates the split, not an unbiasedness claim.
- Support constraint, scaled to the split by the same fraction as the
  invalidated rule (50/750): SELECTABLE iff the threshold accepts
  >= ceil(50 × 2089 / 750) = **140** TRAIN candidates.
- Selection: among selectable thresholds, highest mean TRAIN net_r of
  accepted candidates; ties -> LOWER threshold. If none selectable:
  freeze the LOWEST grid threshold and record "ARM B INSUFFICIENT
  SUPPORT — honest negative".
- The selected threshold is then applied EXACTLY ONCE to validation and
  its validation results are REPORTED — no further selection of any
  kind on validation.

## Arm C — top-K per round (TRAIN only)
- Grid (unchanged): K in {1, 2, 3, 5, 10}. Per TRAIN boundary, rank
  that boundary's candidates by the frozen regressor's (in-sample)
  score; select the top K (score desc, symbol asc tie order).
- Support: SELECTABLE iff total TRAIN selected >= 140.
- Selection: highest mean TRAIN net_r of selected; ties -> SMALLER K.
- The selected K is applied EXACTLY ONCE to validation; validation
  results reported without further selection.

## Outputs and preservation
- New record `bc_train_selection.json`: full TRAIN grids, the two
  selections, and the single validation application per arm.
- The invalidated validation-selected results (B 0.30, C top-3) remain
  preserved unmodified as INVALID selection history and are never used
  downstream again.

## Execution standard
Official execution under lab/tools/provenance_run.py from a clean
detached worktree, with the blocker-F lake addendum where the lake is
consumed (this job consumes ledgers only).
