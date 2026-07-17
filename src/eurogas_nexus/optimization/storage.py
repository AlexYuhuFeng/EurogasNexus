"""Multi-period gas storage dispatch optimizer."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import OptimizationStatus


@dataclass(frozen=True, slots=True)
class StoragePeriod:
    period_id: str
    market_price_gbp_mwh: float


@dataclass(frozen=True, slots=True)
class StorageFacility:
    initial_inventory_mwh: float
    minimum_inventory_mwh: float
    maximum_inventory_mwh: float
    maximum_injection_mwh: float
    maximum_withdrawal_mwh: float
    injection_efficiency: float = 1.0
    withdrawal_efficiency: float = 1.0
    injection_cost_gbp_mwh: float = 0.0
    withdrawal_cost_gbp_mwh: float = 0.0
    terminal_inventory_mwh: float | None = None


@dataclass(frozen=True, slots=True)
class StorageDecision:
    period_id: str
    injection_mwh: float
    withdrawal_mwh: float
    ending_inventory_mwh: float
    cashflow_gbp: float


@dataclass(frozen=True, slots=True)
class StorageDispatchResult:
    status: OptimizationStatus
    objective_value_gbp: float
    decisions: tuple[StorageDecision, ...]
    terminal_inventory_mwh: float
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True


def optimize_storage_dispatch(
    facility: StorageFacility,
    periods: list[StoragePeriod],
    *,
    inventory_step_mwh: float = 1.0,
) -> StorageDispatchResult:
    """Optimize inject/withdraw/hold decisions with inventory-grid dynamic programming."""

    if inventory_step_mwh <= 0:
        raise ValueError("inventory_step_mwh must be positive")
    if not math.isfinite(inventory_step_mwh):
        raise ValueError("inventory_step_mwh must be finite")
    _validate_facility(facility)
    _validate_periods(periods)
    required_levels = [facility.initial_inventory_mwh]
    if facility.terminal_inventory_mwh is not None:
        required_levels.append(facility.terminal_inventory_mwh)
    levels = _inventory_levels(facility, inventory_step_mwh, required_levels)
    initial = facility.initial_inventory_mwh
    states: dict[float, tuple[float, tuple[StorageDecision, ...]]] = {initial: (0.0, ())}

    for period in periods:
        next_states: dict[float, tuple[float, tuple[StorageDecision, ...]]] = {}
        for inventory, (value, decisions) in states.items():
            for next_inventory in levels:
                delta = next_inventory - inventory
                injection = max(delta / facility.injection_efficiency, 0.0)
                withdrawal = max(-delta * facility.withdrawal_efficiency, 0.0)
                if injection > facility.maximum_injection_mwh + 1e-9:
                    continue
                if withdrawal > facility.maximum_withdrawal_mwh + 1e-9:
                    continue
                cashflow = (
                    withdrawal * (period.market_price_gbp_mwh - facility.withdrawal_cost_gbp_mwh)
                    - injection * (period.market_price_gbp_mwh + facility.injection_cost_gbp_mwh)
                )
                candidate_value = value + cashflow
                existing = next_states.get(next_inventory)
                decision = StorageDecision(
                    period_id=period.period_id,
                    injection_mwh=injection,
                    withdrawal_mwh=withdrawal,
                    ending_inventory_mwh=next_inventory,
                    cashflow_gbp=cashflow,
                )
                if existing is None or candidate_value > existing[0]:
                    next_states[next_inventory] = (candidate_value, (*decisions, decision))
        states = next_states

    if not states:
        return StorageDispatchResult(
            status="infeasible",
            objective_value_gbp=0.0,
            decisions=(),
            terminal_inventory_mwh=facility.initial_inventory_mwh,
            warnings=("NO_FEASIBLE_STORAGE_PATH",),
        )

    target = facility.terminal_inventory_mwh
    if target is not None:
        if target not in states:
            return StorageDispatchResult(
                status="infeasible",
                objective_value_gbp=0.0,
                decisions=(),
                terminal_inventory_mwh=facility.initial_inventory_mwh,
                warnings=("TERMINAL_INVENTORY_UNREACHABLE",),
            )
        value, decisions = states[target]
        chosen_inventory = target
    else:
        chosen_inventory, (value, decisions) = max(states.items(), key=lambda item: item[1][0])

    return StorageDispatchResult(
        status="optimal",
        objective_value_gbp=value,
        decisions=decisions,
        terminal_inventory_mwh=chosen_inventory,
    )


def _validate_facility(facility: StorageFacility) -> None:
    numeric_fields = {
        "initial_inventory_mwh": facility.initial_inventory_mwh,
        "minimum_inventory_mwh": facility.minimum_inventory_mwh,
        "maximum_inventory_mwh": facility.maximum_inventory_mwh,
        "maximum_injection_mwh": facility.maximum_injection_mwh,
        "maximum_withdrawal_mwh": facility.maximum_withdrawal_mwh,
        "injection_efficiency": facility.injection_efficiency,
        "withdrawal_efficiency": facility.withdrawal_efficiency,
        "injection_cost_gbp_mwh": facility.injection_cost_gbp_mwh,
        "withdrawal_cost_gbp_mwh": facility.withdrawal_cost_gbp_mwh,
    }
    if facility.terminal_inventory_mwh is not None:
        numeric_fields["terminal_inventory_mwh"] = facility.terminal_inventory_mwh
    for name, value in numeric_fields.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")

    if facility.minimum_inventory_mwh < 0:
        raise ValueError("minimum_inventory_mwh must be non-negative")
    if facility.maximum_inventory_mwh < facility.minimum_inventory_mwh:
        raise ValueError("maximum_inventory_mwh must not be below minimum inventory")
    if not (
        facility.minimum_inventory_mwh
        <= facility.initial_inventory_mwh
        <= facility.maximum_inventory_mwh
    ):
        raise ValueError("initial_inventory_mwh must be within inventory bounds")
    if facility.maximum_injection_mwh < 0 or facility.maximum_withdrawal_mwh < 0:
        raise ValueError("injection and withdrawal limits must be non-negative")
    if not 0 < facility.injection_efficiency <= 1:
        raise ValueError("injection_efficiency must be in (0, 1]")
    if not 0 < facility.withdrawal_efficiency <= 1:
        raise ValueError("withdrawal_efficiency must be in (0, 1]")
    if facility.injection_cost_gbp_mwh < 0 or facility.withdrawal_cost_gbp_mwh < 0:
        raise ValueError("storage variable costs must be non-negative")
    terminal = facility.terminal_inventory_mwh
    if terminal is not None and not (
        facility.minimum_inventory_mwh <= terminal <= facility.maximum_inventory_mwh
    ):
        raise ValueError("terminal_inventory_mwh must be within inventory bounds")


def _validate_periods(periods: list[StoragePeriod]) -> None:
    period_ids: set[str] = set()
    for period in periods:
        if not period.period_id.strip():
            raise ValueError("period_id must not be empty")
        if period.period_id in period_ids:
            raise ValueError(f"duplicate period_id: {period.period_id}")
        period_ids.add(period.period_id)
        if not math.isfinite(period.market_price_gbp_mwh):
            raise ValueError(f"market price must be finite: {period.period_id}")


def _inventory_levels(
    facility: StorageFacility,
    step: float,
    required_levels: list[float],
) -> tuple[float, ...]:
    levels: list[float] = []
    current = facility.minimum_inventory_mwh
    while current < facility.maximum_inventory_mwh - 1e-9:
        levels.append(round(current, 10))
        current += step
    levels.append(facility.maximum_inventory_mwh)
    levels.extend(required_levels)
    return tuple(sorted(set(levels)))
