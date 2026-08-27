"""Step 12: the complete seven-arm END-TO-END SHAKEDOWN.

SHAKEDOWN — INVALID FOR PERFORMANCE CONCLUSIONS (spec §20). Every output
file is prefixed SHAKEDOWN_INVALID_ and every manifest carries the marker;
these ledgers never enter performance claims, are never merged into
official results, never backfilled, never reused.

The run exercises the full production pipeline: shared single-pass
candidate generation, all seven arms with their own engines and governors,
the FROZEN model artifacts (B/C/E LightGBM with the pre-registered
finalized decision rules from bce_finalization.json, D regime, F = the
selected SB3 PPO policy consuming the CANONICAL obs-v2 observation),
G composed strictly as filter -> rank -> min(E, D) x A-size -> governor,
G-shadow entry identity, TRANSACTIONAL synchronized-round invalidation,
and the dashboard build. Defect detection per spec §20 is written into
SHAKEDOWN_INVALID_defects.json.

Full RL observability (adjudication blocker 4): every F/G management
decision is exported with its obs-v2 vector + schema hash, raw and
executed actions, governor outcome, and before/after stop+quantity;
per-arm governor event streams are exported; the manifest carries HOLD
counts, an executed-action reconciliation against the engine event
stream, and a per-boundary coverage check (every valid round in which an
arm held an open position has a matching RL decision record).

Window: the final SHAKEDOWN_DAYS days of readable (pre-quarantine) data;
provider arrays carry FULL history so indicator warm-up matches official
conventions. All reads via GuardedLake, bounded below the quarantine.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

import lightgbm as lgb

from lab import protocol as P
from lab.arms.arm_a import MarketProvider
from lab.arms.indicators import SymbolSeries
from lab.arms.regime import RegimeModel
from lab.arms.rl_sb3 import load_policy
from lab.data import partition as PT
from lab.data.access import GuardedLake
from lab.features.build import FEATURE_NAMES, FeatureSeries, \
    build_features
from lab.orchestration.competition import ARMS, Competition

SHAKEDOWN_DAYS = 180
REGIME_CODE = {"uptrend": 0, "downtrend": 1, "sideways": 2, "stress": 3}


class LakeProvider(MarketProvider):
    def __init__(self, lake: GuardedLake, symbols, end_ms):
        self._d, self._f = {}, {}
        for sym in symbols:
            df = lake.read_klines(sym, 0, end_ms)
            self._d[sym] = {k: df[k].to_numpy(np.float64 if k != "open_time"
                                              else np.int64)
                            for k in ("open_time", "open", "high", "low",
                                      "close", "quote_volume")}
            fdf = lake.read_funding(sym, 0, end_ms)
            self._f[sym] = dict(zip(fdf["funding_time"].astype(np.int64),
                                    fdf["funding_rate"].astype(float)))

    def symbols(self):
        return sorted(self._d)

    def bars_15m(self, symbol):
        return self._d[symbol]

    def funding(self, symbol):
        return self._f.get(symbol, {})


class FeatureContext:
    """Point-in-time F01-F28 for shakedown candidates — same builder code
    as the official feature run; per-round context prepared when the
    orchestrator generates the shared candidate list."""

    def __init__(self, provider: LakeProvider, cals, boundaries, liq,
                 sym_col, regime: RegimeModel):
        self.fs = {}
        for sym, d in provider._d.items():
            ss = SymbolSeries(d["open_time"], d["open"], d["high"],
                              d["low"], d["close"])
            self.fs[sym] = FeatureSeries(ss.t4, ss.close4, ss.hh_entry,
                                         ss.ll_entry, ss.hh_exit,
                                         ss.ll_exit)
        self.provider = provider
        self.liq = liq
        self.bidx = {int(t): i for i, t in enumerate(boundaries)}
        self.sym_col = sym_col
        self.regime = regime
        self.btc = self.fs[P.CONTEXT_SYMBOL]
        self._round: dict = {}

    def prepare_round(self, t: int, cands: list[dict], universe: list[str]):
        vals = []
        for s in universe:
            i = self.fs[s].index_at(t)
            if i is not None and np.isfinite(self.fs[s].sma20[i]):
                vals.append(1.0 if self.fs[s].close[i] > self.fs[s].sma20[i]
                            else 0.0)
        sides = {}
        for c in cands:
            sides[c["side"]] = sides.get(c["side"], 0) + 1
        self._round = {
            "t": t,
            "breadth": float(np.mean(vals)) if vals else float("nan"),
            "sides": sides,
            "regime_code": REGIME_CODE[self.regime.classify(t)["regime"]],
        }

    def features(self, cand: dict) -> dict:
        t, sym = int(cand["t"]), cand["symbol"]
        assert self._round.get("t") == t, "round context not prepared"
        i = self.bidx.get(t)
        lm = self.liq[i][self.sym_col[sym]] if i is not None else np.nan
        fr = self.provider.funding(sym)
        prior = sorted(ts for ts in fr if ts < t)
        f_last = fr[prior[-1]] if prior else float("nan")
        f_mean = (float(np.mean([fr[x] for x in prior[-9:]]))
                  if prior else float("nan"))
        ctx = {"breadth_sma20": self._round["breadth"],
               "round_side_count": self._round["sides"].get(cand["side"], 1),
               "regime_code": self._round["regime_code"],
               "liq_median": float(lm) if np.isfinite(lm) else None,
               "funding_last": f_last, "funding_mean_3d": f_mean}
        return build_features(cand, self.fs[sym], self.btc, ctx)


class FrozenFilter:
    def __init__(self, model_dir, ctx, threshold: float):
        """threshold = the pre-registered FINALIZED value from
        bce_finalization.json (blocker 6) — never a default."""
        self.booster = lgb.Booster(
            model_file=os.path.join(model_dir, "arm_b.txt"))
        self.ctx = ctx
        self.threshold = threshold
        self.version = f"B-lgbm-final-th{threshold}"
        self.fnames = FEATURE_NAMES          # SD-FEATNAMES fix

    def _x(self, cand):
        f = self.ctx.features(cand)
        return np.array([[f[fn] for fn in self.fnames]], float)

    def accept(self, cand, _features):
        prob = float(self.booster.predict(self._x(cand))[0])
        return prob >= self.threshold, prob


class FrozenRanker:
    def __init__(self, model_dir, ctx):
        self.booster = lgb.Booster(
            model_file=os.path.join(model_dir, "arm_c.txt"))
        self.ctx = ctx
        self.version = "C-lgbm-draft-frozen"
        self.fnames = FEATURE_NAMES          # SD-FEATNAMES fix

    def score(self, cand, _features):
        f = self.ctx.features(cand)
        x = np.array([[f[fn] for fn in self.fnames]], float)
        return float(self.booster.predict(x)[0])


class FrozenSizer:
    """Arm E with the pre-registered FINALIZED mapping (blocker 6):
    the frozen regressor's prediction bucketed by the mapping recorded in
    bce_finalization.json (mapping id + frozen train-prediction
    quantiles). E may never choose zero."""
    E_BUCKETS = (0.25, 0.50, 0.75, 1.00)

    def __init__(self, model_dir, ctx, mapping: str, quantiles: dict):
        self.booster = lgb.Booster(
            model_file=os.path.join(model_dir, "arm_e.txt"))
        q = quantiles
        cuts_by_mapping = {
            "M1": [q["q25"], q["q50"], q["q75"]],
            "M2": [0.0, q["q50"], q["q75"]],
            "M3": [q["q25"], q["q75"], q["q90"]],
            "M4": None,
        }
        self.mapping = mapping
        self.cuts = cuts_by_mapping[mapping]
        self.ctx = ctx
        self.version = f"E-lgbm-final-{mapping}"
        self.fnames = FEATURE_NAMES          # SD-FEATNAMES fix

    def bucket(self, cand, _features):
        if self.cuts is None:                # M4 flat control
            return 1.0
        f = self.ctx.features(cand)
        x = np.array([[f[fn] for fn in self.fnames]], float)
        p = float(self.booster.predict(x)[0])
        return self.E_BUCKETS[int(np.searchsorted(self.cuts, p))]


class RegimeAdapter:
    def __init__(self, regime: RegimeModel):
        self.regime = regime
        self.version = regime.version

    def classify(self, t_ms):
        rec = self.regime.classify(t_ms)
        m = rec["multiplier"]
        return {"regime": rec["regime"],
                "multiplier": {1: m["long"] if "long" in m else m[1],
                               -1: m["short"] if "short" in m else m[-1]},
                "model_version": self.version}


class ShakedownCompetition(Competition):
    """Adds per-round feature-context preparation; no semantic change."""

    def __init__(self, *a, feature_ctx: FeatureContext | None = None, **kw):
        super().__init__(*a, **kw)
        self._fctx = feature_ctx

    def _shared_candidates(self, t):
        cands = super()._shared_candidates(t)
        if self._fctx is not None:
            self._fctx.prepare_round(t, cands, self.universe_fn(t))
        return cands


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:  # pragma: no cover — the shakedown run
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--sb3-dir", required=True,
                    help="dir with arm_f_sb3_manifest.json + seed zips")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    # pre-registered FINALIZED B/C/E decision rules (blocker 6)
    with open(os.path.join(args.model_dir, "bce_finalization.json")) as f:
        fin = json.load(f)
    b_threshold = float(fin["arm_b"]["final"]["threshold"])
    c_top_k = int(fin["arm_c"]["final"]["top_k"])
    e_mapping = fin["arm_e"]["final"]["mapping"]
    e_quantiles = fin["arm_e"]["final"]["train_pred_quantiles"]

    # the selected SB3 Arm F policy (blocker 1), canonical obs-v2 only
    with open(os.path.join(args.sb3_dir, "arm_f_sb3_manifest.json")) as f:
        sb3m = json.load(f)
    sel_seed = int(sb3m["selected_seed"])
    rl = load_policy(
        os.path.join(args.sb3_dir, f"arm_f_sb3_seed{sel_seed}.zip"),
        version=f"F-sb3-ppo-seed{sel_seed}-frozen")

    lake = GuardedLake(args.lake, args.manifests_dir)
    part = lake.partition
    q = int(part["quarantine_start_ms"])
    end = q - P.BAR_15M_MS
    start = q - SHAKEDOWN_DAYS * 24 * 3600 * 1000
    start -= start % P.BAR_4H_MS

    with open(os.path.join(args.manifests_dir, "round_validity.json")) as f:
        validity = {int(k): bool(v) for k, v in json.load(f).items()}

    symbols = sorted(os.listdir(os.path.join(args.lake, "klines15m")))
    print(f"loading {len(symbols)} symbols...", flush=True)
    provider = LakeProvider(lake, symbols, end)

    boundaries = np.array(sorted(validity), dtype=np.int64)
    cals = {s: PT.build_symbol_calendar(
        s, provider._d[s]["open_time"], provider._d[s]["quote_volume"])
        for s in symbols}
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

    d = provider._d[P.CONTEXT_SYMBOL]
    ss = SymbolSeries(d["open_time"], d["open"], d["high"], d["low"],
                      d["close"])
    regime = RegimeModel(ss.t4, ss.close4)
    ctx = FeatureContext(provider, cals, boundaries, liq, sym_col, regime)

    comp = ShakedownCompetition(
        provider, 10_000.0, universe_fn,
        valid_round_fn=lambda t: validity.get(int(t), False),
        filter_model=FrozenFilter(args.model_dir, ctx,
                                  threshold=b_threshold),
        ranker_model=FrozenRanker(args.model_dir, ctx),
        sizer_model=FrozenSizer(args.model_dir, ctx, mapping=e_mapping,
                                quantiles=e_quantiles),
        rl_policy=rl,
        regime_model=RegimeAdapter(regime),
        ranker_top_k=c_top_k,
        feature_ctx=ctx)

    print(f"SHAKEDOWN run {start} .. {end} "
          f"(INVALID FOR PERFORMANCE CONCLUSIONS)", flush=True)
    t0 = time.time()
    comp.run(start, end)
    print(f"run complete ({time.time() - t0:.0f}s)", flush=True)

    # ---- defect detection (spec §20) -------------------------------------
    defects = []
    rc = comp.coordinator.counts()
    # G-shadow entry identity (constitutional property)
    g_opens = [(e["t"], e["symbol"], e["side"], round(e["qty"], 10))
               for e in comp.arms["G"].engine.events
               if e["kind"] == "fill_open"]
    s_opens = [(e["t"], e["symbol"], e["side"], round(e["qty"], 10))
               for e in comp.shadow.engine.events
               if e["kind"] == "fill_open"]
    if g_opens != s_opens:
        defects.append({"id": "SD-GSHADOW", "severity": "constitutional",
                        "detail": f"G/shadow entry mismatch: "
                                  f"{len(g_opens)} vs {len(s_opens)}"})
    # missing decisions: every arm must have >= 1 decision record per
    # valid round in which it saw fresh candidates — proxy: nonzero
    n_dec = {a: len(comp.arms[a].decisions) for a in ARMS}
    for a in ARMS:
        if n_dec[a] == 0:
            defects.append({"id": f"SD-NODECISIONS-{a}",
                            "severity": "blocking",
                            "detail": f"arm {a} recorded no decisions"})
    # RL action violations
    for a in ("F", "G"):
        rej = [e for e in comp.arms[a].governor.events
               if e["kind"] == "governor_action_reject"]
        if rej:
            defects.append({"id": f"SD-RLACTION-{a}", "severity": "info",
                            "detail": f"{len(rej)} RL actions rejected by "
                                      f"the governor (filter working)"})
    # ---- blocker-4 observability: coverage + reconciliation --------------
    valid_rounds = {int(t) for t, ok in validity.items()
                    if ok and start <= t <= end
                    and comp.coordinator.is_valid(t)}
    rl_observability = {}
    for a in ("F", "G"):
        st = comp.arms[a]
        recs = st.rl_decisions
        by_t: dict[int, int] = {}
        for r in recs:
            by_t[r["t"]] = by_t.get(r["t"], 0) + 1
        # coverage: every valid round at which the arm HELD an open
        # position must have >= 1 RL decision record. Open intervals are
        # reconstructed from the engine event stream (decision-time info).
        opens = {}
        intervals = []
        for e in st.engine.events:
            if e["kind"] == "fill_open":
                opens[e["pos_id"]] = e["t"]
            elif e["kind"] == "position_closed" and e["pos_id"] in opens:
                intervals.append((opens.pop(e["pos_id"]), e["t"]))
        intervals += [(t0_, end) for t0_ in opens.values()]
        uncovered = sorted(
            t for t in valid_rounds
            if any(o < t <= c for o, c in intervals)
            and t not in by_t)
        n_exec_tighten = sum(
            1 for r in recs
            if r.get("executed_action") in ("tighten_stop",
                                            "move_stop_breakeven"))
        n_engine_tighten = sum(1 for e in st.engine.events
                               if e["kind"] == "stop_tightened")
        recon_ok = n_exec_tighten == n_engine_tighten
        missing_obs = [r["t"] for r in recs
                       if r.get("backstop") is None
                       and r.get("observation") is None]
        rl_observability[a] = {
            "n_rl_decisions": len(recs),
            "hold_count": sum(1 for r in recs
                              if r.get("executed_action") == "hold"),
            "executed_action_counts": {
                act: sum(1 for r in recs
                         if r.get("executed_action") == act)
                for act in sorted({r.get("executed_action")
                                   for r in recs} - {None})},
            "governor_rejects": sum(
                1 for r in recs if r.get("governor") == "reject"),
            "boundaries_with_decisions": len(by_t),
            "uncovered_open_boundaries": uncovered,
            "tighten_reconciliation":
                {"rl_records": n_exec_tighten,
                 "engine_events": n_engine_tighten, "match": recon_ok},
            "obs_schema_hashes": sorted({r["obs_schema_hash"]
                                         for r in recs
                                         if "obs_schema_hash" in r}),
        }
        if uncovered:
            defects.append({"id": f"SD-RLCOVERAGE-{a}",
                            "severity": "blocking",
                            "detail": f"{len(uncovered)} valid rounds with "
                                      f"an open position but no RL "
                                      f"decision record"})
        if not recon_ok:
            defects.append({"id": f"SD-RLRECON-{a}", "severity": "blocking",
                            "detail": "executed tighten_stop counts differ "
                                      "between RL records and engine "
                                      "events"})
        if missing_obs:
            defects.append({"id": f"SD-RLOBSNULL-{a}",
                            "severity": "blocking",
                            "detail": f"{len(missing_obs)} non-backstop RL "
                                      f"records missing the obs vector"})

    marker = "SHAKEDOWN — INVALID FOR PERFORMANCE CONCLUSIONS"
    paths = {}

    def save(name, obj):
        p = os.path.join(args.out_dir, f"SHAKEDOWN_INVALID_{name}")
        if name.endswith(".jsonl.gz"):
            with gzip.open(p, "wt") as fh:
                for rec in obj:
                    fh.write(json.dumps(rec, sort_keys=True, default=float)
                             + "\n")
        else:
            with open(p, "w") as fh:
                json.dump(obj, fh, indent=1, sort_keys=True, default=float)
        paths[name] = p

    for a in ARMS:
        st = comp.arms[a]
        save(f"decisions_{a}.jsonl.gz", st.decisions)
        save(f"events_{a}.jsonl.gz", st.engine.events)
        save(f"equity_{a}.json", st.equity_curve)
        # blocker 4: per-arm governor event stream (all arms, not F/G only)
        save(f"governor_{a}.jsonl.gz", st.governor.events)
    for a in ("F", "G"):
        # blocker 4: full RL decision ledger — obs vectors + schema hash,
        # raw/executed actions, governor outcomes, before/after stop+qty
        save(f"rl_decisions_{a}.jsonl.gz", comp.arms[a].rl_decisions)
    save("rl_observability.json", {"marker": marker,
                                   "per_arm": rl_observability})
    save("events_G_shadow.jsonl.gz", comp.shadow.engine.events)
    save("equity_G_shadow.json", comp.shadow.equity_curve)
    save("candidates.jsonl.gz", comp.candidates)
    save("round_records.jsonl.gz", comp.coordinator.records)
    save("defects.json", {"marker": marker, "defects": defects,
                          "round_counts": rc,
                          "decisions_per_arm": n_dec})

    manifest = {"marker": marker, "start_ms": start, "end_ms": end,
                "days": SHAKEDOWN_DAYS, "round_counts": rc,
                "n_candidates": len(comp.candidates),
                "decisions_per_arm": n_dec,
                "final_equity": {a: comp.arms[a].equity_curve[-1]["equity"]
                                 for a in ARMS},
                "final_equity_G_shadow":
                    comp.shadow.equity_curve[-1]["equity"],
                "n_defects": len(defects),
                "model_wiring": {
                    "arm_b_threshold": b_threshold,
                    "arm_c_top_k": c_top_k,
                    "arm_e_mapping": e_mapping,
                    "arm_f_policy": rl.version,
                    "obs_schema": rl.obs_schema},
                "rl_observability": rl_observability,
                "artifacts": {n: {"path": p, "sha256": sha256_file(p)}
                              for n, p in paths.items()}}
    mp = os.path.join(args.out_dir, "SHAKEDOWN_INVALID_manifest.json")
    with open(mp, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(json.dumps({k: manifest[k] for k in
                      ("round_counts", "decisions_per_arm", "final_equity",
                       "n_defects")}, indent=2), flush=True)
    print("manifest:", mp, flush=True)


if __name__ == "__main__":  # pragma: no cover
    main()
