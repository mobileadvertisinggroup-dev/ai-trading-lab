"""Dashboard skeleton tests: ledger-derived, market-data-free."""
import ast
import os

import numpy as np

from lab import protocol as P
from lab.arms.arm_a import ArmARunner, ArrayProvider
from lab.dashboard.build import build, leaderboard_row

B15 = P.BAR_15M_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % P.BAR_4H_MS)


def test_dashboard_builds_from_real_ledgers(tmp_path):
    levels = [100.0] * 96 + [105.0, 105.0] + [108.0] * 3
    n4 = len(levels)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels), 16)
    prov = ArrayProvider({"AAAUSDT": {
        "open_time": t, "open": lv.copy(), "high": lv + 0.1,
        "low": lv - 0.1, "close": lv.copy()}})
    r = ArmARunner(prov, 10_000, universe_fn=lambda x: ["AAAUSDT"])
    r.run(T0, int(t[-1]))

    out = build(
        [{"arm": "A", "display": "Arm A — Transparent Control",
          "starting_equity": 10_000.0, "equity_curve": r.equity_curve,
          "events": r.engine.events}],
        build_state_path="build_state.json",
        out_path=str(tmp_path / "index.html"))
    html_text = open(out).read()
    assert "Arm A — Transparent Control" in html_text
    assert "Leaderboard" in html_text and "Research integrity" in html_text
    # the displayed equity equals the ledger's final snapshot
    assert f"{r.equity_curve[-1]['equity']:,.2f}" in html_text

    row = leaderboard_row("A", "Arm A", r.equity_curve, r.engine.events,
                          10_000.0)
    closes = [e for e in r.engine.events if e["kind"] == "position_closed"]
    assert row["trades"] == len(closes)
    assert row["equity"] == r.equity_curve[-1]["equity"]


def test_dashboard_is_structurally_incapable_of_market_data_access():
    """§26: the dashboard must be incapable of reading holdout rows.
    Structural proof: its module imports nothing from lab.data (no lake,
    no GuardedLake, no paths into market data)."""
    src = open(os.path.join("lab", "dashboard", "build.py")).read()
    tree = ast.parse(src)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(m.startswith("lab.data") or m == "lab.data"
                   for m in imported), imported
    assert not any(m.startswith("lab.sim") for m in imported), imported
