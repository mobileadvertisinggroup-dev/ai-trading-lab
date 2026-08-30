# CHECKPOINT-2 READINESS — V2 → V3 CHANGES (D76)

Everything below is what changed between CHECKPOINT2_READINESS_BUNDLE
(V2, D69 corrections, sha `8f0c0b2a…0f56`) and this V3 bundle. All V2
mechanisms (frozen-input enforcement, pre-claim identity verification,
resource preflight, streaming decrypt, bounded-chunk wipe, atomic
publish/CONSUMED ordering, fault-injection battery, union loader,
Amendment-A1 outputs) carry forward unchanged unless listed.

## 1. Funding correction (D72, V5) — the evaluator now applies funding
The seven-arm orchestrator (arms A–G + both G diagnostics) and the RL
environment apply the frozen per-bar funding map with ArmARunner/
engine semantics; the reporting collector reads the engine's real
`paid` field; a full reconciliation (by arm/symbol/side/sign/period +
event-to-equity identity) is embedded in the evaluator results; the
activity guard FAILS CLOSED on implausible all-zero funding. Corrected
artifacts: Arm E M1 reselected with funding (U_E 0.9425); all 10 SB3
seeds retrained; selected seed 3.

## 2. G_matched entry-bar exemption (D74, V6)
Position-level `clone_entry_bar_ms` stamp: the matched clone pays no
funding (and emits no funding_missing) on exactly its entry bar —
identical to the mirrored actual position; proven FAIL-under-V5 /
PASS-after-fix; arms A–G byte-identical.

## 3. Gate bindings refreshed (D76)
- `approved_external_root_hash` = the APPROVED V6 root
  `484f538d8b5f9587f2e4ff1f06a061b7aab337b195d6038fdf123d444a886cf0`;
  integrity manifest v6
  `32a59f4376b394f94ca7894ffbcffe534ff8b9fbf0779b8b81c6b594afd6d49f`.
- `checkpoint2_frozen_inputs.json` REGENERATED, sha
  `a9a2aa6c5e9ab9a79839b1086c7f2cdf2f086ce8234f3ed6267e0c5a9a92b01e`:
  now pins the funding-corrected `arm_e_portfolio_selection.json`
  (M1), the retrained SB3 manifest + `arm_f_sb3_seed3.zip` (the
  selected seed is READ from the manifest, never hard-coded), and
  `model_manifest_v5.json` (sha `5f010c7d…1859`) alongside the
  governing docs, dataset/partition manifests, and the frozen
  recipient.
- Mechanical resolution check from the ACTUAL gate locations —
  `data/manifests` + staged `--model-dir`/`--sb3-dir` containing
  exactly the pinned files: `verify_frozen_inputs → (True, [])`
  (`FROZEN_INPUTS_RESOLUTION_CHECK.json`).
- `CHECKPOINT2_AUTHORIZATION_PROCEDURE.md` carries every value pinned
  exactly; the ONLY key-holder fields left are the authorization
  timestamp and the authorized commit.

## 4. Closure evidence refreshed (D76, clean worktree `d6aaeeb`)
- Full suite 210/210; the fail-closed, authorization-negative,
  cleanup, publication, funding, and one-opening batteries 69/69
  (`TESTS_RERUN_d6aaeeb`).
- **The guard caught a real defect live.** The FIRST V6 rehearsal
  FAILED CLOSED in its isolated environment: the funding activity
  guard stopped the evaluation ("arm A: 7384 funding boundaries
  crossed, ZERO rates applied"). Root cause: the seal preserves the
  lake's FLAT funding layout (`funding/SYMBOL.parquet`) but the
  overlay reader only globbed the nested layout — every overlay
  funding file was silently invisible, and the synthetic fixture's
  nested layout had masked it. The REAL opening would have hit this
  AFTER spending the claim; the directed rehearsal + guard caught it
  first (`DRESS_REHEARSAL_V6_GUARD_FAILCLOSED.json`; real ledger
  verified unchanged). Fixed at `cc21007` (`_read_overlay` reads both
  layouts) with a flat-layout regression test; the locked-file test
  change is pre-recorded for the v7 reason-keyed lock.
- FULL-SIZE surrogate dress rehearsal RE-RUN through the exact
  production CLI with the FINAL (fixed) V6 evaluator and corrected
  models (`DRESS_REHEARSAL_EVIDENCE_V6.json`): ephemeral in-process
  keypair, isolated manifests dir + fresh ledger, real ledger verified
  unchanged, real authorization never created. Funding in the
  rehearsal is NONZERO and event-to-equity reconciled for every
  applicable arm (`SURROGATE_FUNDING_RECONCILIATION_V6.json`).
- `checkpoint2_resource_profile.json` re-measured under the V6
  evaluator (consumed by the pre-claim resource preflight).

## 5. Execution-host decision aid (D76 item 7)
`MAC_HOST_CHECK_COMMAND.txt`: one read-only command for the key
holder's Mac printing model/RAM/available memory/swap/disk/hypervisor
support plus a RECOMMENDATION line mapping the hardware to the options
of `MAC_LOCAL_EXECUTION_PLAN.md`. The 16-GiB remote container remains
rejected; the 1.5x margin is unweakened; no option involves the key
leaving the key holder's hardware.

## Unchanged from V2 (carried forward)
Authorization schema/example (two frozen-input fields), fault-injection
battery, union loader + synthetic tests, Amendment A1 outputs and IL
assessment, streaming decrypt + chunked wipe + publish/CONSUMED
ordering, crash-state documentation, DATAFLOW description, and every
standing prohibition. Opening count: ZERO throughout.
