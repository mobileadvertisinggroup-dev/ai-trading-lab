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

No other locked-set changes are planned. Any additional change before
v5 requires its own documented reason before generation, and the v5
tool refuses undocumented changes exactly as v2/v3/v4 did.
