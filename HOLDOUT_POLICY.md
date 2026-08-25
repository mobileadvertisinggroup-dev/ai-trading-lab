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
- **Immutability**: project code treats the lake as read-only after
  ingestion; the manifest hash pins the exact bytes. The ingestion workflow
  is the only writer, and it only ever creates new versions.

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

`lab.data.unseal` refuses to decrypt unless ALL of the following match
(spec §9): approved protocol hash; current Git commit; dataset manifest
hash; model manifest hash; integrity-test manifest hash; the user's most
recently approved externally preserved manifest root hash; and a recorded
Checkpoint-2 authorization. The identity is accepted only via interactive
prompt (never argv, never env-persisted, never files). Every decryption
attempt — refused or authorized — is appended to the audit log. After the
single authorized evaluation, the holdout is marked permanently consumed;
temporary decrypted material is wiped.
