"""ML label construction — SPEC_FINAL-1.2.md §4.

The primary label for Arms B, C, and E: the net R-multiple achieved by the
candidate under Arm A's frozen entry and management rules, including fees,
spread, slippage, and funding. Inputs are ONLY the frozen Arm A ledgers
(candidate ledger + engine event stream), so every label is reproducible
directly from them. No RL-managed outcomes, no Arm G outcomes, no
alternative exits.

Candidates without a realized Arm A outcome produce no label; they are
returned with an explicit exclusion reason (never silently dropped).
"""
from __future__ import annotations


def build_labels(candidates: list[dict], events: list[dict]) -> list[dict]:
    """Returns one record per candidate:
    {**candidate keys, executed, pos_id, qty_filled, entry_t, exit_t,
     net_pnl, net_r, info_interval, exclusion}
    exclusion is None for labeled examples; otherwise one of
    governor_rejected / capacity_rejected / min_notional_rejected /
    cancelled_missing_bar / ruined_rejected / still_open / no_fill.
    """
    opens: dict[tuple[int, str], dict] = {}
    by_pos: dict[int, dict] = {}
    rejections: dict[tuple[int, str], str] = {}
    for ev in events:
        if ev["kind"] == "fill_open":
            key = (int(ev["decision_ts"]), ev["symbol"])
            opens[key] = ev
            by_pos[ev["pos_id"]] = {"open": ev, "funding": 0.0,
                                    "closes": []}
        elif ev["kind"] == "funding" and ev.get("pos_id") in by_pos:
            by_pos[ev["pos_id"]]["funding"] += ev["paid"]
        elif ev["kind"] == "fill_close" and ev.get("pos_id") in by_pos:
            by_pos[ev["pos_id"]]["closes"].append(ev)
        elif ev["kind"] == "rejection" and "decision_ts" in ev:
            rejections[(int(ev["decision_ts"]), ev["symbol"])] = ev["reason"]
        elif ev["kind"] == "entry_cancelled":
            rejections[(int(ev["decision_ts"]), ev["symbol"])] = "missing_bar"

    out = []
    for cand in candidates:
        key = (int(cand["t"]), cand["symbol"])
        rec = dict(cand)
        rec.update({"executed": False, "pos_id": None, "qty_filled": None,
                    "entry_t": None, "exit_t": None, "net_pnl": None,
                    "net_r": None, "info_interval": None, "exclusion": None})
        if cand.get("governor") == "reject":
            rec["exclusion"] = "governor_rejected"
        elif key in opens:
            op = opens[key]
            pos = by_pos[op["pos_id"]]
            fees = op["fee"] + sum(c["fee"] for c in pos["closes"])
            gross = sum(c["pnl"] for c in pos["closes"])
            open_qty = op["qty"] - sum(c["qty"] for c in pos["closes"])
            if open_qty > 1e-12:
                rec["exclusion"] = "still_open"
            else:
                exit_t = max(c["t"] for c in pos["closes"])
                net = gross - fees - pos["funding"]
                risk = op["qty"] * cand["r_dist"]        # 1R at entry
                rec.update({"executed": True, "pos_id": op["pos_id"],
                            "qty_filled": op["qty"], "entry_t": op["t"],
                            "exit_t": int(exit_t), "net_pnl": net,
                            "net_r": net / risk,
                            "info_interval": [int(cand["t"]), int(exit_t)]})
        elif key in rejections:
            reason = rejections[key]
            rec["exclusion"] = {"capacity": "capacity_rejected",
                                "min_notional": "min_notional_rejected",
                                "missing_bar": "cancelled_missing_bar",
                                "ruined": "ruined_rejected",
                                "max_positions": "capacity_rejected",
                                }.get(reason, reason)
        else:
            rec["exclusion"] = "no_fill"
        out.append(rec)
    return out
