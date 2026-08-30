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
KLINE_COLS = ("open_time", "open", "high", "low", "close", "quote_volume")


class CombinedDataError(RuntimeError):
    """Combined-data validation failure — inside the gate this becomes
    FAILED_CLOSED; nothing is silently skipped or imputed."""


def _read_overlay(plain_dir: str, kind: str, symbol: str) -> pd.DataFrame | None:
    files = sorted(glob.glob(os.path.join(plain_dir, kind, symbol, "*.parquet")))
    if not files:
        return None
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _validate_klines(sym: str, klass: str, pre: pd.DataFrame | None,
                     post: pd.DataFrame | None, q: int) -> pd.DataFrame:
    """Schema, timestamp-grid, duplicate, ordering, and quarantine-
    boundary validation for one symbol of any class."""
    parts = [d for d in (pre, post) if d is not None and len(d)]
    if not parts:
        raise CombinedDataError(f"{sym} [{klass}]: no kline rows")
    for name, d in (("pre", pre), ("overlay", post)):
        if d is None or not len(d):
            continue
        missing = [c for c in KLINE_COLS if c not in d.columns]
        if missing:
            raise CombinedDataError(
                f"{sym} [{klass}] {name}: missing columns {missing}")
        ot = d["open_time"].to_numpy(np.int64)
        if (ot % P.BAR_15M_MS).any():
            raise CombinedDataError(
                f"{sym} [{klass}] {name}: off-grid 15m timestamps")
        if name == "pre" and len(ot) and int(ot.max()) >= q:
            raise CombinedDataError(
                f"{sym} [{klass}]: pre-lake rows at/after quarantine")
        if name == "overlay" and len(ot) and int(ot.min()) < q:
            raise CombinedDataError(
                f"{sym} [{klass}]: overlay rows before quarantine "
                f"(seal invariant violated)")
    df = (pd.concat(parts, ignore_index=True)
          .sort_values("open_time", kind="mergesort")
          .reset_index(drop=True))
    ot = df["open_time"].to_numpy(np.int64)
    if len(np.unique(ot)) != len(ot):
        raise CombinedDataError(f"{sym} [{klass}]: duplicate timestamps")
    return df


def _validate_funding(sym: str, klass: str, fpre: pd.DataFrame | None,
                      fpost: pd.DataFrame | None, q: int) -> dict:
    parts = [d for d in (fpre, fpost) if d is not None and len(d)]
    if not parts:
        return {}
    for name, d in (("pre", fpre), ("overlay", fpost)):
        if d is None or not len(d):
            continue
        if "funding_time" not in d.columns or "funding_rate" not in d.columns:
            raise CombinedDataError(
                f"{sym} [{klass}] funding {name}: missing columns")
        ft = d["funding_time"].to_numpy(np.int64)
        if name == "pre" and len(ft) and int(ft.max()) >= q:
            raise CombinedDataError(
                f"{sym} [{klass}]: pre funding at/after quarantine")
        if name == "overlay" and len(ft) and int(ft.min()) < q:
            raise CombinedDataError(
                f"{sym} [{klass}]: overlay funding before quarantine")
    fdf = (pd.concat(parts, ignore_index=True)
           .sort_values("funding_time", kind="mergesort"))
    ft = fdf["funding_time"].to_numpy(np.int64)
    if len(np.unique(ft)) != len(ft):
        raise CombinedDataError(
            f"{sym} [{klass}]: duplicate funding timestamps")
    return dict(zip(ft, fdf["funding_rate"].astype(float)))


def discover_symbols(pre_lake_dir: str, plain_dir: str) -> dict[str, str]:
    """D69 blocker 1: the holdout universe is the VALIDATED UNION of
    pre-lake symbols and decrypted-overlay kline symbols — markets first
    listed after quarantine (overlay-only) are included, never silently
    omitted. Returns {symbol: class} with class in
    {pre_only, overlay_only, combined}."""
    pre = set(os.listdir(os.path.join(pre_lake_dir, "klines15m")))
    op = os.path.join(plain_dir, "klines15m")
    post = set(os.listdir(op)) if os.path.isdir(op) else set()
    return {s: ("combined" if s in pre and s in post else
                "pre_only" if s in pre else "overlay_only")
            for s in sorted(pre | post)}


def load_combined(pre_lake_dir: str, manifests_dir: str,
                  plain_dir: str) -> tuple[dict, dict, dict, dict]:
    """Merge the verified pre-holdout lake with the decrypted overlay
    over the validated symbol UNION. Returns
    (bars_by_symbol, funding_by_symbol, partition, symbol_census)."""
    lake = GuardedLake(pre_lake_dir, manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    classes = discover_symbols(pre_lake_dir, plain_dir)
    bars, funding = {}, {}
    census = {"pre_only": 0, "overlay_only": 0, "combined": 0}
    for sym, klass in classes.items():
        census[klass] += 1
        pre = (lake.read_klines(sym, 0, q - P.BAR_15M_MS)
               if klass != "overlay_only" else None)
        post = (_read_overlay(plain_dir, "klines15m", sym)
                if klass != "pre_only" else None)
        df = _validate_klines(sym, klass, pre, post, q)
        bars[sym] = {k: df[k].to_numpy(np.float64 if k != "open_time"
                                       else np.int64)
                     for k in KLINE_COLS}
        fpre = (lake.read_funding(sym, 0, q - P.BAR_15M_MS)
                if klass != "overlay_only" else None)
        fpost = (_read_overlay(plain_dir, "funding", sym)
                 if klass != "pre_only" else None)
        funding[sym] = _validate_funding(sym, klass, fpre, fpost, q)
    return bars, funding, part, {"classes": classes, "counts": census}


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


def supporting_metrics(curve: np.ndarray, events: list[dict],
                       positions: dict | None = None,
                       equity_curve: list[dict] | None = None) -> dict:
    """Every SPEC-§18 supporting metric promised by the pre-registration
    (D69 blocker 3): profit factor, average trade, turnover, slippage
    estimate, exposure, time in cash, tail loss, stability halves, and
    the top-three-trades-removed outlier-dependence result — each
    mechanical and unit-tested."""
    r = curve[1:] / curve[:-1] - 1.0
    fills = [e for e in events if e["kind"] == "fill_close"]
    fees = sum(e.get("fee", 0.0) for e in events
               if e["kind"] in ("fill_open", "fill_close"))
    # D72 blocker A.4: the engine emits funding transfers under the
    # field name `paid` (positive = the position PAYS; cash -= paid).
    # funding_net is the net funding PnL (positive = received). The
    # previous collector read a nonexistent `amount` field and
    # reported 0 — that defect is D72's origin.
    funding = -sum(e.get("paid", 0.0) for e in events
                   if e["kind"] == "funding")
    dd = max_drawdown_decimal(curve)
    mean, sd = float(np.mean(r)), float(np.std(r))
    half = len(r) // 2
    out = {
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
    # per-closed-trade nets (fees + funding included) — trade metrics
    if positions is not None:
        nets = np.array([p.realized_pnl - p.fees_paid - p.funding_paid
                         for p in positions.values() if p.closed])
        gains = float(nets[nets > 0].sum()) if len(nets) else 0.0
        losses = float(-nets[nets < 0].sum()) if len(nets) else 0.0
        out["n_closed_trades"] = int(len(nets))
        out["profit_factor"] = (gains / losses if losses > 0
                                else (1e6 if gains > 0 else 0.0))
        out["average_trade_net"] = (float(nets.mean()) if len(nets)
                                    else 0.0)
        # outlier dependence: net return with the (up to) three
        # largest-GAIN trades' net pnl removed from the final equity —
        # only gains are ever removed
        top3 = float(np.sort(nets[nets > 0])[-3:].sum()) if len(nets) \
            else 0.0
        out["net_return_ex_top3_trades"] = float(
            (curve[-1] - top3) / curve[0] - 1.0)
        # slippage ESTIMATE: per fill, notional x that position's frozen
        # slippage rate (labeled estimate — slip is embedded in fills)
        slip_rate = {pid: p.costs.slippage for pid, p in positions.items()}
        est = 0.0
        for e in events:
            if e["kind"] in ("fill_open", "fill_close") \
                    and e.get("pos_id") in slip_rate:
                est += abs(e.get("qty", 0.0)) * e.get("price", 0.0) \
                    * slip_rate[e["pos_id"]]
        out["slippage_estimate"] = est
        # turnover: total filled notional / mean equity
        notional = sum(abs(e.get("qty", 0.0)) * e.get("price", 0.0)
                       for e in events
                       if e["kind"] in ("fill_open", "fill_close"))
        out["turnover_notional_over_mean_equity"] = \
            float(notional / np.mean(curve))
    if equity_curve is not None and equity_curve:
        ge = np.array([row.get("gross_exposure", np.nan)
                       for row in equity_curve], float)
        eq = np.array([row["equity"] for row in equity_curve], float)
        if np.isfinite(ge).all():
            frac = np.divide(ge, eq, out=np.zeros_like(ge),
                             where=eq > 0)
            out["mean_exposure_frac"] = float(frac.mean())
            out["time_in_cash_frac"] = float((ge == 0.0).mean())
    return out


# ------------------------------ funding reconciliation (D72 blocker A.5)
def funding_reconciliation(events: list[dict],
                           positions: dict | None = None) -> dict:
    """Every applicable funding boundary, applied payment, and
    missing-rate event — by symbol, side, sign, and period — plus the
    engine-event-to-equity reconciliation: the sum of event `paid`
    transfers must equal the sum of per-position funding_paid (the
    cash/equity impact is exactly -sum(paid))."""
    import time as _time
    applied = [e for e in events if e["kind"] == "funding"]
    missing = [e for e in events if e["kind"] == "funding_missing"]
    side_of = {}
    if positions is not None:
        side_of = {pid: p.side for pid, p in positions.items()}
    by_symbol: dict = {}
    by_period: dict = {}
    by_side = {"long_paid": 0.0, "short_paid": 0.0}
    by_sign = {"paid_positive_count": 0, "paid_positive_sum": 0.0,
               "paid_negative_count": 0, "paid_negative_sum": 0.0,
               "paid_zero_count": 0}
    for e in applied:
        s = e["symbol"]
        d = by_symbol.setdefault(s, {"applied": 0, "missing": 0,
                                     "paid": 0.0})
        d["applied"] += 1
        d["paid"] += e["paid"]
        period = _time.strftime("%Y-%m", _time.gmtime(e["t"] / 1000))
        by_period[period] = by_period.get(period, 0.0) + e["paid"]
        side = side_of.get(e.get("pos_id"))
        if side is not None:
            by_side["long_paid" if side > 0 else "short_paid"] += e["paid"]
        if e["paid"] > 0:
            by_sign["paid_positive_count"] += 1
            by_sign["paid_positive_sum"] += e["paid"]
        elif e["paid"] < 0:
            by_sign["paid_negative_count"] += 1
            by_sign["paid_negative_sum"] += e["paid"]
        else:
            by_sign["paid_zero_count"] += 1
    for e in missing:
        d = by_symbol.setdefault(e["symbol"], {"applied": 0, "missing": 0,
                                               "paid": 0.0})
        d["missing"] += 1
    event_sum = float(sum(e["paid"] for e in applied))
    out = {
        "n_applied": len(applied), "n_missing": len(missing),
        "n_boundary_crossings": len(applied) + len(missing),
        "total_paid": event_sum, "funding_net": -event_sum,
        "by_symbol": by_symbol, "by_side": by_side, "by_sign": by_sign,
        "by_period": by_period,
    }
    if positions is not None:
        pos_sum = float(sum(p.funding_paid for p in positions.values()))
        out["position_funding_paid_sum"] = pos_sum
        out["event_to_equity_reconciled"] = bool(
            abs(event_sum - pos_sum) < 1e-9)
    return out


def funding_activity_guard(recon: dict, span_days: float,
                           n_closed_trades: int) -> tuple[bool, str]:
    """D72: any all-zero funding result over an active multi-month
    window STOPS the procedure unless mechanically proven legitimate.
    Returns (ok, reason)."""
    if span_days < 60 or n_closed_trades < 50:
        return True, "window/trade count below the multi-month threshold"
    if recon["n_boundary_crossings"] == 0:
        return False, ("no position ever crossed a funding boundary over "
                       f"{span_days:.0f} days with {n_closed_trades} "
                       "closed trades — mechanically implausible")
    if recon["n_applied"] == 0:
        return False, (f"{recon['n_missing']} funding boundaries crossed, "
                       "ZERO rates applied — funding data missing or "
                       "unwired")
    if recon["total_paid"] == 0.0:
        return False, (f"{recon['n_applied']} funding payments applied "
                       "summing to exactly 0.0 — mechanically implausible")
    return True, "funding active and reconciled"


# -------------------- frozen IL assessment (Amendment A1, pre-opening)
IL_PERM_SEED = 20260903
IL_BOOT_SEED = 20260904
IL_N_PERM = 200
IL_N_BOOT = 1000


def il_assessment(t: np.ndarray, net_r: np.ndarray, prob: np.ndarray,
                  score: np.ndarray) -> dict:
    """The frozen INSUFFICIENT-LEARNABLE-VARIATION rule applied to
    Checkpoint-2 evidence with FIXED frozen-model scores (no refitting —
    Amendment A1 of the CP2 pre-registration): AUC/IC of the frozen
    scores against holdout labels; exact-multiset circular-rotation
    permutation of the label vector vs the FIXED scores; TRUE circular
    moving-block bootstrap CIs; approximate power at the frozen MUE;
    then the frozen (a)/(b)/(c) verdict."""
    from lab.tools.learnability import auc as _auc
    from lab.tools.learnability import spearman as _spearman
    from lab.tools.learnability_v2 import MUE_AUC_DEV, MUE_IC, two_sided_p
    from lab.tools.learnability_v3 import (draw_rotations,
                                          eligible_rotation_boundaries,
                                          rotate_labels)

    order = np.argsort(t, kind="stable")
    t, net_r = t[order], net_r[order]
    prob, score = prob[order], score[order]
    y = (net_r > 0).astype(int)
    ub = np.unique(t)
    out: dict = {"n": int(len(t)), "unique_boundaries": int(len(ub)),
                 "seeds": {"permutation": IL_PERM_SEED,
                           "bootstrap": IL_BOOT_SEED},
                 "method": "fixed-score rotation permutation + circular "
                           "moving-block bootstrap (Amendment A1; no "
                           "refitting)"}
    if len(ub) < 4 or len(eligible_rotation_boundaries(ub)) == 0:
        out["verdict"] = ("INSUFFICIENT DATA FOR IL ASSESSMENT — "
                          "reported, not adjudicated")
        return out
    obs_auc = _auc(y, prob)
    obs_ic = _spearman(net_r, score)
    rots = draw_rotations(t, IL_N_PERM, IL_PERM_SEED)
    null_auc, null_ic = [], []
    for j in rots:
        yp = rotate_labels(net_r, t, j)
        null_auc.append(_auc((yp > 0).astype(int), prob))
        null_ic.append(_spearman(yp, score))
    null_auc, null_ic = np.array(null_auc), np.array(null_ic)
    p_auc = two_sided_p(null_auc, obs_auc, 0.5)
    p_ic = two_sided_p(null_ic, obs_ic, 0.0)
    rows_by_b = [np.where(t == b)[0] for b in ub]
    span_days = (int(ub[-1]) - int(ub[0])) / 86_400_000
    l_block = max(1, math.ceil(len(ub) * 28 / max(span_days, 28)))
    seqs = circular_moving_block_sequences(len(ub), l_block, IL_N_BOOT,
                                           IL_BOOT_SEED)
    b_auc, b_ic = [], []
    for seq in seqs:
        rows = np.concatenate([rows_by_b[j] for j in seq])
        b_auc.append(_auc(y[rows], prob[rows]))
        b_ic.append(_spearman(net_r[rows], score[rows]))
    b_auc, b_ic = np.array(b_auc, float), np.array(b_ic, float)
    ci_auc = [float(np.nanquantile(b_auc, .025)),
              float(np.nanquantile(b_auc, .975))]
    ci_ic = [float(np.nanquantile(b_ic, .025)),
             float(np.nanquantile(b_ic, .975))]
    se_auc, se_ic = float(np.nanstd(b_auc)), float(np.nanstd(b_ic))

    def power(null, center, se, mue):
        c = float(np.quantile(np.abs(null - center), 0.95))
        if se <= 0:
            return float(mue > c)
        return float(1.0 - 0.5 * (1.0 + math.erf(
            (c - mue) / se / math.sqrt(2.0))))
    pw_auc = power(null_auc, 0.5, se_auc, MUE_AUC_DEV)
    pw_ic = power(null_ic, 0.0, se_ic, MUE_IC)
    a_cond = p_auc["p_upper"] >= 0.05 and p_ic["p_upper"] >= 0.05
    b_cond = (ci_auc[0] <= 0.5 <= ci_auc[1]) and (ci_ic[0] <= 0 <= ci_ic[1])
    c_cond = pw_auc >= 0.60 and pw_ic >= 0.60
    if a_cond and b_cond and c_cond:
        verdict = "INSUFFICIENT LEARNABLE VARIATION"
    elif a_cond and b_cond:
        verdict = "UNDERPOWERED — NO EVIDENCE EITHER WAY"
    else:
        verdict = ("frozen IL rule conditions not all met — see "
                   "statistics; adjudication is the reviewer's")
    out.update({"observed": {"auc": obs_auc, "rank_ic": obs_ic},
                "p_upper": {"auc": p_auc["p_upper"],
                            "rank_ic": p_ic["p_upper"]},
                "ci95": {"auc": ci_auc, "rank_ic": ci_ic},
                "power_at_mue": {"auc": pw_auc, "rank_ic": pw_ic},
                "conditions": {"a_p": bool(a_cond), "b_ci": bool(b_cond),
                               "c_power": bool(c_cond)},
                "verdict": verdict})
    return out


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
    d_btc = provider.bars_15m(P.CONTEXT_SYMBOL)
    g4 = (d_btc["open_time"] // P.BAR_4H_MS) * P.BAR_4H_MS
    u, c = np.unique(g4, return_counts=True)
    btc_map = {int(k): int(v) for k, v in zip(u, c)}
    validity = PT.round_validity_fast(boundaries, cals,
                                      btc_map)             # frozen rule
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

    # D72: full funding reconciliation per arm + diagnostics; the
    # activity guard STOPS the evaluation (fail closed) on any
    # mechanically implausible all-zero funding over this window.
    window_days = (end - start) / 86_400_000
    frecon = {}
    for a in ARMS7:
        rec = funding_reconciliation(comp.arms[a].engine.events,
                                     comp.arms[a].engine.positions)
        n_closed = sum(1 for p in comp.arms[a].engine.positions.values()
                       if p.closed)
        ok, why = funding_activity_guard(rec, window_days, n_closed)
        rec["guard"] = {"ok": bool(ok), "reason": why}
        frecon[a] = rec
        if not ok:
            raise CombinedDataError(
                f"funding activity guard failed for arm {a}: {why}")
        if rec.get("event_to_equity_reconciled") is False:
            raise CombinedDataError(
                "funding event-to-equity reconciliation failed for arm "
                f"{a}")
    frecon["G_matched"] = funding_reconciliation(
        comp.shadow_matched.engine.events,
        comp.shadow_matched.engine.positions)
    frecon["G_feasible"] = funding_reconciliation(
        comp.shadow_feasible.engine.events,
        comp.shadow_feasible.engine.positions)

    # frozen IL assessment (Amendment A1): Arm A's closed holdout trades
    # give labels; the FIXED frozen B probability and C score recorded
    # in those arms' decision ledgers at the same (t, symbol) give the
    # scores — no refitting anywhere.
    a_state = comp.arms["A"]
    close_net = {p.pos_id: p.realized_pnl - p.fees_paid - p.funding_paid
                 for p in a_state.engine.positions.values() if p.closed}
    risk = {p.pos_id: p.qty * p.r_dist
            for p in a_state.engine.positions.values() if p.closed}
    a_opens = {e["pos_id"]: (e["decision_ts"], e["symbol"])
               for e in a_state.engine.events if e["kind"] == "fill_open"}
    b_prob = {(r["t"], r["symbol"]): r["probability"]
              for r in comp.arms["B"].decisions if "probability" in r}
    c_score = {(r["t"], r["symbol"]): r["score"]
               for r in comp.arms["C"].decisions if "score" in r}
    il_rows = []
    for pid, net in close_net.items():
        key = a_opens.get(pid)
        if key is None or key not in b_prob or key not in c_score:
            continue
        il_rows.append((key[0], net / risk[pid], b_prob[key],
                        c_score[key]))
    if il_rows:
        arr = np.array(il_rows, float)
        il = il_assessment(arr[:, 0].astype(np.int64), arr[:, 1],
                           arr[:, 2], arr[:, 3])
    else:
        il = {"n": 0, "verdict": "INSUFFICIENT DATA FOR IL ASSESSMENT — "
                                 "reported, not adjudicated"}

    results = {
        "preregistration": "PREREGISTRATION_CHECKPOINT2_EVALUATION.md",
        "window": {"start_ms": start, "end_ms": end,
                   "n_boundaries": int(len(boundaries)),
                   "n_valid_rounds": int(sum(vmap.values()))},
        "rounds": comp.coordinator.counts(),
        "statistics": stats,
        "funding_reconciliation": frecon,
        "il_assessment": il,
        "supporting_metrics": {
            a: supporting_metrics(curves[a], comp.arms[a].engine.events,
                                  comp.arms[a].engine.positions,
                                  comp.arms[a].equity_curve)
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
        bars, funding, part, census = load_combined(
            pre_lake_dir, manifests_dir, plain_dir)
        provider = CombinedProvider(bars, funding)
        results = run_evaluation(provider, part, manifests_dir,
                                 model_dir, sb3_dir)
        results["symbol_census"] = census["counts"]
        return results
    return evaluator
