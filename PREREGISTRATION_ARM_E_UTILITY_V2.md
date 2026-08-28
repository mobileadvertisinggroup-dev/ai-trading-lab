# PRE-REGISTRATION — Arm E utility, corrected implementation (D61 blocker C)

Committed BEFORE any corrected-utility value is computed or viewed. The
prior M3 selection is INVALIDATED (preserved as history): the previous
implementation used an unannualized per-trade ratio and the 95th
percentile of points along ONE observed drawdown path, which does not
implement the frozen SPEC utility. This document fixes the corrected,
faithful implementation. The four candidate mappings are UNCHANGED
(M1 draft quartiles, M2 sign-anchored, M3 conservative-tail, M4 flat
control) — no new mappings, no refitting.

## Frozen formula (SPEC §3, unchanged)
U_E = Sortino_net(annualized, after costs)
      − 2 × max(0, (DD95_E − DD95_A) / max(DD95_A, 0.01))

## Return unit (fixed)
Validation trades in (t, symbol) order; sized return r_i = bucket_i ×
net_r_i in R units. net_r is the frozen label: net of fees, slippage,
spread, and funding — "after costs" is inherited from the label.
Arm A reference series: r_i^A = 1.0 × net_r_i (identical order).

## Annualization (fixed, openly declared)
- Elapsed validation time: T_years = (t_last − t_first + BAR_4H_MS) /
  (365.25 × 24 × 3600 × 1000), from the first to the last validation
  decision boundary carrying a labeled trade.
- Trade intensity: lambda = n / T_years (n = 750 validation trades,
  synchronized 4h decision structure).
- Per-trade Sortino: S = mean(r) / sqrt(mean(min(r, 0)^2)); downside
  deviation 0 -> S := 0 if mean <= 0 else 1e6 (unchanged edge rule).
- **Annualized Sortino = S × sqrt(lambda).** This is the standard
  sqrt-time scaling; it assumes independence across trades and is
  therefore an APPROXIMATION under overlap — declared here openly, not
  silently. If the adjudicator rejects sqrt-scaling, the numbers are
  reproducible under any replacement scaling from the preserved r
  series.

## DD95 (dependence-aware bootstrap; fixed)
- Bootstrap unit: the ordered unique validation decision boundaries
  b_1..b_U that carry >= 1 labeled trade, treated as a CIRCULAR ring in
  index space.
- Block length: L = ceil(U × 28 days / span_days), where span_days =
  (b_U − b_1)/86_400_000 — i.e. blocks of consecutive boundaries whose
  expected calendar span is the 28-day dependence window already fixed
  for this project.
- One resample: draw uniformly random circular start indices; each
  start contributes L consecutive boundaries (wrapping); concatenate
  drawn blocks until >= U boundaries and truncate to EXACTLY U; the
  resampled return path is the concatenation, in drawn order, of the
  trades of those boundaries (within-boundary trade order preserved).
- **One maximum drawdown per resample**: max over the path of
  (running peak of cumsum − cumsum), starting peak at 0.
- Resamples: **1000**, seed **20260830**. PAIRED resampling: the SAME
  drawn boundary sequences are applied to every mapping's r series AND
  to the Arm A reference series (variance reduction; pre-registered).
- **DD95_X = the 95th percentile (upper 95% confidence bound) of the
  1000 bootstrap maximum drawdowns** for series X.

## Selection (unchanged rules)
Highest U_E among the four mappings; ties -> earliest of M1, M2, M3,
M4. Every mapping's full result (annualized Sortino, DD95_E, penalty,
U_E, bucket counts) is preserved. The invalidated single-path M3
selection remains preserved as history.

## Stop condition (directed)
If, during implementation, the annualization or the overlapping-trade
structure cannot be represented faithfully by the definitions above,
execution STOPS and the ambiguity is submitted for adjudication —
no silent reinterpretation.

## Execution standard
Official execution under lab/tools/provenance_run.py from a clean
detached worktree (ledger inputs; no lake access needed).
