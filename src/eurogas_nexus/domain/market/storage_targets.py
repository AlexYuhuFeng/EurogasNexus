"""Gas-storage filling trajectory against the EU storage target.

Regulation (EU) 2022/1032 (the gas storage regulation, as amended in 2025) sets a
filling target of 90% of storage capacity to be met at any point between
1 October and 1 December, with permitted deviations under unfavourable market
conditions. The exact percentage, window and allowed deviation are inputs here
(defaults: 90%, 1 October - 1 December, 0 pp) so a desk can apply the version in
force for its member state; this module does not encode legal advice.

The trajectory answers the questions a trader asks of an AGSI series every
morning: where is fill today, how much net injection per day is required to hit the
target by the window opening and by the deadline, what has the recent pace been,
and where does that pace land on the deadline.

本模块按欧盟储气目标（默认 90%，10/1–12/1 窗口，可配置）计算当前库存差距、
所需日均净注入量、近期实际注入速度与截止日预测库存，供交易员晨会判断供需紧张度。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

DEFAULT_TARGET_PCT = 90.0
DEFAULT_WINDOW_OPEN = (10, 1)
DEFAULT_DEADLINE = (12, 1)
DEFAULT_PACE_DAYS = 7


class StorageTrajectoryError(ValueError):
    """The input series cannot support a trajectory."""


@dataclass(frozen=True)
class StorageDay:
    """One gas day of storage data for a single AGSI code (country or EU).

    Attributes:
        gas_day: Gas day of the observation.
        inventory_twh: Gas in storage, TWh.
        working_capacity_twh: Working gas volume, TWh.
        injection_twh_d: Injection over the gas day, TWh (None when unreported).
        withdrawal_twh_d: Withdrawal over the gas day, TWh (None when unreported).
    """

    gas_day: date
    inventory_twh: float
    working_capacity_twh: float
    injection_twh_d: float | None = None
    withdrawal_twh_d: float | None = None


@dataclass(frozen=True)
class StorageTrajectory:
    """Trajectory of one storage series against the target.

    ``status`` is one of ``target_met``, ``on_track``, ``behind``, ``unreachable``
    (the deadline day is reached below target) or ``withdrawal_season`` (before
    1 April, when no injection projection is made).
    """

    code: str
    as_of_gas_day: date
    fill_pct: float
    inventory_twh: float
    working_capacity_twh: float
    target_pct: float
    deviation_pp: float
    effective_target_pct: float
    target_inventory_twh: float
    gap_twh: float
    window_open: date
    deadline: date
    days_to_window_open: int
    days_to_deadline: int
    required_net_injection_to_window_twh_d: float | None
    required_net_injection_to_deadline_twh_d: float | None
    recent_net_injection_twh_d: float | None
    pace_days_used: int
    projected_fill_at_deadline_pct: float | None
    status: str
    limitations: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """JSON-ready representation."""

        result: dict[str, object] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, date):
                value = value.isoformat()
            elif isinstance(value, tuple):
                value = list(value)
            result[name] = value
        return result


def _target_dates(as_of: date, window_open: tuple[int, int], deadline: tuple[int, int]):
    year = as_of.year
    deadline_date = date(year, *deadline)
    if as_of > deadline_date:
        year += 1
        deadline_date = date(year, *deadline)
    return date(year, *window_open), deadline_date


def _recent_pace(days: list[StorageDay], pace_days: int) -> tuple[float | None, int]:
    """Average net injection over the last ``pace_days`` reported days, TWh/d.

    Uses reported injection/withdrawal flows; falls back to inventory deltas between
    consecutive gas days when flows are not reported.
    """

    window = days[-pace_days:]
    flows = [
        day.injection_twh_d - day.withdrawal_twh_d
        for day in window
        if day.injection_twh_d is not None and day.withdrawal_twh_d is not None
    ]
    if flows:
        return sum(flows) / len(flows), len(flows)
    tail = days[-(pace_days + 1):]
    deltas = [
        (later.inventory_twh - earlier.inventory_twh) / (later.gas_day - earlier.gas_day).days
        for earlier, later in zip(tail, tail[1:], strict=False)
    ]
    if not deltas:
        return None, 0
    return sum(deltas) / len(deltas), len(deltas)


def storage_trajectory(
    code: str,
    series: Iterable[StorageDay],
    *,
    target_pct: float = DEFAULT_TARGET_PCT,
    deviation_pp: float = 0.0,
    window_open: tuple[int, int] = DEFAULT_WINDOW_OPEN,
    deadline: tuple[int, int] = DEFAULT_DEADLINE,
    pace_days: int = DEFAULT_PACE_DAYS,
) -> StorageTrajectory:
    """Compute the filling trajectory of one storage series.

    Args:
        code: AGSI code (``EU``, ``DE``, ``NL``...).
        series: Gas-day observations; order does not matter, duplicates keep the last.
        target_pct: Filling target, percent of working gas volume.
        deviation_pp: Permitted deviation, percentage points below target.
        window_open: (month, day) the target window opens.
        deadline: (month, day) the target must be met by.
        pace_days: Number of most recent days used for the recent pace.

    Returns:
        The :class:`StorageTrajectory` as of the latest gas day in ``series``.

    Raises:
        StorageTrajectoryError: Empty series, non-positive capacity or bad inputs.
    """

    if not 0 < target_pct <= 100:
        raise StorageTrajectoryError("target_pct must be in (0, 100]")
    if not 0 <= deviation_pp < target_pct:
        raise StorageTrajectoryError("deviation_pp must be in [0, target_pct)")
    if pace_days < 1:
        raise StorageTrajectoryError("pace_days must be positive")
    by_day = {day.gas_day: day for day in series}
    if not by_day:
        raise StorageTrajectoryError(f"no storage observations for {code}")
    days = [by_day[key] for key in sorted(by_day)]
    latest = days[-1]
    capacity = latest.working_capacity_twh
    if not capacity or capacity <= 0:
        raise StorageTrajectoryError(f"working capacity unavailable for {code}")

    effective_target = target_pct - deviation_pp
    target_inventory = capacity * effective_target / 100.0
    fill_pct = latest.inventory_twh / capacity * 100.0
    gap = max(target_inventory - latest.inventory_twh, 0.0)
    open_date, deadline_date = _target_dates(latest.gas_day, window_open, deadline)
    days_to_open = (open_date - latest.gas_day).days
    days_to_deadline = (deadline_date - latest.gas_day).days

    def required(days_left: int) -> float | None:
        if gap <= 0:
            return 0.0
        return gap / days_left if days_left > 0 else None

    pace, used = _recent_pace(days, pace_days)
    # Projecting a winter withdrawal pace to next December is meaningless, so the
    # projection is only made inside the injection season (1 April - deadline).
    injection_season = date(deadline_date.year, 4, 1) <= latest.gas_day <= deadline_date
    projected = None
    if pace is not None and injection_season:
        projected_inventory = latest.inventory_twh + pace * max(days_to_deadline, 0)
        projected = min(max(projected_inventory / capacity * 100.0, 0.0), 100.0)

    in_window = open_date <= latest.gas_day <= deadline_date
    if gap <= 0:
        status = "target_met"
    elif days_to_deadline <= 0:
        status = "unreachable"
    elif not injection_season:
        status = "withdrawal_season"
    elif projected is not None and projected >= effective_target:
        status = "on_track"
    else:
        status = "behind"

    limitations = [
        "Target, window and deviation are configurable inputs; confirm the regulation "
        "version and member-state trajectory in force before relying on the status.",
        "Recent pace is a backward-looking average, not a forecast of injections.",
    ]
    if used < pace_days:
        limitations.append(
            f"Recent pace uses {used} of {pace_days} requested days of reported data."
        )
    if in_window and gap > 0:
        limitations.append("The target window is open and the effective target is not yet met.")

    return StorageTrajectory(
        code=code.upper(),
        as_of_gas_day=latest.gas_day,
        fill_pct=round(fill_pct, 3),
        inventory_twh=latest.inventory_twh,
        working_capacity_twh=capacity,
        target_pct=target_pct,
        deviation_pp=deviation_pp,
        effective_target_pct=effective_target,
        target_inventory_twh=round(target_inventory, 6),
        gap_twh=round(gap, 6),
        window_open=open_date,
        deadline=deadline_date,
        days_to_window_open=days_to_open,
        days_to_deadline=days_to_deadline,
        required_net_injection_to_window_twh_d=(
            None if days_to_open < 0 else _round(required(days_to_open))
        ),
        required_net_injection_to_deadline_twh_d=_round(required(days_to_deadline)),
        recent_net_injection_twh_d=_round(pace),
        pace_days_used=used,
        projected_fill_at_deadline_pct=None if projected is None else round(projected, 3),
        status=status,
        limitations=tuple(limitations),
    )


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)
