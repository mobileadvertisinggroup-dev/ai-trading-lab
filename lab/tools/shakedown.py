"""Step 12: the complete seven-arm END-TO-END SHAKEDOWN.

SHAKEDOWN — INVALID FOR PERFORMANCE CONCLUSIONS (spec §20). Every output
file is prefixed SHAKEDOWN_INVALID_ and every manifest carries the marker;
these ledgers never enter performance claims, are never merged into
official results, never backfilled, never reused.

The run exercises the full production pipeline: shared single-pass
candidate generation, all seven arms with their own engines and governors,
the FROZEN model artifacts (B/C/E LightGBM, D regime, F CEM policy),
G composed strictly as filter -> rank -> min(E, D) x A-size -> governor,
G-shadow entry identity, synchronized-round invalidation, and the
dashboard build. Defect detection per spec §20 is written into
SHAKEDOWN_INVALID_defects.json for the Checkpoint-1 inventory.

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
from lab.arms.rl_train import LinearPolicy
from lab.data import partition as PT
from lab.data.access import GuardedLake
from lab.features.build import FeatureSeries, build_features
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
    def __init__(self, model_dir, ctx, threshold=0.5):
        self.booster = lgb.Booster(
            model_file=os.path.join(model_dir, "arm_b.txt"))
        self.ctx = ctx
        self.threshold = threshold
        self.version = "B-lgbm-draft-frozen"
        self.fnames = self.booster.feature_name()

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
        self.fnames = self.booster.feature_name()

    def score(self, cand, _features):
        f = self.ctx.features(cand)
        x = np.array([[f[fn] for fn in self.fnames]], float)
        return float(self.booster.predict(x)[0])


class FrozenSizer:
    E_BUCKETS = (0.25, 0.50, 0.75, 1.00)

    def __init__(self, model_dir, ctx):
        self.booster = lgb.Booster(
            model_file=os.path.join(model_dir, "arm_e.txt"))
        self.cuts = np.load(os.path.join(model_dir, "arm_e_cuts.npz"))["cuts"]
        self.ctx = ctx
        self.version = "E-lgbm-draft-frozen"
        self.fnames = self.booster.feature_name()

    def bucket(self, cand, _features):
        f = self.ctx.features(cand)
        x = np.array([[f[fn] for fn in self.fnames]], float)
        p = float(self.booster.predict(x)[0])
        return self.E_BUCKETS[int(np.searchsorted(self.cuts, p))]


class FrozenRLPolicy:
    """Adapter from the orchestrator's management-observation dict to the
    trained 10-dim policy. KNOWN INTEGRATION DEFECT (recorded for the
    Checkpoint-1 inventory): the orchestrator supplies only
    {unrealized_r, bars_held}, a strict subset of the 10-dim training
    observation; the remaining dims are fed as 0. The shakedown exists to
    surface exactly this class of mismatch."""
    ACTIONS = ("hold", "reduce_25", "reduce_50", "close", "tighten_stop",
               "move_stop_breakeven")

    def __init__(self, model_dir):
        z = np.load(os.path.join(model_dir, "arm_f_policy.npz"))
        self.policy = LinearPolicy(z["theta"])
        self.version = f"F-cem-seed{int(z['seed'])}-frozen"

    def action(self, obs: dict) -> str:
        v = np.zeros(10)
        v[0] = obs.get("unrealized_r", 0.0)
        v[1] = min(1.0, obs.get("bars_held", 0) / P.MAX_HOLD_BARS_4H)
        return self.ACTIONS[self.policy.act(v)]


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
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

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
        filter_model=FrozenFilter(args.model_dir, ctx),
        ranker_model=FrozenRanker(args.model_dir, ctx),
        sizer_model=FrozenSizer(args.model_dir, ctx),
        rl_policy=FrozenRLPolicy(args.model_dir),
        regime_model=RegimeAdapter(regime),
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
    defects.append({
        "id": "SD-RLOBS", "severity": "integration-defect",
        "detail": ("orchestrator supplies a 2-field management observation "
                   "to a policy trained on the 10-dim env observation; "
                   "remaining dims zero-filled (FrozenRLPolicy). Root "
                   "cause: Competition._rl_management interface predates "
                   "the trained env. Affected arms: F, G (management "
                   "only). Fix scheduled post-Checkpoint-1 with retraining "
                   "assessment under the material-change rule.")})

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
    save("events_G_shadow.jsonl.gz", comp.shadow.engine.events)
    save("equity_G_shadow.json", comp.shadow.equity_curve)
    save("candidates.jsonl.gz", comp.candidates)
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
