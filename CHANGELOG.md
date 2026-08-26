# CHANGELOG — AKRA AI TRADING LAB

Chronological, append-only. Decision IDs refer to BUILD_STATE.md.

## 2026-08-25
- Phase 0-1: repo established; EXPERIMENT_PROTOCOL.md authored and FROZEN
  (sha da469dfd…, hash lineage recorded) before any ingestion.
- FINAL-1.2 governance change (user-authorized): Independent Reference
  Ledger differential gate replaces Engine v7 gate (D10).
- Phases 3-7 scaffolding: engine, refledger, differential gate (two real
  divergences adjudicated: D13 timing, D16 accumulation order), Arm A
  runner, governor (D15), golden fixtures, arms scaffolds, features,
  labels/purge, orchestrator, leak battery.

## 2026-08-26 (review gate)
- Phase-6 independent review verdict executed: G03 v2 correction (D26),
  exact-equality differential policy (D25), actions hardening (D28),
  exclusion registry (D29), unseal gate (D30).
- PC-1 adopted as SPEC_FINAL-1.2.1 (D32); final corrections A/B (D35,
  D36); final narrow review mechanical corrections (D37). REVIEW GATE
  SATISFIED.

## 2026-08-26 (Phase 2: ingestion)
- Age public key committed (public only). Probe 1: S3 listing endpoint
  fix. Probe 2: parsers confirmed; 9.3h sequential projection → concurrent
  acquisition (D38). Probe 3: PROJECTION-OK.
- Full run 1: timeout at 505/824 — daily-fallback request storm fixed
  (DAILY_FALLBACK_MONTHS=2, D39). Full run 2: release transaction gh-repo
  inference fix + draft-aware guard (D41). Full run 3: raw-v1 PUBLISHED.
- Coverage audit gate (D40) PASS, zero losses (D43). Repository-identity
  challenge adjudicated: link defect, no contamination (D42).

## 2026-08-26 (pre-Checkpoint-1 assignment)
- Steps 1-2: lake verified locally; partition reproduced; zero readable
  holdout rows (D44).
- Step 3: official Arm A. D45 capital=10,000. D46 RISK_POLICY v2
  (trailing-90d drawdown peak; v1 absorbing state — MATERIAL pre-lock
  amendment). D47 forced_delist_close conformance (v1 gap OOMed run 2).
  Final ledgers: 26,023 candidates / 2,840 labels.
- Steps 4-6: F01-F28 frozen; purge/embargo; learnability NULL recorded
  (AUC 0.524 p=0.42; IC 0.029 p=0.67) — no tuning (D48).
- Steps 7-8: compute profile in budget; B/C/E fits; Arm F deterministic
  CEM, 10 official seeds, seed 8 frozen by pre-specified rule (D49).
- Step 11: CONSTITUTIONAL LOCK — 41 files, hash c423f782… (D49).
- Step 12: shakedown run 1 INVALID (SD-FEATNAMES; containment proven);
  fix = canonical FEATURE_NAMES binding; shakedown run 2 INVALID and
  operationally clean; OPEN defect SD-RLOBS (D50).
- Step 13: CHECKPOINT 1 package; external root hash 80c7c5b5…; STOPPED.

## 2026-08-26 (post-Checkpoint-1 submission)
- User preserved the root hash (NOT approved); CHECKPOINT1_REVIEW_BUNDLE
  requested. This changelog, ARCHITECTURE.md, MODEL_CARDS.md added for the
  bundle. NO code, test, policy, model, or ledger changes; SD-RLOBS
  deliberately preserved unfixed pending adjudication.
