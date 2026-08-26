# CHECKPOINT 1 — SHAKEDOWN REVIEW PACKAGE (spec §21)

Status: **STOPPED at Checkpoint 1, awaiting user approval.** Nothing past
this point (official candidate reset/launch, Checkpoint-2 preparation,
holdout anything) proceeds without it.

## 1. Defect inventory (complete, with root causes)

| ID | Severity | Root cause | Affected arms | Affected decisions | Fix |
|---|---|---|---|---|---|
| SD-FEATNAMES | blocking (fixed) | LightGBM boosters fitted from bare numpy matrices carry generic `Column_N` feature names; shakedown adapters bound by `booster.feature_name()` raised KeyError on every candidate | B, C, E, G (and, via synchronized-round invalidation, every arm's execution in affected rounds) | Shakedown run 1: 611 rounds invalidated; zero B–G decisions; **containment worked exactly as designed** — nothing executed anywhere in a failed round | Canonical `FEATURE_NAMES` list (verified identical to the official feature parquet order); adapters bind by it; frozen model artifacts untouched; shakedown rerun clean (run 2: 1,080/1,080 rounds valid) |
| SD-RLOBS | integration defect (OPEN) | `Competition._rl_management` supplies `{unrealized_r, bars_held}` to a policy trained on the 10-dim env observation; remaining dims zero-filled | F, G (management only; entries unaffected) | All F/G management decisions in shakedown run 2 | Post-Checkpoint-1: extend the orchestrator observation to the full 10-dim spec, then retraining assessment under the material-change rule |

Earlier defects found and fixed during this assignment (full detail in
BUILD_STATE D38–D49): probe listing endpoint (D-ingest), daily-fallback
request storm (D39), gh repo inference outside the checkout (D41),
RISK_POLICY v1 absorbing drawdown state (D46, material pre-lock policy
amendment), missing mid-run `forced_delist_close` conformance (D47,
quadratic event flood → OOM).

## 2. Affected metrics

Shakedown metrics are **permanently INVALID for performance conclusions**
(spec §20) — both runs' ledgers are preserved under `data/shakedown/`
(run 2) and `data/shakedown_run1/` with the INVALID marker in every file
name and manifest, and are never merged, backfilled, or reused. Official
metrics (Arm A ledgers, learnability) are unaffected by SD-FEATNAMES
(adapters are shakedown-side); they DO depend on RISK_POLICY v2 and D47
(documented in LIMITATIONS.md).

## 3. Implementation / test / scientific / semantic changes

- Implementation: D38 concurrent acquisition; D39 daily-fallback window;
  D41 GH_REPO + draft-aware guard; D46 governor trailing-window drawdown;
  D47 `Engine.force_close` + runner delist rule; cursor-based runner bar
  lookup (behavior-preserving); shakedown adapters + FEATURE_NAMES.
- Tests: +release-behavior test (governor v2), +forced_delist_close
  regression, +10 coverage-audit tests; suite 124 → 136, all green at the
  lock and at HEAD.
- Scientific: RISK_POLICY v2 (D46, material, pre-lock, flagged);
  D45 starting capital 10,000; Arm F algorithm choice (deterministic CEM);
  learnability null recorded with no tuning.
- Semantic: none to the frozen EXPERIMENT_PROTOCOL.md or
  SIMULATOR_SEMANTICS.md (hash lineage unchanged since Phase 1 freeze).

## 4. Retraining requirements (material-change rule)

Fixing SD-RLOBS changes Arm F's observation interface → Arm F retraining
required after the fix; Arms B/C/E unaffected by it. Any change to
RISK_POLICY numbers post-lock, or any locked file, triggers §16.

## 5. Independent Reference Ledger reconciliation

The exact-equality differential gate (engine vs `lab/refledger`, zero
shared code) passes at the locked commit: golden fixtures G01–G12
(layer-1 Decimal-quantize exact + 1e-8), randomized differential fuzzing
(85 fixtures, zero divergences), property invariants — all inside the
locked 136-test suite. Two historical divergences were adjudicated per
§13 (D13 timing, D16 accumulation order) with the reference ledger
corrected both times and the simulator unchanged.

## 6. Integrity-test status

LOCKED 2026-08-26 (D49): 41 files (all tests, golden fixtures, governing
documents, `lab/protocol.py`) hashed in
`data/manifests/integrity_manifest.json`;
`integrity_manifest_hash = c423f7826d0e3c667681a981f75e69d553c619022f17cdf2eea62c48ae01afb6`;
136/136 passing at the lock and at HEAD.

## 7. Shakedown invalidity confirmation

Confirmed: both shakedown runs are permanently marked
`SHAKEDOWN — INVALID FOR PERFORMANCE CONCLUSIONS` in every artifact and
manifest, never to enter performance claims, official results, backfills,
or holdout evidence.

## 8. Proposed frozen release candidate

- Data: `raw-v1` (published, audited PASS, accepted — D43).
- Code: repository HEAD at this report's commit.
- Models: `data/models/` artifacts per `model_manifest.json`
  (B/C/E LightGBM drafts, Arm F CEM seed 8 of 10 official seeds).
- Ledgers: `data/ledgers/` official Arm A ledgers + features +
  learnability report (hashes in their manifests).
- Subject to: SD-RLOBS fix + Arm F retraining decision at review.

## 9. Root integrity-manifest hash for EXTERNAL preservation

`data/manifests/checkpoint1_root_hash.json` — preserve this value
OUTSIDE the repository:

**`80c7c5b578ce168a4a391812e560aa451a3f2dc20af8993d950158d11dcabcaf`**

## 10. Standing confirmations

No holdout access occurred (audit log + hash-chained state ledger; the
sealed artifact was never opened). The private key was never requested.
Paper-only throughout. No partial dataset was ever represented as
complete. Gap effects, BTC-context sufficiency, and the learnability null
are in LIMITATIONS.md §§2–3, 6.
