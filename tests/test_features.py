"""Feature-builder tests: dictionary conformance + the no-lookahead proof."""
import numpy as np
import pytest

from lab import protocol as P
from lab.arms.indicators import SymbolSeries
from lab.features.build import FeatureSeries, build_features

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)


def bars_15m(levels_4h, wiggle=0.1):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
            "low": lv - wiggle, "close": lv.copy()}


def fseries(levels):
    d = bars_15m(levels)
    ss = SymbolSeries(d["open_time"], d["open"], d["high"], d["low"],
                      d["close"])
    return FeatureSeries(ss.t4, ss.close4, ss.hh_entry, ss.ll_entry,
                         ss.hh_exit, ss.ll_exit)


CONTEXT = {"breadth_sma20": 0.6, "round_side_count": 2, "regime_code": 0,
           "liq_median": 5e7, "funding_last": 1e-4, "funding_mean_3d": 5e-5}


def make_candidate(n_bars, close, hh, ll, atr, side=1):
    return {"t": T0 + n_bars * H4, "symbol": "AAAUSDT", "side": side,
            "close": close, "hh_entry": hh, "ll_entry": ll, "atr": atr,
            "r_dist": 2 * atr, "rank": 3, "n_eligible": 40,
            "equity": 10_000.0, "qty_submitted": 1.0}


def test_feature_values_hand_checked():
    n = 96
    levels = [100.0] * (n - 1) + [105.0]
    sym = fseries(levels)
    btc = fseries([50.0] * n)
    cand = make_candidate(n, close=105.0, hh=100.1, ll=99.9, atr=0.375)
    f = build_features(cand, sym, btc, CONTEXT)
    assert f["F01_side"] == 1
    assert f["F02_atr_pct"] == pytest.approx(0.375 / 105)
    assert f["F03_breakout_strength"] == pytest.approx((105 - 100.1) / 0.375)
    assert f["F04_channel_width"] == pytest.approx(0.2 / 105)
    assert f["F05_rank_frac"] == pytest.approx(2 / 40)
    assert f["F07_ret_1"] == pytest.approx(np.log(105 / 100))
    assert f["F09_ret_20"] == pytest.approx(np.log(105 / 100))
    assert f["F13_trend_sma20"] == pytest.approx((105 - 100.25) / 0.375)
    assert f["F16_breakout_run"] == 1.0        # first bar above midpoint
    assert f["F17_btc_ret_5"] == pytest.approx(0.0)
    assert f["F21_breadth_sma20"] == 0.6
    assert f["F23_regime_code"] == 0
    assert f["F24_log_liq"] == pytest.approx(np.log10(5e7))
    assert f["F27_hour_slot"] == ((T0 + n * H4) // H4) % 6
    assert 0 <= f["F28_dow"] <= 6
    assert f["feature_set_version"] == "features-v1-draft"
    assert len([k for k in f if k.startswith("F")]) == 28


def test_short_side_signs_mirror():
    n = 96
    levels = [100.0] * (n - 1) + [95.0]
    sym = fseries(levels)
    btc = fseries([50.0] * n)
    cand = make_candidate(n, close=95.0, hh=100.1, ll=99.9, atr=0.375,
                          side=-1)
    f = build_features(cand, sym, btc, CONTEXT)
    # breached level for shorts is LL; strength positive when below it
    assert f["F03_breakout_strength"] == pytest.approx((99.9 - 95) / 0.375 * 1)
    assert f["F03_breakout_strength"] > 0
    assert f["F16_breakout_run"] == 1.0        # signed by side


def test_no_lookahead_future_mutation_changes_nothing():
    """Constitutional-prototype: mutate EVERY bar at/after t — every feature
    must be bit-identical."""
    n_hist, extra = 96, 20
    levels = [100.0 + 0.3 * np.sin(i / 5.0) for i in range(n_hist)] \
        + [105.0] + [107.0] * extra
    t_cand = T0 + (n_hist + 1) * H4      # candidate sees bars 0..n_hist

    def features_from(levels_variant):
        sym = fseries(levels_variant)
        btc = fseries([50.0] * len(levels_variant))
        cand = make_candidate(n_hist + 1, close=105.0, hh=100.4, ll=99.6,
                              atr=0.4)
        return build_features(cand, sym, btc, CONTEXT)

    base = features_from(levels)
    mutated = list(levels)
    for k in range(n_hist + 1, len(mutated)):
        mutated[k] = 999.0                # absurd future
    alt = features_from(mutated)
    assert base == alt


def test_missing_history_yields_nan_not_fabrication():
    n = 30                                # < 60-bar windows
    sym = fseries([100.0] * n)
    btc = fseries([50.0] * n)
    cand = make_candidate(n, close=100.0, hh=100.1, ll=99.9, atr=0.2)
    f = build_features(cand, sym, btc, CONTEXT)
    assert np.isnan(f["F10_ret_60"])
    assert np.isnan(f["F14_trend_sma60"])
