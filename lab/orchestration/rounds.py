"""Synchronized-round coordinator — SPEC_FINAL-1.2.md §23 Operations.

At every 4h boundary all seven arms receive the same snapshot; any arm
unable to decide invalidates the round for ALL arms. The failure is
recorded; rounds are never backfilled; healthy arms never accumulate
official results during an asymmetric round.

Contract: the orchestrator opens a round, reports every arm's decision
outcome (ok or failed), then finalizes. Only a finalized-valid round's
decisions may be executed; the coordinator's record is append-only and a
finalized round can never be reopened or altered (backfill attempts raise).
"""
from __future__ import annotations


class RoundError(RuntimeError):
    pass


class RoundCoordinator:
    def __init__(self, arm_ids: list[str]):
        if not arm_ids:
            raise ValueError("at least one arm required")
        self.arm_ids = list(arm_ids)
        self.records: list[dict] = []          # append-only round ledger
        self._finalized: dict[int, bool] = {}  # t -> valid
        self._open: dict[int, dict] = {}       # t -> arm_id -> report

    def begin_round(self, t: int) -> None:
        if t in self._finalized:
            raise RoundError(f"round {t} already finalized — rounds are "
                             f"never reopened or backfilled")
        if t in self._open:
            raise RoundError(f"round {t} already open")
        self._open[t] = {}

    def report(self, t: int, arm_id: str, ok: bool,
               reason: str | None = None) -> None:
        if t not in self._open:
            raise RoundError(f"round {t} is not open")
        if arm_id not in self.arm_ids:
            raise RoundError(f"unknown arm {arm_id!r}")
        if arm_id in self._open[t]:
            raise RoundError(f"arm {arm_id!r} already reported for round {t}")
        self._open[t][arm_id] = {"ok": bool(ok), "reason": reason}

    def finalize(self, t: int) -> bool:
        """Returns validity. A round is valid iff EVERY arm reported ok.
        A missing report is a failure (the arm was unable to decide)."""
        if t not in self._open:
            raise RoundError(f"round {t} is not open")
        reports = self._open.pop(t)
        failed = sorted(a for a in self.arm_ids
                        if a not in reports or not reports[a]["ok"])
        valid = not failed
        self.records.append({
            "t": int(t), "valid": valid,
            "failed_arms": failed,
            "reasons": {a: reports[a]["reason"] for a in failed
                        if a in reports},
            "missing_reports": [a for a in failed if a not in reports],
        })
        self._finalized[t] = valid
        return valid

    def is_valid(self, t: int) -> bool:
        """Only finalized-valid rounds may execute decisions."""
        if t not in self._finalized:
            raise RoundError(f"round {t} was never finalized")
        return self._finalized[t]

    def counts(self) -> dict:
        n_valid = sum(1 for r in self.records if r["valid"])
        return {"total": len(self.records), "valid": n_valid,
                "invalid": len(self.records) - n_valid}
