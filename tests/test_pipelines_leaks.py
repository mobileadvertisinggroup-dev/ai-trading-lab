"""B/C/E pipeline shells end-to-end on synthetic data + the deliberate-leak
battery (constitutional prototypes: leaks MUST fail loudly)."""
import numpy as np
import pytest

from lab import protocol as P
from lab.models.pipelines import (E_BUCKETS, FilterPipeline, LeakError,
                                  RankerPipeline, SizerPipeline,
                                  validate_columns, validate_split)

H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)
FEATS = ["F02_atr_pct", "F03_breakout_strength", "F08_ret_5", "F11_rvol_20"]
VAL_START = T0 + 500 * H4


def synth_examples(n=120, seed=3):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        t = T0 + i * 4 * H4
        f = {"F02_atr_pct": float(rng.uniform(0.002, 0.03)),
             "F03_breakout_strength": float(rng.normal(1.0, 0.5)),
             "F08_ret_5": float(rng.normal(0, 0.02)),
             "F11_rvol_20": float(rng.uniform(0.005, 0.03))}
        net_r = float(0.5 * f["F03_breakout_strength"] + rng.normal(0, 1))
        exit_t = t + int(rng.integers(1, P.MAX_HOLD_BARS_4H)) * H4
        out.append({"t": t, "net_r": net_r, "features": f,
                    "info_interval": [t, exit_t]})
    return [e for e in out if e["info_interval"][1] < VAL_START]


def test_pipelines_fit_and_predict_end_to_end():
    train = synth_examples()
    assert len(train) > 50
    cand = {"rank": 1}
    feats = train[0]["features"]

    b = FilterPipeline().fit(train, FEATS, VAL_START)
    ok, prob = b.accept(cand, feats)
    assert isinstance(ok, bool) and 0.0 <= prob <= 1.0

    c = RankerPipeline().fit(train, FEATS, VAL_START)
    assert isinstance(c.score(cand, feats), float)

    e = SizerPipeline().fit(train, FEATS, VAL_START)
    buckets = {e.bucket(cand, ex["features"]) for ex in train}
    assert buckets <= set(E_BUCKETS)
    assert 0.0 not in buckets                # Arm E never chooses zero


# ------------------------------- deliberate leaks: each MUST fail loudly

def test_leak_label_column_in_features_rejected():
    for bad in ("net_r", "F03_net_r_leak", "label", "target_next"):
        with pytest.raises(LeakError):
            validate_columns(FEATS + [bad])


def test_leak_unknown_column_outside_dictionary_rejected():
    with pytest.raises(LeakError):
        validate_columns(FEATS + ["my_secret_alpha"])


def test_leak_purge_violation_rejected_by_every_pipeline():
    train = synth_examples()
    leaked = dict(train[0])
    leaked["info_interval"] = [leaked["t"], VAL_START + H4]  # crosses val
    for cls in (FilterPipeline, RankerPipeline, SizerPipeline):
        with pytest.raises(LeakError):
            cls().fit(train + [leaked], FEATS, VAL_START)


def test_leak_post_t_feature_impossible_via_builder():
    """The feature builder cannot produce features at a timestamp whose bar
    has not completed — the post-t-bar leak fails at the source."""
    from lab.arms.indicators import SymbolSeries
    from lab.features.build import FeatureSeries, build_features
    B15 = P.BAR_15M_MS
    n4 = 96
    t15 = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.full(n4, 100.0), 16)
    ss = SymbolSeries(t15, lv.copy(), lv + 0.1, lv - 0.1, lv.copy())
    fs = FeatureSeries(ss.t4, ss.close4, ss.hh_entry, ss.ll_entry,
                       ss.hh_exit, ss.ll_exit)
    future_t = T0 + (n4 + 5) * H4            # beyond the last completed bar
    cand = {"t": future_t, "side": 1, "close": 100.0, "hh_entry": 100.1,
            "ll_entry": 99.9, "atr": 0.2, "rank": 1, "n_eligible": 1}
    with pytest.raises(ValueError):
        build_features(cand, fs, fs,
                       {"breadth_sma20": 0, "round_side_count": 1,
                        "regime_code": 0, "liq_median": 1e8})


def test_leak_holdout_examples_refused_before_labeling():
    from lab.labels.purge import HoldoutContaminationError, chronological_split
    ex = {"t": VAL_START + 600 * H4, "net_r": 1.0, "exit_t": VAL_START + 601 * H4,
          "info_interval": [VAL_START + 600 * H4, VAL_START + 601 * H4],
          "exclusion": None}
    with pytest.raises(HoldoutContaminationError):
        chronological_split([ex], VAL_START, VAL_START + 100 * H4)
