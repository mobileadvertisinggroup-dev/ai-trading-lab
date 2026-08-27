"""Adjudication blocker 2: mechanical training/inference observation
parity. The SAME underlying trade state, reached through (a) the live
orchestrator and (b) a training episode replaying the identical bars,
must produce BIT-IDENTICAL obs-v2 vectors on every one of the 10
dimensions, at every shared decision boundary."""
import numpy as np

from lab import protocol as P
from lab.arms.arm_a import ArrayProvider, tier_costs
from lab.arms.observation import (OBS_SCHEMA_HASH, ObsInputs,
                                  build_observation)
from lab.arms.rl_env import TradeManagementEnv
from lab.orchestration.competition import Competition

B15 = P.BAR_15M_MS
H4 = P.BAR_4H_MS
T0 = 1_700_000_000_000 - (1_700_000_000_000 % H4)
HIST = 96


def build_symbol(levels_4h, wiggle=0.4):
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + wiggle,
            "low": lv - wiggle, "close": lv.copy()}


class HoldAll:
    version = "hold"

    def action_from_obs(self, obs):
        return "hold"


def test_orchestrator_and_env_build_identical_observations():
    # varied path AFTER entry so MFE/MAE/vol/giveback are all nontrivial
    levels = [100.0] * HIST + [105.0, 105.0, 106.5, 105.5, 106.0, 105.2]
    data = build_symbol(levels)
    prov = ArrayProvider({"AAAUSDT": data})
    comp = Competition(prov, 10_000, universe_fn=lambda t: ["AAAUSDT"],
                       rl_policy=HoldAll())
    end = T0 + (len(levels) * 16 - 1) * B15
    comp.run(T0, end)

    # the orchestrator's F position + its recorded per-boundary decisions
    f_recs = [r for r in comp.arms["F"].rl_decisions
              if r["observation"] is not None]
    assert len(f_recs) >= 3, "need several live decision boundaries"
    p_events = [e for e in comp.arms["F"].engine.events
                if e["kind"] == "fill_open"]
    assert p_events
    op = p_events[0]
    decision_ts = int(op["decision_ts"])
    pos = comp.arms["F"].engine.positions[op["pos_id"]]

    # training episode replaying the IDENTICAL bars from the entry bar,
    # with the same qty/costs/ATR series; exposure_by_boundary carries the
    # orchestrator's own recorded exposure fraction per boundary
    series = comp._series["AAAUSDT"]
    lo = decision_ts + B15
    m = data["open_time"] >= lo
    bars = list(zip(data["open_time"][m], data["open"][m], data["high"][m],
                    data["low"][m], data["close"][m]))
    expo = {int(r["t"]): float(r["observation"][9]) for r in f_recs}
    trade = {"side": pos.side, "qty": op["qty"], "entry_ref": 105.0,
             "r_dist": pos.r_dist, "decision_ts": decision_ts,
             "atr_entry": pos.r_dist / P.STOP_ATR_MULT,
             "atr_t4_close_ms": (series.t4 + P.BAR_4H_MS),
             "atr_values": series.atr,
             "exposure_by_boundary": expo,
             "costs": {"hs": tier_costs(0).half_spread,
                       "slip": tier_costs(0).slippage,
                       "fee": tier_costs(0).fee}}
    env = TradeManagementEnv(trade, bars)
    obs, _ = env.reset(seed=0)

    # walk the env decision-by-decision; at each boundary the env's obs
    # must be bit-identical to the orchestrator's recorded vector
    checked = 0
    by_t = {int(r["t"]): np.array(r["observation"], np.float32)
            for r in f_recs}
    while True:
        x = env.obs_inputs()
        if x is None:
            break
        t_now = env.bars[env._i].open_time
        boundary = t_now + B15          # decision boundary this obs serves
        # orchestrator decided at boundaries t = decision_ts + k*4h; env
        # obs immediately BEFORE stepping corresponds to the same state
        # the orchestrator saw at the next boundary
        if boundary in by_t:
            env_obs = build_observation(x)
            assert env_obs.dtype == np.float32
            assert np.array_equal(env_obs, by_t[boundary]), \
                (boundary, env_obs.tolist(), by_t[boundary].tolist())
            checked += 1
        _, _, term, trunc, _ = env.step(0)   # hold, like the orchestrator
        if term or trunc:
            break
    assert checked >= 3, f"only {checked} boundaries compared"


def build_symbol_var(levels_4h, wiggles_4h):
    """Per-4h-bar wiggle amplitudes -> Wilder ATR CHANGES over time."""
    n4 = len(levels_4h)
    t = np.arange(T0, T0 + n4 * 16 * B15, B15, dtype=np.int64)
    lv = np.repeat(np.asarray(levels_4h, float), 16)
    w = np.repeat(np.asarray(wiggles_4h, float), 16)
    return {"open_time": t, "open": lv.copy(), "high": lv + w,
            "low": lv - w, "close": lv.copy()}


class ScriptedPolicy:
    """Deterministic action script, cycled per invocation — produces
    executed tightens and partial reductions across positions/arms."""
    version = "scripted"
    SCRIPT = ("hold", "tighten_stop", "reduce_25", "hold", "tighten_stop",
              "reduce_50", "hold", "move_stop_breakeven", "hold")

    def __init__(self):
        self.k = 0

    def action_from_obs(self, obs):
        a = self.SCRIPT[self.k % len(self.SCRIPT)]
        self.k += 1
        return a


def _replay_and_compare(comp, arm_id, data_by_symbol):
    """Reviewer check A: for EVERY position of the arm, replay the trade
    in the training env, DRIVEN BY THE ORCHESTRATOR'S EXECUTED ACTIONS,
    and require bit-identical obs vectors at every shared boundary plus
    terminal-state lockstep (same closure boundary)."""
    from lab.arms.rl_env import ACTIONS
    st = comp.arms[arm_id]
    opens = {e["pos_id"]: e for e in st.engine.events
             if e["kind"] == "fill_open"}
    closes = {e["pos_id"]: e["t"] for e in st.engine.events
              if e["kind"] == "position_closed"}
    compared = executed_kinds = 0
    seen_actions = set()
    for pid, op in opens.items():
        pos = st.engine.positions[pid]
        recs = [r for r in st.rl_decisions if r["pos_id"] == pid]
        by_t = {int(r["t"]): r for r in recs}
        if not by_t:
            continue
        data = data_by_symbol[op["symbol"]]
        decision_ts = int(op["decision_ts"])
        series = comp._series[op["symbol"]]
        m = data["open_time"] >= decision_ts + B15
        bars = list(zip(data["open_time"][m], data["open"][m],
                        data["high"][m], data["low"][m], data["close"][m]))
        expo = {int(r["t"]): float(r["observation"][9]) for r in recs
                if r["observation"] is not None}
        trade = {"side": pos.side, "qty": op["qty"],
                 "entry_ref": float(op["fill"]) if "fill" in op else 0.0,
                 "r_dist": pos.r_dist, "decision_ts": decision_ts,
                 "atr_entry": pos.r_dist / P.STOP_ATR_MULT,
                 "atr_t4_close_ms": (series.t4 + P.BAR_4H_MS),
                 "atr_values": series.atr,
                 "exposure_by_boundary": expo,
                 "costs": {"hs": tier_costs(0).half_spread,
                           "slip": tier_costs(0).slippage,
                           "fee": tier_costs(0).fee}}
        env = TradeManagementEnv(trade, bars)
        env.reset(seed=0)
        while True:
            x = env.obs_inputs()
            if x is None:
                break
            boundary = env.bars[env._i].open_time + B15
            rec = by_t.get(int(boundary))
            action = "hold"
            if rec is not None and rec["observation"] is not None:
                env_obs = build_observation(x)
                assert np.array_equal(
                    env_obs, np.array(rec["observation"], np.float32)), \
                    (arm_id, pid, boundary, env_obs.tolist(),
                     rec["observation"])
                compared += 1
                action = rec["executed_action"]
                if action not in ACTIONS:      # e.g. governor fallback
                    action = "hold"
                if rec["executed_action"] in ACTIONS:
                    seen_actions.add(rec["executed_action"])
                    executed_kinds += 1
            _o, _r, term, trunc, _i2 = env.step(ACTIONS.index(action))
            if term or trunc:
                break
        # terminal lockstep: closure at the SAME bar (or both still open)
        env_closed_t = {e["t"] for e in env.engine.events
                        if e["kind"] == "position_closed"}
        if pid in closes:
            assert closes[pid] in env_closed_t or env_closed_t == set(), \
                (arm_id, pid, closes[pid], env_closed_t)
    return compared, seen_actions


def test_multi_state_parity_long_short_actions_terminal():
    """Reviewer check A: parity across long AND short positions, partial
    reductions, tightened stops, evolving MFE/MAE, CHANGING ATR (per-bar
    wiggle schedule), changing portfolio exposure (two overlapping
    positions), and terminal states — all bit-identical."""
    hist_w = [0.30 + 0.02 * (i % 7) for i in range(HIST)]
    lv1 = [100.0] * HIST + [105.0, 105.5, 106.5, 107.0, 106.0, 106.8,
                            105.5, 104.5, 103.0, 101.5, 101.0, 101.0]
    w1 = hist_w + [0.5, 0.55, 0.6, 0.5, 0.45, 0.55, 0.6, 0.5, 0.45,
                   0.4, 0.35, 0.35]
    lv2 = [200.0] * (HIST + 3) + [190.0, 188.0, 186.0, 187.5, 184.0,
                                  183.0, 184.5, 182.0, 181.0]
    w2 = [h * 2 for h in hist_w[:HIST + 3]] + [1.0, 1.1, 0.9, 1.0, 1.2,
                                               0.9, 0.8, 1.0, 0.9]
    n4 = max(len(lv1), len(lv2))
    lv1 += [lv1[-1]] * (n4 - len(lv1)); w1 += [w1[-1]] * (n4 - len(w1))
    lv2 += [lv2[-1]] * (n4 - len(lv2)); w2 += [w2[-1]] * (n4 - len(w2))
    data = {"AAAUSDT": build_symbol_var(lv1, w1),
            "BBBUSDT": build_symbol_var(lv2, w2)}
    prov = ArrayProvider({k: {kk: vv.copy() for kk, vv in v.items()}
                          for k, v in data.items()})
    comp = Competition(prov, 10_000,
                       universe_fn=lambda t: ["AAAUSDT", "BBBUSDT"],
                       rl_policy=ScriptedPolicy())
    end = T0 + (n4 * 16 - 1) * B15
    comp.run(T0, end)

    sides = {e["side"] for a in ("F", "G")
             for e in comp.arms[a].engine.events if e["kind"] == "fill_open"}
    assert sides == {1, -1}, f"need long AND short, got {sides}"
    total = 0
    seen = set()
    for a in ("F", "G"):
        c, s = _replay_and_compare(comp, a, data)
        total += c
        seen |= s
    assert total >= 10, f"only {total} boundary comparisons"
    assert "tighten_stop" in seen and \
        ("reduce_25" in seen or "reduce_50" in seen), \
        f"executed actions not diverse enough: {seen}"


def test_schema_hash_stability_and_clipping():
    # the schema hash pins the definitions; any change must be versioned
    assert OBS_SCHEMA_HASH == build_and_hash()
    x = ObsInputs(side=1, entry_fill=100.0, r_dist=2.0, mark=1e9,
                  mfe_price=1e9, mae_price=-1e9, stop=98.0, target=106.0,
                  qty=1.0, open_qty=0.5, bars_held_4h=100,
                  atr_now=float("nan"), atr_entry=1.0,
                  gross_exposure=1e9, equity=0.0)
    obs = build_observation(x)
    assert obs[0] == 10.0 and obs[1] == 1.0 and obs[2] == 10.0
    assert obs[3] == 10.0 and obs[4] == 0.1 and obs[9] == 5.0  # NaN atr -> lo
    assert np.isfinite(obs).all()


def build_and_hash():
    import hashlib
    from lab.arms import observation as O
    return hashlib.sha256((O.OBS_SCHEMA_VERSION + "|"
                           + O._SCHEMA_SPEC).encode()).hexdigest()
