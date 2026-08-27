# LIMITATIONS — replacement Checkpoint 1 (v2, 2026-08-27)

Supersedes LIMITATIONS.md (preserved). Honest, current statement of
what this project cannot claim and where its evidence is weak.

1. **No demonstrated learnability.** Dependence-aware statistics (block
   permutation, block bootstrap) leave AUC/IC indistinguishable from
   chance, and power at the pre-registered minimum useful effect is
   very low (0.267 AUC, 0.011 IC): the current design is UNDERPOWERED —
   the data cannot demonstrate presence OR absence of a useful edge.
   Block-level effective sample sizes are ~864 (train) and ~251
   (validation), far below nominal n.
2. **Arm F rewards are ≈ 0 across all 10 seeds** (selected seed 4: mean
   validation reward 0.0045; 7/10 seeds flagged by the convergence
   diagnostic). Selection among near-zero seeds is selection among
   noise; no management edge is claimed. The SB3 policy's behavior in
   the replacement shakedown (31% close actions on F) is a property of
   an unconverged near-zero-signal policy, not a validated strategy.
3. **B/C/E selected rules are chance-consistent.** The finalized
   threshold/top-K/mapping were chosen by pre-registered rules over a
   fixed budget, but the underlying validation signals (AUC 0.524,
   IC 0.029) are not distinguishable from chance; the selections are
   frozen procedure, not evidence of skill. Honest negatives preserved.
4. **All shakedowns are permanently INVALID for performance
   conclusions**, including the replacement run. Its equity numbers are
   mechanical exercise only.
5. **SD-GSHADOW is open for adjudication**: the strict G-shadow
   fill-list-equality check fails under an actively-closing RL policy
   for a fully quantified capacity reason (68/68 divergences =
   shadow-at-cap rejections). A refined property is proposed, not
   applied.
6. **Determinism scope.** SB3/torch runs are seed-deterministic within
   the pinned environment (torch 2.13.0+cu130, CPU); cross-platform bit
   determinism is NOT claimed. Reproducibility rests on the pinned
   environment + recorded seeds + saved artifacts + certified
   provenance manifests.
7. **Provenance history.** Four correction jobs were first launched
   from a mutable working tree; their outputs are preserved as PROFILE
   and were superseded by certified clean-worktree reruns
   (bit-identical where comparable). See
   PROVENANCE_INCIDENT_2026-08-27.md.
8. **Holdout remains sealed.** Every statement in this cycle rests on
   train/validation only; holdout-side verification remains
   metadata/hash-only until an authorized Checkpoint-2 procedure.
9. **Single-market, single-period scope.** USDT-perp universe,
   2021-01-11 → 2025-07-10 pre-holdout window; nothing generalizes
   beyond it.
10. **Costs/fills are simulated** under the frozen cost model;
    real-market microstructure is not represented beyond that model.
