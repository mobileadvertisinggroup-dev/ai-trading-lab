# INTEGRITY_TEST_POLICY — AKRA AI TRADING LAB

Status: **DRAFT — NOTHING IS LOCKED.** Per the user's 2026-08-25 directive
the constitutional lock happens only after the independent fixture review
completes and the reviewer approves the exact-equality differential policy
(REVIEW_ISSUES_PHASE6.md issue A). This document defines the governance so
the lock is a mechanical act, not an improvisation.

## 1. Two test classes (SPEC FINAL-1.2 §15)

**Development tests** — everything under `tests/` today. Freely modifiable
during development with git history preserved. They include prototypes of
future constitutional assertions; a prototype passing is NOT a
constitutional guarantee.

**Constitutional integrity tests** — created as a separate tree
(`tests/constitutional/`) at lock time, then hashed into the integrity
manifest. After locking, Claude may repair *implementation* code when one
fails, but may never silently weaken assertions, raise tolerances, skip,
delete, change expected outcomes, rewrite leaking fixtures, or regenerate
the manifest quietly. A genuinely wrong locked test follows the §15
versioned-replacement procedure (stop → versioned replacement → explain →
record old+new hashes → approval → invalidate → rerun).

## 2. Constitutional test roster (to be locked; current prototype location)

| Constitutional test (spec §15) | Prototype today |
|---|---|
| No-lookahead | indicator prior-N/completed-bar tests; regime point-in-time test |
| Deliberate-leak rejection | to be written at lock (leaking fixtures that MUST fail) |
| Holdout access refusal, all layers | `test_seal_access.py` refusal battery |
| Chronological partitioning | `test_partition.py` |
| Variable-horizon purge | `test_labels.py` purge tests |
| Candidate equality across arms | to be written with Arms B–G runners |
| Timestamp equality | to be written with the multi-arm orchestrator |
| Cross-arm data equality | to be written with the multi-arm orchestrator |
| Risk-governor non-bypass | `test_governor.py`; plus arm-runner wiring test |
| Immutable ledgers | audit-chain test in `test_seal_access.py`; rounds ledger |
| Missing-round invalidation | `test_rounds.py` (G12) |
| Feature-time availability | to be written with `lab/features/build.py` |
| Dataset fingerprint | manifest verify test in `test_seal_access.py` |
| Model artifact isolation | to be written at training freeze |
| Reference-ledger reconciliation | `test_differential.py` + `test_invariants.py` (exact equality) |
| G-shadow identity through entry | to be written with Arm G |

## 3. Manifest and lineage (spec §15)

At lock time a machine-readable manifest records the sha256 of: every
constitutional test file, the leaking fixtures, EXPERIMENT_PROTOCOL.md,
SIMULATOR_SEMANTICS.md, RISK_POLICY.md, HOLDOUT_POLICY.md, the frozen
DATA_DICTIONARY.md, fixtures/golden/*, and the reference-ledger
differential specification (harness + policy). The manifest's **root hash**
is displayed at Checkpoint 1 for the user to preserve OUTSIDE the
repository. Any later manifest change follows the §15 lineage procedure
(old root preserved, new root approved and externally re-preserved);
an unapproved new local hash blocks holdout access.

## 4. Lock preconditions (all must hold)

1. Independent review of fixtures G01–G12 complete, derivations approved.
2. Exact-equality differential policy approved (issue A).
3. Seal-conformance position accepted or clarified (issue D).
4. DATA_DICTIONARY.md frozen.
5. Arms B–G runners exist so candidate/timestamp/cross-arm equality and
   G-shadow tests can be written against real interfaces.
6. Deliberate-leak fixtures written and demonstrated to FAIL the pipeline.
