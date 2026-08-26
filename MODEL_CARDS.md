# MODEL CARDS — AKRA AI TRADING LAB (Checkpoint-1 state)

All models are DRAFT-frozen at Checkpoint 1; artifacts + sha256 in
`data/models/model_manifest.json`. Training data: official Arm A labels
(train split only, purge-guarded); features F01-F28 (features-v1-draft).
NO model here has demonstrated skill: the learnability diagnostic is a
recorded null (see LIMITATIONS.md §6). Nothing in this file is a
performance claim.

## Arm B — Filter (`arm_b.txt`)
- LightGBM binary classifier, draft params (100 trees, depth 4, lr 0.05,
  subsample 0.8), target net_r > 0, threshold 0.5 (draft, unsearched).
- Train: 2,089 examples. Validation: AUC 0.533; accept rate 1.1%;
  accepted mean net R −0.334 vs rejected +0.070 (anti-predictive at the
  draft threshold — recorded, not tuned away).
- Known issue: saved booster carries generic feature names; consumers
  MUST bind by `lab.features.build.FEATURE_NAMES` (SD-FEATNAMES).

## Arm C — Ranker (`arm_c.txt`)
- LightGBM regressor on net_r; reported as "ranked i of n", never
  "confidence". Validation rank IC 0.020 (null-consistent).

## Arm D — Regime (rule model, `lab/arms/regime.py`, regime-v1-draft)
- BTC SMA(60/180) trend + trailing-q90 rvol(20) stress; multipliers
  stress .5/.5, up 1/0, down 0/1, sideways .5/.5; insufficient history →
  stress. Not trained; final freeze scheduled pre-Checkpoint-2 (D21).

## Arm E — Sizer (`arm_e.txt` + `arm_e_cuts.npz`)
- LightGBM regressor mapped to buckets {.25,.5,.75,1} by training-
  prediction quartiles (draft mapping; the spec-§3 utility-based mapping
  is a pre-Checkpoint-2 freeze item). Validation bucket means are
  non-monotonic (recorded).

## Arm F — RL manager (`arm_f_policy.npz`, seeds in `arm_f_seeds.json`)
- Deterministic CEM over a linear softmax policy (66 params) on the
  frozen TradeManagementEnv; 10 official seeds; seed 8 frozen by the
  pre-specified highest-mean-validation-reward rule (0.0758).
- DEVIATION FLAGGED: spec §7/§27 default is a documented
  Stable-Baselines3 algorithm; CEM chosen because no deep-RL/torch stack
  is pinned in requirements.txt and full determinism was prioritized —
  submitted for adjudication in the Checkpoint-1 bundle (§7).
- OPEN DEFECT SD-RLOBS: at orchestrator inference the policy receives a
  zero-padded 2-of-10-field observation; Arm F/G management correctness
  is NOT established. Preserved unfixed pending adjudication.

## Arm G — Composite (no artifact of its own)
- Strictly composed from the frozen B/C/E/F artifacts + D rules:
  B filter → C rank cut → min(E, D) × Arm-A size → governor → F manages.
  No G-specific training exists. G-shadow (diagnostic ledger) shares G's
  entries bit-identically and manages conventionally.
