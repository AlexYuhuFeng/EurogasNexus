"""Gas-day nomination and renomination window validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

from .models import OptimizationStatus


@dataclass(frozen=True, slots=True)
class NominationWindow:
    window_id: str
    opens_at: time
    closes_at: time
    maximum_change_mwh: float | None = None
    maximum_change_pct: float | None = None


@dataclass(frozen=True, slots=True)
class NominationInstruction:
    submitted_at: datetime
    requested_quantity_mwh: float


@dataclass(frozen=True, slots=True)
class NominationDecision:
    submitted_at: datetime
    requested_quantity_mwh: float
    accepted_quantity_mwh: float
    window_id: str | None
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class NominationScheduleResult:
    status: OptimizationStatus
    final_quantity_mwh: float
    decisions: tuple[NominationDecision, ...]
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True


def optimize_nomination_schedule(
    initial_quantity_mwh: float,
    instructions: list[NominationInstruction],
    windows: list[NominationWindow],
) -> NominationScheduleResult:
    """Apply nomination and renomination instructions in chronological order."""

    current = initial_quantity_mwh
    decisions: list[NominationDecision] = []
    warnings: list[str] = []
    for instruction in sorted(instructions, key=lambda item: item.submitted_at):
        window = _find_window(instruction.submitted_at.time(), windows)
        if window is None:
            decisions.append(
                NominationDecision(
                    submitted_at=instruction.submitted_at,
                    requested_quantity_mwh=instruction.requested_quantity_mwh,
                    accepted_quantity_mwh=current,
                    window_id=None,
                    accepted=False,
                    reason="OUTSIDE_NOMINATION_WINDOW",
                )
            )
            warnings.append("OUTSIDE_NOMINATION_WINDOW")
            continue
        change = instruction.requested_quantity_mwh - current
        absolute_limit = window.maximum_change_mwh
        percentage_limit = (
            abs(current) * window.maximum_change_pct / 100
            if window.maximum_change_pct is not None
            else None
        )
        limits = [limit for limit in (absolute_limit, percentage_limit) if limit is not None]
        maximum_change = min(limits) if limits else None
        if maximum_change is not None and abs(change) > maximum_change + 1e-9:
            accepted_quantity = current + maximum_change * (1 if change > 0 else -1)
            decisions.append(
                NominationDecision(
                    submitted_at=instruction.submitted_at,
                    requested_quantity_mwh=instruction.requested_quantity_mwh,
                    accepted_quantity_mwh=accepted_quantity,
                    window_id=window.window_id,
                    accepted=False,
                    reason="RENOMINATION_CHANGE_LIMIT_APPLIED",
                )
            )
            current = accepted_quantity
            warnings.append("RENOMINATION_CHANGE_LIMIT_APPLIED")
            continue
        current = instruction.requested_quantity_mwh
        decisions.append(
            NominationDecision(
                submitted_at=instruction.submitted_at,
                requested_quantity_mwh=instruction.requested_quantity_mwh,
                accepted_quantity_mwh=current,
                window_id=window.window_id,
                accepted=True,
                reason="ACCEPTED",
            )
        )
    status: OptimizationStatus = "optimal" if not warnings else "feasible"
    return NominationScheduleResult(
        status=status,
        final_quantity_mwh=current,
        decisions=tuple(decisions),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _find_window(value: time, windows: list[NominationWindow]) -> NominationWindow | None:
    for window in windows:
        if window.opens_at <= window.closes_at:
            if window.opens_at <= value <= window.closes_at:
                return window
        elif value >= window.opens_at or value <= window.closes_at:
            return window
    return None
