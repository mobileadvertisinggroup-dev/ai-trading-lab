# BUILD_STATE — AKRA AI TRADING LAB

Authoritative session-persistence record required by SPEC_FINAL-1.1.md §24.
Must agree with `build_state.json` at all times. Never rewrite earlier
decisions silently; append, don't erase.

## Current status

- **Current phase:** Phase 1 — Protocol foundation (COMPLETE: Arm A, max holding period, universe rule, data-quality rule, 60/20/20 partition rule authored and FROZEN in EXPERIMENT_PROTOCOL.md, sha256 `6283db52b10103c381530686478a21f205748960d5b6e2374c4ea27811a178ca`, before any ingestion). Phase 0 complete, pending user input on B1/B2 below.
- **Last completed gate:** none (no gates reached yet)
- **Specification:** `SPEC_FINAL-1.1.md`, sha256 `5a7a3f5ce27d76ce97af5adf4b5a59e4f69a4ffd2b968195add7ae80f70c380a`, preserved verbatim at commit `16ec585e6ab281aece7c705a2073f1a02e5ec7ef`
- **Checkpoint 1:** not reached
- **Checkpoint 2:** not reached
- **Holdout:** partition RULE frozen (EXPERIMENT_PROTOCOL.md §7); concrete dates not yet computable (no data ingested); nothing to quarantine yet
- **Dataset hashes:** none (no data ingested)
- **Model hashes:** none (no models trained)
- **Integrity-manifest hash:** none (constitutional tests not yet written)
- **Safe resume command:** clone this repo, read `SPEC_FINAL-1.1.md`, this file, and `build_state.json`, verify the spec sha256 above matches, then continue from "Pending actions".

## Phase 0 — Discovery findings (2026-08-25)

### Existing projects inventory (all untouched, per §1 / R01)

| Project | Location | Status |
|---|---|---|
| BTC Arena | `mobileadvertisinggroup-dev/btc-arena` | Retired 2026-08-25 (cron paused, code/data/history preserved). Read-only reference only. |
| akra-website | `mobileadvertisinggroup-dev/akra-website` | Untouched. |
| binance-execution-manager | `mobileadvertisinggroup-dev/binance-execution-manager` (private) | Presumed host of **Engine v7**. NOT yet inspected — read-only attachment was denied by the session permission layer and requires explicit user authorization. See Blocker B2. |
| AKRA Arena / Wallet D / Forward V1/V3 / Momentum Lab | Not found among repositories visible to this session | If they exist elsewhere, they are outside this session's reach and therefore trivially untouched. |

Standalone-project location convention discovered: one GitHub repository per
project under the `mobileadvertisinggroup-dev` account. This repository
follows that convention.

### Build environment (this Claude Code remote container)

- 4 vCPU (Intel Xeon @ 2.80 GHz), 15 GiB RAM, ~30 GiB usable disk allowance, **no GPU**
- Python 3.11.15; pip works (PyPI/files.pythonhosted allowlisted); Docker and psql binaries present
- ML/RL stack (numpy, pandas, lightgbm, xgboost, torch-cpu, stable-baselines3, duckdb, fastapi, pytest, …) not preinstalled but installable
- **Container is ephemeral**: reclaimed on inactivity. All durable state must live in this git repository. Long-running compute cannot assume container survival → resumable checkpoints (§25) are mandatory from the first training script, not an afterthought.

### Network policy (material constraint)

Outbound HTTPS from this container goes through an allowlist proxy.
**All exchange REST endpoints tested returned proxy 403 (blocked):**
Binance spot, Binance USDT-M futures (klines + funding), data.binance.vision
(bulk historical), Kraken, Bybit. Package registries (PyPI, npm) and GitHub
are reachable.

Consequences for Phase 2 (data ingestion) — two viable paths:

1. **GitHub Actions ingestion (default plan):** ingestion jobs run on GitHub-hosted
   runners, which have open egress. Proven pattern in this account (BTC Arena
   ran live market fetching on Actions for months). Raw data lands as
   content-hashed, versioned artifacts committed to storage (subject to §9
   quarantine including the sealing pass-through for the holdout range).
2. **User widens the environment network policy** to allow the chosen
   exchange's public data domains, enabling in-container ingestion and much
   faster iteration.

Path 1 requires no user action and is adopted as the working plan; if the
user enables path 2, it becomes a non-semantic operational improvement (data
content and hashing identical either way).

### Compute-budget implications (recorded per §25; profiling run still pending)

- No GPU anywhere available to the project (container: none; GitHub-hosted runners: none). RL (§3 Arm F) will be CPU-bound → algorithm/feature design must respect this; SB3 PPO/RecurrentPPO on CPU is feasible for tabular/low-dim observation spaces.
- GitHub-hosted Actions jobs cap at 6 h wall-clock per job. The 24 h-per-seed ceiling is therefore an upper bound, not a target; RL training must checkpoint-resume across chained jobs OR run in interactive sessions with resumable checkpoints. Formal profiling run (one representative seed) remains a Phase 6 prerequisite as specified.
- The forward paper competition's 4-hour decision cadence maps cleanly onto a scheduled GitHub Actions workflow (same operational pattern as BTC Arena, new isolated implementation).

## Decisions (chronological, append-only)

| # | Date | Decision | Rationale | Spec authority |
|---|---|---|---|---|
| D1 | 2026-08-25 | Repository is `mobileadvertisinggroup-dev/ai-trading-lab` instead of the spec-mandated name `akra-ai-trading-lab`. | The user created this repository by hand before the spec was issued; the session's GitHub integration cannot create or rename repositories (403). Isolation (R01) is fully satisfied; only the name deviates. User may rename in GitHub settings at any time (redirects preserve remotes); this file will be updated if so. | §2 "make reasonable decisions and record them"; launch instruction 1 |
| D2 | 2026-08-25 | Development branch is `main`. | Brand-new empty repository; no other branch exists or is protected. | — |
| D3 | 2026-08-25 | Data ingestion will execute on GitHub Actions runners (open egress), not in the dev container (exchange endpoints blocked by proxy allowlist). | Phase 0 network findings above. | §6; §2 |
| D4 | 2026-08-25 | Primary exchange-data source: Binance USDT-M perpetual futures (REST + data.binance.vision bulk archives), pending Phase 1 freeze. Rationale: deepest liquid USDT-perp universe, free bulk historical klines + funding + delisted-symbol archives (survivorship handling per §6). Final choice frozen in Phase 1, before ingestion. | §6 | 
| D5 | 2026-08-25 | Git author identity for this repo: repository owner account; no AI-model identifiers in committed artifacts. | Session policy. | — |

## Active blockers

| ID | Severity | Description | Needed from user | Blocks |
|---|---|---|---|---|
| B1 | none (informational) | Repo name deviates from spec (`ai-trading-lab` vs `akra-ai-trading-lab`). | Optional: rename repo in GitHub Settings → General. | Nothing. |
| B2 | deferred hard blocker | Engine v7 source (presumed in private repo `binance-execution-manager`) is not attachable: session permission layer denied the read-only attachment. Without it, the §13 differential gate (R28) cannot run and — per §13 — the gate may not be skipped or trivialized. | Say "attach binance-execution-manager" (or approve the attachment prompt) so Phase 0 can inventory Engine v7's supported semantics. | Phase 5 gate only. Phases 1–4 proceed regardless. |

## Completed actions

1. 2026-08-25 — Phase 0 discovery: environment profile, network-policy probe, package availability, existing-project inventory, Actions-based operational pattern identified.
2. 2026-08-25 — Spec FINAL-1.1 preserved verbatim (`SPEC_FINAL-1.1.md`), sha256 recorded, committed (`16ec585`).
3. 2026-08-25 — BUILD_STATE.md + build_state.json initialized (this commit).

## Pending actions (next, in spec order)

1. **Phase 2 — Data ingestion + holdout quarantine:** GitHub Actions ingestion of Binance USDT-M 15m klines + funding (per frozen §8); content-hashed immutable raw lake; sealing utility with non-interactive pass-through for the mechanically determined holdout range; refusal layer for all utilities.
2. **Phase 3 — Independent simulator** (SIMULATOR_SEMANTICS.md + implementation).
3. Phase 0 residual: Engine v7 semantic inventory (waiting on B2; blocks Phase 5 gate only).

## Material changes / invalidated artifacts / required retraining

None. No experimental artifacts exist yet.

## Decisions (continued)

| # | Date | Decision | Rationale | Spec authority |
|---|---|---|---|---|
| D6 | 2026-08-25 | Phase-1 protocol frozen: Arm A = Donchian 60-bar breakout (long/short) on 4h bars, ATR(28)-based 2xATR stop / +3R target / 20-bar opposite-channel trailing exit / 42-bar (7-day) max holding period; 0.75% equity risk per trade, 15% notional cap, 10 max positions, 150% gross exposure; universe = point-in-time top-75 USDT-perps by trailing 30d median daily quote volume (>=25M USDT, >=90d history, >=99% completeness); costs = 5bps taker + tiered spread/slippage + real funding; eligible interval + 60/20/20 partition by mechanical rule. Full text: EXPERIMENT_PROTOCOL.md sha256 6283db52b10103c381530686478a21f205748960d5b6e2374c4ea27811a178ca. | Reasonable in-spec design decisions, recorded per s2; classic transparent momentum system, deterministic and unambiguous. | SPEC s2, s3, s5, s6, s7 (R03, R15, R16, R18, R53) |
