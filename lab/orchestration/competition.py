"""Seven-arm competition orchestrator — scaffold (SPEC FINAL-1.2 §3, §23).

Candidate and timestamp equality BY CONSTRUCTION: at every valid round one
shared candidate list is generated once (Arm A's frozen §2.2 logic) and
handed to every arm's decision policy; no arm can see a different candidate
set or timestamp. Each arm owns its Engine (separate paper account) and its
RiskGovernor. Any arm's policy failure invalidates the round for all arms
through the RoundCoordinator — no orders execute anywhere that round.

Arm policies (models plug in behind these stubs later; the pipeline ORDER
is the frozen §3 Arm-G order):
  A: take every candidate at Arm-A size.
  B: filter — model accepts/rejects candidates; accepted trade at A size.
  C: ranker — model scores candidates; top-K selected within limits.
  D: A's candidates scaled by the frozen regime multiplier (0 blocks).
  E: every A trade at bucket x A size (0.25/0.50/0.75/1.00; never 0).
  F: A's entries; RL policy manages post-entry at each boundary.
  G: B filter -> C rank -> min(E,D) multiplier x A size -> governor ->
     entry; F's policy manages. G-SHADOW: an eighth ledger (diagnostic,
     not an arm) receiving G's IDENTICAL entries with frozen conventional
     management — identity through entry is a constitutional property.
"""
from __future__ import annotations

import copy

import numpy as np

from lab import protocol as P
from lab.arms.observation import (OBS_SCHEMA_HASH, OBS_SCHEMA_VERSION,
                                  ObsInputs, atr_at_or_before,
                                  build_observation)
from lab.arms.arm_a import MarketProvider, tier_costs
from lab.arms.indicators import SymbolSeries
from lab.orchestration.rounds import RoundCoordinator
from lab.risk.governor import EntryRequest, PortfolioState, RiskGovernor
from lab.sim.engine import Bar, Engine

ARMS = ("A", "B", "C", "D", "E", "F", "G")
E_BUCKETS = (0.25, 0.50, 0.75, 1.00)


# ------------------------------------------------------------ policy stubs

class AcceptAllFilter:            # Arm B stub
    version = "stub-accept-all"

    def accept(self, cand: dict, features: dict | None) -> tuple[bool, float]:
        return True, 1.0          # (accept, probability)


class PassThroughRanker:          # Arm C stub
    version = "stub-passthrough"

    def score(self, cand: dict, features: dict | None) -> float:
        return -cand["rank"]      # liquidity order


class FullSizeSizer:              # Arm E stub
    version = "stub-full-size"

    def bucket(self, cand: dict, features: dict | None) -> float:
        return 1.00               # one of E_BUCKETS, never 0


class HoldPolicy:                 # Arm F stub
    version = "stub-hold"

    def action_from_obs(self, obs) -> str:
        return "hold"


class PermitAllRegime:            # Arm D stub (real model: lab.arms.regime)
    version = "stub-permit-all"

    def classify(self, t_ms: int) -> dict:
        return {"regime": "uptrend", "multiplier": {1: 1.0, -1: 1.0},
                "model_version": self.version}


class ArmState:
    def __init__(self, arm_id: str, starting_cash: float):
        self.arm_id = arm_id
        self.engine = Engine(starting_cash)
        self.governor = RiskGovernor()
        self.decisions: list[dict] = []      # per-arm decision ledger
        self.rl_decisions: list[dict] = []   # per-decision RL observability
        self.equity_curve: list[dict] = []

    # ---- transactional snapshot/rollback (adjudication blocker 3) ----
    def snapshot(self) -> dict:
        e, g = self.engine, self.governor
        return {
            "cash": e.cash, "ruined": e.ruined, "next_id": e._next_id,
            "positions": copy.deepcopy(e.positions),
            "pend_in": copy.deepcopy(e._pending_entries),
            "pend_out": copy.deepcopy(e._pending_exits),
            "n_events": len(e.events),
            "g_emerg": g.emergency_pause, "g_integ": g.integrity_pause,
            "g_day": g._day, "g_day_eq": g._day_start_equity,
            "g_peaks": dict(g._day_peaks), "g_n_events": len(g.events),
            "n_decisions": len(self.decisions),
            "n_rl": len(self.rl_decisions),
        }

    def rollback(self, snap: dict) -> None:
        e, g = self.engine, self.governor
        e.cash = snap["cash"]; e.ruined = snap["ruined"]
        e._next_id = snap["next_id"]
        e.positions = snap["positions"]
        e._pending_entries = snap["pend_in"]
        e._pending_exits = snap["pend_out"]
        del e.events[snap["n_events"]:]
        g.emergency_pause = snap["g_emerg"]
        g.integrity_pause = snap["g_integ"]
        g._day = snap["g_day"]; g._day_start_equity = snap["g_day_eq"]
        g._day_peaks = snap["g_peaks"]
        del g.events[snap["g_n_events"]:]
        del self.decisions[snap["n_decisions"]:]
        del self.rl_decisions[snap["n_rl"]:]


class Competition:
    def __init__(self, provider: MarketProvider, starting_cash: float,
                 universe_fn, valid_round_fn=None, filter_model=None,
                 ranker_model=None, sizer_model=None, rl_policy=None,
                 regime_model=None, ranker_top_k: int = P.MAX_CONCURRENT_POSITIONS):
        self.provider = provider
        self.universe_fn = universe_fn
        self.valid_round_fn = valid_round_fn or (lambda t: True)
        self.filter_model = filter_model or AcceptAllFilter()
        self.ranker_model = ranker_model or PassThroughRanker()
        self.sizer_model = sizer_model or FullSizeSizer()
        self.rl_policy = rl_policy or HoldPolicy()
        self.regime_model = regime_model or PermitAllRegime()
        self.ranker_top_k = ranker_top_k
        self.coordinator = RoundCoordinator(list(ARMS))
        self.arms = {a: ArmState(a, starting_cash) for a in ARMS}
        self.shadow = ArmState("G_shadow", starting_cash)   # diagnostic
        self.candidates: list[dict] = []     # THE shared candidate ledger

        self._series: dict[str, SymbolSeries] = {}
        self._bars15: dict[str, dict] = {}
        self._bar_index: dict[str, dict[int, int]] = {}
        for sym in provider.symbols():
            d = provider.bars_15m(sym)
            self._bars15[sym] = d
            self._series[sym] = SymbolSeries(d["open_time"], d["open"],
                                             d["high"], d["low"], d["close"])
            self._bar_index[sym] = {int(t): i
                                    for i, t in enumerate(d["open_time"])}
        self._last_close: dict[str, float] = {}

    # ------------------------------------------------------------- shared
    def _bars_at(self, t):
        out = {}
        for sym, idx in self._bar_index.items():
            i = idx.get(t)
            if i is not None:
                d = self._bars15[sym]
                out[sym] = Bar(t, float(d["open"][i]), float(d["high"][i]),
                               float(d["low"][i]), float(d["close"][i]))
        return out

    def _shared_candidates(self, t: int) -> list[dict]:
        """Arm A §2.2 candidate generation, executed ONCE per round."""
        out = []
        universe = self.universe_fn(t)
        for rank, sym in enumerate(universe):
            series = self._series.get(sym)
            sig = series.at_boundary(t) if series else None
            if sig is None or not np.isfinite(sig["atr"]) or sig["atr"] <= 0 \
                    or not np.isfinite(sig["hh_entry"]):
                continue
            side = 0
            if sig["close"] > sig["hh_entry"]:
                side = +1
            elif sig["close"] < sig["ll_entry"]:
                side = -1
            if side == 0:
                continue
            out.append({"t": int(t), "symbol": sym, "side": side,
                        "close": sig["close"], "hh_entry": sig["hh_entry"],
                        "ll_entry": sig["ll_entry"], "atr": sig["atr"],
                        "r_dist": P.STOP_ATR_MULT * sig["atr"],
                        "rank": rank + 1, "n_eligible": len(universe)})
        return out

    # --------------------------------------------------------- arm helpers
    def _submit(self, arm: ArmState, cand: dict, size_mult: float,
                shadow: ArmState | None = None) -> dict:
        """Size, govern, and submit one entry for one arm. Returns record."""
        t = cand["t"]
        eng = arm.engine
        marks = dict(self._last_close)
        equity = eng.equity(marks)
        qty = (P.RISK_FRACTION * equity) / cand["r_dist"] * size_mult
        long_x = short_x = 0.0
        for p in eng.open_positions():
            n = p.open_qty * marks.get(p.symbol, p.last_mark)
            long_x, short_x = (long_x + n, short_x) if p.side > 0 \
                else (long_x, short_x + n)
        decision, allowed_qty, reason = arm.governor.check_entry(
            EntryRequest(t=t, symbol=cand["symbol"], side=cand["side"],
                         qty=qty, price=cand["close"],
                         stop_distance=cand["r_dist"]),
            PortfolioState(equity=equity, gross_exposure=long_x + short_x,
                           long_exposure=long_x, short_exposure=short_x,
                           n_positions=len(eng.open_positions())))
        rec = {"t": t, "symbol": cand["symbol"], "size_mult": size_mult,
               "qty": qty, "governor": decision, "governor_reason": reason}
        if decision != "reject":
            for target_state in ([arm] if shadow is None else [arm, shadow]):
                target_state.engine.submit_entry(
                    cand["symbol"], cand["side"], allowed_qty,
                    stop=0.0, target=0.0, r_dist=cand["r_dist"],
                    decision_ts=t, costs=tier_costs(cand["rank"] - 1),
                    # cap scales WITH the multiplier so a bucketed arm fills
                    # exactly mult x Arm A's post-cap size (spec §3 Arm E:
                    # fractions of Arm A's SIZE, not of the pre-cap request)
                    max_notional=P.NOTIONAL_CAP_FRACTION * equity * size_mult,
                    stop_offset=cand["r_dist"],
                    target_offset=P.TARGET_R_MULT * cand["r_dist"])
        return rec

    def _conventional_exits(self, arm: ArmState, t: int):
        """Frozen Arm-A management (§2.4) — used by A, B, C, D, E, shadow."""
        for p in arm.engine.open_positions():
            sig = self._series[p.symbol].at_boundary(t)
            held = (t - p.decision_ts) // P.BAR_4H_MS
            if sig is not None and np.isfinite(sig["ll_exit"]) \
                    and np.isfinite(sig["hh_exit"]):
                trail = (sig["close"] < sig["ll_exit"] if p.side > 0
                         else sig["close"] > sig["hh_exit"])
                if trail:
                    arm.engine.submit_exit(p.pos_id, 1.0, "trailing_exit")
                    continue
            if held >= P.MAX_HOLD_BARS_4H:
                arm.engine.submit_exit(p.pos_id, 1.0, "time_exit")

    def _obs_inputs_for(self, arm: ArmState, p, t: int) -> ObsInputs:
        """Orchestrator-side construction of the CANONICAL obs-v2 inputs
        (adjudication blocker 2). atr_entry is mechanically exact:
        r_dist = STOP_ATR_MULT x ATR at the entry decision. atr_now uses
        the frozen Wilder ATR over completed 4h bars closing <= t.
        Exposure/equity come from the OWNING arm's engine at t."""
        series = self._series.get(p.symbol)
        atr_entry = p.r_dist / P.STOP_ATR_MULT
        if series is not None and len(series.t4):
            atr_now = atr_at_or_before(series.t4 + P.BAR_4H_MS, series.atr,
                                       t, atr_entry)
        else:
            atr_now = atr_entry
        marks = dict(self._last_close)
        return ObsInputs(
            side=p.side, entry_fill=p.entry_fill, r_dist=p.r_dist,
            mark=p.last_mark, mfe_price=p.mfe, mae_price=p.mae,
            stop=p.stop, target=p.target, qty=p.qty, open_qty=p.open_qty,
            bars_held_4h=max(0, (t - p.decision_ts) // P.BAR_4H_MS),
            atr_now=atr_now, atr_entry=atr_entry,
            gross_exposure=arm.engine.gross_exposure(marks),
            equity=arm.engine.equity(marks))

    def _rl_management(self, arm: ArmState, t: int):
        """Arm F / G management via the RL policy + governor action filter,
        with the frozen time-exit backstop (risk limits always enforced).
        Every decision is recorded with full observability (adjudication
        blocker 4): observation vector + schema id, raw action, governor
        outcome, executed action, before/after stop and quantity."""
        for p in arm.engine.open_positions():
            held = (t - p.decision_ts) // P.BAR_4H_MS
            rec = {"t": int(t), "arm": arm.arm_id, "pos_id": p.pos_id,
                   "symbol": p.symbol,
                   "obs_schema_version": OBS_SCHEMA_VERSION,
                   "obs_schema_hash": OBS_SCHEMA_HASH,
                   "stop_before": p.stop, "qty_before": p.open_qty}
            if held >= P.MAX_HOLD_BARS_4H:
                arm.engine.submit_exit(p.pos_id, 1.0, "time_exit")
                rec.update({"backstop": "time_exit", "observation": None,
                            "raw_action": None, "governor": None,
                            "executed_action": "time_exit_queued",
                            "invalid_reason": None,
                            "stop_after": p.stop, "qty_after": p.open_qty})
                arm.rl_decisions.append(rec)
                continue
            obs = build_observation(self._obs_inputs_for(arm, p, t))
            action = self.rl_policy.action_from_obs(obs)
            rec.update({"backstop": None,
                        "observation": [float(v) for v in obs],
                        "raw_action": action})
            gov_ok = arm.governor.check_action(t, action)
            executed, invalid_reason = "hold", None
            if not gov_ok:
                invalid_reason = "governor_action_reject"
            elif action != "hold":
                if action == "tighten_stop":
                    # identical rule to the training env: move the stop
                    # 25% of the distance toward the last mark
                    new_stop = p.stop + 0.25 * (p.last_mark - p.stop)
                    ok = arm.engine.apply_management_action(
                        t, p.pos_id, "tighten_stop", new_stop=new_stop)
                else:
                    ok = arm.engine.apply_management_action(t, p.pos_id,
                                                            action)
                if ok:
                    executed = action
                else:
                    invalid_reason = "engine_invariant_reject"
            rec.update({"governor": "approve" if gov_ok else "reject",
                        "executed_action": executed,
                        "invalid_reason": invalid_reason,
                        "stop_after": p.stop, "qty_after": p.open_qty})
            arm.rl_decisions.append(rec)

    # ------------------------------------------------------------- rounds
    def _decide(self, t: int, cands: list[dict]):
        """All seven arms' decisions for one round. Raises propagate to the
        coordinator (round invalidation)."""
        regime = self.regime_model.classify(t)
        open_syms = {a: {p.symbol for p in st.engine.open_positions()}
                     for a, st in self.arms.items()}
        fresh = {a: [c for c in cands if c["symbol"] not in open_syms[a]]
                 for a in ARMS}

        for c in fresh["A"]:
            self.arms["A"].decisions.append(
                dict(self._submit(self.arms["A"], c, 1.0), arm="A"))

        for c in fresh["B"]:
            ok, prob = self.filter_model.accept(c, None)
            rec = {"arm": "B", "t": t, "symbol": c["symbol"],
                   "accepted": ok, "probability": prob,
                   "model_version": self.filter_model.version}
            if ok:
                rec.update(self._submit(self.arms["B"], c, 1.0))
            self.arms["B"].decisions.append(rec)

        scored = sorted(((self.ranker_model.score(c, None), c)
                         for c in fresh["C"]), key=lambda x: -x[0])
        for i, (s, c) in enumerate(scored):
            chosen = i < self.ranker_top_k
            rec = {"arm": "C", "t": t, "symbol": c["symbol"],
                   "rank_of": f"{i + 1} of {len(scored)}", "score": s,
                   "selected": chosen,
                   "model_version": self.ranker_model.version}
            if chosen:
                rec.update(self._submit(self.arms["C"], c, 1.0))
            self.arms["C"].decisions.append(rec)

        for c in fresh["D"]:
            mult = regime["multiplier"][c["side"]]
            rec = {"arm": "D", "t": t, "symbol": c["symbol"],
                   "regime": regime["regime"], "d_multiplier": mult}
            if mult > 0:
                rec.update(self._submit(self.arms["D"], c, mult))
            self.arms["D"].decisions.append(rec)

        for c in fresh["E"]:
            b = self.sizer_model.bucket(c, None)
            assert b in E_BUCKETS, "Arm E bucket must be one of the four"
            self.arms["E"].decisions.append(
                dict(self._submit(self.arms["E"], c, b), arm="E",
                     e_bucket=b))

        for c in fresh["F"]:
            self.arms["F"].decisions.append(
                dict(self._submit(self.arms["F"], c, 1.0), arm="F"))

        shadow_open = {p.symbol for p in self.shadow.engine.open_positions()}
        for c in fresh["G"]:
            ok, _ = self.filter_model.accept(c, None)
            if not ok:
                self.arms["G"].decisions.append(
                    {"arm": "G", "t": t, "symbol": c["symbol"],
                     "stage": "filter_rejected"})
                continue
            g_scored = sorted(((self.ranker_model.score(x, None), x)
                               for x in fresh["G"]), key=lambda x: -x[0])
            g_rank = next(i for i, (_, x) in enumerate(g_scored)
                          if x["symbol"] == c["symbol"])
            if g_rank >= self.ranker_top_k:
                self.arms["G"].decisions.append(
                    {"arm": "G", "t": t, "symbol": c["symbol"],
                     "stage": "rank_cut"})
                continue
            mult = min(self.sizer_model.bucket(c, None),
                       regime["multiplier"][c["side"]])
            if mult <= 0 or c["symbol"] in shadow_open:
                self.arms["G"].decisions.append(
                    {"arm": "G", "t": t, "symbol": c["symbol"],
                     "stage": "regime_blocked" if mult <= 0 else "shadow_open"})
                continue
            self.arms["G"].decisions.append(
                dict(self._submit(self.arms["G"], c, mult,
                                  shadow=self.shadow),
                     arm="G", g_multiplier=mult))

    # ---------------------------------------------------------------- run
    def run(self, start_ms: int, end_ms: int):
        t = start_ms
        while t <= end_ms:
            boundary = t % P.BAR_4H_MS == 0
            if boundary and self.valid_round_fn(t):
                # -- TRANSACTIONAL round (adjudication blocker 3): the
                # complete pre-round state of every arm AND the shadow is
                # snapshotted; a failure anywhere rolls back cash,
                # positions (incl. stops/quantities), pending operations,
                # engine event streams, decision + RL ledgers, governor
                # state and events, and the shared candidate ledger. Only
                # the coordinator's centralized invalid-round record (with
                # diagnostics) survives an invalid round.
                snaps = {a: st.snapshot() for a, st in self.arms.items()}
                snaps["__shadow__"] = self.shadow.snapshot()
                n_cand_ledger = len(self.candidates)
                self.coordinator.begin_round(t)
                cands = self._shared_candidates(t)
                try:
                    # management first (uses info strictly before t)
                    for a in ("A", "B", "C", "D", "E"):
                        self._conventional_exits(self.arms[a], t)
                    self._conventional_exits(self.shadow, t)
                    for a in ("F", "G"):
                        self._rl_management(self.arms[a], t)
                    for st in self.arms.values():
                        st.governor.observe(t, st.engine.equity(
                            dict(self._last_close)))
                    self._decide(t, cands)
                    for a in ARMS:
                        self.coordinator.report(t, a, True)
                except Exception as e:  # noqa: BLE001 — any arm failure
                    for a in ARMS:
                        if a not in self.coordinator._open.get(t, {}):
                            self.coordinator.report(t, a, False,
                                                    reason=str(e)[:200])
                if self.coordinator.finalize(t):
                    self.candidates.extend(cands)
                else:
                    # invalid round: FULL rollback — zero surviving effect
                    for a, st in self.arms.items():
                        st.rollback(snaps[a])
                    self.shadow.rollback(snaps["__shadow__"])
                    del self.candidates[n_cand_ledger:]
            bars = self._bars_at(t)
            for st in list(self.arms.values()) + [self.shadow]:
                st.engine.process_bar_time(t, bars,
                                           prev_close=dict(self._last_close))
            for sym, b in bars.items():
                self._last_close[sym] = b.close
            if boundary:
                marks = dict(self._last_close)
                for st in list(self.arms.values()) + [self.shadow]:
                    st.equity_curve.append(
                        {"t": t, "equity": st.engine.equity(marks)})
            t += P.BAR_15M_MS
        return self
