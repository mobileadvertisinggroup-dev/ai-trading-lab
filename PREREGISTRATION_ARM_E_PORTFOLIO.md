# PRE-REGISTRATION — Arm E PORTFOLIO utility (D63 blocker 1)

Committed BEFORE any portfolio-utility value is computed or viewed.
Supersedes the per-trade implementation of PREREGISTRATION_ARM_E_
UTILITY_V2.md, whose M3 selection is INVALIDATED history (its
cumulative-R "DD95" figures, e.g. 95.586 / 45.709, are not the frozen
portfolio maximum-drawdown quantity — drawdown is a positive decimal
fraction of portfolio equity). The four mappings M1–M4 are UNCHANGED;
no model is refit.

## Portfolio simulator (the ACTUAL validation simulator)
- One full seven-arm Competition run per mapping (the production
  orchestrator: real timing, overlapping positions, tiered costs,
  equity-dependent sizing, per-position and portfolio capacity limits,
  the external risk governor, transactional rounds), differing ONLY in
  Arm E's frozen bucket mapping (M1 / M2 / M3 / M4 via the frozen
  regressor and the frozen train-prediction quantiles).
- Window: the OFFICIAL validation partition,
  validation_start_ms = 1716681600000 → validation_end_ms =
  1752120000000 (last pre-quarantine 4h boundary), official round
  validity, official universe eligibility, full indicator warm-up
  history below the window. Fresh account, starting cash 10,000 at the
  window start (pre-registered: the E utility compares mappings on the
  validation window from a common initial state).
- The mechanically relevant outputs per mapping: Arm E's 4h equity
  curve. Arm A's 4h equity curve from the same runs is the DD95_A
  reference (its account is identical across the four runs — verified
  mechanically; any difference is a defect that STOPS the procedure).

## Portfolio quantities (all from the 4h equity time series)
- 4h simple returns: r_k = E_k / E_{k−1} − 1 over consecutive recorded
  boundaries.
- Maximum drawdown (DECIMAL): MDD = max_k (1 − E_k / max_{j<=k} E_j),
  a positive decimal fraction of portfolio equity (0.20 = 20%).
- Annualized Sortino from the TIME-SERIES returns:
  S_ann = [mean(r) / sqrt(mean(min(r,0)^2))] × sqrt(P_YEAR), with
  P_YEAR = 365.25 × 6 = 2191.5 four-hour periods per year (the
  synchronized decision structure). Downside deviation 0 → S := 0 if
  mean(r) <= 0 else 1e6 (unchanged edge rule). No per-trade sqrt(n)
  scaling anywhere.
- DD95 (dependence-aware, paired): circular moving-block bootstrap on
  the 4h RETURN series — block length L = 168 four-hour periods (28
  days); uniformly random circular starts (overlapping blocks);
  concatenated and truncated to the observed series length; the SAME
  drawn index sequences applied to EVERY series (M1, M2, M3, M4, and
  A). Per resample, rebuild the equity path multiplicatively
  (prod(1+r)) and take ONE maximum drawdown (decimal). **1000**
  resamples, seed **20260901**. DD95_X = the 95th percentile (upper
  95% bound) of the resample maximum drawdowns for series X.
- Frozen utility, applied once per mapping:
  U_E = S_ann − 2 × max(0, (DD95_E − DD95_A) / max(DD95_A, 0.01)).
- Selection: highest U_E; ties → earliest of M1, M2, M3, M4. Every
  mapping's full record (equity curve hash, MDD, S_ann, DD95, penalty,
  U_E) is preserved.

## Prohibitions / stop conditions
No refits; no new mappings; no window changes after results are seen;
Arm A reference equality across runs is asserted mechanically, and any
violation STOPS the run for adjudication. Official execution under
lab/tools/provenance_run.py from a clean detached worktree with the
lake-input addendum.
