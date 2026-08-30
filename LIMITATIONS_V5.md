# LIMITATIONS — replacement Checkpoint 1 (v5, 2026-08-30)

Supersedes LIMITATIONS_V4.md (preserved). Honest, current statement
after the D72 funding correction.

1. **A material cost-model defect reached an approved checkpoint.**
   Funding was absent from every seven-arm orchestrator run and from
   RL training/evaluation through V4 — found only at the reviewer's
   pre-authorization reconciliation of an all-zero funding report.
   The correction is mechanical and constitutionally tested, but the
   episode is itself a limitation of the process: a cost term can be
   silently absent while every equity number still "looks right".
   The activity guard now makes that failure loud, everywhere.
2. **No RL management edge — now fully net of funding.** The exact
   frozen conventional manager scores +0.0534 on funding-corrected
   validation episodes; all ten retrained PPO seeds score between
   −0.0116 and −0.0018: **0/10 wins**, and every corrected seed is
   NEGATIVE outright. 7/10 non-converged. Seed 3 is selected purely by
   the frozen rule.
3. **No demonstrated learnability** (unchanged, v3 statistics):
   AUC 0.5240 / IC 0.0288, dependence-aware p_upper 0.478 / 0.667,
   power at the MUE 0.283 / 0.048 — UNDERPOWERED; ESS approximate.
   (Labels always included funding; the learnability record needed no
   correction.)
4. **Arm E's M1 selection is frozen procedure, not skill** — the
   corrected utility (0.9425) still rests on a chance-consistent
   ranking signal; sqrt-annualization of 4h Sortino assumes serial
   independence — an approximation, openly declared.
5. **Funding data coverage is imperfect and stays loud.** In the v5
   shakedown roughly a quarter of funding-boundary crossings had no
   recorded rate at exactly that timestamp in the raw funding layer
   (e.g. arm A: 2,270 applied / 806 missing). The frozen rule refuses
   to impute; missing crossings pay nothing and are individually
   recorded. This understates funding costs for affected symbols —
   a raw-data limitation, mechanically visible per event.
6. **Shakedown remains INVALID for performance conclusions** — it
   overlaps training data and exists to prove mechanics (now including
   funding) end-to-end.
7. **Compute budget**: PPO seeds trained ~149.5k timesteps under the
   pre-registered 4h/10-seed budget — small by RL standards; the
   negative Arm F conclusion is about THIS recipe at THIS budget.
8. **Host constraint**: the Checkpoint-2 resource preflight REFUSES on
   this 16 GiB container at the frozen 1.5x margin; the opening
   requires the key holder's local plan
   (readiness/MAC_LOCAL_EXECUTION_PLAN.md). The D70 resource profile
   predates this correction and will be re-measured before any
   readiness claim.
9. **Forward evidence floor** (unchanged): holdout results never
   authorize real-money trading; the forward paper phase is the only
   genuinely future-unseen evidence.
