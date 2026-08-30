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
2. Constitutional state (SPEC §22 checklist): integrity manifest v7
   hash in `build_state.json` = `b9100883…2412` (V7 — the manifest that describes the evaluator actually executing the holdout, D78); your externally
   preserved APPROVED root = `484f538d…6cf0` (V6, D76) and equals
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
  "protocol_sha256":        "da469dfd0ff2307f4ed30c3c3872b95c0d6468e15b288ce9d3dae6ac16572590",
  "git_commit":             "<git rev-parse HEAD of the commit YOU authorize — verified against the checkout at run time>",
  "dataset_manifest_file":  "lake_manifest_raw-v1.json",
  "dataset_manifest_sha256": "c1ef7262f62b9cbb1cc12b6405ecc21c1898233e8e699c89bd16d31e8e2211ac",
  "model_manifest_file":    "model_manifest_v5.json",
  "model_manifest_sha256":  "5f010c7d83fef9306b97f6458fb2c4c6a1cdf25b454ad3fba4e96fbf5eaf1859",
  "frozen_inputs_manifest_file": "checkpoint2_frozen_inputs.json",
  "frozen_inputs_manifest_sha256": "a9a2aa6c5e9ab9a79839b1086c7f2cdf2f086ce8234f3ed6267e0c5a9a92b01e",
  "integrity_manifest_sha256": "b91008834fdd221677cdb332b74b6b83cd40eb82a84a81d31b19c10fae4a2412",
  "external_root_hash":     "484f538d8b5f9587f2e4ff1f06a061b7aab337b195d6038fdf123d444a886cf0",
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
- `--sb3-dir`: arm_f_sb3_manifest.json, arm_f_sb3_seed3.zip (the funding-corrected selected seed)

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
