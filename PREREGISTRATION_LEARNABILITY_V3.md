# PRE-REGISTRATION — learnability v3 statistical procedure (D61 blocker D)

Committed BEFORE v3 executes or any v3 result is viewed. The v2
QUANTITATIVE procedure is not adjudicated and is preserved as history
(`learnability_report_v2.json`); its two implementation defects are
corrected here: (1) the CI bootstrap resampled fixed non-overlapping
blocks although the v2 pre-registration promised a circular
moving-block bootstrap; (2) the permutation's within-slot modulo
assignment could duplicate/discard labels when boundary-group sizes
differ. v1 remains RETRACTED. The v2 qualitative conclusion
(UNDERPOWERED — NO DEMONSTRATED LEARNABILITY) is unaffected and stands
as the interim conclusion pending v3 and adjudication.

Unchanged from v2 (still frozen): the observed models and metrics
(identical frozen draft hyperparameters, model seed 20260826 — observed
AUC/IC must reproduce exactly), the 28-day dependence window, the MUE
(AUC deviation 0.05, |IC| 0.05), the approximate normal-theory power
method, and the frozen INSUFFICIENT-LEARNABLE-VARIATION rule for
Checkpoint 2.

## Permutation null (exact-multiset circular rotation; fixed)
- TRAIN trades sorted by (t, symbol) — the frozen deterministic order.
  Unique boundaries b_1..b_U with group sizes m_1..m_U fixed on the
  FEATURE side (slots never change size or membership).
- One permutation = a CIRCULAR ROTATION of the entire label vector by
  the total trade count of j consecutive boundaries: labels
  (y_1..y_n) -> (y_{s+1}..y_n, y_1..y_s) with s = m_1 + … + m_j.
- j is drawn uniformly (seeded) from the eligible set
  { j : displacement(b_1 -> b_{j+1}) >= 28 days AND
        displacement <= span − 28 days },
  so every rotation displaces labels by at least the dependence window
  in both circular directions.
- Properties, mechanically guaranteed and TESTED: the permuted label
  vector is a bijective rearrangement — the EXACT multiset, the exact
  sample count, no duplication, no truncation; feature-side boundary
  group sizes unchanged; the label sequence's serial and clustered
  structure preserved up to one circular seam (labels that were
  adjacent remain adjacent). Honest note: because group sizes are
  unequal, a rotated label block may straddle two feature slots — this
  is inherent to any exact-bijection scheme and is disclosed, not
  hidden.
- Permutations: **200**, seed **20260831**; models refit per
  permutation with the frozen draft hyperparameters; two-sided
  p with the +1/(N+1) upper convention (unchanged).

## CI bootstrap (TRUE circular moving-block; fixed)
- Ordered unique VALIDATION boundaries b_1..b_U (U observed), circular
  ring in index space; block length L = ceil(U × 28 days / span_days).
- One resample: uniformly random circular start indices, each
  contributing L CONSECUTIVE boundaries (wrapping — every start
  position allowed, so blocks OVERLAP across draws: a moving-block,
  not a fixed tiling); concatenate until >= U boundaries, truncate to
  exactly U; rows = those boundaries' trades (row count varies per
  resample and is recorded).
- Statistics: AUC and rank IC of the SINGLE observed model's scores on
  the resampled rows; **1000** resamples, seed **20260832**; percentile
  95% CIs; bootstrap SE feeds the (unchanged) power approximation.
- ESS is reported as an **approximation** (design-effect heuristic),
  never as a proven exact effective sample size.

## Mechanical invariance tests (added to the suite before execution)
1. permuted-label multiset == original multiset (exact, sorted equality);
2. sample count unchanged;
3. feature-side per-boundary group sizes unchanged;
4. rotation displacement within the pre-registered bounds;
5. deterministic reproduction: same seed -> identical permutation
   sequence and identical bootstrap draws.

## Outputs and preservation
`learnability_report_v3.json` (procedure v3, seeds, all statistics,
structure diagnostics, power, the directed interim conclusion). v1
(retracted) and v2 (not adjudicated) files remain preserved unmodified.

## Execution standard
Official execution under lab/tools/provenance_run.py from a clean
detached worktree (ledger inputs only).
