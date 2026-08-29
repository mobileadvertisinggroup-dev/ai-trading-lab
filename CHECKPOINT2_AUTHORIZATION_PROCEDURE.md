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
  "frozen_inputs_manifest_file": "checkpoint2_frozen_inputs.json",
  "frozen_inputs_manifest_sha256": "<sha256 of data/manifests/checkpoint2_frozen_inputs.json — currently edb0806d43d4d96ce7cfb228eec37a699365f80f513226841279f0d20d8bddc6>",
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
Requirements: Linux with tmpfs (`/dev/shm`), NO active swap (the gate's
resource preflight refuses if `/proc/swaps` lists any device — tmpfs
pages must never be able to reach persistent storage), python env with
the pinned requirements, `pyrage`, the verified pre-holdout lake, the
frozen model artifacts, and the downloaded `holdout-raw-v1.tar.age`
(the gate verifies its exact basename and sha256 against the approved
manifest — 791,233,451 bytes, sha256 47795aa6…067).

Stage the frozen artifacts in TWO dedicated directories containing
EXACTLY the pinned files and nothing else (strict census — an
additional file refuses):
- `--model-dir`: arm_b.txt, arm_c.txt, arm_e.txt, arm_e_cuts.npz,
  bc_train_selection.json, arm_e_portfolio_selection.json
- `--sb3-dir`: arm_f_sb3_manifest.json, arm_f_sb3_seed4.zip

```
python3 -m lab.data.unseal \
  --artifact  /path/to/holdout-raw-v1.tar.age \
  --manifests-dir data/manifests \
  --pre-lake  /path/to/verified/lake \
  --model-dir /path/to/frozen/models \
  --sb3-dir   /path/to/frozen/models_sb3 \
  --results   /path/outside/repo/checkpoint2_results.json
```

What the gate then does, in order (D69 blockers 2/4/5). EVERYTHING
that can be checked without the holdout runs BEFORE the claim — a
failure there refuses and the opening is NOT spent:
1. verifies the authorization record strictly (recomputed hashes) and
   the hash-chained state ledger (corrupt chain blocks);
2. verifies the artifact's exact manifest-bound name and sha256;
3. verifies EVERY frozen input against checkpoint2_frozen_inputs.json
   (itself hash-bound to your authorization): governing docs,
   dataset/partition manifests, the frozen recipient, and the staged
   model/sb3 files under strict census — missing, additional,
   substituted, symlinked, or path-escaping inputs refuse;
4. verifies the output directory is fresh, outside the repository, on
   verified tmpfs/ramfs;
5. prompts YOU for the age identity on the TTY (never echoed, never
   stored), parses it, and VERIFIES its derived public key equals the
   frozen recipient (data/manifests/holdout_recipient.txt) — a
   mistyped or wrong key refuses HERE, with the opening still unspent;
6. runs the resource preflight: ciphertext size, tmpfs capacity,
   available RAM, no-swap, results-directory capacity, expected peak
   from the measured surrogate profile, 1.5x margin;
7. only now atomically CLAIMS the single opening (OS lock + chain
   verify + no-prior-opening + fsync) — from here the opening is
   spent; any later failure is FAILED_CLOSED;
8. STREAM-decrypts (pyrage.decrypt_io, bounded memory) into the
   verified tmpfs, stream-extracts, and chunk-wipes the intermediate
   tar before evaluation;
9. runs the FROZEN evaluator once (seven arms + both G diagnostics,
   frozen statistics of the pre-registration);
10. writes the results FIRST to a protected temp file (mode 0600,
    fsync) next to your chosen results path;
11. chunk-wipes ALL decrypted material and VERIFIES its absence —
    cleanup failure ⇒ FAILED_CLOSED, temp results removed, no success
    reported;
12. only after verified cleanup: atomically publishes the results
    (rename) and appends CONSUMED. If the CONSUMED append fails, the
    published results are removed again and the run reports failure —
    success is never represented with a failed ledger.

Crash containment: a hard crash (power loss, kill -9) between steps 7
and 12 leaves OPENING_STARTED as the last ledger event (the opening is
permanently spent) and possibly decrypted material on the tmpfs.
Because it is memory-backed it vanishes on power-off; otherwise remove
the `/dev/shm/akra-holdout-eval-*` tree, verify absence, and report.
Do not re-run; recovery is not self-authorizing.

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
