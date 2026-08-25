# DATA_DICTIONARY — AKRA AI TRADING LAB

Status: **DRAFT** (review-gate period). The feature set below is the
candidate feature dictionary for Arms B (filter), C (ranker), and E
(sizing). It is **frozen before any model training** (spec §22 list) and
recorded here first so the freeze is a review event, not an improvisation.

Binding construction rules (already enforced in code paths that will build
these features):

1. Every feature is computed at the candidate's decision timestamp `t` from
   information **strictly before t** — completed bars only, the same
   convention as EXPERIMENT_PROTOCOL.md §1. No feature may read the entry
   fill, any post-t bar, any label, any other arm's output, or any
   holdout-range row (GuardedLake enforces the last).
2. All preprocessing (scaling, encoding, imputation, selection) is fitted
   on training-partition rows only (spec §10).
3. Feature vectors are stored with the candidate ledger row and a
   `feature_set_version`; the frozen version's file hash enters the
   Checkpoint-2 manifest.

## 1. Candidate-intrinsic features (from the candidate ledger row)

| # | Name | Definition |
|---|---|---|
| F01 | side | +1 long / −1 short |
| F02 | atr_pct | ATR(28,t) / signal close |
| F03 | breakout_strength | side × (close − breached channel level) / ATR(28,t); channel level = HH(60,t) for longs, LL(60,t) for shorts |
| F04 | channel_width | (HH(60,t) − LL(60,t)) / close |
| F05 | rank_frac | liquidity rank / n_eligible (0 = most liquid) |
| F06 | n_eligible | number of eligible candidates at t (context for C) |

## 2. Symbol price/trend features (derived 4h series, completed bars < t)

| # | Name | Definition |
|---|---|---|
| F07–F10 | ret_1, ret_5, ret_20, ret_60 | log return of close over the last 1 / 5 / 20 / 60 4h bars |
| F11 | rvol_20 | std of 1-bar log returns over 20 bars |
| F12 | rvol_ratio | rvol_20 / rvol_60 (volatility regime of the symbol) |
| F13 | trend_sma20 | (close − SMA(20)) / ATR(28,t) |
| F14 | trend_sma60 | (close − SMA(60)) / ATR(28,t) |
| F15 | dist_opposite | side × (close − opposite 20-bar channel) / ATR(28,t) (room before the trailing exit) |
| F16 | breakout_run | consecutive completed bars with close beyond the prior-60 channel midpoint, signed by side, capped ±10 |

## 3. Market-context features (BTCUSDT + cross-sectional, < t)

| # | Name | Definition |
|---|---|---|
| F17–F19 | btc_ret_5, btc_ret_20, btc_ret_60 | BTC log returns over 5 / 20 / 60 4h bars |
| F20 | btc_rvol_20 | BTC 20-bar realized vol |
| F21 | breadth_sma20 | fraction of U(t) symbols with close > their SMA(20) |
| F22 | round_side_count | number of same-side candidates generated this round (incl. this one) |
| F23 | regime_code | Arm D regime at t (categorical: 0 up, 1 down, 2 sideways, 3 stress) — input feature only; the multiplier POLICY remains Arm D's |

## 4. Liquidity and funding features (< t)

| # | Name | Definition |
|---|---|---|
| F24 | log_liq | log10 of trailing 30d median daily quote volume (the §4 ranking metric) |
| F25 | funding_last | last funding rate before t |
| F26 | funding_mean_3d | mean funding rate over the 9 funding events before t |

## 5. Calendar features

| # | Name | Definition |
|---|---|---|
| F27 | hour_slot | t's UTC 4h slot (0–5), one-hot |
| F28 | dow | day of week (0–6), one-hot |

## Exclusions (deliberate)

- No order-book or trade-tape features (raw layer is 15m klines + funding).
- No cross-arm features, no model outputs as inputs (except F23, which is
  the independently defined regime CLASSIFIER output, permitted as Arm D's
  published environment state; if the reviewer objects, F23 is dropped
  without touching anything else).
- No features referencing partition identity, calendar date beyond
  F27/F28, or any post-decision quantity.

## Freeze procedure

When training is unblocked (post-review, post-ingestion): this document is
finalized, its sha256 recorded in BUILD_STATE and the Checkpoint-2
manifest, and `lab/features/build.py` (to be written against this table)
becomes the only feature builder. Any later change is a §16 material
change.
