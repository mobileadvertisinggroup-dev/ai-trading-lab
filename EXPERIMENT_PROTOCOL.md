# EXPERIMENT_PROTOCOL — AKRA AI TRADING LAB

Status: **PHASE-1 FROZEN** (Arm A, maximum holding period, universe rule,
data-quality rule, partition rule). Frozen 2026-08-25, before any data
ingestion, candidate generation, label creation, or model training, as
required by SPEC_FINAL-1.1.md §2, §3, §5, §6, §7 (R03, R15, R16, R18, R53).

Sections marked *[Phase-1 frozen]* may not change without a new protocol
version, invalidation, and the full material-change procedure of spec §16.
Sections marked *[to be frozen later]* are completed and frozen at the
spec-mandated later point (no later than Checkpoint 2).

Everything in this document is deterministic. Where this document and
SIMULATOR_SEMANTICS.md both speak, this document defines *what* the strategy
does; SIMULATOR_SEMANTICS.md defines *how* the simulator executes it.

---

## 1. Conventions *[Phase-1 frozen]*

- All timestamps UTC. A "4h boundary" is 00:00, 04:00, 08:00, 12:00, 16:00,
  20:00 UTC.
- A bar is identified by its **open time**; a bar is "completed at" its close
  time. "The bar closing at t" means the 4h bar with open time t−4h.
- **Decision timestamp** t: a 4h boundary. All information used at t must be
  fully observable strictly before t (only completed bars).
- Raw market data layer: **15-minute klines** (OHLCV + quote volume) and
  **funding rates** per symbol. 4h bars are derived deterministically by
  aggregating the 16 15m bars of each 4h window (open = first open,
  high = max high, low = min low, close = last close, volumes summed).
  A derived 4h bar exists only if all 16 15m bars exist.
- "Daily quote volume" on calendar day d = sum of quote volume of the 96 15m
  bars of d (only defined if ≥ 90 of the 96 bars exist; otherwise undefined).
- Indicator definitions:
  - `HH(n, t)` / `LL(n, t)`: highest high / lowest low of the n completed 4h
    bars strictly before the bar closing at t (i.e., excluding the signal bar
    itself).
  - `ATR(n, t)`: Wilder's average true range over 4h bars, period n, computed
    on bars completed at or before t, seeded with the simple mean of the
    first n true ranges. Defined only when ≥ 3n completed 4h bars exist.
- Monetary quantities in USDT. Position size is expressed as base-asset
  quantity `qty`; notional = qty × price.

## 2. Arm A — Transparent Control *[Phase-1 frozen]*

Arm A is a classic Donchian-channel momentum/trend-breakout system, long and
short, on USDT perpetuals.

### 2.1 Candidate times

Every 4h boundary t that is a **valid round** (§6). One evaluation per
eligible symbol per boundary.

### 2.2 Candidate generation

At decision timestamp t, for each symbol s in the universe U(t) (§4) with no
open position and no same-round pending entry in s, using the 4h bar of s
closing at t ("signal bar"):

- **Long candidate** iff `close(signal bar) > HH(60, t)`.
- **Short candidate** iff `close(signal bar) < LL(60, t)`.
- Requires `ATR(28, t)` defined and > 0, and all inputs present; otherwise no
  candidate (missing-data rule §7).

60 4h bars = 10 days of price history. A symbol can never produce both a
long and short candidate at the same t. Symbols with an open position are
excluded from candidate generation (no pyramiding, no signal-driven
reversal; exits are governed solely by §2.4).

### 2.3 Entry

- Candidates are submitted at t; entry executes at the **open of the first
  15m bar at or after t** (normally the bar opening exactly at t).
- Entry fill price assumption: `open × (1 + hs(s,t) + slip(s,t))` for longs,
  `open × (1 − hs(s,t) − slip(s,t))` for shorts, where hs = half-spread and
  slip = slippage per §5. Taker fee per §5 charged on fill notional.
- If the first 15m bar at or after t is missing for s, the candidate is
  **cancelled** (never deferred to a later bar) and logged as such.

### 2.4 Initial protection, exits, and management

Let `fill` = entry fill price and `Rdist = 2 × ATR(28, t)` (from the
decision timestamp; never recomputed).

- **Initial stop** (stop-market): long `fill − Rdist`; short `fill + Rdist`.
- **Target** (take-profit): long `fill + 3 × Rdist`; short `fill − 3 × Rdist`
  (i.e., +3R).
- **Trailing channel exit**: at each completed 4h bar after entry, if
  `close < LL(20, ·)` for a long, or `close > HH(20, ·)` for a short, close
  the full position at the open of the next 15m bar (market exit with §5
  costs).
- **Time exit (maximum holding period)**: if the position is still open when
  **42 4h bars** have completed since the entry decision timestamp t
  (= 7 calendar days), close the full position at the open of the next 15m
  bar (market exit with §5 costs). This 42-bar maximum holding period is the
  frozen §5/R15 strategy parameter.
- Stop and target are monitored on every 15m bar (SIMULATOR_SEMANTICS.md
  defines fill mechanics and the conservative stop-first rule for intrabar
  ambiguity).
- Arm A performs no partial exits, no stop moves, no breakeven moves, and no
  re-entries before a fresh §2.2 candidate.
- Exit priority within the same 15m bar: stop, then target, then trailing
  exit, then time exit.

### 2.5 Position sizing

At decision timestamp t with current account equity E(t):

- Risk budget per trade: `0.75% × E(t)`.
- `qty = (0.0075 × E(t)) / Rdist`, so a stop-out loses ≈ 1R ≈ 0.75% of
  equity before costs.
- **Per-position notional cap**: `min(qty × fill, 0.15 × E(t))`; qty reduced
  to fit.
- **Minimum order notional**: 50 USDT; smaller sized candidates are rejected
  and logged (rejection, not a trade).

### 2.6 Portfolio limits (Arm A strategy limits)

- Maximum concurrent open positions: **10**.
- Maximum gross open notional: **150% of equity** (max effective leverage
  1.5×; margin mechanics in SIMULATOR_SEMANTICS.md).
- When same-round candidates exceed remaining capacity, they are processed
  in deterministic order: descending trailing-liquidity rank (§4 ranking);
  ties broken lexicographically by symbol. Candidates that do not fit are
  rejected and logged with reason `capacity`.
- These are Arm A's own limits. The external risk governor (spec §14) wraps
  every arm — including Arm A — with its own, never-looser, limits
  (RISK_POLICY.md, *[to be frozen later]* no later than the constitutional
  lock).

### 2.7 Missing-data behavior (strategy level)

- Any missing input at candidate evaluation → no candidate for that symbol
  (logged `missing_data`).
- Open position, missing 15m bar: no management evaluation occurs on the
  missing bar; evaluation resumes on the next existing bar using its prices.
  Every such deferral is logged.
- Open position, symbol delisted / trading halted permanently: position is
  closed at the last traded 15m close with double slippage per §5, logged
  `forced_delist_close`. This is honest-availability handling per spec §6.
- Round-level invalidity is defined in §6 and handled identically for all
  arms.

## 3. Maximum holding period *[Phase-1 frozen]*

**42 completed 4h bars (7 days)** from the entry decision timestamp, closing
at the open of the next 15m bar with full §5 costs, as specified in §2.4.
This parameter governs candidate labels, the §10 purge/embargo horizon
(embargo ≥ 42 4h bars), and all phases identically.

## 4. Universe rule (mechanical, point-in-time) *[Phase-1 frozen]*

Evaluated at every decision timestamp t, from information strictly before t.

**Instrument scope**: USDT-margined linear perpetual futures on the primary
data source (§8). Excluded categories: stablecoin-base pairs (base asset
pegged to fiat), and leveraged/inverse token products.

**Eligibility at t** — symbol s is eligible iff all of:

1. **History**: first available 15m bar of s is ≥ 90 days before t.
2. **Liquidity**: median daily quote volume over the trailing 30 calendar
   days before t (days with undefined volume excluded from the median;
   ≥ 20 defined days required) is ≥ **25,000,000 USDT**.
3. **Completeness**: ≥ 99% of the 2,880 expected 15m bars in the trailing 30
   days before t exist.
4. **Availability**: s is tradable at t (not delisted/halted at t).

**Selection**: rank eligible symbols by the §4.2 liquidity median,
descending, ties lexicographic; `U(t)` = top **75** (all eligible if fewer).
This trailing-liquidity rank is also the §2.6 processing order and is
preserved per-round in the ledgers.

The present-day universe is never applied retroactively; U(t) is
recomputed mechanically at every historical t. Compute-budget scope
reduction, if ever required, follows spec §25 exactly (75 → 50 → 30 by
lowering the top-N cutoff only; the eligibility rule itself never changes).

## 5. Cost model *[Phase-1 frozen]*

Applied identically to all seven arms in all phases.

- **Taker fee**: 5.0 bps (0.050%) of fill notional, per side, all fills.
- **Liquidity tiers**: tier 1 = top 10 symbols of U(t) by §4 rank at the
  relevant decision/entry round; tier 2 = all others.
- **Half-spread** hs: tier 1 = 1.0 bp; tier 2 = 2.5 bps.
- **Slippage** slip: tier 1 = 1.5 bps; tier 2 = 3.5 bps. Stop-market fills
  incur 2× slip (stops execute in adverse conditions). Forced delisting
  closes incur 2× slip.
- **Funding**: at each exchange funding timestamp (every 8h), open positions
  pay/receive `funding_rate × notional` at the funding timestamp's mark
  (15m close), sign per exchange convention, from raw funding data. Missing
  funding data for an open position's timestamp: applied as 0 and logged
  (never invented).

## 6. Data-quality rule and eligible interval *[Phase-1 frozen]*

- **Market-context symbol**: BTCUSDT perpetual.
- A 4h boundary t is a **valid round** iff the BTCUSDT 4h bar closing at t
  exists (all 16 15m bars) and ≥ 30 symbols are eligible per §4 at t.
  Invalid rounds generate no candidates for any arm and are excluded — 
  identically for every arm — from all evaluation. Every invalid round is
  logged with its reason.
- **Eligible continuous historical interval**: start = the earliest 4h
  boundary T₀ such that T₀ and ≥ 95% of all 4h boundaries in
  [T₀, T₀ + 60 days] are valid rounds; end = the last valid round at least
  48h before the ingestion-freeze timestamp (recorded in BUILD_STATE at
  ingestion). Both are computed mechanically by code, not chosen by
  inspection.

## 7. Partition rule *[Phase-1 frozen]*

Let B = the ordered list of ALL 4h boundaries (valid and invalid) in the
eligible interval, indexed 0 … N−1. With `i_t = floor(0.6 × N)` and
`i_v = floor(0.8 × N)`:

- **Training**: boundaries with index in `[0, i_t)`
- **Validation**: `[i_t, i_v)`
- **Sealed historical holdout**: `[i_v, N−1]`

Boundaries are 4h decision boundaries by construction (snapping requirement
satisfied). The 60/20/20 ratio is binding (R18). The holdout **date range**
(the timestamps of `[i_v, N−1]`, plus the trailing data needed only by those
rounds) is the quarantined range of spec §9 at every data layer; the
quarantine boundary for raw data is the open time of the first 15m bar
belonging to round `i_v`'s execution window. Because indices derive
mechanically from N (a function of the frozen §6 rule and the ingestion
date), the partition is established before ingestion, mechanically, as
required by R53/R54.

Label information intervals (spec §10): each candidate's interval is
[candidate timestamp, final Arm A exit timestamp]; training examples whose
interval crosses `i_t` are purged; embargo = 42 4h bars (= the maximum
holding period) applied after `i_t` and `i_v`.

## 8. Primary data source *[Phase-1 frozen]*

**Binance USDT-M perpetual futures**: 15m klines and funding-rate history,
via the public REST API and the data.binance.vision bulk archives, ingested
from GitHub Actions runners (BUILD_STATE decision D3). Delisted symbols'
history is included where the source provides it; survivorship coverage is
audited at ingestion and honestly reported in LIMITATIONS.md with realism
loss quantified (spec §6). If discovery during ingestion shows the source
cannot provide survivorship-adequate history, the spec §6 fallback procedure
applies (document, quantify, limit conclusions — never invent data).

## 9. Later-frozen protocol elements *[to be frozen later]*

Completed and frozen at the spec-mandated points, recorded here by
reference so this document remains the protocol index:

- Feature set for Arms B/C/E and regime-model definition for Arm D — frozen
  before training (Phase 6), documented in DATA_DICTIONARY.md and
  MODEL_CARDS.md.
- Arm E utility formula and constants — already fixed by spec §3 (Arm E);
  bucket boundaries and mapping frozen before holdout.
- RL reward coefficients, observation space, and seed-selection rule (Arm F)
  — frozen before holdout.
- Primary risk-adjusted statistic, multiple-comparison correction,
  bootstrap parameters, learnability thresholds, minimum useful improvement
  — frozen at Checkpoint 2 (spec §17–§19, §22).
- Risk-governor numeric limits — RISK_POLICY.md, frozen before the
  constitutional lock (Phase 8 prerequisite).

None of these may alter any *[Phase-1 frozen]* section.
