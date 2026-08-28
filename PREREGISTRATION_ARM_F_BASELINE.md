# PRE-REGISTRATION — Arm F conventional baseline (D63 blocker 2)

Committed BEFORE the corrected comparison is computed. The previous
report's "Arm A conventional management" baseline was action=HOLD
inside TradeManagementEnv — NOT established as the frozen Arm A
manager (which includes the trailing-channel exit and the time exit);
that comparison is INVALIDATED history (file preserved). No PPO
retraining; the ten preserved artifacts and selected seed 4 are kept
unless the corrected calculation exposes an independent
artifact-integrity failure.

## Exact frozen Arm A conventional manager (replayed in-episode)
At every episode decision boundary t (identical boundaries, bars,
costs, engine, exit ordering, and terminal reward definition as the
PPO evaluation), in the SAME order as ArmARunner._boundary_exits:
1. TRAILING EXIT: with the frozen SymbolSeries signal at t (Wilder
   ATR / Donchian on completed 4h bars, identical arrays to the
   official run): long → close if signal close < ll_exit; short →
   close if signal close > hh_exit (only when both channel values are
   finite — the official missing-signal rule);
2. TIME EXIT: close if (t − decision_ts) / 4h >= MAX_HOLD_BARS_4H;
3. otherwise HOLD (stop/target protection remains engine-enforced).
"close" uses the env's management-close path, which queues a full exit
filled at the next 15m open — the identical semantics by which
ArmARunner boundary exits fill in the official run.

## Parity proof (added to the suite BEFORE the official rerun)
Mechanical tests prove the baseline reproduces OFFICIAL Arm A
management outcomes on synthetic trades built through ArmARunner
itself, covering the edge cases: trailing exit, time exit, stop hit,
target hit — the replayed episode's realized economics must equal the
official engine outcome for the same trade.

## Corrected comparison (blocker 2 items 3–4)
For all 10 preserved seeds, on the identical validation episodes with
the identical terminal-reward definition: report each seed's mean
validation reward against the exact-baseline mean; wins/losses
honestly; every other v1-report statistic retained. Output
`arm_f_statistics_report_v2.json`; the v1 report is preserved as
invalidated-comparison history.

## Execution standard
Official run under lab/tools/provenance_run.py from a clean detached
worktree with the lake-input addendum.
