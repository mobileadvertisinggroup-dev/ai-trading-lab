# INDEPENDENT DELTA REVIEW — FINAL CORRECTIONS (verbatim, received 2026-08-26)

DECISION: PC-1 IS EXPLICITLY APPROVED — adopt as FINAL-1.2.1 with complete
hash lineage; scientific consequences accepted; source acquisition may use
isolated ephemeral staging under the listed protections; "project
ingestion" means admission into the readable project lake, which must
contain zero holdout-period rows.

Approvals recorded: (1) G03 v2 APPROVED — canonical 9979.960015, lineage
properly preserved, quantize-to-derivation-precision exact rule + 1e-8 raw
absolute guard accepted, classified as a layer-1 fixture correction, not a
simulator disagreement. (2) The 111-test rerun is accepted. (3) Full-SHA
Action pinning approved. (4) Draft → upload → verify → Git manifest push →
publish ordering approved. (5) Versioned exclusion registry approved for
first ingestion; preserve version, hash, and every discovered-symbol
classification in the dataset manifest.

Correction A — immutable-release evidence must use the dedicated endpoint
GET /repos/{owner}/{repo}/immutable-releases, recording HTTP status,
response body when available, UTC timestamp, repository, workflow commit,
and interpretation; 200 = enabled, 404 = not enabled or unavailable to the
token; any ambiguity recorded as UNVERIFIED, never inferred as enabled;
continue relying only on tamper-evident git-pinned hashes absent a
successful authoritative check.

Correction B — complete the one-time holdout evaluation gate: verify the
supplied artifact is the exact holdout artifact named and hashed in the
approved dataset manifest (refuse differing filename or recomputed sha256);
no general-purpose decrypt-and-leave-directory operation; one controlled
command that verifies every gate, records append-only hash-chained
OPENING_STARTED, decrypts only into protected temporary memory/tmpfs, runs
the exact frozen holdout evaluator, exports only permitted result ledgers,
wipes decrypted material in a finally block on success or failure and
verifies absence, records CONSUMED or FAILED_CLOSED, and refuses a second
opening after OPENING_STARTED unless a formal integrity adjudication
explicitly authorizes recovery. Consumption is established by the
append-only hash-chained state ledger, not by rewriting the authorization
JSON. Nine required negative tests (wrong artifact, renamed, wrong hash,
second opening, cleanup after success, cleanup after failure, pre-existing
output directory, no residue on either path, corrupted chain blocks
access). A deterministic dummy evaluator is acceptable; mark the gate
implementation-complete only when the real frozen evaluator is plugged
into the same controlled path.

Then: rerun the full suite; produce FINAL_DELTA_RESPONSE.zip (changed
files, hashes, tests, commit info, clean git status, state updates); stop
for review. Continue to prohibit: real ingestion; requesting/receiving the
age public key; constitutional locking; shakedown; holdout access. Do not
reopen or redesign already approved components.
