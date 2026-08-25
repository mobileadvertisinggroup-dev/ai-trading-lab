"""Differential gate harness (SPEC_FINAL-1.2.md §13).

Runs one fixture through BOTH independent implementations — the main
simulator (lab.sim) and the Independent Reference Ledger (lab.refledger) —
normalizes each output to a canonical transaction list, and compares
transaction-by-transaction. On mismatch it reports the FIRST divergence with
both sides' records.

This harness is the only module allowed to import both implementations
(verification only); the implementations never import each other.

Comparison tolerance: numeric fields must agree within REL_TOL = 1e-9
relative (covers float-association differences between two independently
ordered computations); anything larger is a divergence. Structural fields
(kind, symbol, pos_id, side, reason, order, count) must match exactly.
"""
from __future__ import annotations

import math

from lab.refledger.ledger import replay as ref_replay
from lab.sim.engine import Bar, Costs, Engine

REL_TOL = 1e-9

_NUMERIC = ("qty", "price", "fee", "pnl", "stop", "target", "rate", "mark",
            "paid", "notional", "equity")
_STRUCT = ("kind", "symbol", "pos_id", "side", "reason", "queued_reason", "t")


# ------------------------------------------------------------ sim adapter

def run_sim(fx: dict) -> tuple[list[dict], float]:
    """Drive lab.sim.engine with a fixture; return (raw events, final cash)."""
    lim = fx["limits"]
    e = Engine(fx["starting_cash"], max_positions=lim["max_positions"],
               max_gross_exposure=lim["max_gross_exposure"],
               min_notional=lim["min_notional"])
    bar_ms = int(fx["bar_ms"])
    f_int = int(fx["funding_interval_ms"])
    bars = {s: {int(r[0]): Bar(int(r[0]), *map(float, r[1:5])) for r in rows}
            for s, rows in fx["bars"].items()}
    funding = {s: {int(t): float(r) for t, r in m.items()}
               for s, m in fx.get("funding", {}).items()}
    by_t: dict[int, list[dict]] = {}
    for ins in fx["instructions"]:
        by_t.setdefault(int(ins["t"]), []).append(ins)
    all_ts = sorted({t for tb in bars.values() for t in tb} | set(by_t))

    for t in all_ts:
        for ins in by_t.get(t, []):
            if ins["type"] == "entry":
                c = ins["costs"]
                e.submit_entry(ins["symbol"], int(ins["side"]),
                               float(ins["qty"]), stop=0.0, target=0.0,
                               r_dist=float(ins["stop_offset"]),
                               decision_ts=t,
                               costs=Costs(c["hs"], c["slip"], c["fee"]),
                               max_notional=ins.get("max_notional"),
                               stop_offset=float(ins["stop_offset"]),
                               target_offset=float(ins["target_offset"]))
            elif ins["type"] == "exit":
                e.submit_exit(int(ins["pos_id"]), 1.0, ins["reason"],
                              slip_mult=float(ins.get("slip_mult", 1.0)))
        t_bars = {s: tb[t] for s, tb in bars.items() if t in tb}
        f_t, prev_close = {}, {}
        if t % f_int == 0:
            for s in bars:
                if t in funding.get(s, {}):
                    f_t[s] = funding[s][t]
                prev = bars[s].get(t - bar_ms)
                if prev is not None:
                    prev_close[s] = prev.close
        e.process_bar_time(t, t_bars, funding=f_t, prev_close=prev_close)
    return e.events, e.cash


# ------------------------------------------------------- normalization

_SIM_KIND = {"fill_open": "open", "fill_close": "close", "rejection": "reject",
             "entry_cancelled": "cancel", "funding": "funding",
             "funding_missing": "funding_missing", "ambiguity": "ambiguity",
             "insolvency": "insolvency", "protection_deferred":
             "protection_deferred", "exit_deferred": "exit_deferred",
             "exit_dropped": "exit_dropped",
             "exit_open_gap_stop_priority": "gap_stop_priority"}
_DROP_SIM = {"position_closed", "stop_tightened", "invalid_action"}


def normalize_sim(events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        if ev["kind"] in _DROP_SIM:
            continue
        kind = _SIM_KIND[ev["kind"]]
        rec = {k: ev[k] for k in ev
               if k in _STRUCT + _NUMERIC and k != "kind"}
        rec["kind"] = kind
        rec.pop("open", None)
        out.append(rec)
    return out


def normalize_ref(ledger: list[dict]) -> list[dict]:
    out = []
    for ev in ledger:
        rec = {k: ev[k] for k in ev if k in _STRUCT + _NUMERIC}
        out.append(rec)
    return out


# --------------------------------------------------------- comparison

def _num_eq(a, b) -> bool:
    return math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=1e-9)


def compare(fx: dict) -> dict:
    """Run both implementations on fx. Returns
    {"match": bool, "n": int, ...on mismatch: first-divergence report...}"""
    sim_events, sim_cash = run_sim(fx)
    ref_ledger = ref_replay(fx)
    ref_cash = ref_ledger[-1]["cash_after"] if ref_ledger else fx["starting_cash"]
    a = normalize_sim(sim_events)
    b = normalize_ref(ref_ledger)

    n = min(len(a), len(b))
    for i in range(n):
        ra, rb = a[i], b[i]
        for k in _STRUCT:
            if ra.get(k) != rb.get(k):
                return {"match": False, "index": i, "field": k,
                        "sim": ra, "ref": rb,
                        "reason": f"structural mismatch on {k!r}"}
        for k in _NUMERIC:
            if (k in ra) != (k in rb):
                return {"match": False, "index": i, "field": k,
                        "sim": ra, "ref": rb,
                        "reason": f"field presence mismatch on {k!r}"}
            if k in ra and not _num_eq(ra[k], rb[k]):
                return {"match": False, "index": i, "field": k,
                        "sim": ra, "ref": rb,
                        "reason": f"numeric divergence on {k!r}: "
                                  f"{ra[k]} vs {rb[k]}"}
    if len(a) != len(b):
        return {"match": False, "index": n, "field": "length",
                "sim": a[n] if n < len(a) else None,
                "ref": b[n] if n < len(b) else None,
                "reason": f"transaction count differs: sim={len(a)} ref={len(b)}"}
    if not _num_eq(sim_cash, ref_cash):
        return {"match": False, "index": None, "field": "final_cash",
                "sim": sim_cash, "ref": ref_cash,
                "reason": "final cash differs"}
    return {"match": True, "n": len(a), "final_cash": sim_cash}
