# REVIEW_ISSUES_PHASE6 — formal responses to the independent reviewer

Date: 2026-08-25. Status of gated work: per the user's directive, the
constitutional manifest is NOT locked, real ingestion has NOT run, the
holdout public key will NOT be requested again, and the shakedown will NOT
begin until this review completes.

---

## A. Differential tolerance — RESOLVED, PENDING REVIEWER APPROVAL

**Finding is accepted.** FINAL-1.2 §13 requires exact reconciliation where
semantics are identical; a silent 1e-9 tolerance was not compliant.

**What was measured.** Instrumenting the harness across all 11 curated
differential fixtures: 38 canonical transactions, **122 numeric field
comparisons, maximum absolute difference 0.0** — the tolerance had never
actually been exercised. The 60-example randomized property fuzz then
surfaced one genuine non-exact case: the `equity` value reported inside a
capacity-rejection record differed in the final bits.

**Root cause (adjudicated per §13).** IEEE-754 addition is not
associative. The main simulator accumulated equity as
`(cash + u1) + u2 + …` (sequential from cash); the reference ledger used
Python `sum()` (`cash + ((0 + u1) + u2 + …)`). Both implement "cash plus
total unrealized P&L"; the SEMANTIC SPEC had not pinned the operation
order, so "exact" was underdefined.

**Resolution (implemented).**
1. SIMULATOR_SEMANTICS.md §1 now specifies the accumulation order for
   equity and gross exposure (sequential from cash / from 0.0, in
   position-id order, one double addition per position). Operation order
   is part of the frozen semantics — this is what makes "exact
   reconciliation" well-defined for floating point.
2. The reference ledger was corrected to the specified order (the main
   simulator was unchanged).
3. The harness (`lab/verify/differential.py`) now compares every numeric
   field with **exact equality** (`==` on IEEE-754 doubles). No tolerance
   affects any verdict. The former 1e-9 threshold survives only as an
   *annotation* on divergence reports (classifying a future mismatch as
   "association noise" vs "likely semantic bug") to aid adjudication.
4. Full suite re-run: 79/79, including the randomized fuzz, under exact
   equality.

**Per-field report.** Fields compared exactly: qty, price, fee, pnl, stop,
target, rate, mark, paid, notional, equity, final cash, plus all
structural fields. Fields using tolerance: **none**.

**Why Decimal/fixed-point was not adopted.** It is feasible (both
implementations are pure Python at the comparison boundary) but not
necessary: with operation order specified, doubles reconcile exactly, as
demonstrated. Migrating both sides to Decimal would require specifying
quantization at every intermediate step (a larger semantic-spec surface,
same class of order-pinning decisions) and would slow the simulator
substantially for the full universe. If the reviewer prefers Decimal for
monetary fields regardless, it is a contained change to both
implementations plus a semantics-doc revision — a new experiment version
under §16 since it alters simulation arithmetic.

**Maximum possible accumulated error under the adopted policy: 0 by
construction** — any nonzero difference fails the gate and goes to
adjudication.

**Proposed binding tolerance policy (for approval):** exact bit equality
on every compared field; divergences of any magnitude stop the gate; the
1e-9 annotation is diagnostic only. The constitutional differential test
will not be locked until the reviewer approves this policy.

---

## B. Incomplete required fixtures — G11 AND G12 CREATED AND PASSING

- **G11 — partial exit followed by breakeven**
  (`fixtures/golden/G11_partial_exit_breakeven.json`): engine-level golden
  fixture with full hand derivation; runs in
  `tests/test_governor.py::test_golden_G11_partial_exit_then_breakeven`.
  Scope note stated inside the fixture: partial exits and stop moves are
  main-simulator scope (SIMULATOR_SEMANTICS §8), OUTSIDE the reference
  ledger's differential subset, so G11 verifies layer 1 (manual) and
  layer 3 (main simulator); layer 2 is not applicable by the frozen subset
  definition. If the reviewer wants partial exits added to the reference
  subset, that is a spec-level decision.
- **G12 — synchronized-round failure**
  (`fixtures/golden/G12_synchronized_round_failure.json`): its responsible
  component now exists (`lab/orchestration/rounds.py`, the
  synchronized-round coordinator: any failed or missing arm report
  invalidates the round for all seven arms; finalized rounds can never be
  reopened — backfill attempts raise). Runs in `tests/test_rounds.py`.

**Golden-fixture gate status: STILL INCOMPLETE** — all twelve fixtures
G01–G12 exist and pass mechanically, but none has received independent
expected-value review. Phase 5's three-layer fixture verification is NOT
declared satisfied and will not be until the reviewer signs off G01–G12.

---

## C. GitHub Release immutability — HONEST STATUS: NOT VERIFIED AS IMMUTABLE

- **raw-v1 does not exist.** No ingestion run has occurred; no data release
  of any kind exists yet. Everything below describes implemented workflow
  behavior, not an existing release.
- **Repository immutable-release setting:** UNVERIFIED. This session's
  GitHub tooling has no API surface for reading that repository setting,
  and I will not claim it. Evidence path: the repository owner can check
  Settings → General → Releases ("immutable releases"), or the first
  ingestion run's job can capture `gh api repos/{owner}/{repo}` output;
  that evidence will be attached to the ingestion record before raw-v1 is
  relied upon.
- **What the workflow actually does** (`.github/workflows/ingest.yml`,
  updated this round): refuses to reuse an existing tag (new data = new
  `raw-v<N>`); creates the release as a **draft**, uploads every asset
  (lake `tar.zst` parts split at 1900 MB against the ~2 GiB per-asset
  limit, the sealed `holdout-*.tar.age`, and `SHA256SUMS`), and publishes
  only after all uploads complete — a partially-uploaded release is never
  visible as published.
- **What the project actually relies on — tamper-evidence, not platform
  immutability:** every asset's sha256 is pinned in git-committed
  manifests; every consumer verifies hashes after download
  (`lab.data.lake.verify_manifest` + `SHA256SUMS`); a modified or replaced
  asset is therefore detected, and git history is the audit trail.
  HOLDOUT_POLICY.md §3 has been rewritten to state this explicitly and no
  longer describes the releases as "immutable".
- **Recovery from administrator deletion:** re-download is impossible, so
  recovery is re-ingestion from the primary source, which must reproduce
  identical content hashes for the same frozen range or the discrepancy is
  investigated and recorded.

---

## D. Seal semantic deviation — REPORTED AS CONFORMING; EXPLANATION BELOW

Claimed conformance, for the reviewer to accept or reject:

- **What the spec requires (§9):** the user alone holds the decryption
  key; the key is accepted only through secure interactive entry at
  Checkpoint 2; decryption refuses unless every recorded hash matches and
  a Checkpoint-2 authorization exists.
- **What is implemented/designed:** age X25519. The user generates the
  identity locally and provides only the PUBLIC key; sealing is
  public-key encryption, so CI never holds any secret and the user is
  cryptographically the only party able to decrypt (satisfying user-sole
  custody more strongly than a shared passphrase would). At Checkpoint 2,
  the `lab.data.unseal` gate (to be implemented before Checkpoint 2 and
  covered by constitutional tests) accepts the SECRET identity line only
  via an interactive terminal prompt — never argv, environment, or a file
  path — holds it in memory only, and decrypts only after ALL of: approved
  protocol hash, git commit, dataset manifest, model manifest,
  integrity-test manifest, the user's externally preserved root hash, and
  a recorded Checkpoint-2 authorization match (HOLDOUT_POLICY.md §7).
  Possession of the identity file is therefore necessary but NOT
  sufficient: the all-hash gate and recorded authorization are enforced by
  the only sanctioned decryption path, every attempt is appended to the
  hash-chained audit log, and the read layer (`GuardedLake`) independently
  refuses holdout reads without a complete, unconsumed authorization
  record (already implemented and tested).
- **Residual honest caveat:** a user who bypasses project tooling and runs
  `age -d` directly against the artifact can decrypt without the gate.
  The same is true of any user-held key under the spec's own §8 honesty
  model (the user could equally re-download public market data). The gate
  binds the PROJECT's evaluation pipeline, not the user's own hands; this
  is already the spec's stated trust boundary.

If the reviewer considers this a deviation rather than an implementation,
the fallback is a versioned specification clarification for approval; no
constitutional test covering the seal will be locked before this issue is
closed either way.

---

## Bundle

`INDEPENDENT_REVIEW_BUNDLE_PHASE6.zip` (committed at repo root) contains
the exact repository files listed in the reviewer's request, a
`BUNDLE_MANIFEST.sha256` covering every bundled file, and
`GIT_STATUS.txt` with the commit hash and clean/dirty state. It contains
no secrets, no age identity, no holdout rows, no market-data rows, no
credentials, and nothing from other repositories (none of which exist in
this project anyway — the raw lake is empty until ingestion is approved).
