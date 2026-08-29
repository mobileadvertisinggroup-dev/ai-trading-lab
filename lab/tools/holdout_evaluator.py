"""THE frozen Checkpoint-2 holdout evaluator (SPEC §18/§19/§22) —
executes PREREGISTRATION_CHECKPOINT2_EVALUATION.md verbatim.

This module completes the one-time gate: `make_evaluator(...)` returns
the callable that `lab.data.unseal.evaluate_holdout` invokes with the
decrypted overlay directory. It NEVER decrypts anything itself, never
touches the holdout outside the gate, and returns/exports only result
ledgers and statistics — no raw market rows.

Structure (testable without any holdout data):
  load_combined(...)   — pre-holdout lake (via GuardedLake, bounded
                         below Q) + decrypted overlay parquets, merged
                         per symbol in-memory;
  run_evaluation(...)  — the frozen seven-arm run + statistics on any
                         provided combined data (unit-tested on
                         synthetic data);
  make_evaluator(...)  — binds the frozen artifact/config paths and
                         returns evaluator(plain_dir) for the gate.
"""
from __future__ import annotations

import glob
import json
import math
import os

import numpy as np
import pandas as pd

from lab import protocol as P
from lab.arms.indicators import SymbolSeries
from lab.arms.regime import RegimeModel
from lab.arms.rl_sb3 import load_policy
from lab.data import partition as PT
from lab.data.access import GuardedLake
from lab.tools.arm_e_portfolio import (max_drawdown_decimal,
                                       sortino_annualized)
from lab.tools.learnability_v3 import circular_moving_block_sequences
from lab.tools.shakedown import (FeatureContext, FrozenFilter,
                                 FrozenRanker, FrozenSizer, RegimeAdapter,
                                 ShakedownCompetition)

ARMS7 = ("A", "B", "C", "D", "E", "F", "G")
CHALLENGERS = ("B", "C", "D", "E", "F", "G")
BOOT_N = 1000
BOOT_SEED = 20260902               # pre-registered
BLOCK_LEN_4H = 168
FAMILY_ALPHA = 0.05


# ------------------------------------------------------------- loading
def _read_overlay(plain_dir: str, kind: str, symbol: str) -> pd.DataFrame | None:
    files = sorted(glob.glob(os.path.join(plain_dir, kind, symbol, "*.parquet")))
    if not files:
        return None
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def load_combined(pre_lake_dir: str, manifests_dir: str,
                  plain_dir: str) -> tuple[dict, dict, dict]:
    """Merge the verified pre-holdout lake with the decrypted overlay.
    Returns (bars_by_symbol, funding_by_symbol, partition)."""
    lake = GuardedLake(pre_lake_dir, manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    symbols = sorted(os.listdir(os.path.join(pre_lake_dir, "klines15m")))
    bars, funding = {}, {}
    for sym in symbols:
        pre = lake.read_klines(sym, 0, q - P.BAR_15M_MS)
        post = _read_overlay(plain_dir, "klines15m", sym)
        df = (pd.concat([pre, post], ignore_index=True)
              if post is not None else pre)
        df = df.sort_values("open_time", kind="mergesort")
        assert int(df.open_time.min()) < q or post is None
        # overlay must contain ONLY holdout-range rows (seal invariant)
        if post is not None:
            assert int(post.open_time.min()) >= q, sym
        bars[sym] = {k: df[k].to_numpy(np.float64 if k != "open_time"
                                       else np.int64)
                     for k in ("open_time", "open", "high", "low",
                               "close", "quote_volume")}
        fpre = lake.read_funding(sym, 0, q - P.BAR_15M_MS)
        fpost = _read_overlay(plain_dir, "funding", sym)
        fdf = (pd.concat([fpre, fpost], ignore_index=True)
               if fpost is not None else fpre)
        funding[sym] = dict(zip(fdf["funding_time"].astype(np.int64),
                                fdf["funding_rate"].astype(float)))
    return bars, funding, part


class CombinedProvider:
    def __init__(self, bars: dict, funding: dict):
        self._d, self._f = bars, funding

    def symbols(self):
        return sorted(self._d)

    def bars_15m(self, symbol):
        return self._d[symbol]

    def funding(self, symbol):
        return self._f.get(symbol, {})


# ---------------------------------------------------------- statistics
def holm_bonferroni(pvals: dict[str, float]) -> dict[str, float]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    adj, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return adj


def evaluation_statistics(curves: dict[str, np.ndarray]) -> dict:
    """The frozen §18/§19 statistics from per-arm 4h equity curves."""
    rets = {a: c[1:] / c[:-1] - 1.0 for a, c in curves.items()}
    nr = len(rets["A"])
    seqs = circular_moving_block_sequences(nr, BLOCK_LEN_4H, BOOT_N,
                                           BOOT_SEED)

    def boot_stats(r):
        sortinos, mdds = [], []
        for seq in seqs:                          # paired across arms
            rs = r[seq]
            sortinos.append(sortino_annualized(rs))
            mdds.append(max_drawdown_decimal(np.cumprod(1.0 + rs)))
        return np.array(sortinos), np.array(mdds)

    boot = {a: boot_stats(r) for a, r in rets.items()}
    out: dict = {"primary_statistic":
                 "annualized Sortino of 4h portfolio returns (frozen)",
                 "arms": {}, "inference": {}}
    for a in curves:
        out["arms"][a] = {
            "final_equity": float(curves[a][-1]),
            "sortino_annualized_observed":
                sortino_annualized(rets[a]),
            "max_drawdown_observed_decimal":
                max_drawdown_decimal(curves[a]),
            "dd95_bootstrap_decimal":
                float(np.quantile(boot[a][1], 0.95)),
        }
    dd95_a = out["arms"]["A"]["dd95_bootstrap_decimal"]
    raw_p = {}
    for x in CHALLENGERS:
        if x not in curves:
            continue
        delta = boot[x][0] - boot["A"][0]
        raw_p[x] = float((np.sum(delta <= 0) + 1) / (len(delta) + 1))
    adj = holm_bonferroni(raw_p)
    for x, p in raw_p.items():
        dd_ok = out["arms"][x]["dd95_bootstrap_decimal"] <= dd95_a
        out["inference"][x] = {
            "p_upper_raw": p, "p_holm": adj[x],
            "drawdown_constraint_pass": bool(dd_ok),
            "improves_over_A":
                bool(adj[x] < FAMILY_ALPHA and dd_ok)}
    out["inference"]["_procedure"] = {
        "bootstrap": {"n": BOOT_N, "seed": BOOT_SEED,
                      "block_len_4h": BLOCK_LEN_4H, "paired": True},
        "correction": "Holm-Bonferroni, family alpha 0.05 (frozen)",
        "drawdown_constraint": "DD95(X) <= DD95(A), paired (frozen)"}
    return out


def supporting_metrics(curve: np.ndarray, events: list[dict]) -> dict:
    r = curve[1:] / curve[:-1] - 1.0
    fills = [e for e in events if e["kind"] == "fill_close"]
    fees = sum(e.get("fee", 0.0) for e in events
               if e["kind"] in ("fill_open", "fill_close"))
    funding = sum(e.get("amount", 0.0) for e in events
                  if e["kind"] == "funding")
    dd = max_drawdown_decimal(curve)
    mean, sd = float(np.mean(r)), float(np.std(r))
    down = float(np.sqrt(np.mean(np.minimum(r, 0.0) ** 2)))
    half = len(r) // 2
    return {
        "net_return": float(curve[-1] / curve[0] - 1.0),
        "max_drawdown_observed": dd,
        "sharpe_ann": (mean / sd * math.sqrt(2191.5)) if sd else 0.0,
        "sortino_ann": sortino_annualized(r),
        "calmar": (float(curve[-1] / curve[0] - 1.0) / dd) if dd else 0.0,
        "n_closes": len(fills),
        "fees_paid": fees, "funding_net": funding,
        "tail_loss_mean_worst5pct":
            float(np.mean(np.sort(r)[: max(1, len(r) // 20)])),
        "stability_halves": [float(np.prod(1 + r[:half]) - 1),
                             float(np.prod(1 + r[half:]) - 1)],
    }


# --------------------------------------------------------------- runs
def run_evaluation(provider, part: dict, manifests_dir: str,
                   model_dir: str, sb3_dir: str) -> dict:
    """The frozen seven-arm holdout run + statistics (pure function of
    the combined data + frozen artifacts)."""
    q = int(part["quarantine_start_ms"])
    end = int(part["holdout_end_ms"])
    start = q
    assert start % P.BAR_4H_MS == 0
    boundaries = PT.all_boundaries(start, end)
    symbols = provider.symbols()
    cals = {s: PT.build_symbol_calendar(
        s, provider.bars_15m(s)["open_time"],
        provider.bars_15m(s)["quote_volume"]) for s in symbols}
    validity = PT.round_validity_fast(boundaries, cals)   # frozen rule
    vmap = {int(t): bool(v) for t, v in
            zip(boundaries, np.asarray(validity))}
    liq = np.full((len(boundaries), len(symbols)), np.nan)
    for j, s in enumerate(symbols):
        liq[:, j] = PT.eligibility_series(cals[s], boundaries).to_numpy()
    bidx = {int(t): i for i, t in enumerate(boundaries)}
    sym_arr = np.array(symbols)
    sym_col = {s: j for j, s in enumerate(symbols)}

    def universe_fn(t):
        i = bidx.get(int(t))
        if i is None:
            return []
        row = liq[i]
        ok = np.isfinite(row)
        order = np.lexsort((sym_arr[ok], -row[ok]))
        return list(sym_arr[ok][order][: P.UNIVERSE_TOP_N])

    d = provider.bars_15m(P.CONTEXT_SYMBOL)
    ss = SymbolSeries(d["open_time"], d["open"], d["high"], d["low"],
                      d["close"])
    regime = RegimeModel(ss.t4, ss.close4)
    ctx = FeatureContext(provider, cals, boundaries, liq, sym_col, regime)

    with open(os.path.join(model_dir, "bc_train_selection.json")) as f:
        fin = json.load(f)
    with open(os.path.join(model_dir,
                           "arm_e_portfolio_selection.json")) as f:
        e_sel = json.load(f)
    with open(os.path.join(sb3_dir, "arm_f_sb3_manifest.json")) as f:
        sb3m = json.load(f)
    rl = load_policy(os.path.join(
        sb3_dir, f"arm_f_sb3_seed{int(sb3m['selected_seed'])}.zip"),
        version=f"F-sb3-ppo-seed{sb3m['selected_seed']}-frozen")

    comp = ShakedownCompetition(
        provider, 10_000.0, universe_fn,
        valid_round_fn=lambda t: vmap.get(int(t), False),
        filter_model=FrozenFilter(
            model_dir, ctx,
            threshold=float(fin["arm_b"]["selected_threshold"])),
        ranker_model=FrozenRanker(model_dir, ctx),
        sizer_model=FrozenSizer(
            model_dir, ctx, mapping=e_sel["selected_mapping"],
            quantiles=fin["arm_e"]["train_pred_quantiles"]),
        rl_policy=rl, regime_model=RegimeAdapter(regime),
        ranker_top_k=int(fin["arm_c"]["selected_top_k"]),
        feature_ctx=ctx)
    comp.run(start, end - (end % P.BAR_15M_MS) if end % P.BAR_15M_MS
             else end)

    curves = {a: np.array([r["equity"]
                           for r in comp.arms[a].equity_curve])
              for a in ARMS7}
    stats = evaluation_statistics(curves)
    results = {
        "preregistration": "PREREGISTRATION_CHECKPOINT2_EVALUATION.md",
        "window": {"start_ms": start, "end_ms": end,
                   "n_boundaries": int(len(boundaries)),
                   "n_valid_rounds": int(sum(vmap.values()))},
        "rounds": comp.coordinator.counts(),
        "statistics": stats,
        "supporting_metrics": {
            a: supporting_metrics(curves[a], comp.arms[a].engine.events)
            for a in ARMS7},
        "ledgers": {
            a: {"decisions": comp.arms[a].decisions,
                "events": comp.arms[a].engine.events,
                "equity_curve": comp.arms[a].equity_curve,
                "governor_events": comp.arms[a].governor.events,
                "rl_decisions": comp.arms[a].rl_decisions}
            for a in ARMS7},
        "diagnostics": {
            "G_matched": {"events": comp.shadow_matched.engine.events,
                          "equity_curve":
                              comp.shadow_matched.equity_curve},
            "G_feasible": {"events": comp.shadow_feasible.engine.events,
                           "equity_curve":
                               comp.shadow_feasible.equity_curve,
                           "decisions": comp.shadow_feasible.decisions}},
        "honest_note": ("Pre-registered prior expectation: no challenger "
                        "meets the success criterion; negative results "
                        "are preserved as-is."),
    }
    return results


def make_evaluator(pre_lake_dir: str, manifests_dir: str, model_dir: str,
                   sb3_dir: str):
    """Bind the frozen inputs; the gate calls the returned closure with
    the decrypted overlay directory."""
    def evaluator(plain_dir: str) -> dict:
        bars, funding, part = load_combined(pre_lake_dir, manifests_dir,
                                            plain_dir)
        provider = CombinedProvider(bars, funding)
        return run_evaluation(provider, part, manifests_dir, model_dir,
                              sb3_dir)
    return evaluator
