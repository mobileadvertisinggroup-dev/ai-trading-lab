# DATA FLOW — the one-time holdout opening, in plain language

This describes exactly where data moves during the (not-yet-authorized)
Checkpoint-2 evaluation. Nothing here has run; the opening count is
zero.

## Where encrypted data enters
The key holder downloads `holdout-raw-v1.tar.age` (age-encrypted to the
key holder's public key at sealing time; 791,233,451 bytes; sha256
`47795aa6a9775e6f191def5c121212c00642eb666daf3cb8df46bf3a495a1067`)
from the published data release to any local path. The gate refuses any
file whose basename or independently recomputed sha256 differs from the
values pinned in the approved, git-committed dataset manifest. The
encrypted file itself is never modified and may remain on disk — it is
useless without the key.

## Where plaintext temporarily exists — and nowhere else
Plaintext exists in exactly two forms, both transient:
1. **In process memory** of the single gate process: bounded streaming
   buffers only — decryption uses `pyrage.decrypt_io` (never a
   whole-file bytes object) and extraction streams from the tar; plus
   the private-identity string, read from the terminal with no echo,
   parsed, verified against the frozen recipient, and deleted.
2. **On a verified memory-backed filesystem**: the decrypted tar and
   the extracted overlay are written only into a FRESH directory (mode
   0700) whose mount is checked against `/proc/mounts` and must be
   tmpfs/ramfs (default `/dev/shm/akra-holdout-eval-<pid>`). The
   intermediate tar is chunk-wiped and deleted before the evaluator
   runs. Disk-backed paths are refused; pre-existing directories are
   refused; any path inside the repository tree is refused; the
   resource preflight refuses if ANY swap is active, so tmpfs pages
   can never be swapped to persistent storage. Memory-backed means the
   plaintext never touches persistent storage and vanishes on power
   loss.

## Which process reads the plaintext
Exactly one: the gate process running the FROZEN evaluator
(`lab/tools/holdout_evaluator.py`), called as a function inside
`evaluate_holdout`. The evaluator reads the overlay parquet files,
merges them in memory with the verified pre-holdout lake, and runs the
frozen seven-arm simulation. No other process, no subprocess, no
network call, no cache, and no ordinary project reader touches the
overlay: `GuardedLake` (the only ordinary read path) structurally
refuses every holdout-range query regardless of the gate's state.

## Exactly what may leave
One JSON results file, written to the path the key holder chooses:
per-arm decision/event/equity/governor/RL ledgers, the two G-diagnostic
ledgers, and the frozen pre-registered statistics. These are outputs of
the simulation (fills, equities, aggregates). **No raw market rows —
no OHLCV records, no funding records — are included**: the evaluator
returns only simulation ledgers and statistics, and the gate writes
only what the evaluator returns.

## How raw rows, logs, exceptions, and temp files are prevented from escaping
- The evaluator writes NOTHING to disk itself; it returns a dict. Only
  the gate writes, and only the results JSON.
- Exception paths: any exception inside the gate is caught; the message
  recorded in the ledger is truncated to 300 characters of the error
  string (an error description, not data rows); the decrypted directory
  is wiped in the same `finally` path before the exception propagates.
- Audit/ledger records contain only metadata (timestamps, decisions,
  artifact names/hashes) — never market values.
- No temporary file is created outside the verified tmpfs directory;
  extraction uses the in-memory tar with `filter="data"` (no device
  nodes, no path escapes).

## How wiping is verified — and how success is (not) represented
After the evaluator returns — and equally on ANY failure — the gate
zero-overwrites every file in bounded 1 MiB chunks (never a
size-of-file buffer), removes the tmpfs directory tree, and then
VERIFIES its absence on the filesystem. The results are written FIRST
to a protected temp file (mode 0600, fsync); only after VERIFIED
cleanup are they atomically renamed to the final path and CONSUMED
appended. If cleanup verification fails, the run is recorded
FAILED_CLOSED, the temp results are removed, and the process raises.
If the atomic rename or the CONSUMED append fails, the published
results are removed again and the run reports failure — success is
never represented with plaintext left behind or with a failed ledger.

## How any failure permanently prevents a second opening
Everything checkable without the holdout — authorization, ledger,
artifact identity, EVERY frozen-input hash, the output directory, the
identity itself (its derived public key must equal the frozen
recipient), and the resource preflight — runs BEFORE the claim, so a
failure there refuses with the opening unspent. Immediately before
real decryption the gate atomically appends `OPENING_STARTED` to the
append-only, hash-chained state ledger (OS file lock + full chain
verification + no-prior-opening check + fsync). From that instant the
single opening is spent: `opening_permitted` refuses whenever ANY
`OPENING_STARTED` exists, whether the attempt later recorded CONSUMED,
FAILED_CLOSED, or nothing at all (a crash). A corrupted chain also
refuses — fail closed, never open. No application code can append a
recovery event, and the gate would not honor one; recovery would
require a future versioned, explicitly user-approved procedure that
does not exist.

## Crash states and manual containment
A hard crash (power loss, SIGKILL) after the claim can leave: (a) the
ledger ending at `OPENING_STARTED` with no terminal event — the
opening is permanently spent either way; (b) decrypted material on the
tmpfs — memory-backed, so it vanishes on power-off; otherwise the
operator removes the `/dev/shm/akra-holdout-eval-*` tree, verifies its
absence, and reports; (c) a `<results>.tmp` file (mode 0600,
simulation outputs only, no raw rows) — delete it. No crash state
leaves raw market rows on persistent storage, and no crash state
permits a second opening.

## How the evaluator prevents holdout-driven retraining, reselection, or parameter changes
- The evaluator contains NO training, fitting, tuning, or selection
  code paths: it loads the frozen, hash-pinned artifacts (B threshold
  0.50, C top-1, E mapping M1, F SB3 seed 4) read-only and runs one
  simulation plus the pre-registered statistics. There is no parameter
  it could change and no code that writes back to any artifact.
- Every statistic, seed, block length, correction, constraint, and
  success criterion was frozen in PREREGISTRATION_CHECKPOINT2_
  EVALUATION.md BEFORE any authorization existed; the honest prior
  expectation (negatives) is recorded there.
- The single-use ledger makes a second, "adjusted" evaluation
  mechanically impossible; and the standing prohibition — no retraining
  or reselection in response to holdout outcomes — is recorded in
  D66/D67 and the pre-registration itself.
