# CHECKPOINT-2 AUTHORIZATION CARD — pre-claim operational preflight

Generated 2026-08-30 on the rehearsal host (the remote container that
ran every official job and the dress rehearsal). Read-only: nothing was
decrypted, no key was prompted for or accepted, no opening was claimed,
no authorization file was created. **Bottom line: NOT READY TO
AUTHORIZE — one scientific blocker (funding, verdict C below) and one
operational refusal (RAM margin on this host).**

## 1–2. Checkout
1. Git commit that would be authorized (current HEAD):
   `e81fbf2353fef2f479ebf5fc37f420d032ca226f`
   (necessarily provisional: the funding blocker below requires a fix
   commit, which will move HEAD and this card).
2. Checkout clean: `git status --porcelain` output is EMPTY at that
   commit (verified immediately before the preflight run).

## 3–7. Exact input identities (no placeholders)
3. Model manifest: `model_manifest.json`, sha256
   `dfc6ac37035b1387706ea3c722abd86447d861a89ccb37c7a5d7d810d3c50ca9`.
   ⚠ OPERATIONAL GAP: this file currently lives at
   `data/models/model_manifest.json`; the gate resolves
   `model_manifest_file` inside `data/manifests/`. It must be committed
   into `data/manifests/` (byte-identical) before the real
   authorization. Flagged, not silently done.
4. Dataset manifest: `lake_manifest_raw-v1.json`, sha256
   `c1ef7262f62b9cbb1cc12b6405ecc21c1898233e8e699c89bd16d31e8e2211ac`.
5. Frozen-input manifest: `checkpoint2_frozen_inputs.json`, sha256
   `edb0806d43d4d96ce7cfb228eec37a699365f80f513226841279f0d20d8bddc6`.
6. Protocol sha256
   `da469dfd0ff2307f4ed30c3c3872b95c0d6468e15b288ce9d3dae6ac16572590`;
   integrity-manifest (v4)
   `ee518f082580e2e4a342cb17a242226e6fc03a824643c74f2dd4cb47f0cb686e`;
   approved external root (v4)
   `0de3c9ab4dd1b0bc4e774d10550ffe3e1fc2a972173d780cb28484bdeb469fe9`.
7. Holdout ciphertext: `holdout-raw-v1.tar.age`, 791,233,451 bytes,
   sha256 RECOMPUTED locally on this host:
   `47795aa6a9775e6f191def5c121212c00642eb666daf3cb8df46bf3a495a1067`
   (exact match to the approved dataset manifest and the release-asset
   digest). The ciphertext was downloaded from the raw-v1 release to
   `/home/user/lake-work/holdout-raw-v1.tar.age` for hash recomputation
   only — bytes were read for SHA-256, never parsed or decrypted.

## 8–12. Host state immediately before the preflight computation
8. MemAvailable: 16,198,455,296 bytes (15.09 GiB).
9. MemTotal: 16,856,133,632 bytes (15.70 GiB).
10. tmpfs: mount `/dev/shm`, fstype `tmpfs`
    (`rw,relatime,size=16461068k`), total 16,856,133,632 bytes,
    available 16,856,133,632 bytes.
11. `/proc/swaps`: ZERO active entries (header only). Confirmed.
12. Results directory (`/home/user/lake-work/`): 19,766,849,536 bytes
    available.

## 13–15. preflight_resources on the REAL artifact and production paths
Inputs: artifact `/home/user/lake-work/holdout-raw-v1.tar.age`,
out_dir `/dev/shm/akra-holdout-eval-<pid>` (probe path, never
created), results `/home/user/lake-work/checkpoint2_results.json`,
manifests `data/manifests` (with the measured surrogate profile).

Complete report — basis: surrogate profile, scale 1.570
(= 791,233,451 / 503,828,856 ciphertext bytes), margin 1.5x:

| quantity | bytes |
|---|---|
| ciphertext | 791,233,451 |
| decrypted-tar estimate | 791,233,451 |
| extracted estimate | 791,233,451 |
| tmpfs peak estimate | 1,582,466,902 |
| evaluator peak RSS estimate (scaled from measured 7,777,550,336) | 12,214,183,287 |
| total RAM demand (RSS + tmpfs) | 13,796,650,189 |
| results estimate | 68,731,188 |
| MemAvailable | 16,198,455,296 |
| tmpfs free | 16,856,133,632 |
| results-dir free | 19,766,849,536 |

14. Per-check verdicts:
    - tmpfs_capacity: **PASS** (16.86 GB free ≥ 1.5 × 1.58 GB)
    - ram_available: **REFUSE** (1.5 × 13.80 GB = 20.69 GB > 16.20 GB)
    - results_capacity: **PASS** (19.77 GB ≥ 1.5 × 68.7 MB)
    - no_swap: **PASS** (zero entries)
    - **Overall: REFUSE** — the gate would refuse pre-claim on this
      host; the opening would NOT be spent.
15. Margin confirmation: the required margin is 1.5x and is ENFORCED;
    at 1.5x the expected real-run demand is NOT covered on this host
    (raw demand 13.80 GB < 16.20 GB available, i.e. covered only at
    ~1.17x). The RSS scaling is linear in ciphertext size and therefore
    conservative (the pre-holdout lake portion of memory does not
    grow), but the frozen preflight uses it. Remediation: run the real
    evaluation on a host with ≥ 32 GiB MemAvailable (and re-generate
    this card there), or adjudicate an explicit change; no change is
    proposed unilaterally.

## 16–18. Safety confirmations
16. `data/manifests/checkpoint2_authorization.json` does NOT exist.
17. `data/manifests/holdout_state.jsonl` does NOT exist — therefore
    zero `OPENING_STARTED` entries; the real opening count is ZERO.
18. This preflight did NOT parse or decrypt the artifact (SHA-256 over
    raw bytes only), did NOT prompt for or accept any key, and did NOT
    claim an opening; the probe out_dir was never created.

## 19. Proposed authorization record (PRINTED ONLY — file NOT created)
Valid only for commit `e81fbf2…` and only after items 3 (manifest
staging) and the funding blocker are resolved — both will move HEAD,
so the hashes below that change (git_commit, frozen-input manifest if
regenerated) must be refreshed from the successor card.

```json
{
  "user_authorization_utc": "<set by the key holder at signing, e.g. 2026-09-02T00:00:00Z>",
  "protocol_sha256": "da469dfd0ff2307f4ed30c3c3872b95c0d6468e15b288ce9d3dae6ac16572590",
  "git_commit": "e81fbf2353fef2f479ebf5fc37f420d032ca226f",
  "dataset_manifest_file": "lake_manifest_raw-v1.json",
  "dataset_manifest_sha256": "c1ef7262f62b9cbb1cc12b6405ecc21c1898233e8e699c89bd16d31e8e2211ac",
  "model_manifest_file": "model_manifest.json",
  "model_manifest_sha256": "dfc6ac37035b1387706ea3c722abd86447d861a89ccb37c7a5d7d810d3c50ca9",
  "frozen_inputs_manifest_file": "checkpoint2_frozen_inputs.json",
  "frozen_inputs_manifest_sha256": "edb0806d43d4d96ce7cfb228eec37a699365f80f513226841279f0d20d8bddc6",
  "integrity_manifest_sha256": "ee518f082580e2e4a342cb17a242226e6fc03a824643c74f2dd4cb47f0cb686e",
  "external_root_hash": "0de3c9ab4dd1b0bc4e774d10550ffe3e1fc2a972173d780cb28484bdeb469fe9",
  "consumed": false
}
```

## 20. Exact production command (NOT run)
```
python3 -m lab.data.unseal \
  --artifact  /home/user/lake-work/holdout-raw-v1.tar.age \
  --manifests-dir /home/user/ai-trading-lab/data/manifests \
  --pre-lake  /home/user/lake-work/lake \
  --model-dir /home/user/lake-work/stage/models \
  --sb3-dir   /home/user/lake-work/stage/models_sb3 \
  --results   /home/user/lake-work/checkpoint2_results.json \
  --repo-root /home/user/ai-trading-lab
```
(`stage/models` = exactly arm_b.txt, arm_c.txt, arm_e.txt,
arm_e_cuts.npz, bc_train_selection.json, arm_e_portfolio_selection.json;
`stage/models_sb3` = exactly arm_f_sb3_manifest.json,
arm_f_sb3_seed4.zip — strict census. These staging dirs do not exist
yet; creating them is a pre-run step for the key holder.)

---

# FUNDING RECONCILIATION — VERDICT: C (with a subsidiary B). STOPPED.

**funding_net = 0 for every arm is NOT legitimate. Funding was not
applied in the seven-arm orchestrator. This is a scientific blocker;
no code was changed.**

Evidence, established mechanically:
- Option A is FALSE: the surrogate window contains funding data (the
  overlay carries funding files; the same window's OFFICIAL Arm A run
  applied funding to labels), and the surrogate Arm A ledger contains
  **7,384 `funding_missing` events and 0 `funding` events** — open
  positions reached funding boundaries and found no rate supplied.
- Verdict C (primary): `lab/orchestration/competition.py` calls
  `engine.process_bar_time(t, bars, prev_close=…)` at both call sites
  (lines 547–553) WITHOUT the `funding=` argument; the engine then
  receives an empty dict and emits `funding_missing` for every open
  position. Funding never touched cash or equity in any
  ShakedownCompetition run.
- Verdict B (subsidiary, also true): the reporting collector sums
  `e.get("amount", 0.0)` for `kind == "funding"` events, but the
  engine emits the field as **`paid`** — so even correctly applied
  funding would have been reported as 0. (My blocker-3 unit test used
  the same wrong field name, which is why it passed; it must be
  corrected together with the collector.)
- Correct reference implementation exists: `lab/arms/arm_a.py`
  (ArmARunner, lines 230–236) builds the per-bar `{symbol: rate}` map
  and passes it — the engine itself handles funding correctly
  (`cash -= transfer`, `p.funding_paid += transfer`, unit-tested).

Scope of impact (what consumed funding-free equity/nets):
- AFFECTED: every ShakedownCompetition run — shakedowns v1–v4, the
  targeted stress fixture, the **approved Arm E portfolio-utility
  selection (M1)**, both G diagnostics, the frozen Checkpoint-2
  evaluator, and the D70 surrogate dress rehearsal (its resource
  profile remains valid — it measures capacity, not returns).
- AFFECTED (internally consistent): the Arm F episode environment
  (`lab/arms/rl_env.py` also omits `funding=`), so SB3 training
  rewards and the 10-seed comparison were funding-free on BOTH sides
  (policy and exact conventional baseline) — a like-for-like
  comparison, but not "after all costs".
- NOT affected: the official Arm A candidate generation and the frozen
  train/validation LABELS (ArmARunner applied funding correctly), and
  therefore the B threshold-0.50 selection, C top-1 selection, and the
  learnability results, which operate on those labels.

Why this blocks Checkpoint 2: the pre-registered primary statistic is
net risk-adjusted return "after all costs"; funding is an explicit
cost in the spec's tiered cost model. Running the holdout with the
current orchestrator would evaluate funding-free equity while
reporting it as after-all-costs.

Proposed correction path (NOT executed — awaiting your direction):
1. Wire the per-bar funding map in `ShakedownCompetition` (same
   construction as ArmARunner) for the seven arms and both
   diagnostics, and in `rl_env.py` for episode replay (inference-time
   accounting only — no retraining).
2. Fix the collector field (`paid`, and count `funding_missing` as a
   loud validation failure when funding data exists), plus the unit
   test that encoded the same mistake.
3. Add a constitutional test: a position held across a funding
   boundary in the orchestrator changes equity by exactly
   rate × qty × mark × side.
4. Re-run the affected non-holdout evidence from a clean worktree
   (at minimum the Arm E portfolio-utility selection; the Arm F
   comparison and shakedown/stress reruns per your scoping), preserve
   all superseded results as history, and report deltas before any
   authorization.

**STOPPED. No authorization should be granted against commit
e81fbf2…; awaiting your adjudication of the funding blocker, the
model-manifest staging step, and the RAM-margin remediation.**
