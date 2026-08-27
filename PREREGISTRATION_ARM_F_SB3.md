# PRE-REGISTRATION — Arm F (Stable-Baselines3), adjudication blocker 1

Committed BEFORE any SB3 training run exists or any result is viewed.
Everything below is fixed now; deviations require a documented amendment.

## Algorithm (single, no comparison)
- **PPO** from stable-baselines3 **2.7.0** (torch 2.13.0, CPU), policy
  `MlpPolicy`. Chosen ex ante as SB3's canonical, most-documented
  algorithm, robust on a small discrete action space (6 actions, 10-dim
  observation) without replay-buffer tuning. NO other algorithm or
  configuration will be trained or compared; if PPO fails mechanically,
  the failure is reported — never silently swapped.

## Hyperparameters (SB3 2.7.0 defaults except as listed)
- `n_steps=512`, `batch_size=128`, `gamma=1.0` (episodic terminal reward,
  undiscounted by design of the frozen reward), `device="cpu"`,
  `seed=<official seed>`; all else = SB3 2.7.0 PPO defaults.
- Official seeds: **1..10** (all trained; none discarded).

## Environment
- `TradeManagementEnv` (obs-v2, canonical builder, parity-proven) wrapped
  in a deterministic episode cycler: episodes ordered by (t, symbol),
  cycled in fixed order; `DummyVecEnv` of 1. Training episodes = the
  purged TRAIN split only, built from the OFFICIAL Arm A ledgers with the
  recorded exposure series and frozen ATR series.

## Compute budget + timesteps formula (fixed before measurement)
- Budget: <= 4 h wall for all 10 seeds on 4 CPU cores.
- Profile first: measure steps/second over a 2,048-timestep probe run
  (seed 0, discarded, never evaluated).
- `total_timesteps_per_seed = min(150_000, floor(0.9 * (4h/10) * sps))`,
  rounded down to a multiple of `n_steps`. The measured sps and resulting
  figure are recorded before seed 1 trains.

## Convergence criterion (diagnostic, not selection)
- Per seed, episode-reward moving average (window 50). Flag
  `non_converged` if the final MA < the seed's median MA over its last
  25% of training. Flags are reported; they do not alter selection.

## Evaluation procedure
- Deterministic policy (`deterministic=True`), one pass over ALL train
  episodes and ALL validation episodes; metric = mean terminal reward
  (identical to the invalidated CEM evaluation, unchanged).

## Seed-selection rule
- The official Arm F policy = the seed with the **highest mean VALIDATION
  reward**; ties broken by the LOWER seed number. All 10 seeds' artifacts,
  histories, and scores are preserved.

## Determinism statement (honest)
- Runs are seed-deterministic within this pinned environment
  (torch 2.13.0 CPU, single build). Cross-platform bit determinism is NOT
  claimed for torch; the pinned environment + recorded seeds + saved
  artifacts are the reproducibility basis.

## Invalidation
- Every CEM artifact (`arm_f_policy.npz`, `arm_f_seeds.json`, the CEM
  section of `model_manifest.json`) is INVALID as of this document and is
  preserved under `data/models_invalid_cem/` as history. Arm G will be
  regenerated from the SB3 artifact; G receives no training of its own.
