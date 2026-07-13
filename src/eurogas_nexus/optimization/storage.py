"""Multi-period gas storage dispatch optimizer."""

from __future__ import annotations

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
    levels = _inventory_levels(facility, inventory_step_mwh)
    initial = _nearest_level(facility.initial_inventory_mwh, levels)
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
        terminal = _nearest_level(target, levels)
        if terminal not in states:
            return StorageDispatchResult(
                status="infeasible",
                objective_value_gbp=0.0,
                decisions=(),
                terminal_inventory_mwh=facility.initial_inventory_mwh,
                warnings=("TERMINAL_INVENTORY_UNREACHABLE",),
            )
        value, decisions = states[terminal]
        chosen_inventory = terminal
    else:
        chosen_inventory, (value, decisions) = max(states.items(), key=lambda item: item[1][0])

    return StorageDispatchResult(
        status="optimal",
        objective_value_gbp=value,
        decisions=decisions,
        terminal_inventory_mwh=chosen_inventory,
    )


def _inventory_levels(facility: StorageFacility, step: float) -> tuple[float, ...]:
    levels: list[float] = []
    current = facility.minimum_inventory_mwh
    while current < facility.maximum_inventory_mwh - 1e-9:
        levels.append(round(current, 10))
        current += step
    levels.append(facility.maximum_inventory_mwh)
    return tuple(sorted(set(levels)))


def _nearest_level(value: float, levels: tuple[float, ...]) -> float:
    return min(levels, key=lambda level: abs(level - value))
