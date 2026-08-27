# INVALID — CEM Arm F artifacts (preserved history, never for use)

These artifacts (`arm_f_policy.npz`, `arm_f_seeds.json`, and the
`arm_f` / `arm_f_compute_profile` sections of `../models/model_manifest.json`)
were trained by the self-contained CEM trainer and are **INVALID** per the
independent Checkpoint-1 adjudication (blocker 1: algorithm not the
approved pinned-library path; blocker 2: trained against pre-obs-v2
observations later shown non-parity with inference, SD-RLOBS).

They are preserved unmodified as historical evidence — the adjudication
prohibits deletion or rewriting of prior evidence. The replacement Arm F
is the Stable-Baselines3 PPO artifact trained per
`PREREGISTRATION_ARM_F_SB3.md` (committed before any SB3 training output
existed).
