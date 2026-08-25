# INDEPENDENT REVIEW VERDICT — PHASE 6 BUNDLE (verbatim, received 2026-08-25)

OVERALL VERDICT

The Phase-6 implementation is conditionally approved. The constitutional
lock, real ingestion, holdout-key request, and shakedown remain blocked until
the corrections below are completed and reviewed.

1. GOLDEN-FIXTURE REVIEW — APPROVED WITHOUT CORRECTION: G01, G02, G04, G05,
G06, G07, G08, G09, G10, G11 (two-layer scope accepted), G12
(coordinator-level scope accepted). G03 APPROVED IN PRINCIPLE, REQUIRES A
VERSIONED NUMERIC CORRECTION: canonical hand-derived final cash is
9979.960015; the fixture stored 9979.960015000002, a binary floating-point
artifact. Preserve old fixture+hash in audit lineage; create versioned
corrected fixture; tighten the golden-value assertion so the discrepancy is
not hidden by a broad pytest.approx; rerun simulator, reference ledger,
differential gate, golden tests, randomized property tests; record old and
new hashes. This was NOT a simulator disagreement — the simulator and
reference ledger agreed; the defect was in the manually stored layer-1
expected value.

2. DIFFERENTIAL GATE — exact-equality policy APPROVED. Binding
interpretation: exact equality determines pass/fail; 1e-9 is diagnostic
annotation only and may never convert a mismatch into a pass; the
sequential summation order frozen in SIMULATOR_SEMANTICS.md remains
binding; any future exact mismatch requires first-divergence adjudication.
Structural independence of lab/refledger APPROVED for the formally defined
shared subset; the harness may import both implementations; the
implementations may not import one another or share calculation helpers.

3. PHASE-1 PROTOCOL — APPROVED as a transparent baseline (Donchian 60,
ATR(28), 2xATR stop, +3R target, 20-bar trailing exit, 42-bar/7-day max
hold, 0.75% risk, 10 positions, 150% gross cap, mechanical point-in-time
universe, binding 60/20/20 partition). Approval means suitable frozen
experimental choices — NOT a claim of optimality or profitability.

4. REQUIRED PARTITION/QUARANTINE ADJUDICATION — material
wording/implementation mismatch: FINAL-1.2 says the holdout range is
established before ingestion; the implementation downloads complete history
into plaintext staging to determine the interval/boundary, then seals.
Prepare a minimal versioned protocol clarification for explicit user
approval distinguishing (A) SOURCE ACQUISITION (ephemeral isolated runner
staging solely for quality validation, interval determination, boundary
computation, stream division, holdout encryption) from (B) READABLE PROJECT
INGESTION (admission into the ordinary readable lake; no holdout-period row
may enter). Required staging protections: inaccessible to
training/validation/dashboard/diagnostic code; no display of holdout
values; metadata-only logs; no Git commit; no ordinary Actions artifact
upload; no caching between runs; destruction immediately after successful
sealing or on failure; failure if destruction cannot be verified; only
pre-holdout data enters the readable lake; holdout data goes directly from
staging into the encrypted seal. Do not perform real ingestion before
approval.

5. GITHUB ACTIONS HARDENING (before real ingestion) — pin every third-party
Action to an audited full commit SHA; correct release transaction order
(draft -> upload all -> verify hashes -> commit+push manifests -> publish
only after push succeeds; failed push leaves the release a draft);
continue describing releases as tamper-evident unless immutable releases
are positively verified; capture repository release-setting evidence during
first authorized ingestion; add resumability or a measured chunking plan;
never publish a partial dataset as complete.

6. POINT-IN-TIME STABLECOIN EXCLUSION — replace the short hard-coded list
with a versioned, reviewable point-in-time exclusion registry or other
deterministic category rule; preserve exact registry version and
classifications in the dataset manifest; never silently change historical
classifications after results exist.

7. HOLDOUT AUTHORIZATION AND UNSEAL GATE — public-key sealing accepted
conceptually; implementation approval conditional on the sanctioned unseal
command: exact matches for protocol hash, Git commit, dataset manifest,
model manifest, constitutional-test manifest, most recently approved
external root hash, and explicit Checkpoint-2 authorization; private
identity only through secure interactive input, never stored anywhere;
decrypted holdout never written into the normal raw lake; decrypted
temporary material removed after the one-time evaluation; authorization and
consumption immutably recorded without recording the key. Add a
constitutional negative test proving a fabricated/nonempty-hash
authorization file cannot grant holdout access.

8. REQUIRED RETURN PACKAGE — compact review-delta package (corrected G03 +
hashes; tests rerun + results; proposed clarification; updated workflow;
SHA pins + provenance; corrected release ordering; stablecoin exclusion
design; updated HOLDOUT_POLICY.md; unseal-gate status; updated BUILD_STATE
files; git commit + clean status; delta manifest). STOP after producing the
delta package. Do not: perform real ingestion; request the age public key;
lock constitutional tests; run the official shakedown; weaken exact
differential equality; modify the frozen trading strategy; access holdout
rows. Wait for independent review and explicit user approval after
delivering the delta package.
