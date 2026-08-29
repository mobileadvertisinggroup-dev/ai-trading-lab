"""Resource-safety preflight for the one-time holdout opening
(D69 blocker 4).

Runs BEFORE the atomic claim, entirely on non-holdout information: the
ciphertext size on disk, the verified tmpfs mount's capacity, available
RAM, the swap configuration, the results-directory capacity, and — when
present — the measured surrogate resource profile
(data/manifests/checkpoint2_resource_profile.json, produced by the
full-size dress rehearsal through the exact production entry point).
Any shortfall REFUSES the run before OPENING_STARTED; the opening is
not spent.

Sizing model (conservative, explained in the report):
  - decrypted tar size      ~= ciphertext size (age adds ~200 B header
    + 16 B/64 KiB chunk overhead; plaintext is marginally SMALLER, so
    ciphertext size is a safe upper bound);
  - extracted overlay size  ~= tar size (parquet members + tar headers);
  - tmpfs peak              = tar + extracted (both present during
    extraction; the tar is wiped before the evaluator runs);
  - RAM demand              = evaluator peak RSS (surrogate profile
    scaled by ciphertext-size ratio, floored at the measured value) +
    tmpfs peak (tmpfs pages ARE RAM) — all compared against
    MemAvailable with the safety margin.

Every check applies `margin` (default 1.5x). This module reads /proc
and statvfs only — it never opens the artifact's contents.
"""
from __future__ import annotations

import json
import os

MARGIN = 1.5
PROFILE = "checkpoint2_resource_profile.json"
# fallback when no surrogate profile exists: evaluator RSS bound as a
# multiple of the extracted overlay size (in-memory numpy copies of all
# columns + arm state; deliberately generous)
FALLBACK_RSS_PER_BYTE = 6.0
FALLBACK_RSS_BASE = 2 << 30            # interpreter + models + lake


def _meminfo() -> dict[str, int]:
    out = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[0].endswith(":"):
                out[parts[0][:-1]] = int(parts[1]) * 1024   # kB -> bytes
    return out


def _swaps() -> list[str]:
    try:
        with open("/proc/swaps") as f:
            lines = [ln.rstrip("\n") for ln in f]
        return lines[1:]                     # header dropped
    except OSError:
        return []


def _existing_ancestor(path: str) -> str:
    p = os.path.realpath(path)
    while not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p


def _free_bytes(path: str) -> int:
    st = os.statvfs(_existing_ancestor(path))
    return st.f_bavail * st.f_frsize


def preflight_resources(artifact_path: str, out_dir: str,
                        results_path: str, manifests_dir: str,
                        margin: float = MARGIN) -> tuple[bool, dict]:
    """(ok, report). ok is False on ANY shortfall — the gate refuses
    before the claim. The report is metadata only (sizes/capacities)."""
    cipher = os.path.getsize(artifact_path)
    tar_est = cipher                              # safe upper bound
    extracted_est = tar_est
    tmpfs_peak_est = tar_est + extracted_est      # both during extract

    profile = None
    ppath = os.path.join(manifests_dir, PROFILE)
    if os.path.isfile(ppath):
        try:
            with open(ppath) as f:
                profile = json.load(f)
        except (OSError, json.JSONDecodeError):
            profile = None
    if profile and profile.get("ciphertext_bytes"):
        scale = max(1.0, cipher / float(profile["ciphertext_bytes"]))
        rss_est = int(float(profile["peak_rss_bytes"]) * scale)
        tmpfs_meas = int(float(profile.get("tmpfs_high_water_bytes", 0))
                         * scale)
        tmpfs_peak_est = max(tmpfs_peak_est, tmpfs_meas)
        results_est = int(float(profile.get("results_bytes", 0)) * scale)
        basis = f"surrogate profile {PROFILE} (scale {scale:.3f})"
    else:
        rss_est = int(FALLBACK_RSS_BASE
                      + FALLBACK_RSS_PER_BYTE * extracted_est)
        results_est = max(1 << 30, extracted_est // 4)
        basis = "fallback sizing model (no surrogate profile)"

    mem = _meminfo()
    avail = mem.get("MemAvailable", 0)
    tmpfs_free = _free_bytes(out_dir)
    results_free = _free_bytes(os.path.dirname(
        os.path.abspath(results_path)) or ".")
    demand_ram = rss_est + tmpfs_peak_est         # tmpfs pages are RAM

    checks = {
        "tmpfs_capacity": tmpfs_free >= margin * tmpfs_peak_est,
        "ram_available": avail >= margin * demand_ram,
        "results_capacity": results_free >= margin * results_est,
    }
    report = {
        "basis": basis, "margin": margin,
        "ciphertext_bytes": cipher,
        "decrypted_tar_estimate_bytes": tar_est,
        "extracted_estimate_bytes": extracted_est,
        "tmpfs_peak_estimate_bytes": tmpfs_peak_est,
        "evaluator_peak_rss_estimate_bytes": rss_est,
        "total_ram_demand_bytes": demand_ram,
        "results_estimate_bytes": results_est,
        "mem_available_bytes": avail,
        "mem_total_bytes": mem.get("MemTotal", 0),
        "swap_entries": _swaps(),
        "swap_note": ("swap present — decrypted tmpfs pages could be "
                      "swapped to persistent storage; a swapless or "
                      "encrypted-swap host is required"
                      if _swaps() else "no active swap"),
        "tmpfs_free_bytes": tmpfs_free,
        "results_dir_free_bytes": results_free,
        "checks": checks,
    }
    # swap is a hard refusal: plaintext on tmpfs must never be able to
    # reach persistent storage.
    checks["no_swap"] = not _swaps()
    return all(checks.values()), report
