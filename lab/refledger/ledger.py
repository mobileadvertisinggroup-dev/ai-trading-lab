"""INDEPENDENT REFERENCE LEDGER — verification only (SPEC_FINAL-1.2.md §13).

Implemented solely from SIMULATOR_SEMANTICS.md (§§1–3, 5: the shared
differential subset). Deliberately minimal and table-driven so a human can
inspect it line by line.

INDEPENDENCE RULES (constitutional): this package shares no accounting,
execution, portfolio, fee, stop, sizing, or P&L implementation code with the
main simulator; it never imports lab.sim, and lab.sim never imports it. It
imports nothing from lab.* at all — every constant it needs arrives inside
the fixture, so the two implementations cannot share a single number by
code path.

Input: a FIXTURE dict (the neutral format defined in lab/verify/README.md):

    {"starting_cash": float,
     "limits": {"max_positions": int, "max_gross_exposure": float,
                "min_notional": float},
     "instructions": [
        {"t": int, "type": "entry", "symbol": str, "side": +1|-1,
         "qty": float, "costs": {"hs": float, "slip": float, "fee": float},
         "stop_offset": float, "target_offset": float,     # anchored at fill
         "max_notional": float | None},
        {"t": int, "type": "exit", "pos_id": int, "reason": str,
         "slip_mult": float}],                             # full closes only
     "bars": {symbol: [[t, o, h, l, c], ...]},
     "funding": {symbol: {t(str|int): rate}},
     "funding_interval_ms": int,
     "bar_ms": int}

Output: replay(fixture) -> list of transaction records, chronological:
    {"t", "kind": "open"|"close"|"reject"|"cancel"|"funding"|"ambiguity"|
     "insolvency", ...numeric detail..., "cash_after"}
Position ids are assigned 1, 2, ... in order of successful opens.
"""
from __future__ import annotations


def replay(fx: dict) -> list[dict]:
    cash = float(fx["starting_cash"])
    lim = fx["limits"]
    bar_ms = int(fx["bar_ms"])
    f_int = int(fx["funding_interval_ms"])

    # index bars: symbol -> {t: (o, h, l, c)}
    bars = {s: {int(r[0]): (float(r[1]), float(r[2]), float(r[3]), float(r[4]))
                for r in rows}
            for s, rows in fx["bars"].items()}
    funding = {s: {int(t): float(r) for t, r in m.items()}
               for s, m in fx.get("funding", {}).items()}

    # instructions grouped by timestamp
    by_t: dict[int, list[dict]] = {}
    for ins in fx["instructions"]:
        by_t.setdefault(int(ins["t"]), []).append(ins)

    all_ts = sorted({t for tb in bars.values() for t in tb} | set(by_t))

    ledger: list[dict] = []
    positions: dict[int, dict] = {}   # id -> state
    next_id = 1
    ruined = False
    pending_exits: list[dict] = []

    def rec(t, kind, **kw):
        kw["t"] = t
        kw["kind"] = kind
        kw["cash_after"] = cash
        ledger.append(kw)

    def openpos():
        return [p for p in positions.values() if not p["closed"]]

    def mark_of(p, bar_open_by_sym):
        if p["symbol"] in bar_open_by_sym:
            return bar_open_by_sym[p["symbol"]]
        return p["last_mark"]

    def equity(bar_open_by_sym):
        # accumulation order is part of the frozen semantics (§1): start at
        # cash, add each open position's unrealized P&L in position-id order
        eq = cash
        for p in openpos():
            eq += p["side"] * p["qty"] * (mark_of(p, bar_open_by_sym)
                                          - p["entry"])
        return eq

    def exposure(bar_open_by_sym):
        x = 0.0
        for p in openpos():
            x += p["qty"] * mark_of(p, bar_open_by_sym)
        return x

    def close_fill(t, p, ref, slip_mult, reason):
        nonlocal cash
        c = p["costs"]
        price = ref * (1 - p["side"] * (c["hs"] + c["slip"] * slip_mult))
        fee = p["qty"] * price * c["fee"]
        pnl = p["side"] * p["qty"] * (price - p["entry"])
        cash += pnl - fee
        p["closed"] = True
        p["reason"] = reason
        rec(t, "close", pos_id=p["id"], symbol=p["symbol"], qty=p["qty"],
            price=price, fee=fee, pnl=pnl, reason=reason)

    for t in all_ts:
        bar_open = {s: tb[t][0] for s, tb in bars.items() if t in tb}

        # -- 0. ingest this timestamp's instructions BEFORE the bar steps:
        #       an exit queued at t executes at t's open (semantics §3.2)
        entries_now = []
        for ins in by_t.get(t, []):
            if ins["type"] == "exit":
                pending_exits.append(ins)
            elif ins["type"] == "entry":
                entries_now.append(ins)

        # -- 1. funding (semantics §3.1): mark = previous bar close, else
        #       current open, else last mark; missing rate -> 0 + record
        if t % f_int == 0:
            for p in openpos():
                s = p["symbol"]
                rate = funding.get(s, {}).get(t)
                if rate is None:
                    rec(t, "funding_missing", pos_id=p["id"], symbol=s)
                    continue
                prev = bars[s].get(t - bar_ms)
                mark = prev[3] if prev else (bar_open.get(s, p["last_mark"]))
                paid = rate * p["qty"] * mark * p["side"]
                cash -= paid
                rec(t, "funding", pos_id=p["id"], symbol=s, rate=rate,
                    mark=mark, paid=paid)

        # -- 2. pending market exits (full closes; stop priority on gap)
        still = []
        for x in pending_exits:
            p = positions.get(x["pos_id"])
            if p is None or p["closed"]:
                rec(t, "exit_dropped", pos_id=x["pos_id"], reason=x["reason"])
                continue
            b = bars[p["symbol"]].get(t)
            if b is None:
                still.append(x)
                rec(t, "exit_deferred", pos_id=p["id"], reason=x["reason"])
                continue
            o = b[0]
            gap_stop = o <= p["stop"] if p["side"] > 0 else o >= p["stop"]
            if gap_stop:
                rec(t, "gap_stop_priority", pos_id=p["id"],
                    queued_reason=x["reason"], stop=p["stop"])
                close_fill(t, p, o, 2.0, "stop")
            else:
                close_fill(t, p, o, x.get("slip_mult", 1.0), x["reason"])
        pending_exits = still

        # -- 3. entries in instruction order (capacity competition)
        for ins in entries_now:
            if ruined:
                rec(t, "reject", symbol=ins["symbol"], reason="ruined")
                continue
            b = bars.get(ins["symbol"], {}).get(t)
            if b is None:
                rec(t, "cancel", symbol=ins["symbol"], reason="missing_bar")
                continue
            c = ins["costs"]
            side = int(ins["side"])
            price = b[0] * (1 + side * (c["hs"] + c["slip"]))
            qty = float(ins["qty"])
            cap = ins.get("max_notional")
            if cap is not None and qty * price > cap:
                qty = cap / price
            notional = qty * price
            if notional < lim["min_notional"]:
                rec(t, "reject", symbol=ins["symbol"], reason="min_notional",
                    notional=notional)
                continue
            if len(openpos()) >= lim["max_positions"]:
                rec(t, "reject", symbol=ins["symbol"], reason="max_positions")
                continue
            eq = equity(bar_open)
            if exposure(bar_open) + notional > lim["max_gross_exposure"] * eq:
                rec(t, "reject", symbol=ins["symbol"], reason="capacity",
                    notional=notional, equity=eq)
                continue
            fee = notional * c["fee"]
            cash -= fee
            p = {"id": next_id, "symbol": ins["symbol"], "side": side,
                 "qty": qty, "entry": price,
                 "stop": price - side * float(ins["stop_offset"]),
                 "target": price + side * float(ins["target_offset"]),
                 "costs": c, "last_mark": price, "closed": False}
            positions[next_id] = p
            next_id += 1
            rec(t, "open", pos_id=p["id"], symbol=p["symbol"], side=side,
                qty=qty, price=price, fee=fee, stop=p["stop"],
                target=p["target"])

        # -- 4. protection, in position-id order (stop-first ambiguity,
        #       gap-through stop ref, target exactly at limit)
        for pid in sorted(positions):
            p = positions[pid]
            if p["closed"]:
                continue
            b = bars[p["symbol"]].get(t)
            if b is None:
                rec(t, "protection_deferred", pos_id=pid)
                continue
            o, h, l, cl = b
            stop_hit = l <= p["stop"] if p["side"] > 0 else h >= p["stop"]
            tgt_hit = h >= p["target"] if p["side"] > 0 else l <= p["target"]
            if stop_hit and tgt_hit:
                rec(t, "ambiguity", pos_id=pid, stop=p["stop"],
                    target=p["target"])
            if stop_hit:
                ref = (min(p["stop"], o) if p["side"] > 0
                       else max(p["stop"], o))
                close_fill(t, p, ref, 2.0, "stop")
            elif tgt_hit:
                # limit: fill exactly at target, taker fee only
                fee = p["qty"] * p["target"] * p["costs"]["fee"]
                pnl = p["side"] * p["qty"] * (p["target"] - p["entry"])
                cash += pnl - fee
                p["closed"] = True
                p["reason"] = "target"
                rec(t, "close", pos_id=pid, symbol=p["symbol"], qty=p["qty"],
                    price=p["target"], fee=fee, pnl=pnl, reason="target")
            else:
                p["last_mark"] = cl

        # -- 5. insolvency at bar-close marks (incl. flat negative cash)
        if not ruined:
            closes = {s: bars[s][t][3] for s in bars if t in bars[s]}
            eq = cash
            for p in openpos():
                eq += p["side"] * p["qty"] * (closes.get(p["symbol"],
                                                         p["last_mark"])
                                              - p["entry"])
            if eq <= 0:
                rec(t, "insolvency", equity=eq)
                for p in list(openpos()):
                    ref = closes.get(p["symbol"], p["last_mark"])
                    close_fill(t, p, ref, 2.0, "insolvency")
                ruined = True

    return ledger
