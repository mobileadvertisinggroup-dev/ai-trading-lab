"""Targeted INVALID stress fixture (D63 closure item 4).

STRESS FIXTURE — INVALID FOR PERFORMANCE CONCLUSIONS. Synthetic market,
never real data. Mechanically exercises, in ONE run:
  (a) same-bar STOP and same-bar TARGET immediately after entry
      (G actual and the matched clone must agree bit-for-bit);
  (b) MORE THAN TEN concurrent G_matched diagnostic positions
      (explicit diagnostic_over_cap recording);
  (c) a REAL G_feasible capacity divergence (feasible at its own
      10-position cap rejecting entries G actual takes);
  (d) nontrivial RL management decisions (tighten / reduce / close);
  (e) NONZERO mechanically reconciled funding (D72): positive rates on
      even wave symbols, negative on odd, ONE symbol deliberately
      without rates — sign semantics, event-to-equity reconciliation
      across every engine (arms + both diagnostics), and loud
      funding_missing are all verified.
Every property is verified mechanically and the ledgers + verdicts are
exported; any failed check is a recorded defect and a nonzero exit.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os

import numpy as np

from lab import protocol as P
from lab.arms.arm_a import ArrayProvider
from lab.orchestration.competition import ARMS, Competition

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)
HIST = 96
N_WAVE = 14                      # staggered breakout symbols
MARKER = "STRESS FIXTURE — INVALID FOR PERFORMANCE CONCLUSIONS"


def build(levels_4h, wiggle=1.0, spikes=None):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    d = {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
         "low": lv - wiggle, "close": lv.copy()}
    for i, (o, h, lo, c) in (spikes or {}).items():
        d["open"][i], d["high"][i] = o, h
        d["low"][i], d["close"][i] = lo, c
    return d


class StressPolicy:
    """Nontrivial RL management: tighten, reduce, then close — so G
    frees capacity fast while the matched clone holds conventionally."""
    version = "stress-tighten-reduce-close"

    def __init__(self):
        self.per_pos: dict = {}

    def action_from_obs(self, obs):
        # keyed per invocation cycle; deterministic across the run
        k = self.per_pos.setdefault("k", 0)
        self.per_pos["k"] = k + 1
        return ("tighten_stop", "reduce_25", "close")[k % 3]


def main() -> None:  # pragma: no cover — fixture run
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    up = [100.0 + 0.02 * i for i in range(HIST)]
    n4 = HIST + N_WAVE + 30
    data = {}
    # staggered breakouts: symbol k breaks out at boundary HIST+1+k and
    # then grinds upward (no conventional exit inside the window)
    for k in range(N_WAVE):
        lv = up + [up[-1]] * k + [106.0 + 0.3 * i
                                  for i in range(n4 - HIST - k)]
        data[f"W{k:02d}USDT"] = build(lv[:n4])
    # same-bar stop / target on the FIRST wave boundary
    i_entry = (HIST + 1) * 16
    sb = up + [106.0] + [106.0] * (n4 - HIST - 1)
    data["SBSTPUSDT"] = build(sb[:n4],
                              spikes={i_entry: (106.0, 106.5, 99.0, 100.0)})
    data["SBTGTUSDT"] = build(sb[:n4],
                              spikes={i_entry: (106.0, 121.0, 105.5,
                                                120.0)})
    # (f) D74 staggered funding-entry scenario: STAGUSDT's first
    # candidate (boundary HIST+2, a 4h boundary) is REJECTED for B/G by
    # the filter, so arm A enters and holds; the second candidate lands
    # on boundary HIST+3 — an 8h FUNDING boundary here (T0 is offset by
    # 4h from the 8h grid, so ODD indices are funding boundaries) —
    # where G first FILLS while the shared map already contains STAG.
    stag_lv = up[:HIST] + [up[-1], 106.0, 112.0] + [112.0] * (n4 - HIST
                                                              - 3)
    data["STAGUSDT"] = build(stag_lv[:n4])
    t_stag_reject = T0 + (HIST + 2) * H4
    t_stag_entry = T0 + (HIST + 3) * H4
    assert t_stag_entry % P.FUNDING_INTERVAL_MS == 0
    assert t_stag_reject % P.FUNDING_INTERVAL_MS != 0

    class StagFilter:
        version = "stress-stagger-filter"

        def accept(self, cand, features):
            if cand["symbol"] == "STAGUSDT" and \
                    int(cand["t"]) == t_stag_reject:
                return False, 0.0
            return True, 1.0

    # (e) D72 funding scenario: +rate on even wave symbols, -rate on
    # odd; W13 deliberately has NO rates (missing-funding loudness)
    F_RATE = 0.0005
    end_t = T0 + n4 * 16 * B15
    f8_grid = list(range((T0 // P.FUNDING_INTERVAL_MS + 1)
                         * P.FUNDING_INTERVAL_MS, end_t,
                         P.FUNDING_INTERVAL_MS))
    funding = {f"W{k:02d}USDT": {int(t): (F_RATE if k % 2 == 0
                                          else -F_RATE)
                                 for t in f8_grid}
               for k in range(N_WAVE - 1)}       # W13 left missing
    funding["STAGUSDT"] = {int(t): F_RATE for t in f8_grid}
    prov = ArrayProvider({s: {k2: v.copy() for k2, v in d.items()}
                          for s, d in data.items()}, funding=funding)
    comp = Competition(prov, 100_000.0,
                       universe_fn=lambda t: sorted(data),
                       filter_model=StagFilter(),
                       rl_policy=StressPolicy())
    end = T0 + (n4 * 16 - 1) * B15
    comp.run(T0, end)

    checks: dict = {}
    defects = []

    def _fills(st):
        return [(e["t"], e["symbol"], e["side"], e["qty"], e["price"],
                 e["stop"], e["target"]) for e in st.engine.events
                if e["kind"] == "fill_open"]

    # (a) same-bar stop/target agreement G vs matched
    for sym, kind in (("SBSTPUSDT", "stop"), ("SBTGTUSDT", "target")):
        g_close = [e for e in comp.arms["G"].engine.events
                   if e["kind"] == "fill_close" and e["symbol"] == sym]
        m_close = [e for e in comp.shadow_matched.engine.events
                   if e["kind"] == "fill_close" and e["symbol"] == sym]
        g_open = [e for e in comp.arms["G"].engine.events
                  if e["kind"] == "fill_open" and e["symbol"] == sym]
        ok = (bool(g_open) and bool(g_close) and bool(m_close)
              and g_close[0]["t"] == g_open[0]["t"]
              and m_close[0]["t"] == g_close[0]["t"]
              and m_close[0]["price"] == g_close[0]["price"]
              and m_close[0]["qty"] == g_close[0]["qty"])
        checks[f"same_bar_{kind}"] = ok
        if not ok:
            defects.append(f"same-bar {kind} mismatch on {sym}")

    # matched-fill identity (constitutional, at stress scale)
    checks["matched_fill_identity"] = \
        _fills(comp.arms["G"]) == _fills(comp.shadow_matched)
    if not checks["matched_fill_identity"]:
        defects.append("matched fill identity failed under stress")

    # (b) > 10 concurrent matched positions, explicitly recorded
    over = [e for e in comp.shadow_matched.engine.events
            if e["kind"] == "diagnostic_over_cap"]
    max_open = max((e["n_open"] for e in over), default=0)
    checks["matched_over_cap"] = {"events": len(over),
                                  "max_concurrent": max_open,
                                  "exceeded_ten": max_open > 10}
    if max_open <= 10:
        defects.append("matched book never exceeded ten positions")

    # (c) REAL feasible capacity divergence, fully explained. Capacity
    # binds at the GOVERNOR first (max_positions / insufficient_capacity
    # rejections recorded in the decision ledger) and at the engine as
    # defense-in-depth — both count as recorded explanations.
    feas = comp.shadow_feasible
    engine_rej = {(e["t"], e["symbol"]) for e in feas.engine.events
                  if e["kind"] in ("rejection", "entry_cancelled")}
    dec_by_key = {}
    for r in feas.decisions:
        dec_by_key.setdefault((r["t"], r["symbol"]), r)
    # key divergences by the fill's own DECISION timestamp — the same
    # key the feasible decision ledger uses
    g_fill_keys = {(e["decision_ts"], e["symbol"]) for e in
                   comp.arms["G"].engine.events if e["kind"] == "fill_open"}
    f_fill_keys = {(e["decision_ts"], e["symbol"])
                   for e in feas.engine.events if e["kind"] == "fill_open"}
    g_only = sorted(g_fill_keys - f_fill_keys)
    capacity_rejects = [r for r in feas.decisions
                        if r.get("stage") == "submitted"
                        and r.get("governor") == "reject"
                        and r.get("governor_reason")
                        in ("max_positions", "insufficient_capacity")]
    explained_stages = {"already_open", "filter_rejected", "rank_cut",
                        "regime_blocked"}
    unexplained = []
    for t_dec, sym in g_only:
        r = dec_by_key.get((t_dec, sym))
        if r is None:
            unexplained.append((t_dec, sym))
        elif r["stage"] in explained_stages:
            pass
        elif r["stage"] == "submitted" and (
                r.get("governor") == "reject"
                or any(k[1] == sym for k in engine_rej)):
            pass
        else:
            unexplained.append((t_dec, sym))
    checks["feasible_capacity_divergence"] = {
        "governor_capacity_rejections": len(capacity_rejects),
        "reasons": sorted({r["governor_reason"]
                           for r in capacity_rejects}),
        "g_only_fills": len(g_only),
        "unexplained": len(unexplained)}
    if not capacity_rejects:
        defects.append("no real feasible capacity divergence occurred")
    if unexplained:
        defects.append(f"{len(unexplained)} unexplained feasible "
                       f"divergences")

    # (d) nontrivial RL decisions
    acts = {}
    for r in comp.arms["G"].rl_decisions + comp.arms["F"].rl_decisions:
        a = r.get("executed_action")
        if a:
            acts[a] = acts.get(a, 0) + 1
    checks["rl_actions_executed"] = acts
    for need in ("tighten_stop", "reduce_25", "close"):
        if acts.get(need, 0) == 0:
            defects.append(f"RL action {need} never executed")

    # (e) nonzero mechanically reconciled funding across EVERY engine
    from lab.tools.holdout_evaluator import funding_reconciliation
    frecon = {}
    total_applied = 0
    total_paid_abs = 0.0
    missing_seen = 0
    sign_bad = []
    states = {a: comp.arms[a] for a in ARMS}
    states["G_matched"] = comp.shadow_matched
    states["G_feasible"] = comp.shadow_feasible
    for name, st in states.items():
        rec = funding_reconciliation(st.engine.events,
                                     st.engine.positions)
        frecon[name] = rec
        total_applied += rec["n_applied"]
        total_paid_abs += abs(rec["total_paid"])
        missing_seen += rec["n_missing"]
        if rec.get("event_to_equity_reconciled") is False:
            defects.append(f"funding event-to-equity reconciliation "
                           f"failed for {name}")
        for e in st.engine.events:
            if e["kind"] != "funding":
                continue
            # all stress positions are LONG: +rate pays, -rate receives
            if e["paid"] != 0 and (e["paid"] > 0) != (e["rate"] > 0):
                sign_bad.append((name, e["symbol"], e["rate"], e["paid"]))
    checks["funding"] = {
        "n_applied_total": int(total_applied),
        "abs_paid_total": total_paid_abs,
        "n_missing_total": int(missing_seen),
        "sign_violations": len(sign_bad),
        "per_engine": {n: {"applied": r["n_applied"],
                           "missing": r["n_missing"],
                           "paid": r["total_paid"],
                           "reconciled":
                               r.get("event_to_equity_reconciled")}
                       for n, r in frecon.items()}}
    if total_applied == 0 or total_paid_abs == 0.0:
        defects.append("funding scenario applied ZERO funding")
    if missing_seen == 0:
        defects.append("deliberately missing funding (W13) was silent")
    if sign_bad:
        defects.append(f"{len(sign_bad)} funding sign violations")

    # (f) D74 staggered funding-entry: G first fills STAG exactly on an
    # 8h boundary while another arm already holds it (shared map
    # contains STAG); NEITHER G actual NOR the matched clone pays
    # entry-bar funding; the matched clone (held conventionally) pays
    # at later boundaries.
    def stag_funding(st, at=None, after=None):
        return [e for e in st.engine.events
                if e["kind"] == "funding" and e["symbol"] == "STAGUSDT"
                and (at is None or e["t"] == at)
                and (after is None or e["t"] > after)]
    g_stag_opens = [e["t"] for e in comp.arms["G"].engine.events
                    if e["kind"] == "fill_open"
                    and e["symbol"] == "STAGUSDT"]
    a_at_entry = stag_funding(comp.arms["A"], at=t_stag_entry)
    g_at_entry = stag_funding(comp.arms["G"], at=t_stag_entry)
    m_at_entry = stag_funding(comp.shadow_matched, at=t_stag_entry)
    m_later = stag_funding(comp.shadow_matched, after=t_stag_entry)
    checks["staggered_funding_entry"] = {
        "g_first_fill_at_8h_boundary":
            bool(g_stag_opens) and g_stag_opens[0] == t_stag_entry,
        "other_arm_held_and_paid_at_entry": len(a_at_entry) > 0,
        "g_entry_bar_funding_events": len(g_at_entry),
        "matched_entry_bar_funding_events": len(m_at_entry),
        "matched_later_funding_events": len(m_later)}
    if not (g_stag_opens and g_stag_opens[0] == t_stag_entry):
        defects.append("staggered scenario: G did not first fill STAG "
                       "at the 8h boundary")
    if not a_at_entry:
        defects.append("staggered scenario: no other arm held STAG "
                       "across the entry funding boundary")
    if g_at_entry:
        defects.append("staggered scenario: G actual paid entry-bar "
                       "funding")
    if m_at_entry:
        defects.append("staggered scenario: matched clone paid "
                       "entry-bar funding (D74 defect)")
    if not m_later:
        defects.append("staggered scenario: matched clone never funded "
                       "after its entry bar")

    # exports
    paths = {}

    def save(name, obj):
        p = os.path.join(args.out_dir, f"STRESS_INVALID_{name}")
        with gzip.open(p, "wt") as fh:
            for rec in obj:
                fh.write(json.dumps(rec, sort_keys=True, default=float)
                         + "\n")
        paths[name] = p

    for a in ARMS:
        save(f"events_{a}.jsonl.gz", comp.arms[a].engine.events)
    save("events_G_matched.jsonl.gz", comp.shadow_matched.engine.events)
    save("events_G_feasible.jsonl.gz", comp.shadow_feasible.engine.events)
    save("decisions_G_feasible.jsonl.gz", comp.shadow_feasible.decisions)
    save("rl_decisions_F.jsonl.gz", comp.arms["F"].rl_decisions)
    save("rl_decisions_G.jsonl.gz", comp.arms["G"].rl_decisions)
    manifest = {"marker": MARKER, "checks": checks, "defects": defects,
                "rounds": comp.coordinator.counts(),
                "artifacts": {n: {"path": p, "sha256":
                                  hashlib.sha256(open(p, "rb").read())
                                  .hexdigest()}
                              for n, p in paths.items()}}
    mp = os.path.join(args.out_dir, "STRESS_INVALID_manifest.json")
    with open(mp, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(json.dumps({"checks": checks, "defects": defects}, indent=1,
                     default=str))
    print("manifest:", mp)
    if defects:
        raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover
    main()
