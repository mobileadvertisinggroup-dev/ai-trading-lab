# ARCHITECTURE — AKRA AI TRADING LAB

## Layers (all Python; storage = Parquet + git-pinned JSON manifests; D20
records why the §27-default server stack is not used in the research phase)

1. **Frozen constants** — `lab/protocol.py`: every protocol number
   (LOCKED file). Docs: EXPERIMENT_PROTOCOL.md (frozen), 
   SIMULATOR_SEMANTICS.md, RISK_POLICY.md, DATA_DICTIONARY.md.
2. **Data plane** — `lab/data/`:
   `ingest.py` (Actions-only acquisition → split-and-seal per PC-1),
   `seal.py` (age X25519 to the user's public key), `lake.py`
   (content-hashed Parquet lake + manifest), `partition.py` (mechanical
   universe/validity/interval/partition, vectorized fast path),
   `access.py` (GuardedLake — the ONLY read path; holdout refusal +
   hash-chained audit), `authz.py` / `holdout_ledger.py` / `unseal.py`
   (strict Checkpoint-2 gate: recomputed hashes, atomic one-time opening,
   tmpfs-only, FAILED_CLOSED), `audit.py` (coverage-audit acceptance
   gate).
3. **Simulation** — `lab/sim/engine.py` (deterministic engine;
   conservative ambiguity; management invariants) mirrored by
   `lab/refledger/ledger.py` (zero shared code) under
   `lab/verify/differential.py` (exact equality; first-divergence
   adjudication).
4. **Arms** — `lab/arms/`: `indicators.py` (4h aggregation, Donchian,
   Wilder ATR), `arm_a.py` (frozen baseline runner), `regime.py` (Arm D),
   `rl_env.py` (Arm F gymnasium env), `rl_train.py` (deterministic CEM);
   `lab/models/pipelines.py` (Arms B/C/E LightGBM with structural leak
   guards).
5. **Labels/features** — `lab/labels/` (spec-§4 labels from ledgers;
   variable-horizon purge/embargo), `lab/features/build.py` (F01-F28,
   no-lookahead proven by test; canonical FEATURE_NAMES order).
6. **Orchestration** — `lab/orchestration/`: `rounds.py` (synchronized
   rounds; any-arm failure voids the round), `competition.py` (seven arms
   + G-shadow, shared single-pass candidates).
7. **Risk** — `lab/risk/governor.py`: external deterministic governor
   wrapping every arm (approve/restrict/reject; pauses; action filter).
8. **Tools** — `lab/tools/`: verify_lake, run_arm_a, build_features,
   learnability, train_arms, shakedown, lock_integrity,
   immutable_evidence.
9. **Dashboard** — `lab/dashboard/build.py`: static, ledger-derived,
   structurally unable to read market data.
10. **Ops** — `.github/workflows/ingest.yml` (probe/full/audit,
    SHA-pinned, release transaction, PC-1 staging destruction),
    `forward.yml` (refuse-until-authorized scaffold).

## Data flow
archive → (Actions) staging → split at quarantine → plaintext lake
(release asset, hash-pinned) + sealed holdout (user's key) → GuardedLake →
official Arm A ledgers → labels + features → training → frozen artifacts →
orchestrated competition → immutable ledgers → dashboard.

## Integrity spine
Frozen protocol hash → git-pinned data manifests → coverage audit →
constitutional lock (integrity_manifest_hash) → Checkpoint-1 external
root hash; every gate fails closed; every refusal/opening audit-chained.
