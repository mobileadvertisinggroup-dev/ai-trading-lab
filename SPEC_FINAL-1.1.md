AKRA AI TRADING LAB — DEFINITIVE IMPLEMENTATION SPECIFICATION

Version: FINAL-1.1 (consolidated, post-audit)
Status: APPROVED FOR IMPLEMENTATION
Supersedes: All prior drafts, amendments, and review correspondence. No other document is binding.

User-facing statement: Seven systems. Same market. Measurable evidence.

⸻

1. PROJECT PURPOSE

Build a new, isolated project named AKRA AI TRADING LAB: a controlled competition determining whether specific AI components improve a transparent momentum/trend-breakout trading strategy—individually and in combination.

This is:

* Research only
* Historical simulation followed by paper trading
* Not real-money trading
* Not a modification or extension of AKRA Arena, Wallet D, Forward V1/V3, Momentum Lab, or Engine v7

Create: a new repository, a new simulator, a new database, new models, new ledgers, a new dashboard, a new deployment, and a new audit trail. Existing projects must remain untouched.

⸻

2. EXECUTION MODEL

One autonomous master assignment containing internal phases and verification gates. Not one uncontrolled implementation pass.

Proceed autonomously through:

1. Phase 0: Read-only discovery
2. Phase 1: Protocol foundation—define and freeze Arm A, maximum holding period, universe rule, and the exact partition rule
3. Phase 2: Data ingestion and holdout quarantine—the holdout range is mechanically established by the frozen Phase-1 partition rule before ingestion
4. Phase 3: Independent simulator
5. Phase 4: Arm A implementation
6. Phase 5: Golden fixtures and Engine v7 differential gate
7. Phase 6: Arms B–G
8. Phase 7: Dashboard and operations
9. Phase 8: Invalid end-to-end shakedown
10. Checkpoint 1: Shakedown review—human approval required
11. Retraining and validation
12. Checkpoint 2: Protocol and holdout authorization—human approval and key required
13. One-time sealed holdout evaluation
14. Frozen forward paper competition

Stop only for:

* A genuine hard blocker
* Checkpoint 1
* Checkpoint 2
* A required security or destructive-action approval

Do not repeatedly ask minor implementation questions. Make reasonable decisions within this specification and record them in BUILD_STATE.md.

⸻

3. SEVEN OFFICIAL ARMS

Arm A — Transparent Control

A deterministic momentum/trend-breakout strategy.

Before any candidate generation, Arm A must define and freeze:

* Eligible market universe through the frozen mechanical rule
* Long rules
* Short rules
* Candidate times
* Entry rules and entry-price assumptions
* Stop rules
* Target rules
* Exit rules
* Position sizing
* Maximum holding period
* Maximum concurrent positions
* Exposure limits
* Maximum leverage
* Time-based exit behavior
* Missing-data behavior

Arm A becomes frozen before any AI label is generated. It is the common candidate generator and benchmark.

Arm B — ML Trade Filter

Uses exactly Arm A’s candidate events.

The model may only accept or reject each candidate.

It may not change:

* Candidate generation
* Candidate timing
* Ranking
* Position size
* Entry execution
* Exit management

Start with an explainable tabular model such as LightGBM or XGBoost.

Preserve:

* Model probability
* Decision threshold
* Accept/reject decision
* Feature values
* Feature explanation
* Model version
* Dataset version

Arm C — ML Asset Ranker

Uses exactly Arm A’s candidate events.

At every decision timestamp, rank eligible candidates relative to one another and select within portfolio limits.

Preserve:

* Rank
* Number of eligible candidates
* Ranking score
* Selection cutoff
* Feature values
* Model version

Never display arbitrary model scores as “confidence.”

Use meaningful language such as:

Ranked 2 of 61 eligible candidates.

Arm D — Market-Regime Model

Uses Arm A candidates and management, plus an independently defined regime model.

Initial regimes:

* Uptrend
* Downtrend
* Sideways/choppy
* High-volatility stress

The frozen regime policy may permit a trade, block a trade, or reduce exposure, expressed as a frozen numeric multiplier:

* Permit → D multiplier = 1.00
* Reduce → D multiplier = 0.50
* Block → D multiplier = 0.00

The D multiplier policy is frozen before evaluation.

Preserve:

* Detected regime
* Regime probabilities when applicable
* Inputs
* Resulting action and multiplier
* Model version

Arm E — Intelligent Position Sizing

Arm E tests sizing only.

Binding rules:

1. Arm E trades every trade taken by Arm A. It may not reject a trade.
2. Permitted sizes are exactly:
    * 0.25× Arm A size
    * 0.50× Arm A size
    * 0.75× Arm A size
    * 1.00× Arm A size
3. Arm E may never choose zero.
4. Arm E may never exceed Arm A’s size.
5. Arm E uses the same entries and frozen exit management as Arm A.
6. If the external risk governor blocks or restricts a trade for capacity reasons, that is an external restriction recorded as such—it is not Arm E choosing zero.

Training design:

* Supervised sizing model using:
    * Primary outcome target: Arm A’s frozen net R-multiple label
    * Downside target: probability and/or magnitude of adverse net R
    * Features available at Arm A’s decision timestamp only
* Frozen model outputs map into the four size buckets.
* Bucket boundaries, predictive method, and mapping are selected using training and validation only, then frozen before holdout.

Frozen model-selection utility using validation only:

[
U_E =
\operatorname{Sortino}_{net}
−
2 \times
\max\left(
0,
\frac{DD95_E-DD95_A}
{\max(DD95_A,0.01)}
\right)
]

Where:

* Sortino_net is Arm E’s annualized validation Sortino ratio after fees, spread, slippage, and funding.
* Minimum acceptable return, or MAR, is zero.
* DD95_E is the pre-registered upper 95% confidence bound of Arm E’s maximum-drawdown distribution using the dependence-aware bootstrap.
* DD95_A is the equivalent validation value for Arm A.
* Drawdowns are positive decimal magnitudes: 0.20 means 20%.
* The denominator floor of 0.01 prevents division instability.
* The penalty applies only when Arm E’s drawdown bound is worse than Arm A’s.
* The multiplier 2 is frozen before model selection.

Tie-breaking order:

1. Lower DD95_E
2. Higher net validation return after all costs
3. Lower turnover
4. Simpler model

Do not modify the formula or its constants after selectively viewing validation candidates or after any holdout access.

Any future formula change creates a new experiment version requiring complete retraining and approval.

Arm F — Reinforcement-Learning Manager

Uses Arm A’s entries, initial position sizes, and initial protective rules.

The RL agent controls post-entry management only.

Permitted actions:

* Hold
* Reduce by 25%
* Reduce by 50%
* Close completely
* Tighten stop
* Move stop to breakeven when permitted

Prohibited actions:

* Increasing position size
* Widening a stop
* Removing protection
* Exceeding risk limits
* Opening independent trades

Observations may include:

* Unrealized P&L in R
* Time in trade
* Maximum favorable excursion
* Maximum adverse excursion
* Volatility
* Momentum deterioration
* Regime changes
* Distance to stop
* Distance to target
* Portfolio exposure

Reward must include:

* Net realized performance
* Fees
* Slippage
* Funding
* Drawdown penalty
* Excessive-turnover penalty
* Risk-violation penalty

Use a stable, documented algorithm from Stable-Baselines3 unless discovery justifies a better documented standard.

Train at least 10 independent seeds.

Report:

* Median
* Mean
* Best seed
* Worst seed
* Interquartile range
* Seed variance
* Percentage of seeds beating Arm A
* Training stability
* Numerically defined convergence diagnostic
* Selected-policy rule

The official policy-selection rule must use training and validation only and must be frozen before holdout access.

Arm G — Complete AI System

Combine the exact frozen artifacts of Arms B–F in this exact pipeline order:

1. Arm A generates candidates.
2. Regime model classifies the environment.
3. ML filter accepts or rejects candidates.
4. ML ranker ranks accepted candidates.
5. Risk governor calculates available portfolio capacity.
6. Sizing model selects permitted size using Arm E’s frozen buckets and mapping.
7. Frozen execution rules enter positions.
8. RL agent manages open positions.
9. Risk governor approves or restricts every action.

Arm G sizing composition:

[
\text{G requested size}
=
\min(\text{E multiplier},\text{D multiplier})
\times \text{Arm A size}
]

Where:

* E multiplier is one of 0.25, 0.50, 0.75, or 1.00.
* D multiplier is one of 0.00, 0.50, or 1.00.
* D multiplier 0.00 means no position is opened.
* The external risk governor may restrict the requested size further.
* The external risk governor may never increase it.

The risk governor can restrict an AI action but can never increase its risk.

Arm G Shadow Counterfactual

Maintain:

* G actual: Complete system including RL
* G pre-RL shadow: Identical G decisions through entry, followed by frozen conventional management

The shadow is diagnostic and is not an eighth official arm.

It determines whether RL improved or damaged the otherwise identical combined pipeline.

G-shadow identity through entry is a constitutional test.

⸻

4. ML LABEL DEFINITION

The primary label for Arms B, C, and E is:

Net R-multiple achieved by the candidate under Arm A’s frozen entry and management rules, including fees, spread, slippage, and funding.

No arm’s training may use:

* RL-managed outcomes
* Arm G outcomes
* Future regime knowledge
* Alternative exit rules selected after observing results

The label must be reproducible directly from the frozen Arm A ledger.

⸻

5. ARM A MAXIMUM HOLDING PERIOD

The maximum holding period is a strategy parameter.

It must be defined and frozen before:

* Candidate generation
* Label creation
* Feature generation
* Training
* Validation
* Holdout partitioning

At expiry, close the position through a deterministic, pre-specified execution rule including all costs.

Apply it identically during:

* Training
* Validation
* Holdout
* Forward paper trading

Changing it requires:

* New Arm A version
* Candidate regeneration
* Label regeneration
* Model retraining
* Validation regeneration
* New invalid shakedown
* New protocol approval

⸻

6. MARKET AND DATA DESIGN

Preferred initial scope:

* Liquid USDT perpetual markets
* Long and short
* Target universe of approximately 50–100 assets
* Four-hour candidate decisions
* Fifteen-minute execution and management simulation
* BTC and market-wide context
* Realistic fees
* Spread
* Slippage
* Funding where reliable
* Honest delisting and availability handling

Universe membership must be determined at every historical timestamp using a frozen mechanical rule based only on information available at that timestamp.

Possible criteria include:

* Trailing liquidity
* Trading-history requirement
* Market availability
* Data completeness
* Spread constraints

The exact rule must be frozen before candidate generation.

Do not apply the present-day universe retroactively.

If reliable survivorship-free perpetual history is unavailable:

* Do not invent it.
* Document the fallback.
* Quantify the realism lost.
* Limit conclusions accordingly.

Raw data must be:

* Immutable
* Content-hashed
* Versioned
* Separated from derived data
* Protected against destructive cleanup
* Reproducibly downloadable where licensing permits
* Subject to the holdout quarantine, which applies at every layer including the raw lake

Storage technology—Parquet, DuckDB, or PostgreSQL—is an engineering decision.

Whichever is chosen:

* Raw market data is read-only after ingestion.
* Derived data is separately reproducible.
* Decision and trading ledgers are immutable.

⸻

7. MECHANICAL DATE PARTITIONING

Partitions are selected mechanically, never by favorable appearance.

After determining the eligible continuous historical interval through frozen data-quality rules, divide it chronologically using this binding partition:

* Training: first 60%
* Validation: next 20%
* Sealed historical holdout: final 20%

Snap boundaries to valid four-hour decision boundaries.

This ratio is fixed as of FINAL-1.1.

Changing it requires:

* A new protocol version
* Explicit user approval
* The change must occur before ingestion

After freezing:

* Do not move boundaries.
* Do not choose favorable periods.
* Do not exclude difficult regimes based on performance.
* Do not redesign universe rules using knowledge of the holdout period.

⸻

8. HONEST HOLDOUT SCOPE

The historical holdout is public market history.

Quarantine and encryption prevent project code and trained models from accessing its rows before authorization. They cannot make the designing agent entirely ignorant of widely known historical market behavior.

Distinguish clearly:

* Historical holdout: Unseen by models and evaluation code during development
* Forward paper data: Genuinely unavailable to both models and builder at design time

LIMITATIONS.md and the forensic report must state:

These controls prevent project-level and accidental computational access to the historical holdout before authorization. Because the underlying market history is public and may be obtainable from external sources, they cannot prove that a sufficiently privileged or deliberately adversarial builder is wholly incapable of retrieving equivalent historical information. Mechanical partitioning, audit logs, restricted project utilities, and the forward test mitigate this limitation.

Never describe the historical holdout as completely unseen by the builder.

The forward paper phase is the only genuinely future-unseen evidence.

⸻

9. HOLDOUT QUARANTINE AND PHYSICAL SEAL

The quarantine applies to the entire frozen holdout date range at every data layer:

* Raw candles
* Funding
* Universe information
* Derived data

Before Checkpoint 2:

1. No plaintext holdout-period data may exist in the project’s readable raw lake.
2. Raw holdout-period data must pass directly through a non-interactive sealing process into encrypted storage at ingestion.
3. Mechanical pass-through inside the sealing utility is permitted; display is not.
4. Holdout rows, values, summaries, and outcomes must never be printed to:
    * Console
    * Logs
    * Reports
    * Agent context
    * Dashboard
    * Temporary debugging files
5. Project ingestion, backfill, download, and diagnostic utilities must refuse requests intersecting the holdout date range.
6. Constitutional tests must verify refusal for:
    * Exact holdout range
    * Partial overlap
    * Individual holdout timestamps
    * Alternate symbols
    * Funding endpoints
    * Universe and metadata requests
7. Where operationally practical, restrict direct exchange-data retrieval during the sealed phase.
8. The decrypted holdout must never be written back into the ordinary raw lake.

Seal mechanics:

1. Store the holdout as a strongly encrypted artifact.
2. The user alone holds the decryption passphrase.
3. Never store the key in:
    * Repository
    * Files
    * Environment files
    * Shell history
    * Logs
    * Database
    * Build artifacts
    * Claude instructions
4. Accept the key only through secure interactive entry at Checkpoint 2.
5. Training, validation, dashboard, and diagnostic code must be incapable of reading holdout rows before authorization.
6. Premature access attempts are rejected, immutably logged, and constitute a critical integrity failure.
7. Never commit decrypted data.
8. Never retain decrypted temporary copies after evaluation.

Produce:

* Encrypted holdout artifact
* Content hash
* Non-outcome partition metadata
* Encryption documentation
* Verification command
* Decryption audit log

Decryption must refuse unless all of the following match:

* Approved protocol hash
* Git commit
* Dataset manifest
* Model manifest
* Integrity-test manifest
* User’s most recently approved externally preserved manifest root hash
* Recorded Checkpoint-2 authorization

⸻

10. VARIABLE-HORIZON PURGING

Each label’s information interval is:

[candidate timestamp, final Arm A exit timestamp]

Remove any training example whose complete information interval overlaps validation or holdout.

The embargo must be no shorter than Arm A’s maximum holding period.

Do not use a fixed bar count shorter than the label horizon.

Fit all of the following using training data only:

* Scalers
* Encoders
* Preprocessors
* Feature selectors
* Thresholds

⸻

11. INDEPENDENT SIMULATOR

Build a new simulator appropriate to this project.

There must be no:

* Import of Engine v7
* Modification of Engine v7
* Runtime dependency on Engine v7

The simulator must support:

* Long and short
* Partial exits
* Stops and targets
* Intrabar ambiguity
* Fees
* Spread
* Slippage
* Funding
* Position sizing
* Portfolio capital competition
* Margin
* Multiple simultaneous positions
* Maximum holding time
* Deterministic seeds
* Decision snapshots
* Rejection logging
* RL actions
* G-shadow accounting
* Immutable trade lifecycles

Use conservative deterministic handling when OHLC data cannot determine whether a stop or target occurred first.

Record every ambiguity.

Document every execution assumption in SIMULATOR_SEMANTICS.md.

⸻

12. GOLDEN FIXTURES

Create independently auditable fixtures covering at minimum:

* Long winning exactly +2R
* Short losing exactly −1R
* Partial exit followed by breakeven
* Gross winner becoming net loser after costs
* Correct funding timestamps
* Overlapping positions
* Capital competition
* Margin constraints
* Intrabar stop/target ambiguity
* Portfolio loss-limit rejection
* Insolvency
* Time-based exit
* Missing price data
* Invalid RL action
* Synchronized-round failure

Expected fixture values must receive independent review by the user, ChatGPT, or another reviewer.

Do not rely exclusively on values calculated by the simulator’s author.

⸻

13. MANDATORY ENGINE v7 DIFFERENTIAL GATE

Engine v7 serves as a differential oracle for the formally defined common semantic subset—never as a dependency.

Minimum required common subset for the gate to count as satisfied:

* Long positions
* Short positions
* Multiple simultaneous positions
* Portfolio capital competition
* Position sizing
* Protective stops
* Deterministic exits
* Trading fees
* Cash accounting
* Equity accounting
* Exposure accounting
* Rejection due to insufficient capacity
* Insolvency or ruin protection

Use a dataset and fixture exercising all of these behaviors.

Run one deterministic shared strategy and identical dataset through both engines.

Reconcile at ledger level:

* Candidate timestamps
* Entries
* Exits
* Position sizes
* Rejections
* Fees
* Realized P&L
* Cash
* Equity
* Exposure
* Insolvency behavior

Require exact agreement where semantics are defined as identical.

On mismatch:

1. Stop the gate.
2. Produce a transaction-level difference report identifying the first divergence.
3. Adjudicate whether the cause is:
    * New-engine bug
    * Engine v7 issue
    * Data mismatch
    * Intentional semantic difference
4. Record the adjudication.
5. Rerun after resolution.
6. Never silently alter either engine merely to force agreement.

If discovery shows Engine v7 cannot support the minimum subset comparably:

1. Do not claim the gate passed.
2. Report the unsupported semantics.
3. Stop for adjudication.
4. Propose an independent differential implementation or external ledger calculator covering the missing minimum.
5. Do not reduce the gate to a trivial long-only, single-position comparison.

Engine v7 is not authoritative for:

* RL actions
* ML ranking
* G-shadow behavior
* New funding semantics
* New portfolio rules
* Features it never supported

⸻

14. EXTERNAL RISK GOVERNOR

Create a deterministic risk governor outside every model.

It must enforce:

* Maximum risk per trade
* Maximum exposure
* Maximum leverage
* Maximum correlated exposure
* Maximum concurrent positions
* Daily loss limit
* Portfolio drawdown safety limit
* Valid protective order on every position
* Emergency pause
* Missing-data fail-safe

No AI model may bypass it.

The safe response to missing or invalid required data is:

No new trade.

Never silently substitute Arm A when an AI arm fails.

⸻

15. CONSTITUTIONAL TEST GOVERNANCE

Development Tests

Examples:

* API
* UI
* Parsing
* Database
* Formatting
* Ordinary implementation tests

Claude may modify these while developing, with Git history preserved.

Constitutional Integrity Tests

Lock and hash these before the official shakedown:

* No-lookahead
* Deliberate-leak rejection
* Holdout access refusal at all layers
* Chronological partitioning
* Variable-horizon purge
* Candidate equality
* Timestamp equality
* Cross-arm data equality
* Risk-governor non-bypass
* Immutable ledgers
* Missing-round invalidation
* Feature-time availability
* Dataset fingerprint
* Model artifact isolation
* Engine v7 reconciliation
* G-shadow identity through entry

Produce a cryptographic manifest covering:

* Constitutional tests
* Leaking fixtures
* Partition specification
* Protocol
* Risk policy
* Simulator semantics
* Engine v7 differential specification

Display the root hash at Checkpoint 1.

The user must preserve a copy outside the repository.

Claude may repair implementation code when a constitutional test fails.

Claude may not silently:

* Weaken assertions
* Increase tolerances
* Skip tests
* Delete tests
* Change expected outcomes
* Rewrite leaking fixtures
* Regenerate the manifest and pretend nothing changed

If a locked test is genuinely wrong:

1. Stop.
2. Create a versioned replacement.
3. Explain the error.
4. Record old and new hashes.
5. Obtain approval.
6. Invalidate results generated under the previous version.
7. Rerun affected phases.

Manifest Hash Lineage

When an approved versioned change modifies the manifest:

1. Preserve the old manifest and root hash.
2. Create a new versioned manifest.
3. Record:
    * Previous root hash
    * New root hash
    * Files changed
    * Reason
    * Approval
    * Results invalidated
    * Phases rerun
4. Present the new root hash to the user for external preservation.
5. Mark it as the currently approved root.
6. At Checkpoint 2, compare against the most recently approved externally preserved root.
7. Preserve the complete hash lineage in the forensic report.

A new local hash without explicit approval and external re-preservation is invalid and blocks holdout access.

⸻

16. MATERIAL-CHANGE AND RETRAIN RULE

A material change is anything affecting:

* Data
* Universe
* Candidates
* Features
* Labels
* Feature timing
* Label timing
* Purging
* Embargo
* Preprocessing
* Simulation
* Fees
* Funding
* Slippage
* Margin
* Capital competition
* Entry
* Exit
* Stops
* Position size
* Regime logic
* RL rewards
* Risk
* Arm G composition
* Candidate equality
* Decision timing

After a material change:

1. Invalidate affected results.
2. Invalidate affected model artifacts.
3. Regenerate candidates and labels when applicable.
4. Retrain affected models from scratch.
5. Refit preprocessing from scratch.
6. Regenerate validation.
7. Rerun constitutional tests.
8. Rerun Engine v7 reconciliation when shared semantics changed.
9. Run another invalid shakedown when operational behavior changed.
10. Record all old and new hashes.

Never reuse:

* Old weights
* RL checkpoints
* Fitted scalers
* Cached labels
* Selected thresholds
* Pre-fix validation artifacts

A shakedown repair must not become an informal additional training pass.

⸻

17. LEARNABILITY DIAGNOSTIC

Before holdout access, using training and validation only, measure:

* Candidate count
* Effective independent sample size
* Label distribution
* Long/short balance
* Assets represented
* Regimes represented
* Candidate dependence
* Feature stability
* Label stability
* Temporal stability
* Class imbalance
* Performance dispersion
* Approximate achievable ranking separation
* Statistical power to detect the pre-registered minimum useful improvement

Before Checkpoint 2, freeze:

* Calculations
* Thresholds
* Power assumptions
* Minimum effective sample size
* Conditions producing INSUFFICIENT LEARNABLE VARIATION

After holdout access:

* Thresholds cannot change.
* Holdout results cannot redefine learnability.
* A failed ML result cannot retroactively be excused as unlearnable.
* Holdout values cannot enter the learnability calculation.

Allowed verdicts:

* PROMISING
* NO DEMONSTRATED IMPROVEMENT
* HARMFUL
* INSUFFICIENT EVIDENCE
* INSUFFICIENT LEARNABLE VARIATION

Never generalize a result to all AI trading.

Scope every conclusion to:

* This candidate generator
* These features
* These labels
* These assets
* This period
* These costs
* These models

⸻

18. PRIMARY SCIENTIFIC QUESTION

Does an AI arm improve net risk-adjusted return over Arm A after all costs without violating the pre-registered bootstrap drawdown constraint?

Select one frozen primary risk-adjusted statistic before holdout.

Supporting metrics—never sufficient alone—include:

* Net return
* Maximum drawdown
* Sharpe
* Sortino
* Calmar
* Profit factor
* Average trade
* Turnover
* Fees
* Slippage
* Funding
* Exposure
* Time in cash
* Tail loss
* Stability across periods and regimes
* Outlier dependence

Apply a pre-registered multiple-comparison correction across the six challengers.

Do not declare success merely because one supporting metric improved.

⸻

19. BOOTSTRAP DRAWDOWN

Report:

* Observed maximum drawdown
* Dependence-aware bootstrap drawdown distribution
* Pre-registered upper confidence bound

Use:

* Block bootstrap, or
* Another justified dependence-preserving method

Do not independently shuffle correlated trades.

The pass/fail drawdown constraint uses the frozen bootstrap statistic—not only the single observed path.

⸻

20. INVALID SHAKEDOWN

The first complete seven-arm run is always:

SHAKEDOWN — INVALID FOR PERFORMANCE CONCLUSIONS

Use it to detect:

* Missing decisions
* Candidate inequality
* Timestamp inequality
* Feature failures
* Model failures
* RL violations
* Ledger corruption
* Restart failures
* Dashboard disagreements
* Data gaps
* Asymmetric downtime
* Seal failures
* Risk-governor failures

Shakedown results must:

* Remain permanently marked invalid
* Never enter performance claims
* Never be merged into official results
* Never be backfilled
* Never be reused as holdout evidence

⸻

21. CHECKPOINT 1 — SHAKEDOWN REVIEW

After the shakedown, stop and provide:

* Complete defect inventory with root causes
* Affected arms
* Affected decisions
* Affected metrics
* Every implementation change
* Every test change
* Every scientific change
* Every semantic change
* Retraining requirements under the material-change rule
* Engine v7 reconciliation results
* Integrity-test status
* Confirmation that shakedown ledgers remain permanently invalid
* Proposed frozen release candidate
* Root integrity-manifest hash for external preservation

Do not reset and launch the official candidate until the user approves Checkpoint 1.

⸻

22. CHECKPOINT 2 — PROTOCOL AND HOLDOUT AUTHORIZATION

After training and validation—but before decryption—stop and provide:

* Frozen protocol
* Frozen Arm A specification
* Frozen maximum holding period
* Frozen universe rule
* Frozen partition dates
* Frozen features
* Frozen labels
* Frozen models
* Frozen hyperparameters
* Frozen thresholds
* Frozen Arm E utility formula
* Frozen Arm E buckets and mapping
* Frozen RL seed-selection method
* Frozen learnability thresholds
* Frozen success criteria
* Frozen multiple-comparison correction
* Bootstrap procedure
* Forward evidence floor
* Dataset hashes
* Model manifest
* Git commit
* Constitutional-test manifest
* External hash comparison using the most recently approved root
* Confirmation that no holdout access occurred

Do not decrypt until:

* The user explicitly approves.
* All hashes match.
* The user supplies the key interactively.

The holdout may be evaluated once.

After opening it, mark it permanently consumed.

⸻

23. FORWARD PAPER COMPETITION

Model Vintage

The forward competition uses the exact frozen artifacts evaluated on the sealed historical holdout.

No refitting on:

* Validation
* Holdout
* Train plus validation
* Train plus validation plus holdout
* Any post-holdout data

The forward package must be identical to the holdout-evaluated package, including:

* Features
* Preprocessors
* Models
* Thresholds
* Regime artifacts
* Sizing mappings
* RL policy
* Arm G composition
* Risk configuration

Any retrained or adaptive model is a separate future experiment and may not be merged with this forward cohort.

Arm G Artifact Provenance

Arm G uses the exact frozen artifacts from Arms B–F.

Arm G may not:

* Retrain components
* Fine-tune them jointly
* Change thresholds
* Recalibrate outputs
* Select new features
* Optimize component interaction after seeing results

Arm G tests frozen composition—not a separately trained model.

LIMITATIONS.md must state:

Arm F’s RL policy is trained using Arm-A-sized entries. Inside Arm G, it manages positions sized by Arm E’s frozen mapping. This creates an accepted position-size distribution shift. The RL state uses normalized exposure and R-based quantities where possible, but the difference remains a limitation and is reported. Frozen forward models may become stale; this is accepted in exchange for preserving identity between historical evaluation and forward evaluation.

Operations

* Freeze code, configurations, and model artifacts.
* Reset separate paper ledgers.
* Start all seven arms simultaneously.
* Use identical live snapshots.
* Preserve all decisions immutably.

At every four-hour boundary:

* All seven arms receive the same complete snapshot.
* Any arm unable to decide invalidates the round for all arms.
* Record the failure.
* Never backfill.
* Never allow healthy arms to accumulate official results during an asymmetric round.

Forward horizons:

* 13 weeks: Descriptive
* 26 weeks: Descriptive
* 52 weeks: Primary ruling unless pre-registered power analysis requires longer

Forward results count as confirmatory evidence only if:

1. At least 95% of scheduled rounds are valid and synchronized.
2. At least 100 completed trades exist for every actively trading arm.
3. There is adequate frozen regime representation.
4. There is no unresolved critical integrity incident.
5. There is no unauthorized material change.
6. There are no reconstructed or backfilled decisions.

Below the floor:

INSUFFICIENT EVIDENCE

Do not lower the floor after observing results.

Remaining flat is a valid decision, but an arm with insufficient completed trades cannot receive a conclusive forward verdict unless Checkpoint 2 pre-registered a different statistically justified minimum.

⸻

24. SESSION PERSISTENCE

Maintain:

* BUILD_STATE.md
* build_state.json

They must agree.

Record:

* Current phase
* Last completed gate
* Current Git commit
* Dataset hashes
* Model hashes
* Integrity-manifest hash
* Completed actions
* Pending actions
* Active blockers
* Approved decisions
* Material changes
* Invalidated artifacts
* Required retraining
* Checkpoint status
* Exact safe resume command

Rules:

1. Update after every material milestone.
2. Commit with the corresponding code state.
3. Never rewrite earlier decisions silently.
4. Preserve chronological decision history.
5. A new session must read:
    * This specification
    * BUILD_STATE.md
    * Git status
    * Relevant manifests
    * Latest forensic report
6. Verify recorded hashes before resuming.
7. Do not re-decide frozen choices.
8. Do not repeat completed work unless verification fails.
9. Record any discrepancy before continuing.

⸻

25. COMPUTE BUDGET

Perform a profiling run before full training:

* Benchmark one representative RL seed.
* Estimate total wall-clock time.
* Estimate memory.
* Estimate storage.
* Determine safe parallelism.
* Record the estimate in BUILD_STATE.md.

Resource policy:

* No paid cloud resources without explicit approval.
* No real-money service activation.
* Non-RL training and validation: maximum 48 wall-clock hours per complete cycle.
* RL: maximum 24 wall-clock hours per seed.
* Minimum 10 official RL seeds—never fewer.
* Parallelism limited by safely available CPU, RAM, and storage.
* Preferred maximum 48 wall-clock hours for the complete 10-seed RL stage when safe parallelism permits.
* Use deterministic seeds and resumable checkpoints.
* Record CPU, RAM, storage, and runtime consumption.

If projected compute exceeds the caps, reduce scope in this order:

1. Optimize implementation without semantic change.
2. Cache deterministic reusable features.
3. Reduce the mechanically selected universe:
    * 100 assets
    * Then 75
    * Then 50
    * Then 30
4. Preserve the same frozen trailing-liquidity rule.
5. Reduce nonessential hyperparameter-search breadth.
6. Reduce descriptive dashboard precomputation.

Never:

* Reduce below 30 assets without approval.
* Reduce below 10 RL seeds.
* Shorten RL training silently.
* Change convergence criteria to meet the clock.
* Select only convenient seeds.

If the minimum 30-asset, 10-seed configuration still cannot fit within available resources:

* Stop with a measured compute-blocker report.
* Report measured requirements.
* State the smallest additional compute needed.
* Do not silently weaken the experiment.

Any universe reduction must occur before official model training and must be frozen at Checkpoint 2.

⸻

26. DASHBOARD

Overview

Show a seven-arm leaderboard with:

* Starting equity
* Current or final equity
* Net return
* Maximum drawdown
* Primary risk-adjusted metric
* Sharpe
* Sortino
* Calmar
* Profit factor
* Win rate
* Trade count
* Average winner
* Average loser
* Exposure
* Turnover
* Fees
* Slippage
* Funding
* Time in cash
* Experiment status

Equity and Drawdown

Show:

* Seven equity curves
* Drawdown curves
* Arm toggles
* Visible training, validation, holdout, and forward boundaries

Decision Comparison

For every shared candidate, show:

* Timestamp
* Candidate
* Arm actions
* Acceptance
* Rank
* Regime
* Position size
* Entry
* Stop
* Exit actions
* Net result
* Avoided loss
* Missed winner
* Model version
* Explanation

Trades

Show:

* Completed trades
* Open positions
* Partial exits
* Costs
* Maximum adverse excursion
* Maximum favorable excursion
* Dollar result
* Percentage result
* R-multiple result

AI Audit

Preserve and display:

* Inputs available at decision time
* Model output
* Selected action
* Rejected alternatives
* Explanation
* Model version
* Dataset version
* Risk-governor response
* Later outcome displayed separately

Regime Analysis

Compare arms across:

* Uptrends
* Downtrends
* Sideways periods
* High-volatility periods
* Longs
* Shorts
* Assets
* Calendar periods

Research Integrity

Display:

* Git commit
* Dataset fingerprint
* Configuration hash
* Model versions
* Partition dates
* Number of configurations tried
* Seeds
* Known limitations
* Test status
* Holdout state
* Forward or simulated status
* Valid and invalid round counts

The dashboard must never rewrite historical decisions.

Every displayed number must trace to immutable ledger records.

The dashboard must be incapable of reading holdout rows before Checkpoint-2 authorization.

⸻

27. TECHNICAL STACK

Use the following unless discovery establishes a stronger documented reason otherwise:

* Python
* FastAPI
* PostgreSQL
* Parquet or DuckDB where beneficial for market data
* LightGBM or XGBoost
* Stable-Baselines3
* React or Next.js
* Docker Compose
* Alembic
* Pytest
* Structured JSON logging

Prefer a modular monolith over unnecessary microservices.

Provide one-command workflows for:

* Setup
* Data ingestion
* Verification
* Training
* Validation
* Shakedown
* Holdout authorization
* Holdout evaluation
* Forward launch
* Dashboard
* Health check
* Evidence export
* Safe shutdown
* Resume

⸻

28. REQUIRED DOCUMENTATION

Create:

* README.md
* ARCHITECTURE.md
* EXPERIMENT_PROTOCOL.md
* DATA_DICTIONARY.md
* MODEL_CARDS.md
* RISK_POLICY.md
* SIMULATOR_SEMANTICS.md
* INTEGRITY_TEST_POLICY.md
* HOLDOUT_POLICY.md
* DEPLOYMENT.md
* OPERATIONS.md
* LIMITATIONS.md
* CHANGELOG.md
* BUILD_STATE.md
* build_state.json
* Machine-readable manifest
* Final forensic report

⸻

29. FINAL VERIFICATION

Before declaring any stage complete, verify:

* Tests pass.
* Constitutional tests remain hash-valid.
* No lookahead exists.
* Candidate equality holds.
* Timestamp equality holds.
* Risk governor cannot be bypassed.
* Existing projects remain unchanged.
* No real-money endpoint is active.
* Simulator accounting reconciles.
* Engine v7 minimum-subset reconciliation passes.
* Shakedown is marked invalid.
* Dashboard matches ledgers.
* Holdout remains sealed at every data layer.
* Session state is current.
* Restart and recovery work.
* Missing-round invalidation works.
* Every result traces to immutable evidence.

⸻

30. GOVERNING PRINCIPLE

The agent may build the experiment.

It may not silently:

* Grade its own protections
* Weaken failed tests
* Change labels
* Move date boundaries
* Change the universe
* Redesign Arm A
* Reuse invalid models
* Peek at holdout rows
* Lower evidence requirements
* Backfill missed rounds
* Rewrite old decisions
* Declare broad AI conclusions from a narrow experiment

The historical holdout is unseen by the models, not necessarily unknown to the builder.

The forward paper phase is the only genuinely future-unseen evidence.

⸻

APPENDIX A — CHANGE LOG

1. The 240 core-hours RL ceiling was removed completely.
2. RL compute is governed by:
    * 24 wall-clock hours per seed
    * At least 10 seeds
    * Parallelism bounded by safely available resources
    * Preferred 48 wall-clock hours for the full RL stage
    * No paid cloud without approval
3. Arm E’s old zero-size, flatness, and rejection language was deleted.
4. Arm E trades every Arm A trade using exactly 0.25×, 0.50×, 0.75×, or 1.00×.
5. Arm E’s exact utility formula and constants were inserted.
6. Holdout quarantine applies at every data layer.
7. Forward model vintage A was selected.
8. Manifest lineage and external re-preservation were defined.
9. Arm G artifact provenance was frozen.
10. Engine v7’s minimum common subset was defined.
11. Phase ordering was corrected so the protocol and partition are frozen before ingestion.
12. The chronological partition is binding at 60/20/20.
13. Arm D multipliers and Arm G sizing composition were defined.

⸻

APPENDIX B — MACHINE-CHECKABLE REQUIREMENTS TABLE

ID	Binding rule	Section
R01	New isolated repository, database, simulator; existing projects untouched	1
R02	Autonomous phased execution; stop only at blockers or checkpoints	2
R03	Arm A frozen, including maximum holding period, before labels	3, 5
R04	Arm B accepts or rejects Arm A candidates only	3
R05	Arm C ranks candidates relatively; no fake confidence	3
R06	Arm D uses frozen permit, reduce, and block multipliers	3
R07	Arm E trades every Arm A trade using four permitted sizes	3
R08	Arm E never chooses zero and never exceeds Arm A size	3
R09	Arm E uses frozen utility formula and tie-breakers	3
R10	Arm F controls post-entry management only	3
R11	Arm F uses at least 10 seeds and frozen selection rule	3
R12	Arm G uses exact nine-step pipeline	3
R13	G pre-RL shadow maintained; not an eighth arm	3
R14	Label equals net R under Arm A management after all costs	4
R15	Maximum holding period is a frozen strategy parameter	5
R16	Universe uses frozen point-in-time mechanical rule	6
R17	Raw data immutable and versioned, subject to quarantine	6, 9
R18	Binding chronological 60/20/20 partition	7
R19	Honest holdout limitation disclosed	8
R20	Quarantine covers every data layer	9
R21	Sealing permits mechanical pass-through but no display	9
R22	Utilities refuse holdout-range requests	9
R23	User alone holds key; interactive all-hash gate	9
R24	Variable-horizon purge covers full information interval	10
R25	Preprocessing fitted on training data only	10
R26	Independent simulator; no Engine v7 dependency	11
R27	Golden fixtures require independent review	12
R28	Engine v7 differential gate has meaningful minimum subset	13
R29	Differential mismatch stops for adjudication	13
R30	External risk governor; no silent Arm A substitution	14
R31	Constitutional tests locked and hashed before shakedown	15
R32	Locked-test change requires version and approval	15
R33	Manifest changes require new externally preserved hash	15
R34	Material changes require invalidation and retraining	16
R35	Learnability diagnostic frozen before holdout	17
R36	One primary question and multiple-comparison correction	18
R37	Dependence-aware bootstrap drawdown constraint	19
R38	First complete run permanently invalid	20
R39	Checkpoint 1 approval required	21
R40	Checkpoint 2 approval and key required	22
R41	Forward uses exact holdout-evaluated model vintage	23
R42	Arm G uses exact frozen B–F artifacts	23
R43	RL distribution-shift limitation disclosed	23
R44	Missed round invalidates all seven arms	23
R45	Forward floor: 95% valid rounds, 100 trades, 52-week ruling	23
R46	Durable BUILD_STATE files and resume protocol	24
R47	RL compute: 24h per seed, at least 10 seeds, no core-hour cap	25
R48	Scope reduction has fixed order and minimum floor	25
R49	Dashboard traces to immutable records and cannot read holdout early	26
R50	Required documentation produced	28
R51	Verification checklist required before stage completion	29
R52	Agent may not grade or weaken its own protections	30
R53	Protocol foundation frozen before data ingestion	2
R54	Partition change requires new approved version before ingestion	7
R55	G requested size equals min of E and D multipliers times Arm A size	3

⸻

APPENDIX C — REMAINING CONTRADICTIONS

None found.

Specifically verified:

* No clause permits Arm E to choose zero, remain flat, or reject a trade.
* No core-hour limit remains.
* Raw-data immutability is subordinated to holdout quarantine.
* The risk governor’s external no-trade decision does not conflict with Arm E’s no-zero rule.
* Manifest lineage is compatible with the decryption hash gate.
* Protocol and partition rules are frozen before ingestion.
* The partition is binding at 60/20/20.
* Arm G’s size-composition rule is consistent with Arm E, Arm D, and the risk governor.

FINAL DECISION: APPROVED FOR IMPLEMENTATION — FINAL-1.1

⸻

IMPLEMENTATION LAUNCH INSTRUCTION

FINAL-1.1 is approved for implementation.

Treat everything above as the sole binding project specification. All previous drafts, amendments, review messages, and discussions are superseded and non-binding.

Begin implementation now.

1. Create a new isolated repository named akra-ai-trading-lab using the existing standalone-project location convention discovered during Phase 0.
2. Preserve this complete FINAL-1.1 specification verbatim inside the new repository as the authoritative specification.
3. Initialize BUILD_STATE.md and build_state.json immediately.
4. Record the initial Git commit and specification hash before implementation.
5. Proceed autonomously through the phases in the exact FINAL-1.1 order.
6. Do not modify any existing project.
7. Do not use real-money execution.
8. Do not stop for minor questions.
9. Do not silently weaken, replace, or reinterpret any binding requirement.
10. Stop only for:
    * A genuine hard blocker
    * A required security or destructive-action approval
    * Checkpoint 1
    * Checkpoint 2

The first complete seven-arm run must remain permanently labelled:

SHAKEDOWN — INVALID FOR PERFORMANCE CONCLUSIONS

At Checkpoint 1, stop and return the complete evidence package required by Section 21, including the externally preservable integrity-manifest root hash.

Do not open or evaluate the sealed holdout before Checkpoint 2 approval.

Do not stop after producing another plan.

Proceed with Phase 0 now.
