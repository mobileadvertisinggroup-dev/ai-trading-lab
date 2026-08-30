# Proposed post-Checkpoint-2 constitutional lineage (NOT yet executed)

At the Checkpoint-2 closure (after the reviewer's authorization and the
one-time evaluation, or a decision not to open), constitutional
integrity manifest **v5** will be generated with explicit
v1 → v2 → v3 → v4 → v5 lineage, all predecessors preserved unmodified.
Reason-keyed changes it will carry:

1. `tests/test_checkpoint2_readiness.py` — ADDED (D67, post-v4-approval
   readiness): frozen-statistics correctness and gate-refusal tests;
   openly recorded in FAILCLOSED_VERIFICATION.md and D67 at creation
   time. The APPROVED v4 manifest is preserved byte-unmodified.
2. Any Checkpoint-2 closure artifacts the reviewer directs to be
   locked (e.g. the results-hash record and the CONSUMED ledger state).
3. `tests/test_gate_fault_injection.py` — ADDED (D69 blocker 5):
   fault-injection battery covering identity validation, decryption,
   extraction, the evaluator, result serialization, cleanup, result
   publication, and the ledger append; pre-claim faults proven unspent,
   post-claim faults proven FAILED_CLOSED with no success
   representation.
4. `tests/test_holdout_evaluator_units.py` — ADDED (D69 blockers 1+3):
   synthetic union-loader tests (overlay-only symbols enter the
   mechanical universe and generate candidates; every per-class
   validation refuses loudly) and hand-computed tests for every
   pre-registered reported quantity incl. the Amendment-A1 IL
   assessment.
5. `tests/test_holdout_gate.py` — MODIFIED (D69 blockers 2+5): the
   valid-environment fixture now carries the frozen-input manifest,
   staged model/sb3 dirs, and the frozen recipient; identity failure
   is proven to refuse BEFORE the claim (opening unspent), and a
   wrong-but-valid key is proven refused against the frozen recipient.
6. `tests/test_authz_negative.py`, `tests/test_checkpoint2_readiness.py`
   — MODIFIED (D69 blocker 2): gate calls updated for the new required
   `model_dir`/`sb3_dir` parameters; fabricated authorizations now also
   fail the frozen-inputs requirement.

No other locked-set changes are planned. Any additional change before
v5 requires its own documented reason before generation, and the v5
tool refuses undocumented changes exactly as v2/v3/v4 did.

## Pre-recorded reason for the NEXT lock (v7)
7. `tests/test_holdout_evaluator_units.py` — MODIFIED (D76 defect fix,
   post-v6-lock): the fixture's synthetic funding layout corrected to
   the REAL flat seal layout (funding/SYMBOL.parquet) and a regression
   added proving the overlay reader finds flat funding files. The
   nested-only fixture had masked a frozen-evaluator defect that the
   V6 dress rehearsal's funding activity guard caught by FAILING
   CLOSED in its isolated environment
   (readiness/DRESS_REHEARSAL_V6_GUARD_FAILCLOSED.json) — openly
   recorded here at change time for the v7 reason-keyed lock.
