# SPEC AMENDMENT A1 — Arm G Shadow Counterfactual (D61 blocker A)

**Authority:** directed by the independent replacement-Checkpoint-1
adjudication (2026-08-28, recorded as D61) through the material-change
procedure (SPEC §16). **SPEC_FINAL-1.2.1.md is preserved byte-unmodified**
(its hash is a pinned root component); from this amendment forward the
specification is read WITH this amendment, which supersedes the section
quoted below. This amendment is a governed constitutional document
(locked in integrity manifest v3).

## Superseded text (SPEC_FINAL-1.2.1.md, "Arm G Shadow Counterfactual")
> Maintain:
> * G actual: Complete system including RL
> * G pre-RL shadow: Identical G decisions through entry, followed by
>   frozen conventional management
> The shadow is diagnostic and is not an eighth official arm.
> It determines whether RL improved or damaged the otherwise identical
> combined pipeline.
> G-shadow identity through entry is a constitutional test.

## Why (adjudicated design conflict, recorded)
Different post-entry management changes holding time and therefore
capacity; two accounts under independent ten-position caps can then
produce different future fills; forcing portfolio-level entry equality
would suppress or distort exactly the capacity effect RL management
creates. The strict identity test fired CORRECTLY on the replacement
shakedown (G 328 fills vs single-shadow 260, all 68 divergences =
shadow-at-cap rejections); that failed result and its SD-GSHADOW record
are preserved permanently (data/shakedown_v2/).

## Amended text (in force)
Maintain:

* **G actual** — the complete system including RL. G actual gates its
  entries on ITS OWN state only; no diagnostic ledger's open-symbol or
  capacity state may suppress, alter, or reorder G actual's independent
  valid entries, decisions, capacity, or execution.

* **G matched-entry management shadow** (diagnostic 1) — clones every
  ACTUAL G fill at the identical timestamp, symbol, side, quantity,
  price, and initial protection, then applies frozen conventional
  management. Used ONLY for matched trade-level attribution of
  management effects. If cloning produces more than ten simultaneous
  diagnostic positions, that is recorded explicitly
  (`diagnostic_over_cap` events); this ledger is NOT an independently
  feasible portfolio and is never described as one, and is not an
  eighth official arm. **Constitutional test: exact matched-fill
  identity** — every G actual fill has an identical clone.

* **G feasible conventional counterfactual** (diagnostic 2) — runs the
  same pre-RL entry pipeline (filter → rank → min(E,D) × A-size →
  governor) with frozen conventional management under its OWN capital,
  exposure, and position limits. Its later fills may diverge from G
  actual because its management changes its capacity. Used for
  total-system counterfactual comparison; it claims NO strict entry
  identity after state divergence. **Constitutional test: fully
  explained divergence** — every shared candidate has a recorded
  feasible decision (submitted / already_open / filter_rejected /
  rank_cut / regime_blocked), and every submitted-but-unfilled entry
  has a recorded governor or engine rejection; no divergence is silent.

* **Constitutional test 3: diagnostic inertness** — running with the
  diagnostics enabled versus absent leaves G actual (and every arm)
  byte-identical in decisions, events, cash, positions, and governor
  streams.

Together the two diagnostics determine whether RL improved or damaged
the combined pipeline: the matched shadow isolates the management
effect trade-by-trade; the feasible counterfactual bounds the
system-level effect including capacity.

## Mechanical changes bound to this amendment
- `lab/sim/engine.py`: diagnostic-only `Engine.clone_open` (bypasses
  capacity BY DESIGN, emits `diagnostic_over_cap`; never called by any
  official arm account; outside SIMULATOR_SEMANTICS entry semantics).
- `lab/orchestration/competition.py`: `shadow_matched` +
  `shadow_feasible` replace the single shadow; G actual's
  `shadow_open` entry gate REMOVED; both diagnostics inside the
  transactional snapshot/rollback; `diagnostics=False` mode exists so
  inertness is testable.
- `tests/test_competition.py`: the strict-identity test replaced by the
  three constitutional tests above (+ explicit over-cap recording
  test); `tests/test_transactional_rounds.py` byte-compares both
  diagnostics.
- `lab/tools/shakedown.py`: exports both diagnostics' ledgers; defect
  checks SD-GMATCHED (constitutional) and SD-GFEASIBLE-UNEXPLAINED
  (blocking); records over-cap counts and fill-divergence summary.
- ARCHITECTURE.md and DATA_DICTIONARY.md updated in place (living
  documents) to describe the two diagnostics.
