# CHECKPOINT-2 READINESS BUNDLE V2 — D69 corrections

Produced in response to "CHECKPOINT 2 READINESS REVIEW — NOT AUTHORIZED"
(recorded as D69). All five blockers were corrected WITHOUT opening,
decrypting, or inspecting the holdout; the opening count remains ZERO,
no real authorization record exists, and the key holder's private key
was never requested, entered, transmitted, or stored.

## Blocker 1 — overlay-only symbols (silent omission) — CORRECTED
`lab/tools/holdout_evaluator.py`: `discover_symbols` builds the
validated UNION of pre-lake and decrypted-overlay kline symbols with
explicit classes (pre_only / overlay_only / combined); `load_combined`
applies per-class schema, 15m-grid, duplicate, ordering, funding, and
quarantine-boundary validation (`CombinedDataError` fails the gate
closed — nothing is skipped or imputed); the per-class symbol census is
reported in the results. The pinned universe definition is Amendment A1
§3 of the pre-registration. Synthetic tests
(`tests/test_holdout_evaluator_units.py`) prove an overlay-only symbol
becomes eligible mechanically, enters the universe, and generates §2
candidates through the real orchestrator — no real holdout filename was
inspected to develop them.

## Blocker 2 — frozen artifact hashes not enforced — CORRECTED
ONE exact frozen-input manifest, `data/manifests/
checkpoint2_frozen_inputs.json` (generator `lab/tools/
make_frozen_inputs.py`; sha256
edb0806d43d4d96ce7cfb228eec37a699365f80f513226841279f0d20d8bddc6),
pins every consumed file: governing docs (protocol, spec, G-shadow
amendment, CP2 pre-registration, IL-blocks pre-registration), dataset/
partition manifests, the frozen recipient, and the exact model
artifacts (boosters, cuts, selections, SB3 manifest + seed-4 ZIP).
The authorization record must carry `frozen_inputs_manifest_file` +
`frozen_inputs_manifest_sha256` (`lab/data/authz.py`); BEFORE the
atomic claim the gate recomputes every pinned hash and refuses missing,
ADDITIONAL (strict census of the staged model/sb3 dirs), substituted,
symlinked, or path-escaping inputs (`lab/data/frozen_inputs.py`).
Negative tests: one-byte mutation per artifact class (protocol,
dataset manifest, recipient, booster, SB3 zip), an additional unpinned
file, and a same-bytes symlink substitution — each proven to refuse
BEFORE OPENING_STARTED (`tests/test_gate_fault_injection.py`).

## Blocker 3 — missing pre-registered outputs — CORRECTED
`supporting_metrics` now reports profit factor, average trade,
turnover, slippage estimate, exposure, time in cash, and the
top-3-gains-removed result; the frozen INSUFFICIENT-LEARNABLE-VARIATION
assessment runs inside the evaluator with FIXED frozen-model scores and
no refitting (`il_assessment`, seeds 20260903/20260904, exact-multiset
rotation permutation + true circular moving-block bootstrap, explicit
"INSUFFICIENT DATA" branch). All mechanics were pinned BEFORE any
opening as formal Amendment A1 of
`PREREGISTRATION_CHECKPOINT2_EVALUATION.md`; no statistic, seed,
correction, constraint, or success criterion of the original
pre-registration changed. Every quantity has a hand-computed unit test.

## Blocker 4 — resource safety unproven — CORRECTED
`lab/data/preflight.py`: pre-claim resource gate (ciphertext size,
tmpfs capacity via statvfs, MemAvailable, HARD no-swap requirement,
results-directory capacity, expected peak scaled from the measured
surrogate profile, conservative 1.5x margin; refusal costs nothing —
the opening is unspent). Whole-file decrypt was replaced by STREAMING
`pyrage.decrypt_io` into the verified tmpfs + streamed extraction; the
intermediate tar is chunk-wiped before evaluation. The complete
evaluator was profiled by a FULL-SIZE dress rehearsal on a non-holdout
surrogate (the validation span) through the exact production entry
point `python -m lab.data.unseal` on a pty — measured peak RSS, tmpfs
high-water, runtime, and results size are in
`data/manifests/checkpoint2_resource_profile.json`;
`readiness/DRESS_REHEARSAL_EVIDENCE.json` holds the full record,
including proof the real ledger was untouched and the ephemeral keypair
was generated and discarded in-process.

## Blocker 5 — claim/key/cleanup/results ordering — CORRECTED
`lab/data/unseal.py` restructured: everything checkable without the
holdout — authorization, ledger, artifact identity, EVERY frozen-input
hash, output-directory checks, identity entry + parsing + verification
of the derived public key against the frozen recipient, resource
preflight — runs BEFORE the claim (a wrong key leaves the opening
unspent); the claim happens immediately before real decryption;
results go FIRST to a protected 0600 temp file; ALL decrypted material
is zero-overwritten in bounded 1 MiB chunks (the `b"\0" * size`
pattern is gone) and absence is VERIFIED; cleanup failure is always
FAILED_CLOSED with temp results removed; atomic publication (rename) +
CONSUMED happen only after verified cleanup; a publication or ledger
failure removes the results again and never represents success. Crash
states and manual containment are documented in
`DATAFLOW_HOLDOUT_OPENING.md` and the procedure. Fault-injection
tests cover identity validation, decryption, extraction, the
evaluator, result serialization, cleanup, result publication, and the
ledger append.

## Closure evidence
- Clean detached worktree (commit 18cbad9…, zero uncommitted changes):
  full suite 191/191; fail-closed batteries 50/50
  (`data/manifests/TESTS_RERUN_18cbad9.{json,txt}`).
- Full-size surrogate dress rehearsal: `readiness/
  DRESS_REHEARSAL_EVIDENCE.json` + `readiness/
  SURROGATE_RESULTS_SUMMARY.json` (statistics only; the surrogate is
  built exclusively from NON-holdout validation-span rows).
- The real holdout artifact was never read; the real ledger hash is
  unchanged (verified in the evidence record); no
  `data/manifests/checkpoint2_authorization.json` exists.

STOPPED after producing this bundle. Checkpoint 2 remains
NOT AUTHORIZED until the reviewer's separate explicit authorization.
