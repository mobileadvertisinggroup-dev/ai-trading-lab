# LIMITATIONS — replacement Checkpoint 1 (v3, 2026-08-28)

Supersedes LIMITATIONS_V2.md (preserved). Honest, current statement.

1. **No demonstrated learnability.** Under the corrected v3 statistics
   (exact-multiset rotation permutation; true circular moving-block
   bootstrap): AUC 0.5240 (p_upper 0.478, CI95 [0.460, 0.584]), IC
   0.0288 (p_upper 0.667, CI95 [−0.057, 0.112]); power at the
   pre-registered minimum useful effect 0.283 / 0.048 — UNDERPOWERED:
   the data cannot demonstrate presence OR absence of a useful edge.
   ESS figures are approximations.
2. **No RL management edge.** Mean validation reward across the ten
   preserved seeds is −0.0058; 0/10 seeds beat the Arm A
   conventional-management baseline (+0.0461) on identical episodes and
   reward; 7/10 seeds (including selected seed 4) are non-converged.
   Seed 4 is kept solely because the frozen pre-registered rule selects
   it; its +0.0045 is selection among noise.
3. **Arm B's spec-compliant selection is an honest negative.** The
   TRAIN-only procedure selects 0.50; applied once to validation it
   accepts 8/750 trades with mean −0.334. This is preserved and
   reported as-is; the in-sample nature of train probabilities for the
   frozen booster is a recorded caveat of the mandated procedure.
4. **Arm C top-1 and Arm E M3 are frozen procedure, not skill**: the
   underlying signals remain chance-consistent.
5. **Annualized-Sortino scaling is openly approximate** (sqrt-time under
   independence; trades overlap). The full return series is preserved so
   any replacement scaling is reproducible. DD95 is a bootstrap upper
   95% bound, dependent on the pre-registered block design.
6. **The matched-entry G diagnostic is not a feasible portfolio**
   (capacity checks bypassed by design, over-cap recorded); the feasible
   counterfactual claims no entry identity after state divergence. At
   the v3 shakedown's corrected entry rates (8 G fills) both diagnostics
   were trivially exercised; their discriminating power grows with entry
   volume and remains to be observed at scale.
7. **All shakedowns are permanently INVALID for performance
   conclusions**, including the zero-defect v3 run.
8. **Determinism scope**: seed-deterministic within the pinned
   environment (torch 2.13.0+cu130, CPU); no cross-platform bit claim.
9. **Provenance history**: PROFILE runs from the mutable tree are
   preserved; official results come solely from certified clean-worktree
   runs (v2/v3), with the lake-input addendum active from v3 onward.
10. **Holdout remains sealed**; single-market, single-period scope;
    simulated costs under the frozen model.
