# LIMITATIONS — AKRA AI TRADING LAB (through Checkpoint 1)

Honest, binding statement of every known limitation. Nothing here is
softened; every item traces to a recorded decision or artifact.

## Data and coverage

1. **Survivorship realism**: the archive lists delisted symbols and the
   ingestion is survivorship-free to the extent the source provides
   history; coverage was audited against the archive itself (coverage
   audit PASS, zero losses, D43). Symbols whose entire history predates
   the archive's coverage are unobservable and unquantifiable from this
   source.
2. **108 symbol-months contain intra-month 15m gaps** (completeness
   < 0.99 in the coverage audit). The frozen rules handle them
   mechanically: rounds fail validity, symbols fail the ≥99%
   completeness eligibility criterion, candidates with missing signal
   inputs are skipped. Missing OHLCV is NEVER imputed. Measured effects
   (official run): 2,255 of 12,103 pre-holdout rounds invalid (all from
   the <30-eligible rule; ZERO from BTC 4h incompleteness), 12,562
   symbol-boundary exclusions attributable solely to the completeness
   rule, 283 missing-input candidate skips, 1 cancelled_missing_bar.
3. **BTC context is sufficient**: 12,104 of 12,104 pre-holdout BTC 4h
   bars complete; no round was invalidated by BTC data.
4. **Holdout-side verification before Checkpoint 2 is metadata-only**:
   sealed file names/counts, artifact hash, sealing records. Holdout
   values and outcomes have never been read (audit log, hash chain).
5. The historical holdout is *unseen by the models*, not *unknown to the
   world* (spec §8 honesty): market history is public. The forward paper
   phase is the only genuinely future-unseen evidence.

## Statistical

6. **Learnability is indistinguishable from chance** at the current
   sample size and draft hyperparameters: Arm B validation AUC 0.524
   (permutation p = 0.42), Arm C rank IC 0.029 (p = 0.67), 200
   deterministic permutation nulls. NO tuning was performed to chase
   significance. Any later performance claim must overcome this
   documented null.
7. **Labeled sample is small**: 2,840 labeled candidates (2,089 train /
   750 validation / 1 purged). Governor pauses and the 10-position book
   cap the label rate by design; 23,183 candidates are unlabeled with
   recorded exclusion reasons (none silently dropped).
8. Arm B at the draft 0.5 threshold is **anti-predictive on validation**
   (accept rate 1.1%, accepted mean net R −0.334 vs rejected +0.070);
   Arm E's draft bucket mapping is non-monotonic on validation. Both are
   draft artifacts reported as-is.
9. Arm A itself **loses money** over the readable interval (10,000 →
   4,090; win rate 29.8%; mean net R −0.008): the transparent baseline is
   a baseline, not an edge, exactly as the spec frames it.

## Design and process

10. **RISK_POLICY v2 (D46)** replaced the all-time-peak drawdown
    reference with a trailing 90-day peak after the official run proved
    the v1 rule an absorbing state. This is a pre-lock amendment of a
    draft policy, version-bumped and flagged for review; the frozen
    EXPERIMENT_PROTOCOL.md is untouched. Labels depend on this choice.
11. **Official starting capital 10,000 USDT (D45)** is an execution
    parameter, not a spec number; sizing is equity-fractional but the
    governor's 50-USDT min-notional makes small-equity states behave
    differently than large ones.
12. **SD-RLOBS (open integration defect)**: the orchestrator supplies a
    2-field management observation to an Arm F policy trained on the
    10-dim environment observation (remaining dims zero-filled). Arm F/G
    management in the shakedown therefore under-uses the trained policy.
    Fix requires an orchestrator interface change + retraining assessment
    under the material-change rule — scheduled for post-Checkpoint-1.
13. **Arm F algorithm** is a deterministic CEM over a 66-parameter linear
    softmax policy (no deep-RL library is pinned in this project). It is
    reproducible and honest but deliberately low-capacity.
14. **Shakedown scope**: 180 days, all 1,080 rounds valid, one prior run
    (run 1) aborted by SD-FEATNAMES — both runs permanently INVALID for
    performance conclusions and preserved.
15. **Indicator warm-up**: Wilder ATR is recursively history-dependent;
    shakedown series use full history so values match official
    conventions, but any future re-run over truncated history would not
    bit-match.
16. **Release-platform immutability is UNVERIFIED** (API status unknown
    at evidence capture); integrity relies on tamper-evident git-pinned
    hashes, as documented (D35/D18).
