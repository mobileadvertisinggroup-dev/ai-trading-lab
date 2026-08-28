"""Adjudication blocker 3: synchronized rounds must be fully
TRANSACTIONAL. A late arm failure — after earlier arms have proposed
entries, proposed exits, tightened a stop, invoked governor checks, and
appended decision records — must leave every arm and the G-shadow with
byte-identical pre-round state: cash/equity, positions (quantities AND
stops), pending operations, engine event streams, decision + RL ledgers,
governor state and events, model/adaptor state, and the shared candidate
ledger. Only the coordinator's centralized invalid-round record (with
diagnostics) may survive."""
import copy

import numpy as np

from lab import protocol as P
from lab.arms.arm_a import ArrayProvider
from lab.orchestration.competition import ARMS, Competition

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


class TightenPolicy:
    """Tightens the stop at every decision — guarantees a stop mutation
    happened inside the failing round before the failure."""
    version = "test-tighten"

    def action_from_obs(self, obs) -> str:
        return "tighten_stop"


class LateBomb:
    """Sizer (consulted by arms E and G, LATE in the round) that raises at
    a chosen boundary — after A/B/C/D decided, exits were proposed, F/G
    stops were tightened, governor checks ran, and decision records were
    appended. `capture` (optional) is invoked immediately BEFORE the
    raise so the test can prove in-round mutations (e.g. an already
    tightened stop) really happened prior to the failure."""
    version = "test-bomb"

    def __init__(self, fail_at: int, capture=None):
        self.fail_at = fail_at
        self.capture = capture
        self.captured = None

    def bucket(self, cand, features) -> float:
        if cand["t"] == self.fail_at:
            if self.capture is not None and self.captured is None:
                self.captured = self.capture()
            raise RuntimeError("late-arm failure injected by test")
        return 1.00


def full_state(comp):
    def arm_state(st):
        e, g = st.engine, st.governor
        return {
            "cash": e.cash, "ruined": e.ruined, "next_id": e._next_id,
            "positions": {pid: copy.deepcopy(vars(p))
                          for pid, p in e.positions.items()},
            "pending_in": copy.deepcopy(e._pending_entries),
            "pending_out": copy.deepcopy(e._pending_exits),
            "events": copy.deepcopy(e.events),
            "decisions": copy.deepcopy(st.decisions),
            "rl_decisions": copy.deepcopy(st.rl_decisions),
            "gov": {"emerg": g.emergency_pause, "integ": g.integrity_pause,
                    "day": g._day, "day_eq": g._day_start_equity,
                    "peaks": dict(g._day_peaks),
                    "events": copy.deepcopy(g.events)},
        }
    out = {a: arm_state(comp.arms[a]) for a in ARMS}
    # D61 blocker A: both G diagnostics are in the byte-compare
    out["__matched__"] = arm_state(comp.shadow_matched)
    out["__feasible__"] = arm_state(comp.shadow_feasible)
    out["__candidates__"] = copy.deepcopy(comp.candidates)
    return out


def test_late_arm_failure_equivalent_to_no_round_at_all():
    """The rigorous zero-effect proof: a run whose round at t_fail is
    invalidated BY A LATE FAILURE (after entries were proposed, exits
    queued, stops tightened, governor checks invoked, and decision records
    appended) must end in state IDENTICAL to a control run where that
    round simply never occurred (valid_round_fn False at t_fail). Market
    bar processing continues identically in both — the only permitted
    difference is the coordinator's centralized invalid-round record."""
    # SYM1: long-lived open position at the failing round (grinds at 106:
    # above the ~2xATR stop, below the +3R target, no trailing exit).
    # SYM2: fresh breakout candidate exactly AT the failing round.
    lv1 = [100.0] * HIST + [105.0, 105.0] + [106.0] * 12
    lv2 = [100.0] * (HIST + 6) + [108.0, 108.0] + [110.0] * 6
    n4 = max(len(lv1), len(lv2))
    lv1 += [lv1[-1]] * (n4 - len(lv1))
    lv2 += [lv2[-1]] * (n4 - len(lv2))
    d1, d2 = build_symbol(lv1), build_symbol(lv2)
    fail_at = T0 + (HIST + 7) * H4          # SYM2 breakout round
    end = T0 + (n4 * 16 - 1) * B15

    holder = {}

    def capture_stops():
        # runs INSIDE the failing round, just before the injected raise:
        # snapshot every F/G stop so the test can prove a stop was
        # ALREADY mutated by the RL tighten before the failure
        return {a: {p.pos_id: p.stop
                    for p in holder["bombed"].arms[a].engine
                    .open_positions()} for a in ("F", "G")}

    def make(bombed: bool):
        prov = ArrayProvider({"AAAUSDT": {k: v.copy() for k, v in d1.items()},
                              "BBBUSDT": {k: v.copy() for k, v in d2.items()}})
        sizer = (LateBomb(fail_at, capture=capture_stops) if bombed
                 else LateBomb(-1))
        valid = ((lambda t: True) if bombed
                 else (lambda t: t != fail_at))
        return Competition(prov, 10_000,
                           universe_fn=lambda t: ["AAAUSDT", "BBBUSDT"],
                           valid_round_fn=valid,
                           sizer_model=sizer, rl_policy=TightenPolicy())

    bombed = make(True)
    holder["bombed"] = bombed
    control = make(False)
    # confirm the failing round REALLY exercised the late-failure path:
    # open positions existed (wave 1), candidates existed (wave 2)
    bombed.run(T0, fail_at - B15)
    assert any(bombed.arms[a].engine.open_positions() for a in ARMS)
    control.run(T0, fail_at - B15)
    assert full_state(bombed) == full_state(control)
    pre_round_stops = {a: {p.pos_id: p.stop
                           for p in control.arms[a].engine.open_positions()}
                       for a in ("F", "G")}
    # reviewer check B: adapter/model state must carry NO round effects —
    # snapshot the stateless production-model surfaces before the failure
    model_state_before = {
        "ranker": dict(vars(bombed.ranker_model)),
        "regime": {k: v for k, v in vars(bombed.regime_model).items()},
        "policy": dict(vars(bombed.rl_policy)),
    }

    # process ONLY the failing round (plus its 15m bars, no further
    # decision round) so rollback effects are observable in isolation
    bombed.run(fail_at, fail_at + H4 - B15)
    control.run(fail_at, fail_at + H4 - B15)
    # reviewer check B — immediate stop mutation: inside the failing
    # round, BEFORE the injected failure, at least one F/G stop had
    # already been tightened relative to its pre-round value ...
    cap = bombed.sizer_model.captured
    assert cap is not None, "capture hook never ran"
    mutated = [(a, pid) for a in ("F", "G")
               for pid, s in cap[a].items()
               if pre_round_stops[a].get(pid) is not None
               and s != pre_round_stops[a][pid]]
    assert mutated, "no in-round stop mutation was observed pre-failure"
    # ... and the rollback restored every stop to the pre-round value
    for a in ("F", "G"):
        post = {p.pos_id: p.stop
                for p in bombed.arms[a].engine.open_positions()}
        for pid, s in pre_round_stops[a].items():
            assert post.get(pid) == s, (a, pid, s, post.get(pid))
    assert full_state(bombed) == full_state(control)

    bombed.run(fail_at + H4, end)
    control.run(fail_at + H4, end)
    assert full_state(bombed) == full_state(control), \
        "invalid round leaked state relative to the no-round control"
    assert not bombed.coordinator.is_valid(fail_at)
    assert bombed.coordinator.counts()["invalid"] >= 1
    # reviewer check B — adapter/model state after the failure: the
    # production adapters are stateless; nothing about the failed round
    # may persist in them (TightenPolicy holds no state by construction)
    assert dict(vars(bombed.ranker_model)) == model_state_before["ranker"]
    assert dict(vars(bombed.rl_policy)) == model_state_before["policy"]
    assert {k: v for k, v in vars(bombed.regime_model).items()} \
        == model_state_before["regime"]


def test_failure_before_any_decision_also_rolls_back():
    levels = [100.0] * HIST + [105.0, 105.0] + [108.0] * 3
    prov = ArrayProvider({"AAAUSDT": build_symbol(levels)})

    class FilterBomb:
        version = "test-filter-bomb"

        def accept(self, cand, features):
            raise RuntimeError("filter failure injected by test")

    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"],
                       filter_model=FilterBomb())
    end = T0 + (len(levels) * 16 - 1) * B15
    comp.run(T0, end)
    # every candidate-bearing round invalidates; NOTHING ever executed
    for a in ARMS:
        assert not [e for e in comp.arms[a].engine.events
                    if e["kind"] == "fill_open"], a
        assert comp.arms[a].engine.cash == 10_000
    assert comp.candidates == []
    assert comp.coordinator.counts()["invalid"] > 0
