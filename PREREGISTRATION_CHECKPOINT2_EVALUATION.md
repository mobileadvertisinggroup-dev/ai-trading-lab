# PRE-REGISTRATION — the one-time Checkpoint-2 holdout evaluation

Committed BEFORE any Checkpoint-2 authorization exists and before any
holdout row is readable. This is the FROZEN evaluation plan (SPEC §18,
§19, §22): it is executed exactly once, inside the sanctioned
`lab.data.unseal.evaluate_holdout` gate, only after the reviewer's
separate explicit authorization. Nothing here may change after the
holdout is opened; deviations before opening require a documented
amendment. **No holdout row has been accessed, decrypted, inspected,
summarized, or evaluated in preparing this plan.**

## Frozen artifacts under evaluation (Checkpoint-1-v4-approved; hashes
pinned in data/manifests/checkpoint1_root_hash_v4.json)
- Arm A: frozen §2 rules (baseline).
- Arm B: frozen classifier, TRAIN-only threshold **0.50**.
- Arm C: frozen regressor, TRAIN-only **top-1**.
- Arm D: frozen regime model + multiplier policy.
- Arm E: frozen regressor, mapping **M1** (portfolio-utility selected).
- Arm F: SB3 PPO **seed 4** through the canonical obs-v2 adapter.
- Arm G: frozen composite (B→C→min(E,D)×A→governor; F's policy manages)
  with BOTH G diagnostics (matched-entry shadow; feasible
  counterfactual).
No retraining, retuning, or artifact alteration — the negative
Checkpoint-1 conclusions stand regardless of holdout outcomes.

## Mechanics (the frozen evaluator, lab/tools/holdout_evaluator.py)
- Data: the decrypted holdout overlay (identical lake layout, rows >= Q
  = 1752134400000) is merged in-memory with the verified pre-holdout
  lake; full history feeds indicator warm-up. The overlay lives only on
  the gate's verified tmpfs and is wiped by the gate.
- Round validity for holdout boundaries is computed by the SAME frozen
  mechanical rule used pre-holdout (lab.data.partition.round_validity),
  from the combined data — no manual overrides.
- One full seven-arm orchestrator run (transactional rounds, tiered
  costs, equity-dependent sizing, capacity limits, external governor,
  full RL observability, both G diagnostics), fresh 10,000 accounts at
  the first holdout boundary, window = quarantine start → last eligible
  holdout boundary (partition holdout_end).
- Outputs (the ONLY thing that leaves the gate): per-arm decision/event/
  equity/governor/RL ledgers, diagnostic ledgers, and the statistics
  below. NO raw market rows are exported.

## Primary scientific question (SPEC §18) and frozen statistic
Does an AI arm improve net risk-adjusted return over Arm A after all
costs without violating the pre-registered bootstrap drawdown
constraint?
- **Frozen primary statistic: annualized Sortino of the 4h portfolio
  equity returns, after all costs** — computed exactly as in the
  approved Arm E portfolio utility (S = mean(r)/sqrt(mean(min(r,0)²)) ×
  sqrt(2191.5); downside 0 → 0 if mean<=0 else 1e6).
- Challengers: the six arms B, C, D, E, F, G vs baseline A.

## Frozen inference procedure
- Paired dependence-aware bootstrap on the 4h return series: circular
  moving-block, block length L = 168 four-hour periods (28 days),
  **1000** resamples, seed **20260902**, the SAME drawn index sequences
  applied to every arm and to A.
- Per challenger X: Δ* = S*(X) − S*(A) per resample; one-sided
  p_upper = (#{Δ* <= 0} + 1) / (N + 1).
- **Frozen multiple-comparison correction: Holm–Bonferroni across the
  six challengers at family α = 0.05.**
- **Frozen bootstrap drawdown constraint (SPEC §19): X passes iff
  DD95(X) <= DD95(A)**, where DD95 = the 95th percentile of the paired
  bootstrap MAXIMUM-drawdown distribution (decimal fraction of
  portfolio equity; one max drawdown per resample; identical method to
  the approved E selection). The observed single-path max drawdown is
  reported but is not the constraint statistic.
- **Frozen success criterion: challenger X "improves over Arm A" iff
  its Holm-adjusted p < 0.05 AND it passes the drawdown constraint.**
  Anything else is reported as an honest negative. One supporting
  metric improving is never sufficient (SPEC §18).
- Supporting metrics reported per arm (never sufficient alone): net
  return, observed max drawdown, Sharpe, Sortino, Calmar, profit
  factor, average trade, turnover, fees, slippage estimate, funding,
  exposure, time in cash, tail loss (worst 5% of 4h returns),
  stability across halves, outlier dependence (result with top-3 trades
  removed).
- The frozen INSUFFICIENT-LEARNABLE-VARIATION rule
  (PREREGISTRATION_LEARNABILITY_BLOCKS.md) is applied, unchanged, to
  the supervised arms' Checkpoint-2 evidence.

## Forward evidence floor (SPEC §22)
Holdout results — positive or negative — never authorize real-money
trading. The forward paper phase remains the only genuinely
future-unseen evidence; no real-money step exists in this project.

## Honest expectations (stated before opening)
Checkpoint-1 evidence showed no demonstrated learnability
(underpowered), Arm B an honest negative, Arm F 0/10 against the exact
conventional baseline. The prior expectation is therefore that NO
challenger will meet the success criterion; the holdout evaluation is
run to complete the pre-registered protocol, not because an edge is
expected. A positive result under these criteria would itself warrant
skeptical independent review.

## Single use, fail closed
Execution happens ONLY through `evaluate_holdout` (strict authorization
+ hash-chained ledger + atomic single claim + TTY-only key entry +
verified tmpfs + wipe-and-verify + CONSUMED/FAILED_CLOSED). Any failure
permanently blocks a second opening; recovery is not self-authorizing.
