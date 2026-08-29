# FAIL-CLOSED CONTROLS — MECHANICAL VERIFICATION (pre-Checkpoint-2, 2026-08-29)

Executed from a clean detached worktree at commit 3a92d9f (zero
uncommitted changes). Evidence: verbatim test output
`data/manifests/FAILCLOSED_TESTS_3a92d9f.txt` and live-probe record
`data/manifests/FAILCLOSED_LIVE_PROBES.json`. **No holdout row was
accessed at any point — every probe below verifies REFUSAL.**

## Test batteries (34/34 passed, clean worktree)
| Control | Battery |
|---|---|
| Read-layer refusal: exact/partial/point/funding/universe holdout queries refuse | tests/test_seal_access.py |
| Authorization strictness: fabricated/nonempty/stale hashes never grant; every field recomputed | tests/test_authz_negative.py |
| One-time gate: manifest-bound artifact name+hash; atomic single claim; tmpfs-only decrypt; wipe-and-verify; FAILED_CLOSED on every post-claim failure; permanent second-opening block; corrupt chain fails closed; recovery not self-authorizing | tests/test_holdout_gate.py |
| Gate unchanged with the frozen evaluator plugged in (refuses before touching anything; refusal audit-logged) + frozen-statistics correctness (Holm, paired bootstrap, drawdown constraint blocks) | tests/test_checkpoint2_readiness.py |
| Leak battery: label-in-features, off-dictionary column, purge violation, post-t feature, holdout contamination all fail loudly | tests/test_pipelines_leaks.py |

## Live-state probes (REAL lake + real manifests)
| Probe | Result |
|---|---|
| `verify_authorization` with no record | REFUSED: "no authorization record" |
| Holdout state ledger | no `holdout_state.jsonl`, no OPENING_STARTED — opening never claimed |
| `GuardedLake.read_klines(BTCUSDT, Q, Q+1d)` on the real lake | **HoldoutAccessError** |
| `GuardedLake.read_klines(BTCUSDT, 0, Q+1d)` (partial overlap) | **HoldoutAccessError** |
| `GuardedLake.read_funding(BTCUSDT, Q, Q+1d)` | **HoldoutAccessError** |
| Audit log | every refusal appended; hash-chained; tail decision = REFUSED |

## Gate completeness
The previously recorded gap — "the gate is NOT implementation-complete
until the real frozen evaluator is plugged in" — is CLOSED:
`lab.data.unseal.main` now wires the frozen evaluator
(`lab/tools/holdout_evaluator.py`, executing
PREREGISTRATION_CHECKPOINT2_EVALUATION.md) into `evaluate_holdout`.
Nothing upstream of the evaluator changed; the readiness test proves
the gate still refuses identically.

## Post-approval locked-set note (honest, not silent)
`tests/test_checkpoint2_readiness.py` is a NEW file inside the locked
census, added AFTER manifest v4 was approved. The approved v4 manifest
is preserved unmodified; this addition is recorded here and in D67 and
will be carried, reason-keyed, into the next constitutional manifest
version at the Checkpoint-2 closure. No approved evidence was altered.
