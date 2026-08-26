# HOLDOUT_POLICY — AKRA AI TRADING LAB

Implements SPEC_FINAL-1.1.md §8 (honest holdout scope) and §9 (quarantine and
physical seal), plus the user's 2026-08-25 GitHub Actions operating
constraints. Binding on all project code and all operational procedures.

## 1. What is quarantined

The **holdout range**: all timestamps from the quarantine boundary
`Q = boundaries[i_v]` (the decision timestamp of the first holdout round,
per EXPERIMENT_PROTOCOL.md §7) through the eligible-interval end, inclusive
— at **every data layer**: 15m klines, funding rates, universe/eligibility
information, and any derived data for that range. All symbols, including the
BTC context symbol.

## 2. Honest scope (spec §8 disclosure)

These controls prevent project-level and accidental computational access to
the historical holdout before authorization. Because the underlying market
history is public and may be obtainable from external sources, they cannot
prove that a sufficiently privileged or deliberately adversarial builder is
wholly incapable of retrieving equivalent historical information. Mechanical
partitioning, audit logs, restricted project utilities, and the forward test
mitigate this limitation. The historical holdout is unseen by the models,
not necessarily unknown to the builder. The forward paper phase is the only
genuinely future-unseen evidence.

## 3. Storage design (no market data in Git)

Constraint (user, 2026-08-25): raw market data, secrets, and decrypted
holdout data are **never committed to Git**.

| Artifact | Where it lives | In Git? |
|---|---|---|
| Plaintext raw lake (pre-holdout rows only): Parquet, per symbol | GitHub **Release assets** on data releases (tag `raw-v<N>`) | No — only its manifest (paths, sizes, sha256) |
| Encrypted holdout artifact `holdout-v<N>.tar.age` | GitHub Release asset on the same data release | No — only its sha256 and non-outcome metadata |
| Manifests, partition metadata (non-outcome), availability calendars (pre-holdout) | `data/manifests/` in Git | Yes (metadata only) |
| Decrypted holdout data | Nowhere durable. Exists only in memory / tmpfs during the one authorized Checkpoint-2 evaluation; wiped after | **Never** |
| Secrets | GitHub Actions encrypted secrets (least privilege); user-held age identity | Never |

- **Retention**: Release assets persist until deliberately deleted; data
  releases are marked non-draft, non-prerelease and are never overwritten —
  a changed dataset is a NEW release tag (`raw-v2`, …) with a new manifest
  (spec §6 versioning). Intermediate GitHub Actions artifacts (if any) carry
  the minimum retention (1 day) and never contain holdout plaintext.
- **Recovery**: any environment re-downloads the lake from the release by
  manifest and verifies every file's sha256 before use. Full re-ingestion
  from the primary source is the second recovery path and must reproduce
  identical content hashes for the same frozen range (or the discrepancy is
  investigated and recorded — never papered over).
- **Immutability model (honest statement)**: GitHub releases are, by
  default, mutable by repository administrators; whether the repository's
  platform-level immutable-releases setting is enabled is verified and
  evidenced at ingestion time (review issue C). The layer this project
  RELIES on is tamper-evidence, not platform immutability: every asset's
  sha256 is pinned in git-committed manifests (`SHA256SUMS` + the lake
  manifest), so any later modification of a release asset is detected by
  the mandatory hash verification on download, and the audit trail lives
  in git history. The workflow refuses to reuse an existing tag (new data
  = new version), publishes draft → upload-all → publish so partial
  uploads are never visible, and project code treats the lake as
  read-only after ingestion. Recovery from administrator deletion:
  re-ingestion from the primary source must reproduce identical content
  hashes for the same frozen range, or the discrepancy is investigated
  and recorded.

## 4. Seal mechanics

1. Ingestion (GitHub Actions, §6 below) downloads the full eligible range to
   the runner's **temporary** storage only.
2. The **sealing utility** (`lab/data/seal.py`) mechanically splits every
   file at the quarantine boundary Q: rows `< Q` go to the plaintext lake;
   rows `≥ Q` pass **directly** through to an in-memory/temp tar that is
   immediately encrypted. Pass-through is mechanical; nothing from the
   holdout range is displayed, printed, logged, summarized, or written to
   any durable plaintext location (spec §9.1–9.4).
3. Encryption: **age** (X25519, via `pyrage`) to the **user's age public
   key** (recipient). The user generates the identity locally
   (`age-keygen`), keeps the private identity, and provides only the public
   key (`age1…`), which is committed as `data/manifests/holdout_recipient.txt`
   (public keys are not secrets). Consequences:
   - Sealing runs fully non-interactively (public-key encryption).
   - **The user alone can decrypt.** The passphrase/identity never exists in
     the repository, environment, logs, shell history, database, build
     artifacts, or agent context (spec §9 seal mechanics 2–4).
4. Produced artifacts: encrypted `holdout-v<N>.tar.age`, its sha256,
   non-outcome partition metadata (boundary timestamps, round indices/counts,
   file inventory of the sealed tar — names/row-counts/hashes only, no
   values), encryption documentation (this file), a verification command
   (`python -m lab.data.verify`), and the decryption audit log.
5. The decrypted holdout is never written back into the ordinary raw lake
   (spec §9.8) and never uploaded anywhere.

## 4a. Acquisition staging (PC-1 protections; review verdict §4)

The sealing pipeline's acquisition staging — the ephemeral runner storage
holding the complete source stream before the split-and-seal — is governed
by these binding protections regardless of PC-1's approval status:

1. Lives only in `RUNNER_TEMP`, outside the repository checkout: it can
   never be committed to Git.
2. Inaccessible to model training, validation, dashboard, and ordinary
   diagnostic code (none of which run in the ingestion job; the readable
   lake is the only thing they ever see, via GuardedLake).
3. No display of holdout values, rows, summaries, or outcomes;
   metadata-only logs (counts, names, hashes).
4. Never uploaded as an ordinary Actions artifact; never cached between
   runs.
5. Destroyed immediately after successful sealing or on failure, by an
   `always()` workflow step that FAILS the run if the staging directories
   still exist after removal (verified destruction).
6. Only pre-holdout data enters the readable lake; holdout data goes
   directly from staging into the encrypted seal.

The corresponding protocol wording change is PROPOSED_CLARIFICATION_PC1.md,
awaiting explicit user approval; real ingestion is prohibited until then.

## 5. Access refusal layer

- **All** project data reads go through `lab.data.access.GuardedLake`. Raw
  Parquet paths are internal to it; ingestion, training, validation,
  dashboard, and diagnostic code use it exclusively.
- Any read, download, backfill, or diagnostic request whose time range
  intersects the holdout range — exact range, partial overlap, single
  timestamps, any symbol, klines or funding or universe/metadata — is
  **refused** (`HoldoutAccessError`) unless a valid Checkpoint-2
  authorization record exists.
- Every refusal is appended to the immutable audit log
  `data/manifests/access_audit.jsonl` (append-only; entries hash-chained to
  the previous entry). A premature-access attempt is a critical integrity
  failure and is reported, not retried (spec §9.6).
- Constitutional tests (locked before shakedown) verify refusal for: the
  exact range, partial overlaps, individual holdout timestamps, alternate
  symbols, funding queries, and universe/metadata queries (spec §9.6).

## 6. GitHub Actions operating rules (user constraints, 2026-08-25)

1. Ingestion and forward paper operation may run on GitHub Actions;
   everything is **paper-only** — no real-money endpoint, no order-placing
   credential is ever configured.
2. Actions logs must never contain holdout rows, values, or summaries.
   Ingestion logging for the holdout range is restricted to counts, file
   names, and hashes. Log statements in sealing code are the only code
   allowed to touch holdout data, and they log metadata only.
3. No raw market data, secret, or decrypted holdout data is committed to
   Git; encrypted holdout and plaintext pre-holdout lake go to Release
   assets only (§3).
4. Decrypted holdout data is never uploaded as an artifact of any kind.
5. Workflow permissions are least-privilege (`contents: write` only where
   release upload requires it; nothing else). Public market data needs no
   API secret; if any secret is ever added it is scoped to the single
   workflow that needs it.
6. Checkpoint-2 holdout evaluation does **not** run on GitHub Actions: the
   user supplies the age identity interactively in a controlled session
   (spec §9 seal mechanics 4); CI is non-interactive by definition and must
   never hold the identity.

## 7. Decryption gate (Checkpoint 2)

COMPLETED per the delta review correction B (`lab/data/unseal.py` +
`lab/data/authz.py` + `lab/data/holdout_ledger.py`): there is NO
general-purpose decrypt operation — the single sanctioned path is the
controlled one-time evaluation `evaluate_holdout`, which additionally to
the gate below: resolves the exact holdout artifact FILENAME and SHA-256
from the approved dataset manifest and refuses any supplied artifact whose
basename or recomputed hash differs; records an append-only hash-chained
OPENING_STARTED event before decryption; decrypts only into a fresh
protected tmpfs directory (pre-existing directories and any path inside
the project tree are refused); runs the exact frozen holdout evaluator
(a deterministic dummy until the real frozen evaluator exists — the gate
is NOT declared implementation-complete until it is plugged in); exports
only the evaluator's returned result ledgers; wipes decrypted material on
success AND failure with verified absence; records CONSUMED or
FAILED_CLOSED in the chained state ledger (`holdout_state.jsonl`) —
consumption is established by that LEDGER, never by rewriting the
authorization JSON, which remains an input record only; and refuses any
second opening unless a formal integrity adjudication records
RECOVERY_AUTHORIZED. A corrupted state ledger blocks all holdout access
(fail closed). Negative-tested: wrong/renamed/tampered artifact, second
opening, cleanup on both evaluator outcomes with residue checks,
pre-existing output directory, corrupted chain (tests/test_holdout_gate.py).

Underlying gate (unchanged): decryption refuses unless ALL of the following match EXACTLY against
independently recomputed current values — protocol hash (recomputed from
EXPERIMENT_PROTOCOL.md), current Git commit (`git rev-parse HEAD`), dataset
manifest hash (of the named manifest file), model manifest hash, locked
integrity-test manifest hash (from build_state.json), the user's most
recently approved externally preserved root hash (from build_state.json),
plus a recorded, non-consumed Checkpoint-2 authorization. An authorization
record with fabricated or merely nonempty hashes can never grant access —
negative-tested at both the read layer and the unseal gate
(tests/test_authz_negative.py; becomes a locked constitutional test). The
identity is accepted only via interactive TTY prompt (never argv, env,
or file path; never stored; held in memory for the single decryption).
Decrypted output is refused inside the project tree or lake (default
/dev/shm). Every attempt — refused or authorized — is appended to the
hash-chained audit log; consumption is recorded immutably WITHOUT the key;
after the single authorized evaluation the temporary material is wiped.
