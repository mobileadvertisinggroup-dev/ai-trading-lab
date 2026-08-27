"""Frozen protocol constants — single code-level source of truth.

Every value here transcribes EXPERIMENT_PROTOCOL.md (Phase-1 frozen,
sha256 recorded in build_state.json). Code must import these constants and
never restate the numbers. Changing any [Phase-1 frozen] value is a material
change under SPEC_FINAL-1.1.md §16 and requires the full invalidation
procedure — do not edit casually.
"""

# ---- time conventions ----------------------------------------------------
MS = 1
SEC = 1000 * MS
MIN = 60 * SEC
BAR_15M_MS = 15 * MIN
BAR_4H_MS = 4 * 60 * MIN
BARS_15M_PER_4H = 16
BARS_15M_PER_DAY = 96
FUNDING_INTERVAL_MS = 8 * 60 * MIN

# ---- Arm A signal parameters (protocol §2) -------------------------------
DONCHIAN_ENTRY_BARS = 60      # HH/LL lookback for entry breakout (4h bars)
DONCHIAN_EXIT_BARS = 20       # opposite-channel trailing exit lookback
ATR_PERIOD = 28               # Wilder ATR period on 4h bars
ATR_MIN_HISTORY_BARS = 3 * ATR_PERIOD  # ATR defined only with >= 3n bars
STOP_ATR_MULT = 2.0           # initial stop distance = 2 x ATR28
TARGET_R_MULT = 3.0           # target at +3R
MAX_HOLD_BARS_4H = 42         # frozen maximum holding period (7 days), §3

# ---- Arm A sizing and portfolio limits (protocol §2.5–2.6) ---------------
RISK_FRACTION = 0.0075        # 0.75% of equity risked per trade
NOTIONAL_CAP_FRACTION = 0.15  # per-position notional cap, fraction of equity
MIN_ORDER_NOTIONAL_USDT = 50.0
MAX_CONCURRENT_POSITIONS = 10
MAX_GROSS_EXPOSURE = 1.50     # gross open notional / equity

# ---- universe rule (protocol §4) -----------------------------------------
UNIVERSE_MIN_HISTORY_DAYS = 90
UNIVERSE_MIN_MEDIAN_DAILY_QVOL_USDT = 25_000_000.0
UNIVERSE_TRAILING_DAYS = 30
UNIVERSE_MIN_DEFINED_DAYS = 20     # days with defined daily qvol in window
UNIVERSE_MIN_COMPLETENESS = 0.99   # share of expected 15m bars, trailing 30d
UNIVERSE_TOP_N = 75
DAILY_QVOL_MIN_BARS = 90           # daily qvol defined only with >= 90/96 bars
# "tradable at t": a 15m bar within the last 2 days. PINNED PERMANENT
# INTERPRETATION (D52, independent adjudication): "permanent delisting"
# is operationally INFERRED after two days without bars — this frozen
# reading (forced_delist_close trigger) is never to be changed silently.
TRADABLE_LOOKBACK_MS = 2 * 24 * 60 * MIN

# ---- cost model (protocol §5) --------------------------------------------
TAKER_FEE = 0.0005            # 5.0 bps per side
TIER1_TOP_N = 10              # top 10 of U(t) by liquidity rank
HALF_SPREAD = {1: 0.0001, 2: 0.00025}   # tier -> fraction of price
SLIPPAGE = {1: 0.00015, 2: 0.00035}
STOP_SLIPPAGE_MULT = 2.0      # stop-market and forced-delist fills: 2x slip

# ---- data-quality / eligible interval (protocol §6) ----------------------
CONTEXT_SYMBOL = "BTCUSDT"
VALID_ROUND_MIN_ELIGIBLE = 30
INTERVAL_START_WINDOW_DAYS = 60
INTERVAL_START_VALID_FRACTION = 0.95
INTERVAL_END_BUFFER_MS = 48 * 60 * MIN

# ---- partition rule (protocol §7) ----------------------------------------
TRAIN_FRACTION = 0.60
VALIDATION_END_FRACTION = 0.80
EMBARGO_BARS_4H = MAX_HOLD_BARS_4H  # embargo = max holding period (spec §10)


def four_hour_floor(ts_ms: int) -> int:
    """Largest 4h UTC boundary <= ts_ms."""
    return ts_ms - (ts_ms % BAR_4H_MS)


def is_four_hour_boundary(ts_ms: int) -> bool:
    return ts_ms % BAR_4H_MS == 0


def partition_indices(n_boundaries: int) -> tuple[int, int]:
    """(i_t, i_v) per protocol §7: train [0,i_t), val [i_t,i_v), holdout [i_v,N)."""
    if n_boundaries <= 0:
        raise ValueError("no boundaries")
    i_t = int(TRAIN_FRACTION * n_boundaries)
    i_v = int(VALIDATION_END_FRACTION * n_boundaries)
    return i_t, i_v
