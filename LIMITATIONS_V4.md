# LIMITATIONS — replacement Checkpoint 1 (v4, 2026-08-28)

Supersedes LIMITATIONS_V3.md (preserved). Honest, current statement.

1. **No RL management edge — now against the true bar.** The exact
   frozen conventional manager scores +0.0540 on the validation
   episodes; all ten PPO seeds score between −0.0160 and +0.0045:
   **0/10 wins**. 7/10 seeds (including preserved seed 4) are
   non-converged. Seed 4 is retained purely by the frozen rule.
2. **No demonstrated learnability** (unchanged, v3 statistics):
   AUC 0.5240 / IC 0.0288, dependence-aware p_upper 0.478 / 0.667,
   power at the MUE 0.283 / 0.048 — UNDERPOWERED; ESS approximate.
3. **Arm E's M1 selection is frozen procedure, not skill.** The
   portfolio utility now measures real decimal drawdowns (MDD 0.18–
   0.36; DD95 0.34–0.61) and time-series Sortino, but the underlying
   ranking signal remains chance-consistent; the M1-vs-M3 ordering is
   a property of this validation window and the frozen formula. The
   sqrt-annualization of 4h Sortino assumes serial independence of 4h
   returns — an approximation, openly declared.
4. **Portfolio-utility scope**: mappings were compared from a common
   fresh account over the validation window only; DD95 depends on the
   pre-registered block design (L=168, 1000 resamples); a different
   dependence model would move the bounds.
5. **B's spec-compliant selection remains an honest negative**
   (train-only 0.50 → 8/750 validation accepts, mean −0.334).
6. **Diagnostics scope**: the matched shadow is not a feasible
   portfolio (over-cap by design, recorded); the feasible
   counterfactual claims no entry identity after state divergence. The
   stress fixture exercises both at synthetic scale; production-scale
   discriminating power grows with entry volume.
7. **All shakedowns and the stress fixture are permanently INVALID for
   performance conclusions.**
8. **Determinism scope**: seed-deterministic within the pinned
   environment (torch 2.13.0+cu130, CPU); no cross-platform bit claim.
9. **Provenance**: official results come solely from certified
   clean-worktree runs under the gate (lake addendum active); PROFILE
   histories preserved.
10. **Holdout sealed; single market and period; simulated costs.**
