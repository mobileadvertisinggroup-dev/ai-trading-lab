"""Dashboard skeleton — static, ledger-derived (SPEC FINAL-1.2 §26).

Generates a self-contained HTML page from IMMUTABLE ledgers only: per-arm
candidate ledgers, engine event streams, and equity curves, plus research-
integrity metadata (git commit, build state, test status, holdout state).
Every displayed number traces to a ledger record; the builder never reads
market data at all — it has no import of, or path to, the lake or
GuardedLake — so it is structurally incapable of touching holdout rows
(§26 last clause).

DECISION D20: the research-phase dashboard is a static generated artifact
(hostable on GitHub Pages, immutable per publication, zero server
infrastructure) rather than the spec-§27-default React/Next.js app. §27
permits this with a documented reason: no serving infrastructure exists in
this project's runtime (GitHub Actions + Pages), and a generated artifact
is itself part of the audit trail. A richer interactive UI can be layered
later without touching ledger semantics.
"""
from __future__ import annotations

import html
import json


def leaderboard_row(arm_id: str, display: str, equity_curve: list[dict],
                    events: list[dict], starting_equity: float) -> dict:
    """All values derived from the immutable ledgers passed in."""
    eq = [p["equity"] for p in equity_curve] or [starting_equity]
    peak, max_dd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    closes = [e for e in events if e["kind"] == "position_closed"]
    wins = [e for e in closes if e["realized_pnl"] > 0]
    losses = [e for e in closes if e["realized_pnl"] <= 0]
    fees = sum(e["fee"] for e in events if e["kind"] in
               ("fill_open", "fill_close"))
    funding = sum(e["paid"] for e in events if e["kind"] == "funding")
    return {
        "arm": arm_id, "display": display,
        "starting_equity": starting_equity,
        "equity": eq[-1],
        "net_return": eq[-1] / starting_equity - 1.0,
        "max_drawdown": max_dd,
        "trades": len(closes),
        "win_rate": len(wins) / len(closes) if closes else None,
        "avg_winner": (sum(e["realized_pnl"] for e in wins) / len(wins))
                      if wins else None,
        "avg_loser": (sum(e["realized_pnl"] for e in losses) / len(losses))
                     if losses else None,
        "fees": fees, "funding": funding,
        "rejections": sum(1 for e in events if e["kind"] == "rejection"),
    }


def _fmt(v, pct=False):
    if v is None:
        return "—"
    return f"{v:.2%}" if pct else f"{v:,.2f}"


def render(arms: list[dict], integrity: dict, title: str) -> str:
    """arms: list of leaderboard_row() outputs. integrity: git commit,
    spec/protocol hashes, test status, holdout state, round counts,
    experiment status — straight out of build_state.json."""
    rows = "\n".join(
        "<tr><td>{d}</td><td>{eq}</td><td>{nr}</td><td>{dd}</td>"
        "<td>{tr}</td><td>{wr}</td><td>{fees}</td><td>{rej}</td></tr>".format(
            d=html.escape(a["display"]), eq=_fmt(a["equity"]),
            nr=_fmt(a["net_return"], pct=True),
            dd=_fmt(a["max_drawdown"], pct=True), tr=a["trades"],
            wr=_fmt(a["win_rate"], pct=True), fees=_fmt(a["fees"]),
            rej=a["rejections"])
        for a in arms)
    integ = "\n".join(
        f"<tr><td>{html.escape(str(k))}</td>"
        f"<td><code>{html.escape(str(v))}</code></td></tr>"
        for k, v in integrity.items())
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:2rem;background:#0e1117;color:#e6e6e6}}
 table{{border-collapse:collapse;margin:1rem 0;width:100%}}
 td,th{{border:1px solid #333;padding:.4rem .6rem;text-align:right}}
 th{{background:#1a1f2b}} td:first-child,th:first-child{{text-align:left}}
 .banner{{background:#3a2f00;border:1px solid #665500;padding:.6rem 1rem;
   border-radius:6px;margin-bottom:1rem}}
 code{{color:#9ecbff}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<div class="banner">{html.escape(integrity.get('experiment_status', ''))}</div>
<h2>Leaderboard</h2>
<table><tr><th>Arm</th><th>Equity</th><th>Net return</th><th>Max DD</th>
<th>Trades</th><th>Win rate</th><th>Fees</th><th>Rejections</th></tr>
{rows}</table>
<h2>Research integrity</h2>
<table>{integ}</table>
<p>Every number on this page derives from immutable ledger records; this
generator reads no market data and cannot access the sealed holdout.</p>
</body></html>"""


def build(arm_inputs: list[dict], build_state_path: str, out_path: str,
          title: str = "AKRA AI TRADING LAB") -> str:
    """arm_inputs: [{arm, display, starting_equity, equity_curve, events}]"""
    with open(build_state_path) as f:
        bs = json.load(f)
    integrity = {
        "experiment_status": bs.get("phase_6_status") or bs.get("current_phase"),
        "current_phase": bs.get("current_phase"),
        "spec_version": bs.get("spec", {}).get("version"),
        "spec_sha256": bs.get("spec", {}).get("sha256"),
        "protocol_sha256": bs.get("protocol", {}).get("phase1_frozen_sha256"),
        "tests": bs.get("tests", {}).get("dev_suite"),
        "holdout": json.dumps(bs.get("holdout", {})),
        "integrity_manifest": bs.get("integrity_manifest_hash") or "not locked",
        "updated": bs.get("updated"),
    }
    rows = [leaderboard_row(a["arm"], a["display"], a["equity_curve"],
                            a["events"], a["starting_equity"])
            for a in arm_inputs]
    doc = render(rows, integrity, title)
    with open(out_path, "w") as f:
        f.write(doc)
    return out_path
