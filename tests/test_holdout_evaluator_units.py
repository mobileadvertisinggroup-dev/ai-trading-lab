"""D69 blockers 1 + 3 — mechanical tests for the frozen holdout
evaluator's combined loader and every pre-registered reported quantity.

Blocker 1 (symbol-universe UNION): fully synthetic pre-lake + overlay
fixtures (no real holdout filename was inspected to build these) prove
that overlay-only symbols — markets first listed after quarantine — are
discovered, validated, enter the mechanical universe once eligible, and
generate candidates; and that every per-class validation (schema, 15m
grid, duplicates, ordering, quarantine boundary, funding) fails loudly.

Blocker 3 (pre-registered outputs): profit factor, average trade,
turnover, slippage estimate, exposure, time in cash, top-3-removed
outlier dependence, and the frozen IL assessment (Amendment A1 seeds,
fixed scores, INSUFFICIENT-DATA branch) — each verified against
hand-computed values.
"""
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from lab import protocol as P
from lab.data import lake as L
from lab.data import partition as PT
from lab.tools.holdout_evaluator import (CombinedDataError,
                                         CombinedProvider,
                                         _validate_funding,
                                         _validate_klines,
                                         discover_symbols, il_assessment,
                                         load_combined,
                                         supporting_metrics)

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
DAY = 86_400_000
T0 = 20_000 * DAY                    # day- and 4h-aligned
Q = T0 + 100 * DAY                   # synthetic quarantine start
END = Q + 100 * DAY


def bars_df(t_start, t_end, level=100.0, qvol=1_000_000.0):
    t = np.arange(t_start, t_end, B15, dtype=np.int64)
    lv = np.full(len(t), float(level))
    return pd.DataFrame({"open_time": t, "open": lv, "high": lv + 0.1,
                         "low": lv - 0.1, "close": lv,
                         "volume": np.full(len(t), 1.0),
                         "quote_volume": np.full(len(t), qvol)})


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """Synthetic pre-lake + decrypted-overlay directory pair:
    BTCUSDT combined, OLDUSDT pre-only, NEWUSDT overlay-only."""
    tmp = tmp_path_factory.mktemp("union")
    lake = tmp / "lake"
    plain = tmp / "plain"
    manifests = tmp / "manifests"
    manifests.mkdir()
    (manifests / "partition_meta.json").write_text(
        '{"quarantine_start_ms": %d, "holdout_start_ms": %d, '
        '"holdout_end_ms": %d}' % (Q, Q, END))

    # pre-lake: BTCUSDT + OLDUSDT, rows strictly before Q
    for sym in ("BTCUSDT", "OLDUSDT"):
        L.write_parquet(bars_df(T0, Q),
                        str(lake / "klines15m" / sym / "m.parquet"))
    L.write_parquet(pd.DataFrame({"funding_time":
                                  np.arange(T0, Q, 8 * H4 // 4,
                                            dtype=np.int64),
                                  "funding_rate": 0.0001}),
                    str(lake / "funding" / "BTCUSDT" / "f.parquet"))

    # overlay: BTCUSDT continues; NEWUSDT lists AT quarantine with an
    # engineered breakout late in the window (flat 100 -> 110)
    L.write_parquet(bars_df(Q, END),
                    str(plain / "klines15m" / "BTCUSDT" / "m.parquet"))
    new = bars_df(Q, END)
    brk = new["open_time"] >= Q + 96 * DAY
    for c in ("open", "high", "low", "close"):
        new.loc[brk, c] = new.loc[brk, c] + 10.0
    L.write_parquet(new,
                    str(plain / "klines15m" / "NEWUSDT" / "m.parquet"))
    L.write_parquet(pd.DataFrame({"funding_time":
                                  np.arange(Q, END, 2 * H4,
                                            dtype=np.int64),
                                  "funding_rate": 0.0001}),
                    str(plain / "funding" / "NEWUSDT" / "f.parquet"))
    return {"lake": str(lake), "plain": str(plain),
            "manifests": str(manifests)}


# ------------------------------------------------ blocker 1: the UNION
def test_discover_symbols_classes(env):
    classes = discover_symbols(env["lake"], env["plain"])
    assert classes == {"BTCUSDT": "combined", "OLDUSDT": "pre_only",
                       "NEWUSDT": "overlay_only"}


def test_load_combined_census_and_merge(env):
    bars, funding, part, census = load_combined(
        env["lake"], env["manifests"], env["plain"])
    assert census["counts"] == {"pre_only": 1, "overlay_only": 1,
                                "combined": 1}
    # combined symbol: contiguous 15m grid across the quarantine boundary
    ot = bars["BTCUSDT"]["open_time"]
    assert ot[0] == T0 and ot[-1] == END - B15
    assert (np.diff(ot) == B15).all()
    # overlay-only symbol present, rows only >= Q
    assert bars["NEWUSDT"]["open_time"].min() == Q
    # pre-only symbol present, rows only < Q
    assert bars["OLDUSDT"]["open_time"].max() < Q
    # funding merged for the overlay-only symbol
    assert funding["NEWUSDT"] and min(funding["NEWUSDT"]) >= Q


def test_validation_missing_column_refuses():
    bad = bars_df(Q, Q + DAY).drop(columns=["quote_volume"])
    with pytest.raises(CombinedDataError, match="missing columns"):
        _validate_klines("X", "overlay_only", None, bad, Q)


def test_validation_off_grid_timestamp_refuses():
    bad = bars_df(Q, Q + DAY)
    bad.loc[0, "open_time"] += 1
    with pytest.raises(CombinedDataError, match="off-grid"):
        _validate_klines("X", "overlay_only", None, bad, Q)


def test_validation_overlay_rows_before_quarantine_refuse():
    bad = bars_df(Q - DAY, Q + DAY)
    with pytest.raises(CombinedDataError, match="before quarantine"):
        _validate_klines("X", "overlay_only", None, bad, Q)


def test_validation_pre_rows_at_or_after_quarantine_refuse():
    bad = bars_df(Q - DAY, Q + B15)
    with pytest.raises(CombinedDataError, match="at/after quarantine"):
        _validate_klines("X", "combined", bad, None, Q)


def test_validation_duplicate_timestamps_refuse():
    pre = bars_df(Q - DAY, Q)
    post = bars_df(Q, Q + DAY)
    dup = pd.concat([post, post.iloc[[0]]], ignore_index=True)
    with pytest.raises(CombinedDataError, match="duplicate"):
        _validate_klines("X", "combined", pre, dup, Q)


def test_validation_funding_boundary_and_duplicates():
    fpre = pd.DataFrame({"funding_time": [Q - 8 * H4, Q],
                         "funding_rate": [0.1, 0.1]})
    with pytest.raises(CombinedDataError, match="at/after quarantine"):
        _validate_funding("X", "combined", fpre, None, Q)
    fpost = pd.DataFrame({"funding_time": [Q, Q], "funding_rate": [0, 0]})
    with pytest.raises(CombinedDataError, match="duplicate"):
        _validate_funding("X", "overlay_only", None, fpost, Q)
    fbad = pd.DataFrame({"funding_time": [Q - 8 * H4],
                         "funding_rate": [0.1]})
    with pytest.raises(CombinedDataError, match="before quarantine"):
        _validate_funding("X", "overlay_only", None, fbad, Q)


def test_overlay_only_symbol_enters_universe_and_generates_candidates(env):
    """THE blocker-1 property: a market first listed after quarantine
    becomes eligible once it has the protocol history/liquidity, appears
    in the mechanical universe, and produces §2 candidates."""
    from lab.orchestration.competition import Competition

    bars, funding, part, census = load_combined(
        env["lake"], env["manifests"], env["plain"])
    provider = CombinedProvider(bars, funding)
    boundaries = PT.all_boundaries(Q, END)
    cals = {s: PT.build_symbol_calendar(
        s, provider.bars_15m(s)["open_time"],
        provider.bars_15m(s)["quote_volume"])
        for s in provider.symbols()}
    liq = {s: PT.eligibility_series(cals[s], boundaries)
           for s in provider.symbols()}

    # NEWUSDT (overlay-only) is INELIGIBLE early (< 90d history) and
    # ELIGIBLE late in the holdout window — mechanically, no override
    early = boundaries[10]
    late = boundaries[-8]
    assert not np.isfinite(liq["NEWUSDT"][early])
    assert np.isfinite(liq["NEWUSDT"][late])

    def universe_fn(t):
        out = [(s, liq[s][int(t)]) for s in provider.symbols()
               if np.isfinite(liq[s].get(int(t), np.nan))]
        out.sort(key=lambda kv: (-kv[1], kv[0]))
        return [s for s, _ in out[: P.UNIVERSE_TOP_N]]

    assert "NEWUSDT" in universe_fn(late)
    assert "NEWUSDT" not in universe_fn(early)

    # run the real orchestrator over the breakout window: the
    # overlay-only symbol generates candidates and is traded
    comp = Competition(provider, 10_000.0, universe_fn=universe_fn,
                       diagnostics=False)
    comp.run(int(boundaries[-30]), int(END - B15))
    new_cands = [c for c in comp.candidates if c["symbol"] == "NEWUSDT"]
    assert new_cands, "overlay-only symbol produced no candidates"
    assert all(c["side"] == +1 for c in new_cands)


# --------------------------------- blocker 3: every reported quantity
def pos(net, fees=0.0, fund=0.0, slip=0.001, closed=True):
    return SimpleNamespace(realized_pnl=net + fees + fund,
                           fees_paid=fees, funding_paid=fund,
                           closed=closed,
                           costs=SimpleNamespace(slippage=slip))


def test_profit_factor_average_trade_and_top3():
    curve = np.array([100.0, 104.0, 110.0])
    positions = {1: pos(10.0), 2: pos(-5.0), 3: pos(2.0), 4: pos(1.0)}
    m = supporting_metrics(curve, [], positions=positions)
    assert m["n_closed_trades"] == 4
    assert abs(m["profit_factor"] - 13.0 / 5.0) < 1e-12
    assert abs(m["average_trade_net"] - 8.0 / 4.0) < 1e-12
    # top-3 GAINS are 10, 2, 1 -> removed from final equity
    assert abs(m["net_return_ex_top3_trades"]
               - ((110.0 - 13.0) / 100.0 - 1.0)) < 1e-12


def test_profit_factor_edge_cases():
    m = supporting_metrics(np.array([100.0, 101.0]), [],
                           positions={1: pos(5.0)})
    assert m["profit_factor"] == 1e6          # gains, no losses
    m = supporting_metrics(np.array([100.0, 99.0]), [],
                           positions={1: pos(-5.0)})
    assert m["profit_factor"] == 0.0          # losses only
    # only-losses top3: nothing removed
    assert abs(m["net_return_ex_top3_trades"] - (99.0 / 100.0 - 1.0)) \
        < 1e-12


def test_slippage_estimate_and_turnover():
    positions = {7: pos(0.0, slip=0.001)}
    events = [
        {"kind": "fill_open", "pos_id": 7, "qty": 2.0, "price": 100.0,
         "fee": 0.1},
        {"kind": "fill_close", "pos_id": 7, "qty": -2.0, "price": 105.0,
         "fee": 0.1},
    ]
    curve = np.array([100.0, 100.0])
    m = supporting_metrics(curve, events, positions=positions)
    # |2|x100x0.001 + |-2|x105x0.001
    assert abs(m["slippage_estimate"] - (0.2 + 0.21)) < 1e-12
    assert abs(m["turnover_notional_over_mean_equity"]
               - (200.0 + 210.0) / 100.0) < 1e-12
    assert abs(m["fees_paid"] - 0.2) < 1e-12


def test_exposure_and_time_in_cash():
    ec = [{"t": 0, "equity": 100.0, "gross_exposure": 0.0},
          {"t": 1, "equity": 100.0, "gross_exposure": 50.0},
          {"t": 2, "equity": 100.0, "gross_exposure": 100.0}]
    m = supporting_metrics(np.array([100.0, 100.0, 100.0]), [],
                           equity_curve=ec)
    assert abs(m["mean_exposure_frac"] - 0.5) < 1e-12
    assert abs(m["time_in_cash_frac"] - 1.0 / 3.0) < 1e-12


def test_il_assessment_insufficient_data_branch():
    t = np.array([0, H4, 2 * H4], dtype=np.int64)     # 3 boundaries
    out = il_assessment(t, np.array([1.0, -1.0, 0.5]),
                        np.array([0.9, 0.1, 0.6]),
                        np.array([0.9, 0.1, 0.6]))
    assert out["verdict"].startswith("INSUFFICIENT DATA")
    # short span (< 28d displacement possible): also insufficient
    t2 = np.arange(0, 40 * H4, H4, dtype=np.int64)
    r = np.random.default_rng(0).normal(size=len(t2))
    out2 = il_assessment(t2, r, r, r)
    assert out2["verdict"].startswith("INSUFFICIENT DATA")


def test_il_assessment_frozen_seeds_and_determinism():
    rng = np.random.default_rng(7)
    t = np.arange(0, 120 * DAY, DAY, dtype=np.int64)   # 120 daily bnds
    net = rng.normal(size=len(t))
    prob = rng.uniform(size=len(t))
    score = rng.normal(size=len(t))
    a = il_assessment(t, net, prob, score)
    b = il_assessment(t, net, prob, score)
    assert a == b                                       # deterministic
    assert a["seeds"] == {"permutation": 20260903, "bootstrap": 20260904}
    assert a["n"] == 120 and "verdict" in a
    assert 0.0 <= a["p_upper"]["auc"] <= 1.0
    # perfectly informative fixed scores -> AUC 1.0, tiny p
    y_perfect = il_assessment(t, net, (net > 0).astype(float) * 0.98
                              + 0.01, net)
    assert y_perfect["observed"]["auc"] == 1.0
    assert y_perfect["p_upper"]["auc"] < 0.05


def test_supporting_metrics_reports_every_preregistered_quantity():
    """The pre-registration's supporting-metric list is complete."""
    positions = {1: pos(3.0)}
    ec = [{"t": 0, "equity": 100.0, "gross_exposure": 0.0}]
    # D72: the engine emits funding as `paid` (positive = position pays)
    m = supporting_metrics(np.array([100.0, 103.0]),
                           [{"kind": "funding", "paid": 0.5}],
                           positions=positions, equity_curve=ec)
    for key in ("net_return", "max_drawdown_observed", "sharpe_ann",
                "sortino_ann", "calmar", "profit_factor",
                "average_trade_net", "turnover_notional_over_mean_equity",
                "fees_paid", "slippage_estimate", "funding_net",
                "mean_exposure_frac", "time_in_cash_frac",
                "tail_loss_mean_worst5pct", "stability_halves",
                "net_return_ex_top3_trades", "n_closed_trades"):
        assert key in m, key
    assert m["funding_net"] == -0.5
