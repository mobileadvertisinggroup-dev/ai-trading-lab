# CHECKPOINT 1 — REPLACEMENT REPORT (v2, 2026-08-27)

Supersedes `CHECKPOINT1_REPORT.md` (preserved unmodified as the
historical NOT-APPROVED submission). This report covers the corrections
directed by the independent Checkpoint-1 adjudication (D52) and the
reviewer's provenance directive, executed as decisions D53–D60.
**Everything here remains paper-only; no holdout access, no private-key
request, no Checkpoint-2 step has occurred.**

## 0. Standing re-description (directed)
Shakedown run 2 (the previously "operationally clean" run) is
henceforth described as: **"operationally completed under known
defective RL observations, with insufficient RL-action evidence and
unproven transactional rollback."** All prior artifacts are preserved
unmodified.

## 1. Blocker resolutions

### Blocker 1 — Arm F rebuilt on pinned Stable-Baselines3 (D55, D59)
- `PREREGISTRATION_ARM_F_SB3.md` committed (03303e0) BEFORE any SB3
  output existed: PPO / SB3 2.7.0 / torch 2.13.0+cu130 (exact build,
  Amendment A1) / MlpPolicy; n_steps=512, batch_size=128, gamma=1.0,
  device=cpu, all else defaults; seeds 1..10; budget formula
  min(150000, floor(0.9·(4h/10)·sps)) → 149,504 timesteps/seed;
  convergence diagnostic (MA-50, non-selection); deterministic
  evaluation over ALL train + ALL validation episodes; selection =
  highest mean validation reward, ties → lower seed. NO algorithm
  comparison occurred.
- Official run: CERTIFIED provenance (clean detached worktree, commit
  2242f7a); **selected seed 4, validation mean reward 0.0045**; all 10
  seeds' train/validation rewards identical to an independent earlier
  run (seed-determinism confirmed cross-run); 7/10 seeds flagged
  non_converged (diagnostic only, reported not hidden); ~33 min wall
  (budget 4 h). Honest reading: rewards are near zero across all seeds —
  consistent with the learnability nulls; no management edge is claimed.
- Validation isolation: the trainer ASSERTS train/validation episode
  disjointness; validation is consumed only by the pre-registered
  selection rule; all evaluation predictions `deterministic=True`.
- Every CEM artifact is INVALID, preserved unmodified under
  `data/models_invalid_cem/` with its README; Arm G is regenerated from
  the SB3 artifact via the canonical adapter (no G-side training).

### Blocker 2 — SD-RLOBS closed: one canonical observation builder (D53, D54)
- `lab/arms/observation.py` = THE builder for training AND inference
  (schema obs-v2, hash 9fdb8210…): all 10 dims with decision-time
  definition, provenance, units, clipping, and missing rules; no
  vol=1.0 hardcode (frozen Wilder ATR series, most-recent-defined ≤ t,
  entry-ATR carry); no exposure=0 placeholder (inference: the arm's own
  account; training: the RECORDED official exposure fraction).
- Mechanical parity: bit-identical float32 vectors between orchestrator
  and training env at every shared boundary — proven across long AND
  short positions, executed partial reductions and stop tightenings,
  evolving MFE/MAE, per-bar-varying ATR, changing exposure, and
  terminal-state lockstep, with the replay driven by the orchestrator's
  recorded executed actions (tests/test_observation_parity.py).
- Exposure provenance: the official equity ledger was regenerated WITH
  `gross_exposure`; behavior neutrality proven bit-identically
  (candidates, labels, decompressed events, [t, equity] all IDENTICAL;
  final equity 4090.2240675064613 unchanged); original preserved;
  amendment EQUITY-EXPOSURE-COLUMN records old (6d451e58…) → new
  (fe8dea69…) hashes and cites the certified provenance manifest.

### Blocker 3 — transactional synchronized rounds (D53)
- `ArmState.snapshot()/rollback()` covers cash/ruined/ids, positions
  (stops AND quantities), pending operations, engine event streams,
  decision + RL ledgers, governor state and events, and the shared
  candidate ledger, for every arm AND the G-shadow.
- Zero-effect proof: a LATE arm failure — after entries proposed, exits
  queued, stops tightened (captured in-round immediately before the
  injected failure), governor checks run, decision records appended —
  leaves the end state byte-identical to a control run in which the
  round never occurred; the tightened stops are proven restored to
  their exact pre-round values; adapter/model state is proven to carry
  nothing. Only the coordinator's centralized invalid-round record
  survives (tests/test_transactional_rounds.py).

### Blocker 4 — full RL observability in the replacement shakedown (D58)
Every F/G management decision in the replacement shakedown records: the
obs-v2 vector, schema version+hash, raw action, governor outcome,
executed action, invalid reason, and before/after stop+quantity.
Exports: per-arm governor event streams, F/G RL decision ledgers,
`rl_observability.json` (HOLD counts, executed-action counts,
governor-reject counts, tighten reconciliation against engine
`stop_tightened` events, per-boundary open-position coverage), and the
full round-record ledger. Results: coverage complete (ZERO uncovered
open boundaries for F and G), reconciliation exact, one schema hash
everywhere, 0 governor rejects, F: 3,798 records (2,623 holds, 1,175
closes), G: 1,495 records (1,205 holds, 290 closes).

### Blocker 5 — dependence-aware learnability; v1 p-values retracted (D56)
- v1 i.i.d. permutation p-values RETRACTED as dependence-blind (v1
  report preserved).
- Pre-registered (990a8a4, before the rerun): 28-day blocks, block-order
  permutation with boundary groups intact, 200 permutations seed
  20260827; validation block bootstrap 1000 resamples seed 20260828;
  structure diagnostics; block-level ESS; MUE (AUC dev 0.05, |IC| 0.05);
  approximate normal-theory power; and the FROZEN
  INSUFFICIENT-LEARNABLE-VARIATION rule for Checkpoint 2.
- Certified results: observed AUC 0.5240 (identical to v1 — same frozen
  models), block-permutation p_upper 0.552, CI95 [0.456, 0.579];
  IC 0.0288, p_upper 0.726, CI95 [−0.042, 0.107]. Nominal n 2,089
  train / 750 validation; unique boundaries 1,245 / 443; overlapping
  info-interval pair fraction 0.0064 (train); block-level ESS 864.2
  (train) and 251.1 (validation). Power at the MUE: 0.267 (AUC), 0.011
  (IC) — under the frozen rule the present evidence sits in the
  **UNDERPOWERED — NO EVIDENCE EITHER WAY** branch (rule applies at
  Checkpoint 2; recorded, not self-adjudicated).
- Interim conclusion (directed, verbatim): **"NO DEMONSTRATED
  LEARNABILITY; statistical significance not adjudicated."**

### Blocker 6 — B/C/E finalized under a pre-registered budget (D57)
- Pre-registered 18-configuration budget (9 B thresholds + 5 C top-K +
  4 E mappings), support constraints, tie rules, and the SPEC-frozen
  U_E utility — committed before any grid value was computed; every
  result recorded; certified byte-identical official rerun.
- Selected: **B threshold 0.30** (218/750 accepts, accepted mean net_r
  0.083), **C top-K 3** (670 selected, mean 0.079), **E mapping M3**
  (U_E 0.1016; DD95 26.24 vs flat-control 55.00).
- Directed anomaly explanations (honest negatives, preserved):
  B draft 0.50 sits ABOVE the classifier's 99th-percentile probability
  (median 0.257, q99 0.4985) because the validation base rate ≈ 0.30 —
  its 8-trade accepted set is a tail artifact (SE ≈ 0.5), not a
  preference for bad trades. E draft bucket deviations are within 2×SE
  except the monotone-consistent 0.25 bucket — non-monotonicity is
  chance-level ranking noise. No profitability claim is made for any
  selected rule; the levels remain chance-consistent.

## 2. Provenance gate (reviewer directive; D59)
All four correction jobs launched from the session's mutable tree were
demoted to **PROFILE — NOT OFFICIAL** (mechanical launch-state facts in
`PROVENANCE_INCIDENT_2026-08-27.md`) and re-executed under
`lab/tools/provenance_run.py` from a clean DETACHED worktree at commit
2242f7a: zero uncommitted changes enforced pre- and post-run, pre/post
source-hash census (no consumed file changed mid-run), loaded-module
census (imports solely from the worktree), exact dependency versions
(python 3.11.15, torch 2.13.0+cu130, SB3 2.7.0, gymnasium 1.2.3, numpy
2.4.6, pandas 3.0.5, lightgbm 4.7.0), command lines, times, input and
output hashes. All four official reruns CERTIFIED; Arm A, B/C/E, and
learnability outputs bit-identical to their cross-checks; SB3 rewards
identical across independent runs.

## 3. Replacement shakedown (permanently INVALID; D60)
Run from the clean worktree at 76a1c2e under the provenance gate,
window 2025-01-11 → 2025-07-10 (final 180 pre-quarantine days), with
the certified frozen artifacts (B 0.30 / C top-3 / E M3 / F SB3 seed 4
via the canonical obs-v2 adapter). **1,080/1,080 rounds valid; all
seven arms decided every round; full RL observability recorded.**
Marked INVALID FOR PERFORMANCE CONCLUSIONS in every file, as always.

One constitutional defect fired and is PRESERVED: **SD-GSHADOW**
(G 328 fills vs shadow 260). Mechanical root cause
(`data/shakedown_v2/FINDING_SD-GSHADOW.md`): the shadow's fills are a
strict subset of G's; all 68 divergent fills pair 1:1, at the same
(t, symbol), with shadow-engine `max_positions` rejections, each with
the shadow at exactly the 10-position cap — the expected capacity
effect of an actively-closing RL policy on a hold-to-conventional-exit
diagnostic account. Entry-SUBMISSION identity holds (single dual-target
submission path; symbol-level re-entry is gated on the SHADOW's open
set). The strict fill-list-equality check was previously green only
because the defective policy never freed capacity. A refined
constitutional property is PROPOSED in the finding for adjudication;
the strict check and its defect record stand unchanged until then.

## 4. Constitutional lineage (D52 procedure)
- v1 integrity manifest (c423f782…) preserved unmodified; recorded as
  HISTORICAL — NOT APPROVED.
- Integrity manifest v2 (`data/manifests/integrity_manifest_v2.json`,
  hash **2268007d…**): 38 unchanged / 3 modified / 2 added locked
  files, every change carrying a decision-keyed reason (D53 test
  additions + required fixture field; D58 comment-only protocol pin and
  RISK_POLICY retraction); generation refuses undocumented changes;
  independently re-verified (per-file hashes + self-hash).
- Full suite rerun from the clean worktree at 76a1c2e: **141/141**
  (includes the exact-equality differential gate and the golden
  fixtures); verbatim output preserved with its hash.
- Original external root hash 80c7c5b5… remains PRESERVED, NOT
  APPROVED; the replacement root hash is in
  `data/manifests/checkpoint1_root_hash_v2.json` (predecessor recorded
  inside).

## 5. Directed wording corrections (D58)
- D46: the "cannot increase risk" claim is RETRACTED in RISK_POLICY.md
  (correct claim: v2 preserves the stated limits while preventing an
  unintended absorbing pause).
- D47: "permanent delisting inferred after two days without bars"
  pinned in lab/protocol.py as the permanent interpretation, never to
  be changed silently.
- Run-2 re-description installed (CHANGELOG; §0 above).

## 6. What is NOT claimed
No profitability, no demonstrated learnability, no holdout evidence of
any kind, no validated management edge (Arm F rewards ≈ 0). All
shakedowns are permanently INVALID for performance conclusions. The
experiment remains paper-only.

## 7. Stop
Work STOPS at this replacement Checkpoint 1. Awaiting independent
adjudication. Continuing prohibitions honored: no private-key request
or access; no holdout decryption or inspection; no Checkpoint-2
authorization; no official holdout evaluation; no real-money trading;
no deletion or rewriting of prior evidence; no silent protocol,
threshold, fixture, or expected-outcome changes.
