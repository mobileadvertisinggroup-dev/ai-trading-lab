# PROVENANCE INCIDENT RECORD — 2026-08-27 (reviewer directive)

Four correction-phase jobs were launched from the session's mutable
working tree while implementation/documentation work continued in the
same checkout. Under the reviewer's provenance gate, their outputs are
**PROFILE — NOT OFFICIAL**, preserved unmodified, and every job is
re-executed from a clean, detached git worktree at a single committed
SHA under `lab/tools/provenance_run.py` (automatic provenance manifest;
outputs outside the checkout).

## Launch-state facts (mechanical, from the session record)

| Job | Launch state | Violation | Disposition |
|---|---|---|---|
| Arm A regeneration (exposure column) → `/home/user/lake-work/ledgers_v2` | tree at 52cfec0 + UNCOMMITTED `lab/arms/arm_a.py` edit (later committed verbatim in 03303e0) | launched from an uncommitted source state; on-disk bytes at launch not cryptographically provable | PROFILE; official rerun from worktree |
| SB3 Arm F training (run 2) → `/home/user/lake-work/models_sb3` | tree at 990a8a4 + UNCOMMITTED `lab/tools/train_arm_f_sb3.py` merge fix (committed verbatim in 90b1d7b) | uncommitted entry script AND a consumed module (`lab/protocol.py`, comment-only pin, commit b3fb376) changed on disk mid-run (after import) | PROFILE; official rerun from worktree |
| B/C/E finalization → `bce_finalization.json` (sha256 6ec782bb…) | tree at 90b1d7b−1 with UNCOMMITTED `lab/tools/finalize_bce.py` (committed verbatim in b252cbe) | launched from an uncommitted source state | PROFILE; official rerun from worktree (identical pre-registered grids; deterministic; budget not consumed twice — Amendment A1) |
| Learnability v2 → `learnability_report_v2.json` | tree CLEAN at b69fc0b; no consumed file changed during the run | none (reconstructible exactly) | still re-executed from the worktree for uniformity; the b69fc0b run is retained as a bit-identity cross-check |

The earlier failed SB3 launch (KeyError before any training) produced no
output and required no disposition.

## Additional corrections executed under the same directive
- Exact torch build recorded: **2.13.0+cu130** (abstract pin
  `torch==2.13.0`; `device="cpu"` enforced). Pre-registration Amendment
  A1 corrects the dependency record; no algorithmic change.
- Observation-parity coverage extended beyond a single fixture:
  long AND short positions, executed partial reductions and stop
  tightenings, evolving MFE/MAE, per-bar-varying ATR, changing
  portfolio exposure, terminal-state lockstep — all bit-identical
  (tests/test_observation_parity.py::test_multi_state_parity_*).
- Rollback proof extended: in-round stop mutation captured immediately
  before the injected late-arm failure and proven reverted to the exact
  pre-round values; adapter/model state proven carried over unchanged;
  governor history/events, decision ledgers, engine events, position
  quantities, pendings, G-shadow, candidates all in the byte-compare
  (tests/test_transactional_rounds.py).
- Trainer now ASSERTS train/validation episode disjointness at load
  (no validation information during fitting; validation used only by
  the pre-registered selection rule; deterministic inference).
- Replacement shakedown remains BLOCKED until: SB3 training complete
  and frozen, B/C/E finalized (official rerun), learnability v2
  complete (official rerun), all replacement artifacts frozen, and
  constitutional manifest v2 generated and verified.

Adopted-artifact rollback: the equity ledger adopted earlier today from
the PROFILE Arm A regeneration remains in place ONLY until the official
worktree rerun completes; the official rerun's output replaces it (bit
identity expected and verified), and the ledger-manifest amendment is
updated to cite the certified provenance manifest.

Continuing prohibitions unchanged: no private key, no holdout access,
no Checkpoint-2 steps, no real-money trading, no evidence deletion, no
silent changes.
