# LOCAL (MAC) EXECUTION PLAN for the one-time Checkpoint-2 opening

D72 §D. Standing facts: the 16-GiB remote host is REJECTED for the real
opening; the 1.5x resource margin is frozen and will not be weakened;
the private key remains ONLY on your Mac — never pasted into an SSH
session, remote container, VPS, CI runner, Claude session, log, file,
or clipboard controlled by the project.

## 1. Why discovery could not be performed remotely
This project runs in an isolated remote container with no access to
your Mac (no reachable local session, no SSH, nothing to probe — and by
design it should stay that way). The read-only discovery below is
therefore a script YOU run locally; paste its output back as text. It
reads system facts only — it never touches keys, files, or the network.

## 2. Read-only discovery (run on the Mac, paste the output)
```bash
# READ-ONLY system discovery — no writes outside mktemp, no key access
sysctl -n hw.model machdep.cpu.brand_string hw.memsize hw.ncpu
uname -m && sw_vers
vm_stat | head -8                      # free/inactive pages
memory_pressure -Q 2>/dev/null | tail -3 || true
df -h / ~                              # free disk
sysctl vm.swapusage                    # swap in use right now
ls /private/var/vm/ 2>/dev/null        # swapfiles present?
# ability to create and verify a memory-backed workspace (RAM disk):
DEV=$(hdiutil attach -nomount ram://524288) && \
  diskutil erasevolume APFS AKRATEST $DEV >/dev/null && \
  mount | grep AKRATEST && \
  diskutil eject $DEV                  # 256 MiB probe, then removed
```

## 3. Expected capacity under the corrected evaluator
Measured on the full-size non-holdout surrogate through the exact
production CLI (D70): peak RSS 7.78 GB at 503.8 MB ciphertext. Scaled
linearly to the real 791.2 MB ciphertext: **12.3 GB peak RSS + 1.6 GB
tmpfs/RAM-disk peak ≈ 13.9 GB demand; x1.5 margin ⇒ ~20.9 GB of
genuinely available memory required.** (The D72 funding correction
adds negligible memory; the profile will be re-measured in the next
readiness cycle.) Practical requirement: **a 32 GB machine with ~24 GB
available**, or a proven-smaller optimized evaluator (§5.1).

## 4. Platform gap that must be decided BEFORE any local run
The gate's fail-closed platform checks are Linux-specific by
construction: verified tmpfs via `/proc/mounts`, RAM via
`/proc/meminfo`, the hard no-swap refusal via `/proc/swaps`, and
`/dev/shm` as the default workspace. macOS has none of these, and
macOS's dynamic pager cannot be cleanly disabled — so plaintext on a
macOS RAM disk does not carry the same never-touches-persistent-storage
guarantee the frozen procedure requires. Running the gate directly on
macOS would require porting those checks — a reviewed protocol change,
not a silent adaptation. The honest options:

## 5. Options for your explicit decision (key stays on the Mac in all)
1. **Optimize + prove, then a local Linux VM on the Mac** (if the Mac
   has ≥ 32 GB): run the unmodified Linux gate inside a local VM
   (UTM/Lima, no network share of the key; the key is typed into the
   VM's console ON the Mac — it never crosses a network). Requires:
   (a) your discovery output confirming RAM; (b) a full-size surrogate
   dress rehearsal executed INSIDE that VM (the rehearsal tool ships
   with the repo and generates its own ephemeral key; one command);
   (c) the VM's swap disabled (Linux: swapoff, verified by the gate's
   /proc/swaps check). If the Mac has 16 GB, this option additionally
   requires the evaluator memory optimization below, proven by the
   same Mac-local rehearsal before any authorization:
   - per-symbol streaming loads in `load_combined` (drop the pandas
     frame after the numpy conversion, process symbols in one pass),
     and results-ledger streaming serialization — estimated to cut the
     13.9 GB demand materially, but ONLY a measured Mac-local
     rehearsal number counts against the 1.5x margin.
2. **Dedicated local Linux hardware** you control (≥ 32 GB RAM, no
   swap): run the gate exactly as frozen; the key is typed on that
   machine's console, which then holds it — this satisfies
   "private-key-only-on-your-hardware" only if you accept that box as
   equivalent to the Mac; otherwise it is out per your rule, and
   option 1 stands.
3. **Stop here**: keep the holdout sealed until a satisfactory host
   exists. Nothing in the protocol expires.

NOT an option, per your rule and this plan: entering the key on the
current remote container or any other project-controlled remote host —
regardless of its RAM.

## 6. What happens next
Send the discovery output and your option choice. The next readiness
cycle then (a) re-measures the resource profile under the corrected
evaluator, (b) implements/proves any directed memory optimization with
a full-size rehearsal on the chosen host, and (c) regenerates the
authorization card there — before any authorization exists.
