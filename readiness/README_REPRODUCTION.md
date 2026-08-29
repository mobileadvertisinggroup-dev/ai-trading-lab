# Reproduction instructions (no holdout decryption required)

Everything below verifies the readiness claims WITHOUT touching the
sealed holdout. Requires: the repository at the bundle's recorded
commit, python 3.11 with the pinned requirements, and (for step 4) the
verified pre-holdout lake.

1. **Checkout + integrity.**
   `git checkout <git_commit from ENVIRONMENT_RECORD.json>` in a fresh
   clone/worktree; `git status --porcelain` must be empty. Verify every
   bundle file's sha256 against BUNDLE_MANIFEST.sha256
   (`sha256sum -c BUNDLE_MANIFEST.sha256` from the bundle root).
2. **Full suite (expect 159/159).**
   `python3 -m pytest -q` — includes the differential/reference-ledger
   gate, golden fixtures, and all constitutional properties.
3. **Fail-closed batteries alone (expect 34/34).**
   `python3 -m pytest -q tests/test_holdout_gate.py
   tests/test_authz_negative.py tests/test_checkpoint2_readiness.py
   tests/test_seal_access.py tests/test_pipelines_leaks.py`
4. **Live refusal probes (real lake; still zero holdout access).**
   With the verified pre-holdout lake at <LAKE>:
   - `verify_authorization("data/manifests")` returns
     (False, ["no authorization record"]);
   - `holdout_ledger.opening_permitted("data/manifests")` is permitted
     with NO holdout_state.jsonl present (opening count zero);
   - `GuardedLake(<LAKE>, "data/manifests").read_klines("BTCUSDT", Q,
     Q+86_400_000)` raises HoldoutAccessError (likewise partial-overlap
     and funding reads), and each refusal appends to
     data/manifests/access_audit.jsonl.
   (Exactly the probes recorded in FAILCLOSED_LIVE_PROBES.json.)
5. **Refusal of the NON-AUTHORIZING example.** Copy
   checkpoint2_authorization.EXAMPLE.INVALID.json to
   data/manifests/checkpoint2_authorization.json in a THROWAWAY
   worktree and call verify_authorization — every hash check fails and
   access stays refused. Delete the file afterwards.
6. **Frozen inputs.** Recompute the sha256 of each file listed in
   EVALUATOR_INPUTS_FROZEN_HASHES.json and compare.
7. **Evaluator statistics correctness** is covered by step 2/3
   (tests/test_checkpoint2_readiness.py) on synthetic data — Holm
   example, identical-arm non-improvement, dominant-arm improvement,
   drawdown-constraint blocking, gate refusal with the evaluator
   plugged in.

At no step is the holdout artifact decrypted, inspected, or evaluated,
and no private key is used or requested.
