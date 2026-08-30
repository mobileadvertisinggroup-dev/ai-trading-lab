# REPLACEMENT CHECKPOINT 1 — V6 (D74 G_matched entry-bar funding fix)

Addendum to CHECKPOINT1_REPORT_V5.md, produced under the reviewer's
D74 focused review: the D72 funding correction was ACCEPTED for arms
A–G, the RL environment, the Arm E reselection, the Arm F retraining/
comparison, and G actual; V5 (root `7104e277…59c3`) is preserved as
NOT-APPROVED history because G_matched carried an uncovered
entry-boundary ordering defect. The holdout was never accessed; the
opening count is zero.

## The defect (exactly as adjudicated)
At a funding boundary t where another engine already holds X — so the
shared frozen map contains X — G actual with no prior X fills a new X
entry ON t and pays no entry-bar funding (engine order: funding →
exits → entries). The mirrored clone, created by `_mirror_g_fills`
BEFORE the matched engine processes bar t, was already open at its
funding phase and could pay entry-bar funding G actual did not. The
prior diagnostic-funding test missed it because G and the arms entered
together there.

## The correction (position-level, arms untouched)
`Position.clone_entry_bar_ms` — stamped ONLY by the diagnostic
`clone_open`, never by any actual arm's entry path — and
`_process_funding` skips exactly that position on exactly that bar
(no funding, no funding_missing: identical entry-bar semantics to the
mirrored actual, which does not exist at the funding phase). No
symbol-level workaround. Later boundaries charge normally.

## Proof obligations discharged
1. **Fails under V5, passes after the fix.** The exact staggered
   constitutional regression (another arm holds X across t; G first
   fills X at t; map contains X; zero funding for the new position at
   t in BOTH G and G_matched; same-bar fill/stop/target/MFE/MAE
   identity; later boundaries reconcile identically) was committed
   FIRST and run against the V5 ordering: **4 failed** — including the
   literal assertion "NEW X clone paid entry-bar funding"
   (`readiness/D74_REGRESSION_FAIL_UNDER_V5.txt`). After the fix:
   **19/19 pass** (`readiness/D74_REGRESSION_PASS_AFTER_FIX.txt`).
2. **Directed test set** (all in
   `tests/test_funding_constitutional.py`): pre-existing matched
   positions still funded normally; exemption scoped to the entry bar
   only; multiple symbols with mixed pre-existing/new clones (the new
   clone exempt while the pre-existing clone is charged at the same
   boundary); rollback restores the exemption stamp and funding state
   exactly; diagnostics-on vs diagnostics-off leaves G actual
   byte-identical on the staggered scenario.
3. **No actual-arm change.** Clean-worktree suite **210/210** at
   `e1c2a34` including the differential harness
   (`TESTS_RERUN_e1c2a34`), and the v6 shakedown's per-arm final
   equities are IDENTICAL to v5's for every arm A–G
   (`readiness/D74_ACCEPTANCE_EVIDENCE.json`) — only the G_matched
   diagnostic's funding stream changed (entry-bar funding and
   entry-bar funding_missing now correctly absent; reconciliation
   still exact).
4. **Re-runs** (no Arm E rerun, no Arm F retraining — their engines
   were unaffected), all provenance-certified from the clean worktree:
   - **Stress fixture v6** with the new staggered funding-entry
     scenario (STAGUSDT: G first fills on an 8h boundary while arm A
     holds and pays; entry-bar funding zero for G actual AND the
     matched clone; the clone funded at 20 later boundaries): zero
     defects.
   - **Full INVALID shakedown v6**: zero defects, 1080/1080 valid
     rounds, funding reconciled in all nine engines.
   - **Funding + dashboard reconciliation**: v5-vs-v6 comparison in
     `readiness/D74_ACCEPTANCE_EVIDENCE.json`; dashboard rebuilt from
     the v6 ledgers (`docs/dashboard_shakedown_v6.html`).

## Constitutional state
Integrity manifest **v6** (explicit v1→…→v5→v6 lineage; the single
locked-file change reason-keyed; undocumented changes refused) and the
replacement **Checkpoint-1 V6 root** are recorded in
`data/manifests/integrity_manifest_v6.json` and
`data/manifests/checkpoint1_root_hash_v6.json`, with V5 listed as
NOT-APPROVED history.

## Unchanged
All V5 scientific results and honest conclusions (they came from
actual arms, which this fix provably did not touch): M1 selection
(U_E 0.9425), seed 3 selection with all corrected seeds negative,
baseline +0.05340 with 0/10 wins, learnability underpowered. STOPPED
at replacement Checkpoint 1 V6; no Checkpoint-2 work; opening count
zero; no authorization; no key.
