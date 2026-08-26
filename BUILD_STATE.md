# BUILD_STATE — AKRA AI TRADING LAB

Authoritative session-persistence record required by SPEC_FINAL-1.2.1.md §24.
Must agree with `build_state.json` at all times. Never rewrite earlier
decisions silently; append, don't erase.

## Current status

- **Current phase:** PHASE 2 INGESTION IN PROGRESS (2026-08-26): user supplied the age PUBLIC key (validated by pyrage round-trip, committed as `data/manifests/holdout_recipient.txt`) and authorized probe → full ingestion under FINAL-1.2.1. Probe run 1 (32935186732) failed on the S3 listing endpoint — data.binance.vision serves website HTML for query URLs — while CONFIRMING every S-ING-1 parser assumption against real data; fixed via VISION_LIST (commit 1a5b5f0). Probe run 2 (32935673870) PASSED: 824 included USDT-perp symbols, 124/124 tests on the runner, but timing projected ~9.3h SEQUENTIAL vs the 5.8h job budget → acquisition made concurrent in-job (D38); probe run 3 must show the measured concurrent projection within budget (PROJECTION-OK) before mode=full is triggered. Still prohibited: constitutional lock, shakedown, holdout access; paper-only; the private key is never requested or accepted outside the interactive Checkpoint-2 prompt. Previous: REVIEW GATE SATISFIED (final narrow review 2026-08-26: APPROVED subject to mechanical cleanup; all four mechanical corrections executed — see D37). Phase 2 may proceed: next steps are the user's age PUBLIC key, then the probe run, then (probe passing) full ingestion. Still prohibited: constitutional lock, shakedown, holdout access; paper-only. Previous: FINAL CORRECTIONS EXECUTED (2026-08-26): reviewer's FINAL CORRECTIONS message received in full; approvals recorded (D34); correction A (authoritative immutable-releases evidence endpoint) and correction B (complete one-time holdout evaluation gate with hash-chained state ledger) implemented and tested; 120/120 tests; FINAL_DELTA_RESPONSE.zip produced; STOPPED for final narrow review. Still blocked: age key, real ingestion, constitutional lock, shakedown, holdout access. Previous: DELTA PARTIALLY ACCEPTED + PC-1 ADOPTED (2026-08-25): user relayed the delta review — 111-test rerun and G03 correction ACCEPTED; PC-1 EXPLICITLY APPROVED by the user and now adopted as SPEC_FINAL-1.2.1 (authoritative). TWO FINAL SECURITY CORRECTIONS remain OUTSTANDING: the reviewer message 'INDEPENDENT DELTA REVIEW — FINAL CORRECTIONS' never reached this session and has been requested from the user; FINAL_DELTA_RESPONSE.zip is owed after it arrives and is executed. Still blocked: age key, real ingestion, constitutional lock, shakedown. Previous: REVIEW DELTA DELIVERED (verdict received 2026-08-25, recorded verbatim in reviews/REVIEW_VERDICT_PHASE6.md): Phase-6 CONDITIONALLY APPROVED; G01,G02,G04-G12 approved without correction; differential exact-equality policy APPROVED (binding interpretation recorded); Phase-1 protocol APPROVED as transparent baseline (not a claim of optimality/profitability); corrections executed per verdict §§1,5,6,7; PC-1 clarification PROPOSED and awaiting explicit user approval (verdict §4); STOPPED pending independent review of the delta package. Still blocked: constitutional lock, real ingestion, holdout-key request, shakedown. Previous state: REVIEW GATE + data-free scaffolding round complete (90/90 tests): DATA_DICTIONARY.md draft (F01-F28), Arm D regime model (lab/arms/regime.py, draft-frozen multiplier policy), Arm F RL environment (lab/arms/rl_env.py, gymnasium, deterministic), dashboard skeleton (lab/dashboard/build.py, ledger-derived, structurally market-data-free), INTEGRITY_TEST_POLICY.md draft (nothing locked); PLUS lab/features/build.py implementing DATA_DICTIONARY F01-F28 with the no-lookahead proof test (mutating every post-t bar leaves all 28 features bit-identical); 94/94 tests; PLUS scaffolding round 3: seven-arm orchestrator (lab/orchestration/competition.py — shared single-pass candidate generation, per-arm engines+governors, G pre-RL shadow with entry identity, failing arm invalidates the round for everyone), Arms B/C/E LightGBM pipeline shells with structural leak guards (lab/models/pipelines.py), deliberate-leak battery (tests/test_pipelines_leaks.py — label-in-features, off-dictionary column, purge violation, post-t feature, holdout contamination: each fails loudly); 106/106 tests. Gate terms unchanged: per user directive, NO constitutional lock, NO real ingestion, NO holdout-key requests, NO shakedown until the independent fixture review completes. INDEPENDENT_REVIEW_BUNDLE_PHASE6.zip committed at repo root (source commit 70605df); REVIEW_ISSUES_PHASE6.md answers reviewer issues A-D. Data-free scaffolding continues. Phase 6 status (prior) — External risk governor built and wired around Arm A (RISK_POLICY.md limits, D15); deferred golden fixtures G09/G10 added; ML label construction (spec §4, reproducible from the frozen Arm A ledgers) and variable-horizon purge/embargo (spec §10, holdout-contamination raises) built and tested; 76/76 tests. Model training remains blocked on real data (user age key + Actions runs). Phase 5 status: lab/refledger (Independent Reference Ledger, zero shared code, imports nothing from lab.*), lab/verify/differential.py (transaction-level comparison, first-divergence reporting, 1e-9 tolerance), 8 golden fixtures with hand-derived expected values (PENDING INDEPENDENT REVIEW), property-based invariants incl. randomized differential fuzzing (85 random fixtures, zero divergences); 61/61 tests. The gate found and adjudicated one real timing divergence (see D13). Phase 4 status: `lab/arms/indicators.py` (deterministic 4h aggregation, prior-N Donchian, Wilder ATR with 3n minimum) + `lab/arms/arm_a.py` (runner: boundary exits, breakout candidates over U(t) in rank order, sizing, tier costs, candidate ledger, equity curve) over the Phase 3 engine; 40/40 dev tests. Engine gained fill-anchored protection (protocol §2.4), per-position notional cap at fill (§2.5), and stop-priority on gap-through queued exits. Awaiting: user age key + Actions ingestion runs (Phase 2 runtime). Next: Phase 5 (Independent Reference Ledger + golden fixtures + property-based invariants). Phase 1 COMPLETE (: Arm A, max holding period, universe rule, data-quality rule, 60/20/20 partition rule authored and FROZEN in EXPERIMENT_PROTOCOL.md, sha256 `6283db52b10103c381530686478a21f205748960d5b6e2374c4ea27811a178ca`, before any ingestion). Phase 0 complete.
- **Last completed gate:** none (no gates reached yet)
- **Specification:** `SPEC_FINAL-1.2.1.md` (AUTHORITATIVE), sha256 `84309a6bf53f941b6bd6353d2b14640eddbbfcb0ad95d2dd752d822e1f9665f8`. Historical lineage only: FINAL-1.2 (`SPEC_FINAL-1.2.md`, sha256 `a29b6c9eb942cb56f7bfe44b1d3a861436875762ded37fbc37ecf96f5a369cc8`) and FINAL-1.1 (`SPEC_FINAL-1.1.md`, sha256 `5a7a3f5ce27d76ce97af5adf4b5a59e4f69a4ffd2b968195add7ae80f70c380a`, commit `16ec585`).
- **Checkpoint 1:** not reached
- **Checkpoint 2:** not reached
- **Holdout:** partition RULE frozen (EXPERIMENT_PROTOCOL.md §7); concrete dates not yet computable (no data ingested); nothing to quarantine yet
- **Dataset hashes:** none (no data ingested)
- **Model hashes:** none (no models trained)
- **Integrity-manifest hash:** none (constitutional tests not yet written)
- **Safe resume command:** clone this repo, read `SPEC_FINAL-1.2.1.md` (the authoritative specification, sha256 `84309a6bf53f941b6bd6353d2b14640eddbbfcb0ad95d2dd752d822e1f9665f8`), this file, and `build_state.json`, verify that sha256 matches, then continue from "Pending actions". Older specifications are historical lineage only.

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
| D12 | 2026-08-25 | Engine semantics refinements recorded in SIMULATOR_SEMANTICS.md before any official run: (a) protective levels submitted as offsets anchor at the FILL price (protocol §2.4); (b) per-position notional cap reduces qty at fill (§2.5); (c) a queued full-close whose bar opens beyond the stop executes as the STOP (§2.4 exit priority), event recorded. | Protocol conformance found during Phase 4 wiring. | protocol §2.4-2.5 |
| D13 | 2026-08-25 | Differential-gate adjudication #1: the reference ledger ingested same-timestamp exit instructions after its pending-exit step (one bar late); the main simulator + Arm A runner fill a queued exit at the queueing timestamp's open. Adjudicated cause: ambiguous wording in SIMULATOR_SEMANTICS §3.2 ("from strictly earlier timestamps"). Resolution: semantics clarified (queued at or before t, decisions use strictly earlier information; fill at t's open); REFERENCE LEDGER corrected, main simulator unchanged. Gate rerun: full agreement. | FINAL-1.2 §13 mismatch procedure followed: first divergence identified, cause classified as reference-ledger error rooted in spec wording, corrected, gate rerun. | FINAL-1.2 §13 |
| D14 | 2026-08-25 | Golden fixtures G01-G08 created with expected values derived by explicit hand arithmetic in the generator script (independent of both implementations). Marked PENDING INDEPENDENT REVIEW; user (or another reviewer, e.g. ChatGPT) must verify the derivations before the constitutional lock. Fixtures for risk-governor rejection, invalid RL action, partial-exit/breakeven, and synchronized-round failure are deferred to when those components exist (risk governor: Phase 6 start; orchestration: Phase 7) and recorded here so they are not forgotten. | FINAL-1.2 §12-13. | §12, §13 |
| D15 | 2026-08-25 | Risk-governor numeric limits set (RISK_POLICY.md): 1.0% max risk/trade, 150% gross, 120% per-direction correlated cap, 10 positions, 3% daily loss pause, 25% drawdown pause, protective-stop requirement with integrity pause, emergency pause, missing-data fail-safe. Frozen no later than the constitutional lock. Governor wraps every arm incl. Arm A; decisions recorded in candidate ledger + governor event ledger; governor rejection recorded as external restriction (Arm E rule 6). | SPEC §14. | §14 |
| D16 | 2026-08-25 | Differential policy: EXACT bit equality binding on every compared numeric field (review issue A); tolerance removed from verdicts, retained only as a divergence-report annotation. Adjudication #2: equity/exposure ACCUMULATION ORDER added to SIMULATOR_SEMANTICS §1 (sequential from cash, position-id order); reference ledger aligned; simulator unchanged; 79/79 under exact equality. Policy awaits reviewer approval before the constitutional differential test is locked. | FINAL-1.2 §13; reviewer issue A. | §13 |
| D17 | 2026-08-25 | G11 (partial exit + breakeven; engine scope, layers 1+3, refledger N/A per frozen subset) and G12 (synchronized-round failure; new component lab/orchestration/rounds.py) created and passing. Golden-fixture gate EXPLICITLY INCOMPLETE until independent review of G01-G12. | Reviewer issue B. | §12, §13, §23 |
| D18 | 2026-08-25 | Release integrity model restated honestly (reviewer issue C): tamper-evidence via git-pinned sha256 manifests + mandatory download verification, NOT platform immutability (setting unverified; raw-v1 nonexistent); workflow now draft→upload-all→publish. | Reviewer issue C. | §6 |
| D19 | 2026-08-25 | Seal conformance position (reviewer issue D): age X25519 with user-sole identity + interactive-only secret entry + all-hash gate + recorded Checkpoint-2 authorization reported as CONFORMING to §9; identity possession necessary but not sufficient within project tooling; residual user-bypass caveat stated under the spec's §8 honesty model. Awaits reviewer acceptance or a versioned clarification. | Reviewer issue D. | §9 |
| D20 | 2026-08-25 | Research-phase dashboard is a static ledger-derived generated artifact (GitHub Pages hostable, itself part of the audit trail) instead of the §27-default React/Next app; documented reason: no server runtime exists in the project's GitHub-Actions/Pages infrastructure. Interactive UI can be layered later without touching ledger semantics. | SPEC §26-27 ("unless discovery establishes a stronger documented reason"). | §26, §27 |
| D21 | 2026-08-25 | Arm D regime model draft-frozen: BTC-context SMA(60)/SMA(180) trend classification + trailing-90th-percentile rvol(20) stress detector (1080-bar window); multiplier policy stress 0.50/0.50, uptrend 1.00 long / 0.00 short, downtrend 0.00/1.00, sideways 0.50/0.50; insufficient-history fail-safe = stress (reduce). Final freeze at Checkpoint 2. | SPEC §3 Arm D. | §3 |
| D22 | 2026-08-25 | Arm F RL env scaffolded: episode = one Arm-A trade replayed through the main engine (invariants enforced by the engine itself); Discrete-6 action space; observation per spec Arm F list; terminal reward = net R minus turnover/invalid-action/drawdown penalties (constants DRAFT until pre-training freeze). | SPEC §3 Arm F. | §3 |
| D23 | 2026-08-25 | Orchestrator semantic: a bucketed arm's per-position notional cap scales with its size multiplier so E/D/G fill exactly mult × Arm A's post-cap size (spec §3: fractions of Arm A's SIZE). Found by test: with the cap binding, a pre-cap multiplier had no effect. | Spec §3 Arm E/G sizing composition. | §3 |
| D24 | 2026-08-25 | Pipeline shells carry structural leak guards as API contracts: forbidden label/outcome columns, off-dictionary feature names, and purge-violating training examples all raise LeakError at fit time. These become constitutional deliberate-leak tests at lock. | Spec §15 deliberate-leak rejection. | §10, §15 |
| D25 | 2026-08-25 | Verdict recorded verbatim (reviews/REVIEW_VERDICT_PHASE6.md). Approvals: fixtures G01,G02,G04-G12; exact-equality differential policy with binding interpretation (exact decides pass/fail; 1e-9 diagnostic only, may never convert mismatch to pass; frozen summation order binding; future mismatches -> first-divergence adjudication); refledger structural independence for the shared subset; Phase-1 protocol as transparent baseline. | Independent review verdict. | §12-§13, Phase 1 |
| D26 | 2026-08-25 | G03 versioned numeric correction per verdict §1: v1 (stored float artifact 9979.960015000002) superseded -> fixtures/golden/superseded/G03_gross_winner_net_loser_v1.json, sha256 dc1add29ecf69bce81d1e61b3d369c2dd3e28701f0e624fd86df1c8ba0247d28; v2 stores the canonical hand-derived 9979.960015, sha256 8bb5363d9321480301b34c010e072c78d838515507c619ce61bf6f672366586e. NOT a simulator disagreement — sim and refledger agreed; the defect was the stored layer-1 value. New LAYER-1 COMPARISON RULE for all engine fixtures: Decimal-quantize implementation cash to the derivation's 6 decimals, exact equality to the canonical value, plus abs bound 1e-8 — broad pytest.approx removed. Reruns: full suite 111/111 (simulator, reference ledger, exact differential, goldens G01-G12, randomized property fuzz). | Verdict §1. | §12-§13 |
| D27 | 2026-08-25 | PC-1 partition/quarantine clarification PROPOSED (PROPOSED_CLARIFICATION_PC1.md): source acquisition (ephemeral, protected, verified-destroyed staging) vs readable project ingestion; NOT adopted — awaiting explicit user approval; real ingestion prohibited until then. Staging protections implemented as binding regardless (HOLDOUT_POLICY §4a; workflow destruction verification). | Verdict §4. | §2, §7, §9 |
| D28 | 2026-08-25 | Actions hardening per verdict §5: actions/checkout pinned to 08eba0b27e820071cde6df949e0beb9ba4906955 (v4.3.0) and actions/setup-python to a26af69be951a213d495a4c3e4e4022e16d87065 (v5.6.0), provenance = git ls-remote against github.com 2026-08-25; release transaction reordered draft -> upload-all -> download-and-verify-hashes -> commit+push manifests -> publish (failed push leaves an unofficial draft); repo release-setting evidence captured to manifests at first ingestion; probe now measures per-symbol-month timing and projects total vs the job timeout (never publish a partial dataset as complete — over-budget means redesign, not truncation). | Verdict §5. | §6 |
| D29 | 2026-08-25 | Point-in-time exclusion registry v1 (data/manifests/exclusion_registry_v1.json): versioned, append-only category rules (stablecoin bases incl. USDE/USDS/PYUSD/RLUSD/etc., leveraged/inverse pattern, wrapped-quote); ingest classifies every discovered symbol and preserves registry version+sha256+all classifications in the dataset manifest; historical classifications never silently changed — changes are new registry versions. | Verdict §6. | §4 |
| D30 | 2026-08-25 | Unseal gate implemented (lab/data/unseal.py + lab/data/authz.py): strict verification of ALL hashes against independently recomputed current values; interactive-TTY-only identity entry, never stored; output refused inside the project tree; consumption recorded immutably without the key; GuardedLake now uses the same strict verifier. Constitutional-prototype NEGATIVE tests prove fabricated/nonempty-hash authorizations can never grant access at either layer (tests/test_authz_negative.py). | Verdict §7. | §9, §22 |
| D31 | 2026-08-25 | STOP honored per verdict §8: delta package delivered; no ingestion, no key request, no constitutional lock, no shakedown, no strategy change, no holdout access; awaiting independent review of the delta and explicit user approval (incl. PC-1). | Verdict §8. | — |
| D32 | 2026-08-25 | PC-1 ADOPTED with explicit user approval ("PC-1 is approved by us"): SPEC_FINAL-1.2.1.md is now authoritative, sha256 84309a6bf53f941b6bd6353d2b14640eddbbfcb0ad95d2dd752d822e1f9665f8; FINAL-1.2 preserved unchanged for audit. Amendment: §9.3a acquisition-vs-ingestion + §2 phase wording + R53 reading (Appendix A3). EXPERIMENT_PROTOCOL.md deliberately untouched (its cited sections §2,3,5,6,7 are unchanged in 1.2.1 — no hash churn on the frozen doc). | User approval relayed 2026-08-25. | §2, §9, R53 |
| D33 | 2026-08-25 | Delta review partial outcome recorded: 111/111 rerun and G03 v2 ACCEPTED. The reviewer's "INDEPENDENT DELTA REVIEW — FINAL CORRECTIONS" message (two security corrections) was NOT received in this session; requested from the user verbatim before anything is executed or FINAL_DELTA_RESPONSE.zip is produced — the corrections will not be guessed. | Honest-record rule; verdict §8 discipline. | — |
| D34 | 2026-08-26 | Reviewer approvals recorded verbatim (reviews/REVIEW_FINAL_CORRECTIONS.md): PC-1 explicitly approved (already adopted as FINAL-1.2.1, D32); G03 v2 APPROVED (canonical 9979.960015; lineage proper; quantize-exact + 1e-8 guard accepted; layer-1 classification confirmed); 111-test rerun accepted; full-SHA Action pinning approved; draft→upload→verify→manifest-push→publish ordering approved; exclusion registry approved for first ingestion (version+hash+classifications preserved in dataset manifest). | FINAL CORRECTIONS message. | — |
| D35 | 2026-08-26 | Correction A: workflow evidence step now calls the authoritative GET /repos/{owner}/{repo}/immutable-releases endpoint via lab/tools/immutable_evidence.py, recording HTTP status, body, UTC timestamp, repository, workflow commit, and interpretation; 200=ENABLED, 404=NOT ENABLED/unavailable, anything else=UNVERIFIED never inferred; tamper-evident git-pinned hashes remain the reliance basis absent a successful 200. | FINAL CORRECTIONS §A. | §6 |
| D36 | 2026-08-26 | Correction B: one-time holdout evaluation gate completed — manifest-bound artifact identity (filename + sha256), no general decrypt operation, controlled evaluate_holdout with OPENING_STARTED/CONSUMED/FAILED_CLOSED in the append-only hash-chained holdout_state.jsonl (consumption by LEDGER, not JSON rewrite), finally-block wipe with verified absence on success AND failure, fresh-tmpfs-only output, second-opening refusal absent RECOVERY_AUTHORIZED (formal adjudication), corrupt chain blocks all access (also enforced in authz/GuardedLake). Nine required negative tests pass (tests/test_holdout_gate.py). Gate marked implementation-complete ONLY when the real frozen evaluator is plugged in (currently a deterministic dummy). | FINAL CORRECTIONS §B. | §9, §22 |
| D37 | 2026-08-26 | Final narrow review recorded (reviews/REVIEW_FINAL_NARROW.md): APPROVED — PC-1/FINAL-1.2.1, correction A endpoint, manifest-bound artifact verification, controlled evaluation architecture, chained state ledger, cleanup structure, fail-closed corruption, 120-test run; no further review ZIP. Four mechanical corrections executed: (1) state consistency — authoritative spec = SPEC_FINAL-1.2.1.md sha256 84309a6b… everywhere incl. safe-resume; PC-1 doc retitled ADOPTED with history preserved; stale pending fields cleared; fixtures G01-G12 marked REVIEWED. (2) tmpfs actually enforced — decrypted output must be on verified tmpfs/ramfs per /proc/mounts; fresh disk-backed dir refused (tested). (3) recovery not self-authorizing — append_event refuses RECOVERY_AUTHORIZED and OPENING_STARTED; opening_permitted ignores the string; ANY prior opening permanently blocks. (4) atomic claim — claim_opening under exclusive flock with chain verify + fsync; two-process concurrency test proves exactly one opens; every post-claim exception (incl. identity entry) closes FAILED_CLOSED, with OPENING_STARTED as the backstop. | Final narrow review §§1-4. | §9, §22, §24 |
| D38 | 2026-08-26 | Acquisition made CONCURRENT within the single ingestion job (ThreadPoolExecutor, ACQ_WORKERS=12, env-overridable): probe run 2 (32935673870, PASSED — 824 included symbols, 124/124 on the runner) measured 0.68s/symbol-month sequential => ~9.3h for 824 symbols x ~60 months vs the 5.8h budget. Multi-job sharding REJECTED because PC-1 (spec §9.3a / HOLDOUT_POLICY §4a) forbids holdout-range staging from leaving the runner as any artifact — acquisition must complete inside one RUNNER_TEMP lifetime. Symbols are independent (distinct staging paths, pure parsers); any worker failure fails the whole run (never publish a partial dataset, verdict §5.5). Probe now measures REAL concurrent throughput on a 12-month non-holdout batch and prints PROJECTION-OK / PROJECTION-EXCEEDS-BUDGET; mode=full is triggered only after PROJECTION-OK. | Verdict §5.5 measured chunking plan; PC-1. | §6, §9.3a |
