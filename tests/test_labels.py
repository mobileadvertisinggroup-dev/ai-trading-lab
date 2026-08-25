"""Tests: label construction (spec §4) and variable-horizon purge (§10)."""
import numpy as np
import pytest

from lab import protocol as P
from lab.arms.arm_a import ArmARunner, ArrayProvider
from lab.labels.labels import build_labels
from lab.labels.purge import (HoldoutContaminationError, MAX_HORIZON_MS,
                              chronological_split)

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)
HIST = 96


def build_symbol(levels_4h, wiggle=0.1):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
            "low": lv - wiggle, "close": lv.copy()}


def run_breakout():
    levels = [100.0] * HIST + [105.0, 105.0] + [108.0] * 3
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})
    r = ArmARunner(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"])
    r.run(T0, T0 + (len(levels) * 16 - 1) * B15)
    return r


def test_labels_reproducible_from_arm_a_ledger():
    r = run_breakout()
    labels = build_labels(r.candidates, r.engine.events)
    assert len(labels) == len(r.candidates)
    first = labels[0]
    assert first["executed"] and first["exclusion"] is None
    # reproducibility: net_r recomputed independently from the raw events
    op = [e for e in r.engine.events if e["kind"] == "fill_open"
          and e["pos_id"] == first["pos_id"]][0]
    closes = [e for e in r.engine.events if e["kind"] == "fill_close"
              and e["pos_id"] == first["pos_id"]]
    net = sum(c["pnl"] for c in closes) - op["fee"] \
        - sum(c["fee"] for c in closes)
    assert first["net_pnl"] == pytest.approx(net)
    assert first["net_r"] == pytest.approx(
        net / (op["qty"] * first["r_dist"]))
    # the position hit its +3R target; costs make net_r slightly below 3
    assert 2.5 < first["net_r"] < 3.0
    assert first["info_interval"][0] == first["t"]
    assert first["info_interval"][1] == closes[-1]["t"]
    # second candidate's position is still open at sim end -> excluded
    second = labels[1]
    assert second["exclusion"] == "still_open" and second["net_r"] is None


def test_labels_record_exclusions_not_silence():
    r = run_breakout()
    # forge a governor-rejected candidate and an unmatched one
    cands = r.candidates + [
        dict(r.candidates[0], symbol="ZZZUSDT", governor="reject"),
        dict(r.candidates[0], symbol="NOFILL", governor="approve"),
    ]
    labels = build_labels(cands, r.engine.events)
    assert labels[-2]["exclusion"] == "governor_rejected"
    assert labels[-1]["exclusion"] == "no_fill"


def make_ex(t, exit_t, net_r=1.0, exclusion=None):
    return {"t": t, "exit_t": exit_t, "net_r": None if exclusion else net_r,
            "info_interval": None if exclusion else [t, exit_t],
            "exclusion": exclusion}


def test_purge_variable_horizon_split():
    val_start = T0 + 1000 * H4
    holdout_start = T0 + 1400 * H4
    hold_ms = P.MAX_HOLD_BARS_4H * H4
    ex = [
        make_ex(T0, T0 + 10 * H4),                              # train
        make_ex(val_start - hold_ms, val_start - 1),            # train (ends just before)
        make_ex(val_start - 2 * H4, val_start + 3 * H4),        # purged_train
        make_ex(val_start, val_start + 10 * H4),                # validation
        make_ex(holdout_start - H4, holdout_start + H4),        # purged_validation
        make_ex(T0, T0 + H4, exclusion="capacity_rejected"),    # unlabeled
    ]
    s = chronological_split(ex, val_start, holdout_start)
    assert [len(s[k]) for k in ("train", "validation", "purged_train",
                                "purged_validation", "unlabeled")] \
        == [2, 1, 1, 1, 1]
    # nothing lost
    assert sum(len(v) for v in s.values()) == len(ex)
    # no training interval touches validation
    assert all(e["info_interval"][1] < val_start for e in s["train"])
    assert all(e["info_interval"][1] < holdout_start
               for e in s["validation"])


def test_purge_rejects_holdout_contamination_and_horizon_violation():
    val_start = T0 + 1000 * H4
    holdout_start = T0 + 1400 * H4
    with pytest.raises(HoldoutContaminationError):
        chronological_split([make_ex(holdout_start + H4,
                                     holdout_start + 2 * H4)],
                            val_start, holdout_start)
    too_long = make_ex(T0, T0 + MAX_HORIZON_MS + B15)
    with pytest.raises(ValueError):
        chronological_split([too_long], val_start, holdout_start)


def test_purge_boundary_alignment_enforced():
    with pytest.raises(ValueError):
        chronological_split([], T0 + 1, T0 + H4)
    with pytest.raises(ValueError):
        chronological_split([], T0 + H4, T0 + H4)
