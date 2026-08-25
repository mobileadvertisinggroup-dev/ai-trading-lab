"""Development tests for mechanical partition / universe / interval logic."""
import numpy as np
import pandas as pd
import pytest

from lab import protocol as P
from lab.data import partition as PT

DAY = PT.DAY_MS
H4 = P.BAR_4H_MS


def make_calendar(symbol, start_day_ms, n_days, qvol=50e6, bars=96):
    """Synthetic full-coverage calendar."""
    times = []
    qvs = []
    for d in range(n_days):
        day0 = start_day_ms + d * DAY
        for b in range(bars):
            times.append(day0 + b * P.BAR_15M_MS)
            qvs.append(qvol / bars)
    return PT.build_symbol_calendar(symbol, np.array(times, dtype=np.int64),
                                    np.array(qvs))


def test_partition_indices_60_20_20():
    i_t, i_v = P.partition_indices(1000)
    assert (i_t, i_v) == (600, 800)
    # snapping is by construction; ratio binding per spec §7
    i_t, i_v = P.partition_indices(7)
    assert (i_t, i_v) == (4, 5)


def test_all_boundaries_are_4h():
    b = PT.all_boundaries(0, 10 * H4)
    assert len(b) == 11
    assert all(x % H4 == 0 for x in b)
    with pytest.raises(ValueError):
        PT.all_boundaries(1, 10 * H4)


def test_compute_partition_metadata_is_non_outcome():
    meta = PT.compute_partition(0, 999 * H4)
    assert meta["n_boundaries"] == 1000
    assert meta["holdout_start_ms"] == meta["quarantine_start_ms"] == 800 * H4
    assert meta["train_end_ms"] == 599 * H4
    assert meta["validation_start_ms"] == 600 * H4
    # nothing but timestamps/counts in the metadata
    assert all(isinstance(v, int) for v in meta.values())


def test_eligibility_requires_history_liquidity_completeness():
    t = 200 * DAY  # midnight => 4h boundary
    good = make_calendar("GOODUSDT", 0, 200)
    ok, med = PT.is_eligible(good, t)
    assert ok and med == pytest.approx(50e6)

    young = make_calendar("YOUNGUSDT", t - 30 * DAY, 30)
    assert not PT.is_eligible(young, t)[0]          # < 90 days history

    illiquid = make_calendar("THINUSDT", 0, 200, qvol=1e6)
    assert not PT.is_eligible(illiquid, t)[0]       # below $25M median

    gappy = make_calendar("GAPUSDT", 0, 200, bars=80)  # 83% completeness
    assert not PT.is_eligible(gappy, t)[0]

    delisted = make_calendar("DEADUSDT", 0, 190)    # last bar ~10d before t
    assert not PT.is_eligible(delisted, t)[0]


def test_universe_ranking_top_n_and_ties():
    t = 200 * DAY
    cals = {f"S{i:03d}USDT": make_calendar(f"S{i:03d}USDT", 0, 200,
                                           qvol=30e6 + i * 1e6)
            for i in range(80)}
    u = PT.universe_at(t, cals)
    assert len(u) == P.UNIVERSE_TOP_N
    assert u[0] == "S079USDT"           # highest volume first
    assert "S004USDT" not in u          # bottom 5 excluded

    # ties broken lexicographically
    cals2 = {"BBBUSDT": make_calendar("BBBUSDT", 0, 200),
             "AAAUSDT": make_calendar("AAAUSDT", 0, 200)}
    assert PT.universe_at(t, cals2) == ["AAAUSDT", "BBBUSDT"]


def test_round_validity_and_eligible_interval():
    n_days = 200
    t0, t1 = 100 * DAY, 199 * DAY
    cals = {f"S{i:02d}USDT": make_calendar(f"S{i:02d}USDT", 0, n_days)
            for i in range(35)}
    cals[P.CONTEXT_SYMBOL] = make_calendar(P.CONTEXT_SYMBOL, 0, n_days)
    boundaries = PT.all_boundaries(t0, t1)
    # BTC 4h completeness map: all complete except one broken boundary
    btc_map = {int(b) - H4: 16 for b in boundaries}
    broken = int(boundaries[10])
    btc_map[broken - H4] = 15
    v = PT.round_validity(boundaries, cals, btc_map)
    assert bool(v.loc[broken]) is False
    assert v.drop(broken).all()

    freeze = int(t1) + DAY
    start, end = PT.eligible_interval(v, freeze)
    assert start == t0
    assert end == PT.all_boundaries(t0, freeze - P.INTERVAL_END_BUFFER_MS
                                    - (freeze - P.INTERVAL_END_BUFFER_MS) % H4)[-1]

    # too few eligible symbols -> rounds invalid -> honest failure
    few = {k: cals[k] for k in list(cals)[:10]}
    few[P.CONTEXT_SYMBOL] = cals[P.CONTEXT_SYMBOL]
    v2 = PT.round_validity(boundaries[:20], few, btc_map)
    assert not v2.any()
    with pytest.raises(RuntimeError):
        PT.eligible_interval(v2, freeze)


def test_fast_path_matches_slow_path():
    """Vectorized eligibility/validity must agree exactly with definitions."""
    rng = np.random.default_rng(7)
    n_days = 160
    cals = {}
    for i in range(40):
        sym = f"R{i:02d}USDT"
        # irregular data: random gaps, varying volumes, staggered listings
        start = int(rng.integers(0, 40)) * DAY
        times, qvs = [], []
        for d in range(n_days - start // DAY):
            day0 = start + d * DAY
            bars = int(rng.choice([96, 96, 96, 92, 80, 0],
                                  p=[.6, .15, .1, .07, .05, .03]))
            for b in range(bars):
                times.append(day0 + b * P.BAR_15M_MS)
                qvs.append(float(rng.uniform(1e5, 1.2e6)))
        cals[sym] = PT.build_symbol_calendar(
            sym, np.array(times, dtype=np.int64), np.array(qvs))
    cals[P.CONTEXT_SYMBOL] = make_calendar(P.CONTEXT_SYMBOL, 0, n_days)

    boundaries = PT.all_boundaries(120 * DAY, 155 * DAY)
    btc_map = {int(b) - H4: 16 for b in boundaries}

    for sym, cal in cals.items():
        fast = PT.eligibility_series(cal, boundaries)
        for t in boundaries:
            ok, med = PT.is_eligible(cal, int(t))
            assert ok == bool(pd.notna(fast.loc[int(t)])), (sym, t)
            if ok:
                assert fast.loc[int(t)] == pytest.approx(med), (sym, t)

    slow = PT.round_validity(boundaries, cals, btc_map)
    fast = PT.round_validity_fast(boundaries, cals, btc_map)
    assert (slow == fast).all()
