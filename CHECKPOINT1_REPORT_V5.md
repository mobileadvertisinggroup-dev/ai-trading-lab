# REPLACEMENT CHECKPOINT 1 — V5 (D72 funding correction)

Produced under the reviewer's D72 adjudication: the missing-funding
finding is a material scientific defect; V4 remains APPROVED history
(root `0de3c9ab…9fe9`, preserved) but is SUPERSEDED FOR CHECKPOINT-2
ELIGIBILITY. This V5 package replaces the affected portfolio/RL
evidence with funding-corrected results. The holdout was never
accessed; the opening count is zero.

## The defect and the correction (D72 §A)
The seven-arm orchestrator and the RL episode environment never passed
the per-bar funding map to the engine (the engine itself was correct
and funding-tested; the official ArmARunner — candidates and labels —
applied it correctly). A secondary reporting defect read a nonexistent
`amount` field where the engine emits `paid`, so the absence reported
as 0. Corrected:
- `ShakedownCompetition._funding_at` builds the exact ArmARunner
  per-bar map once per bar and passes it to EVERY engine — arms A–G,
  G_matched, G_feasible (`lab/orchestration/competition.py`).
- `TradeManagementEnv` applies per-episode frozen `funding_by_time`
  with prev-close marks; rewards are net of funding per the policy's
  actual holding and reductions (`lab/arms/rl_env.py`).
- Collector fixed (`paid`; `funding_net = −Σ paid`); full
  reconciliation by arm/symbol/side/sign/period + event-to-equity
  identity; the activity guard STOPS implausible all-zero funding over
  active multi-month windows (evaluator fails closed; shakedown flags
  blocking defects).
- Missing rates stay LOUD (`funding_missing`), never imputed.
- Constitutional battery `tests/test_funding_constitutional.py`
  (13 tests) covering all ten directed properties, including exact
  ArmARunner event-stream equality and rollback restoration.
Exact diffs: `readiness/FUNDING_DIFFS_D72.patch`.

## Invalidation and re-execution (D72 §B)
Retained (funding was correct or not involved): dataset/partition,
official Arm A candidates + frozen labels, F01–F28 features,
purge/embargo, learnability (v1–v3), Arm B threshold 0.50, Arm C
top-1, and the fitted B/C/E boosters. Superseded (preserved
unmodified; `readiness/INVALIDATION_LINEAGE_D72.json`): the
no-funding Arm E portfolio selection, the entire no-funding SB3
10-seed family + v1/v2 F reports, shakedowns v1–v4, stress fixture
v4, dashboards v1–v4, and — for CP2 eligibility only — the V4 root.

All re-runs executed under the provenance gate from the clean detached
worktree at `7334e04` (CERTIFIED=True on every record):

1. **Arm E portfolio-utility selection (with funding)** — frozen
   procedure unchanged (Amendment D72 recorded first). Result:
   **M1 again selected**; U_E 0.9872 → **0.9425**; M1 DD95 0.3908 →
   0.3967 ≤ DD95(A) 0.6147; Arm A reference final equity 10,462.96 →
   10,482.94 (funding NET slightly positive for A: short legs and
   negative rates receive). `official_v5/arm_e/`.
2. **Arm F retrained — ALL 10 official seeds** (frozen recipe:
   SB3 2.7.0 PPO, same hyperparameters, budget formula → 149,504
   timesteps/seed at 598.1 SPS, convergence diagnostic, deterministic
   evaluation). Corrected validation rewards, all NEGATIVE: best seed
   3 at −0.0018, worst seed 2 at −0.0116; mean −0.0068; 7/10
   non-converged. **Selected seed: 3** (unchanged frozen rule) —
   replacing superseded no-funding seed 4 (+0.0045).
   `official_v5/models_sb3/` (+ per-seed provenance).
3. **Exact conventional baseline + comparison (with funding)** —
   baseline mean validation reward **+0.05340** (5,253 funding events
   across baseline episodes; vs +0.05399 without funding); **0/10
   corrected seeds beat the exact baseline** (unchanged honest
   negative); per-seed recomputation matches the manifest exactly.
   `official_v5/arm_f/arm_f_statistics_report_v3.json`.
4. **Arm G reconstructed** from the corrected frozen artifacts inside
   the shakedown — composition only, no G-specific training.
5. **Full INVALID shakedown v5** (180d, funding active): zero defects,
   1080/1080 valid rounds; funding applied and event-to-equity
   reconciled in ALL NINE engines (A–G + both diagnostics; e.g. arm A:
   2,270 applied / 806 loud missing / net −2.48); activity guard PASS
   everywhere. **Targeted stress fixture** now includes the nonzero
   funding scenario (positive AND negative rates, one deliberately
   missing symbol): zero defects. `official_v5/shakedown/`,
   `official_v5/stress/`.
6. **Dashboard rebuilt** from the v5 ledgers
   (`docs/dashboard_shakedown_v5.html`).

## Constitutional state
Integrity manifest **v5** (explicit v1→v2→v3→v4→v5 lineage, reason-
keyed changes, refusal of undocumented locked-file changes) and the
replacement **Checkpoint-1 V5 root hash** are recorded in
`data/manifests/integrity_manifest_v5.json` and
`data/manifests/checkpoint1_root_hash_v5.json`; clean-worktree suite
results in the TESTS_RERUN record referenced there. The exact model
manifest a future authorization names is
`data/manifests/model_manifest_v5.json` (D72 §E — no placeholders).

## Honest scientific conclusions (unchanged in direction)
No demonstrated learnability (underpowered); Arm B honest negative;
Arm F 0/10 against the exact conventional baseline, now net of
funding; nothing was retrained or reselected in response to negative
results — the retraining here was the reviewer-directed correction of
a cost-model defect, executed under the unchanged frozen rules.
Holdout results, whenever separately authorized, never authorize
real-money trading.

## STOPPED
At replacement Checkpoint 1 for focused independent review (D72 §B.9).
No return to Checkpoint 2 without your explicit direction; the real
opening count remains zero; no authorization record exists; the
private key was never requested or accepted.
