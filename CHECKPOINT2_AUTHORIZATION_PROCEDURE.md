# CHECKPOINT-2 AUTHORIZATION & ONE-TIME HOLDOUT OPENING PROCEDURE

Prepared as pre-Checkpoint-2 readiness (D66 directive). **Nothing in
this document opens anything.** The holdout remains sealed until YOU
(the reviewer/key holder) complete every step below yourself. The
private key is never requested by, sent to, or stored in this project;
it is entered interactively on your local terminal, once.

## 0. What you are authorizing
Exactly one execution of the FROZEN evaluation plan
(`PREREGISTRATION_CHECKPOINT2_EVALUATION.md`) over the sealed holdout,
through the fail-closed gate (`lab/data/unseal.py`). One opening —
success or failure — permanently consumes it (append-only hash-chained
ledger; recovery is not self-authorizing).

## 1. Before authorizing, verify independently
1. The repository at the commit you will authorize:
   `git status --porcelain` empty; `git rev-parse HEAD` = the commit in
   your authorization file (step 2).
2. Constitutional state (SPEC §22 checklist): integrity manifest v4
   hash in `build_state.json` = `ee518f08…686e`; your externally
   preserved APPROVED root = `0de3c9ab…9fe9` and equals
   `build_state.json .approved_external_root_hash`.
3. Full suite green from a clean worktree: `python3 -m pytest -q`.
4. Confirmation that no holdout access has occurred:
   `data/manifests/holdout_state.jsonl` absent or contains NO
   `OPENING_STARTED`; `access_audit.jsonl` shows only REFUSED entries.
5. The frozen plan says what you expect it to say — read
   `PREREGISTRATION_CHECKPOINT2_EVALUATION.md` in full.

## 2. The authorization record (created BY YOU, only when satisfied)
Create `data/manifests/checkpoint2_authorization.json`:

```json
{
  "user_authorization_utc": "<UTC timestamp when YOU authorize>",
  "protocol_sha256":        "<sha256 of EXPERIMENT_PROTOCOL.md — currently da469dfd0ff2307f4ed30c3c3872b95c0d6468e15b288ce9d3dae6ac16572590>",
  "git_commit":             "<git rev-parse HEAD of the authorized commit>",
  "dataset_manifest_file":  "lake_manifest_raw-v1.json",
  "dataset_manifest_sha256": "<sha256 of data/manifests/lake_manifest_raw-v1.json>",
  "model_manifest_file":    "<the frozen model manifest file in data/manifests you authorize>",
  "model_manifest_sha256":  "<its sha256>",
  "integrity_manifest_sha256": "<build_state.json .integrity_manifest_hash (v4: ee518f082580e2e4a342cb17a242226e6fc03a824643c74f2dd4cb47f0cb686e)>",
  "external_root_hash":     "0de3c9ab4dd1b0bc4e774d10550ffe3e1fc2a972173d780cb28484bdeb469fe9",
  "consumed": false
}
```

Every hash is RE-VERIFIED by the gate against independently recomputed
values at run time; a stale or fabricated value refuses (and the
refusal is immutably audit-logged). The file is an input record only —
consumption is established by the ledger, never by editing this JSON.

## 3. The one-time opening (run LOCALLY by you)
Requirements: Linux with tmpfs (`/dev/shm`), python env with the pinned
requirements, `pyrage`, the verified pre-holdout lake, the frozen
model artifacts, and the downloaded `holdout-raw-v1.tar.age` (the gate
verifies its exact basename and sha256 against the approved manifest —
791,233,451 bytes, sha256 47795aa6…067).

```
python3 -m lab.data.unseal \
  --artifact  /path/to/holdout-raw-v1.tar.age \
  --manifests-dir data/manifests \
  --pre-lake  /path/to/verified/lake \
  --model-dir /path/to/frozen/models \
  --sb3-dir   /path/to/frozen/models_sb3 \
  --results   /path/outside/repo/checkpoint2_results.json
```

What the gate then does, in order (any failure ⇒ FAILED_CLOSED, the
opening stays spent, the holdout stays blocked):
1. verifies the authorization record strictly (recomputed hashes) and
   the hash-chained state ledger (corrupt chain blocks);
2. verifies the artifact's exact manifest-bound name and sha256;
3. atomically CLAIMS the single opening (OS lock + chain verify +
   no-prior-opening + fsync) — from here the opening is spent;
4. prompts YOU for the age identity on the TTY (never echoed, never
   stored, deleted from memory after parsing);
5. decrypts only into a fresh, verified tmpfs/ramfs directory outside
   the repository;
6. runs the FROZEN evaluator once (seven arms + both G diagnostics,
   frozen statistics of the pre-registration);
7. writes ONLY the results JSON (ledgers + statistics; no raw rows);
8. wipes the decrypted material and VERIFIES its absence;
9. appends CONSUMED (or FAILED_CLOSED) to the chained ledger.

## 4. After the run
Commit (append-only): the results JSON's sha256, the updated
`holdout_state.jsonl`, and the audit log — then STOP for your
Checkpoint-2 adjudication of the results. The frozen success criteria,
Holm correction, drawdown constraint, and the
INSUFFICIENT-LEARNABLE-VARIATION rule are applied exactly as
pre-registered; negative results are preserved as-is; nothing is
retrained or reselected in response to holdout outcomes. Holdout
results never authorize real-money trading (forward evidence floor).

## 5. Explicit non-actions by the assistant
The assistant will not: create the authorization record, ask for or
accept the key, download/decrypt/inspect/summarize/evaluate the
holdout, or run any part of step 3. Those acts are yours alone, after
your separate explicit authorization.
