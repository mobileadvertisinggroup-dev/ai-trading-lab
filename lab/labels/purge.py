"""Variable-horizon purge and embargo — SPEC_FINAL-1.2.md §10.

Each labeled example's information interval is [candidate t, final Arm A
exit t]. Any training example whose complete interval overlaps validation
(or beyond) is purged; any validation example whose interval overlaps the
holdout is purged. The embargo equals Arm A's frozen maximum holding period
by construction, and this module VERIFIES rather than assumes it: an
interval longer than the maximum possible horizon raises immediately.

Holdout-period candidates must never reach this code before Checkpoint-2
authorization — encountering one raises, it is not silently binned.
"""
from __future__ import annotations

from lab import protocol as P

# max horizon: 42 4h bars plus one 15m bar for the next-open exit fill
MAX_HORIZON_MS = P.MAX_HOLD_BARS_4H * P.BAR_4H_MS + P.BAR_15M_MS


class HoldoutContaminationError(RuntimeError):
    pass


def chronological_split(examples: list[dict], val_start_ms: int,
                        holdout_start_ms: int) -> dict:
    """Split labeled examples into train / validation with variable-horizon
    purging. Unlabeled examples (exclusion set) pass through untouched in
    'unlabeled'. Returns dict with train, validation, purged_train,
    purged_validation, unlabeled — every example accounted for, none
    silently dropped."""
    if val_start_ms % P.BAR_4H_MS or holdout_start_ms % P.BAR_4H_MS:
        raise ValueError("partition boundaries must be 4h boundaries")
    if not val_start_ms < holdout_start_ms:
        raise ValueError("val_start must precede holdout_start")

    out = {"train": [], "validation": [], "purged_train": [],
           "purged_validation": [], "unlabeled": []}
    for ex in examples:
        t = int(ex["t"])
        if t >= holdout_start_ms:
            raise HoldoutContaminationError(
                f"candidate at {t} lies in the sealed holdout range "
                f"(>= {holdout_start_ms}); labeling code must never see it "
                f"before Checkpoint-2 authorization")
        if ex.get("exclusion") is not None or ex.get("net_r") is None:
            out["unlabeled"].append(ex)
            continue
        lo, hi = ex["info_interval"]
        if hi - lo > MAX_HORIZON_MS:
            raise ValueError(
                f"info interval {hi - lo} ms exceeds the frozen maximum "
                f"horizon {MAX_HORIZON_MS} ms — label-horizon violation")
        if t < val_start_ms:
            if hi < val_start_ms:
                out["train"].append(ex)
            else:
                out["purged_train"].append(ex)     # overlaps validation
        else:
            if hi < holdout_start_ms:
                out["validation"].append(ex)
            else:
                out["purged_validation"].append(ex)  # overlaps holdout
    return out
