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

## 5. Options for your explicit decision (key stays on your hardware in all)

**D78 correction.** An earlier revision of this plan asserted that
macOS swap would not see the VM's guest memory. That claim was
unsupported and is WITHDRAWN: disabling swap INSIDE a Linux guest
(`/proc/swaps` empty) does nothing to stop the macOS HOST from paging
the VM process's memory — including decrypted holdout pages — to
persistent storage. The gate's Linux no-swap check governs only the
guest.

1. **Local Linux VM on the Mac — CONDITIONAL, currently NOT
   recommended unless every host-persistence property below is
   mechanically proven.** Under the frozen no-plaintext-persistence
   policy, ALL of the following must be verified before a VM
   qualifies, and each is a real obstacle on macOS:
   - **Host swap**: `sysctl vm.swapusage` must show zero used before,
     during, and after the run — guest `/proc/swaps` is NOT evidence.
   - **Guest RAM actually locked on the host**: the hypervisor must
     wire the guest's memory non-pageable (e.g. QEMU
     `-overcommit mem-lock=on`) and this must be PROVEN on the host
     (wired-memory accounting equal to the guest allocation), not
     assumed. Common macOS VM front ends do not guarantee it.
   - **FileVault / encrypted swap is NOT automatically sufficient**:
     the frozen policy prohibits plaintext-bearing memory from
     reaching persistent storage at all (the Linux gate refuses ANY
     swap, encrypted or not). Treating FileVault-encrypted host swap
     as acceptable would be a formal policy amendment for YOUR
     explicit adjudication — it is not assumed here.
   - **Crash/core dumps, snapshots, suspend/save-state, hibernation**:
     host core dumps disabled; VM snapshots and suspend/save-state
     never used (they serialize guest RAM to disk); hibernation off
     (`pmset hibernatemode 0`) and no `/private/var/vm/sleepimage`.
   - **Physical RAM headroom**: host + guest must fit without memory
     pressure (guest needs ~21 GB by the frozen margin; macOS itself
     needs several GB — realistically a ≥ 48 GB Mac for a locked
     32 GB guest), verified by the discovery output and by
     `memory_pressure` during a full-size rehearsal.
   - **Verified cleanup**: after the run, VM disk images and any
     hypervisor working files are inspected/removed; the in-VM gate's
     own wipe-and-verify covers the guest tmpfs only.
   If ANY of these cannot be proven mechanically, this option is out.
   A full-size surrogate dress rehearsal INSIDE the configured VM
   (the tool ships with the repo; ephemeral key; one command) is
   required in every case, with the host-persistence checks recorded
   before/during/after.

2. **RECOMMENDED (Option A): dedicated local Linux hardware you
   control** — ≥ 32 GiB RAM, swap disabled (`swapoff -a`, verified by
   the gate), no hibernation, core dumps disabled, the key entered
   locally on its console. This runs the gate exactly as frozen, with
   no host/guest split and no unproven layer. It satisfies the
   key-control rule only if you accept that machine as under your
   exclusive control, equivalent to the Mac; that acceptance is yours
   to make explicitly.

3. **Option B: a formally amended native-macOS execution design** with
   equivalent no-persistence guarantees (a reviewed amendment
   replacing the Linux-specific checks with mechanically verifiable
   macOS equivalents), independently dress-rehearsed at full size
   before any authorization.

4. **Option C: keep the holdout sealed** until a satisfactory host
   exists. Nothing in the protocol expires.

The 1.5x margin and the no-plaintext-persistence rule are frozen and
will not be weakened to make any host qualify. NOT an option, ever:
entering the key on the current remote container or any other
project-controlled remote host — regardless of its RAM.

## 6. What happens next
Send the discovery output and your option choice. The next readiness
cycle then (a) re-measures the resource profile under the corrected
evaluator, (b) implements/proves any directed memory optimization with
a full-size rehearsal on the chosen host, and (c) regenerates the
authorization card there — before any authorization exists.
