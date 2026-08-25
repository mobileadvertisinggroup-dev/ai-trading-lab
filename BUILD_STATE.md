# BUILD_STATE — AKRA AI TRADING LAB

Authoritative session-persistence record required by SPEC_FINAL-1.1.md §24.
Must agree with `build_state.json` at all times. Never rewrite earlier
decisions silently; append, don't erase.

## Current status

- **Current phase:** Phase 3 — Independent simulator: SIMULATOR_SEMANTICS.md authored (frozen semantic input for BOTH independent implementations) and main engine `lab/sim/engine.py` built; 32/32 dev tests. Phase 2 code complete, awaiting user age key + Actions probe/full ingestion runs. Next: Phase 4 (Arm A runner on the engine). Phase 1 COMPLETE (: Arm A, max holding period, universe rule, data-quality rule, 60/20/20 partition rule authored and FROZEN in EXPERIMENT_PROTOCOL.md, sha256 `6283db52b10103c381530686478a21f205748960d5b6e2374c4ea27811a178ca`, before any ingestion). Phase 0 complete.
- **Last completed gate:** none (no gates reached yet)
- **Specification:** `SPEC_FINAL-1.2.md` (AUTHORITATIVE), sha256 `a29b6c9eb942cb56f7bfe44b1d3a861436875762ded37fbc37ecf96f5a369cc8`. FINAL-1.1 preserved unchanged for audit (`SPEC_FINAL-1.1.md`, sha256 `5a7a3f5ce27d76ce97af5adf4b5a59e4f69a4ffd2b968195add7ae80f70c380a`, commit `16ec585`).
- **Checkpoint 1:** not reached
- **Checkpoint 2:** not reached
- **Holdout:** partition RULE frozen (EXPERIMENT_PROTOCOL.md §7); concrete dates not yet computable (no data ingested); nothing to quarantine yet
- **Dataset hashes:** none (no data ingested)
- **Model hashes:** none (no models trained)
- **Integrity-manifest hash:** none (constitutional tests not yet written)
- **Safe resume command:** clone this repo, read `SPEC_FINAL-1.1.md`, this file, and `build_state.json`, verify the spec sha256 above matches, then continue from "Pending actions".

## Specification version FINAL-1.2 (governance change, 2026-08-25)

- **User explicitly authorized** this change (2026-08-25, in-session instruction).
- **Change:** the mandatory Engine v7 differential gate is replaced everywhere
  by the INDEPENDENT REFERENCE LEDGER DIFFERENTIAL GATE; total-independence
  mandate added (no previous project may be attached, inspected, copied,
  imported, called, or used — verification included); property-based
  accounting invariant tests added. Minimum differential subset, golden
  fixtures, independent review, and mismatch adjudication retained unweakened.
- **Reason:** preserve total independence from previous projects while
  retaining differential verification.
- **Timing:** before data-derived model training, constitutional-test
  locking, shakedown, holdout evaluation, or official results.
- **Affected phase:** Phase 5 verification only. **No existing results or
  models required invalidation** (none exist; nothing built so far touches
  any previous project).
- **B2 permanently closed:** REMOVED BY APPROVED SPECIFICATION CHANGE.
  No permission exists to attach binance-execution-manager.
- Hash lineage (protocol doc reference update only, no semantic change):
  EXPERIMENT_PROTOCOL.md `6283db52b10103c381530686478a21f205748960d5b6e2374c4ea27811a178ca` (Phase-1 freeze under FINAL-1.1)
  → `da469dfd0ff2307f4ed30c3c3872b95c0d6468e15b288ce9d3dae6ac16572590` (same frozen content, authority reference now FINAL-1.2).
  All *[Phase-1 frozen]* content is byte-identical apart from that one line.
- SIMULATOR_SEMANTICS.md, INTEGRITY_TEST_POLICY.md, ARCHITECTURE.md do not
  exist yet; they will be authored under FINAL-1.2 from the start.

## Repository identity (recorded per user instruction, 2026-08-25)

- Name: `ai-trading-lab` — Owner: `mobileadvertisinggroup-dev`
- URL: https://github.com/mobileadvertisinggroup-dev/ai-trading-lab
- Branch: `main`
- Renaming during an active workflow is deferred unless references, Actions
  configuration, and state files can be updated safely and atomically (user
  constraint). B1 remains informational only.

## User-imposed operating constraints (2026-08-25, binding)

1. **[SUPERSEDED by FINAL-1.2, 2026-08-25 — Engine v7 gate removed; no previous project may be touched at all.]** Original text: Engine v7 location must be established, not assumed. Do not request
   attachment of `binance-execution-manager` (or any repo) for the §13 gate
   until it is established to actually contain the frozen Engine v7. Before
   Phase 5, produce the Engine v7 requirements report: exact artifact
   required; expected repository/path; known frozen version/commit/sha256;
   minimum files or ledger exports required; whether a read-only exported
   snapshot suffices. If Engine v7 remains unavailable, B2 is the Phase-5
   hard blocker; the differential gate is never weakened, bypassed, or
   replaced without adjudication.
2. **GitHub Actions rules**: never print holdout rows/summaries in Actions
   logs; never commit raw market data, secrets, or decrypted holdout data to
   Git; never upload decrypted holdout data as an ordinary artifact;
   least-privilege secrets and controlled artifact retention; all execution
   paper-only. Persistence/retention/recovery design recorded in
   HOLDOUT_POLICY.md §3 and below.

## Phase 0 — Discovery findings (2026-08-25)

### Existing projects inventory (all untouched, per §1 / R01)

| Project | Location | Status |
|---|---|---|
| BTC Arena | `mobileadvertisinggroup-dev/btc-arena` | Retired 2026-08-25 (cron paused, code/data/history preserved). Read-only reference only. |
| akra-website | `mobileadvertisinggroup-dev/akra-website` | Untouched. |
| binance-execution-manager | `mobileadvertisinggroup-dev/binance-execution-manager` (private) | Untouched, not inspected. NOT presumed to contain Engine v7 (user instruction 2026-08-25: establish, don't assume). |
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
| B2 | **CLOSED — REMOVED BY APPROVED SPECIFICATION CHANGE (FINAL-1.2, 2026-08-25)** | (historical) Engine v7 location and artifact were unknown. Per user instruction (2026-08-25) its location must be established, never assumed from a repository name; the earlier presumption about `binance-execution-manager` is withdrawn. The §13 gate cannot run without the genuine frozen Engine v7. | Before Phase 5: the Engine v7 requirements report (see user-imposed constraints above); user identifies the artifact/location or supplies a read-only exported snapshot. | Phase 5 gate only. Phases 1–4 proceed regardless. |

## Completed actions

1. 2026-08-25 — Phase 0 discovery: environment profile, network-policy probe, package availability, existing-project inventory, Actions-based operational pattern identified.
2. 2026-08-25 — Spec FINAL-1.1 preserved verbatim (`SPEC_FINAL-1.1.md`), sha256 recorded, committed (`16ec585`).
3. 2026-08-25 — BUILD_STATE.md + build_state.json initialized (this commit).

### Phase 2 progress (2026-08-25)

Built and tested (11/11 dev tests passing):

- `lab/protocol.py` — frozen protocol constants, single code-level source.
- `lab/data/partition.py` — mechanical universe eligibility, round validity,
  eligible-interval and 60/20/20 partition computation (pure functions).
- `lab/data/lake.py` — content-hashed Parquet lake + manifest build/verify.
- `lab/data/seal.py` — sealing utility: splits at the quarantine boundary,
  age-encrypts holdout rows to the user's public key (pyrage/X25519),
  metadata-only logging, transient tar shredded.
- `lab/data/access.py` — GuardedLake: sole sanctioned read path; refuses
  holdout-intersecting requests (exact/partial/single-ts/alt-symbol/funding/
  universe) absent complete Checkpoint-2 authorization; hash-chained
  append-only audit log; consumed-holdout refusal.
- `HOLDOUT_POLICY.md` — quarantine, seal, storage/retention/recovery, Actions
  log-hygiene, key custody, decryption gate.

Phase 2 remainder built (2026-08-25, later same day): `lab/data/ingest.py`
(archive symbol discovery incl. delisted, monthly+daily kline & funding
download with CHECKSUM verify, defensive parsers, vectorized calendars,
interval/partition, seal, manifests), differential-tested vectorized
universe fast path in `partition.py`, `.github/workflows/ingest.yml`
(probe/full modes, immutable release publisher, metadata-only manifest
commits), pinned `requirements.txt`. 19/19 dev tests.
Live-source validation deliberately deferred to the Actions `probe` run
(S-ING-1) because exchange endpoints are unreachable from this container.
Ingestion RUN still requires the user's age public key.

## Pending user inputs (non-blocking for current work)

1. **Age public key for the holdout seal** — required before the first real
   ingestion run. Generate locally: install `age`, run `age-keygen -o akra-holdout-identity.txt`;
   keep that file private (it is the only decryption key; SPEC §9 requires
   user-sole custody) and provide ONLY the public line (`age1…`).
2. Engine v7 identification (see B2) — needed before Phase 5.

## Pending actions (next, in spec order)

1. **Phase 2 (remainder):** ingestion downloader + availability calendars + ingestion Actions workflow + release publisher.
2. **Phase 3 — Independent simulator** (SIMULATOR_SEMANTICS.md + implementation).
3. Phase 5 (revised): Independent Reference Ledger + golden fixtures + property-based invariant gate (FINAL-1.2 §13).

## Material changes / invalidated artifacts / required retraining

None. No experimental artifacts exist yet.

## Decisions (continued)

| # | Date | Decision | Rationale | Spec authority |
|---|---|---|---|---|
| D6 | 2026-08-25 | Phase-1 protocol frozen: Arm A = Donchian 60-bar breakout (long/short) on 4h bars, ATR(28)-based 2xATR stop / +3R target / 20-bar opposite-channel trailing exit / 42-bar (7-day) max holding period; 0.75% equity risk per trade, 15% notional cap, 10 max positions, 150% gross exposure; universe = point-in-time top-75 USDT-perps by trailing 30d median daily quote volume (>=25M USDT, >=90d history, >=99% completeness); costs = 5bps taker + tiered spread/slippage + real funding; eligible interval + 60/20/20 partition by mechanical rule. Full text: EXPERIMENT_PROTOCOL.md sha256 6283db52b10103c381530686478a21f205748960d5b6e2374c4ea27811a178ca. | Reasonable in-spec design decisions, recorded per s2; classic transparent momentum system, deterministic and unambiguous. | SPEC s2, s3, s5, s6, s7 (R03, R15, R16, R18, R53) |
| D7 | 2026-08-25 | Raw-lake storage: GitHub Release assets on immutable data releases (`raw-v<N>`), content-hashed manifests committed to git; NO market data, secrets, or decrypted holdout in git ever. Retention/recovery per HOLDOUT_POLICY.md §3. | User constraint (2026-08-25); SPEC §6, §9. | §6, §9 |
| D8 | 2026-08-25 | Seal cryptography: age (X25519, pyrage). USER generates the identity locally and provides only the public key; sealing is non-interactive public-key encryption; user alone can decrypt at Checkpoint 2. | Satisfies SPEC §9 user-sole-key custody while allowing non-interactive CI sealing. | §9 |
| D9 | 2026-08-25 | Validation-period positions still open at the holdout boundary are force-closed at the last pre-boundary 15m close for evaluation purposes (logged); labels whose information interval crosses a partition boundary are purged per §10. Prevents any evaluation path from needing sealed rows. | Consequence of §7 + §10; recorded now, implemented in simulator (Phase 3). | §7, §9, §10 |
| D10 | 2026-08-25 | Specification FINAL-1.2 adopted as authoritative (user-authorized): Engine v7 gate → Independent Reference Ledger gate; absolute independence from previous projects; property-based invariant tests added; B2 closed permanently. FINAL-1.1 preserved for audit. | Explicit user governance instruction. | FINAL-1.2 §13, Appendix A2 |
| D11 | 2026-08-25 | Simulator semantics decided and documented (SIMULATOR_SEMANTICS.md): collateralized-notional account model; fill formulas incl. take-profit at exact limit; per-bar processing order funding→exits→entries→protection→insolvency; conservative stop-first intrabar ambiguity; **gap-through stops fill at the bar open, never better**; insolvency/ruin fires whenever equity ≤ 0 including flat-negative-cash; management-action invariants (never widen, never grow). | Deterministic, conservative, honest-fill choices per SPEC §11; gap-through and flat-ruin added after dev tests exposed the generous variants. | FINAL-1.2 §11, §13 |
