"""Pre-Checkpoint-2 readiness (D66): the frozen evaluator's statistics
machinery is verified on synthetic data (no holdout access anywhere),
and the gate remains fail-closed with the evaluator plugged in.
"""
import numpy as np

from lab.tools.holdout_evaluator import (evaluation_statistics,
                                         holm_bonferroni,
                                         supporting_metrics)


def test_holm_bonferroni_known_example():
    p = {"B": 0.01, "C": 0.04, "D": 0.03, "E": 0.005, "F": 0.5,
         "G": 0.2}
    adj = holm_bonferroni(p)
    # E smallest: 6*0.005=0.03; B next: 5*0.01=0.05; D: 4*0.03=0.12;
    # C: 3*0.04=0.12; G: 2*0.2=0.4; F: 1*0.5=0.5 (monotone enforced)
    assert abs(adj["E"] - 0.03) < 1e-12
    assert abs(adj["B"] - 0.05) < 1e-12
    assert abs(adj["D"] - 0.12) < 1e-12
    assert abs(adj["C"] - 0.12) < 1e-12
    assert abs(adj["G"] - 0.40) < 1e-12
    assert abs(adj["F"] - 0.50) < 1e-12
    assert all(0 < v <= 1 for v in adj.values())


def _curve(rets):
    return np.concatenate([[10_000.0], 10_000.0 * np.cumprod(1 + rets)])


def test_evaluation_statistics_identical_arm_never_improves():
    rng = np.random.default_rng(5)
    r = rng.normal(0.0002, 0.01, size=800)
    curves = {"A": _curve(r), "B": _curve(r.copy())}
    out = evaluation_statistics(curves)
    inf = out["inference"]["B"]
    # identical returns: paired deltas are exactly 0 -> delta<=0 always
    assert inf["p_upper_raw"] > 0.99
    assert inf["drawdown_constraint_pass"] is True   # DD95 equal
    assert inf["improves_over_A"] is False
    assert out["arms"]["B"]["dd95_bootstrap_decimal"] == \
        out["arms"]["A"]["dd95_bootstrap_decimal"]


def test_evaluation_statistics_dominant_arm_improves():
    rng = np.random.default_rng(6)
    r = rng.normal(0.0, 0.01, size=800)
    curves = {"A": _curve(r), "B": _curve(r + 0.004)}  # strictly better
    out = evaluation_statistics(curves)
    inf = out["inference"]["B"]
    assert inf["p_upper_raw"] < 0.01
    assert inf["p_holm"] < 0.05
    assert inf["drawdown_constraint_pass"] is True    # smaller drawdowns
    assert inf["improves_over_A"] is True


def test_evaluation_statistics_drawdown_constraint_blocks():
    rng = np.random.default_rng(7)
    r = rng.normal(0.0005, 0.004, size=800)
    # B: higher mean but far riskier (bigger drawdowns)
    rb = r * 6.0 + 0.0015
    curves = {"A": _curve(r), "B": _curve(rb)}
    out = evaluation_statistics(curves)
    inf = out["inference"]["B"]
    assert out["arms"]["B"]["dd95_bootstrap_decimal"] > \
        out["arms"]["A"]["dd95_bootstrap_decimal"]
    assert inf["drawdown_constraint_pass"] is False
    assert inf["improves_over_A"] is False            # regardless of p


def test_supporting_metrics_sanity():
    rng = np.random.default_rng(8)
    r = rng.normal(0.0003, 0.008, size=400)
    c = _curve(r)
    m = supporting_metrics(c, [])
    assert abs(m["net_return"] - (c[-1] / c[0] - 1)) < 1e-12
    assert 0 <= m["max_drawdown_observed"] < 1
    assert m["tail_loss_mean_worst5pct"] < 0
    assert len(m["stability_halves"]) == 2


def test_gate_still_fail_closed_with_evaluator_plugged_in(tmp_path):
    """Plugging in the frozen evaluator changed NOTHING upstream: with
    no authorization record, evaluate_holdout refuses before touching
    anything, and the refusal is audit-logged."""
    import os

    import pytest

    from lab.data.unseal import UnsealRefused, evaluate_holdout
    mdir = tmp_path / "manifests"
    mdir.mkdir()
    art = tmp_path / "holdout-raw-v1.tar.age"
    art.write_bytes(b"irrelevant")
    with pytest.raises(UnsealRefused):
        evaluate_holdout(str(art), str(mdir),
                         evaluator=lambda d: {},
                         results_path=str(tmp_path / "res.json"),
                         repo_root=str(tmp_path),
                         model_dir=str(tmp_path), sb3_dir=str(tmp_path))
    assert os.path.exists(mdir / "access_audit.jsonl")