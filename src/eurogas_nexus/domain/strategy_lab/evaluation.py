"""Strategy-lab models for backtest, shadow-run, and live monitoring."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time
from enum import StrEnum

from pydantic import BaseModel, Field


class StrategyRunMode(StrEnum):
    BACKTEST = "BACKTEST"
    SHADOW_RUN = "SHADOW_RUN"
    LIVE_MONITOR = "LIVE_MONITOR"


class StrategyComponentType(StrEnum):
    OCM_VS_DAY_AHEAD = "OCM_VS_DAY_AHEAD"
    MEAN_REVERSION = "MEAN_REVERSION"
    BEST_BUCKETS = "BEST_BUCKETS"
    SCORING = "SCORING"
    WEIGHTED_COMBINATION = "WEIGHTED_COMBINATION"


class StrategyPriceObservation(BaseModel):
    observation_id: str
    source_system: str
    venue: str
    hub: str
    product: str
    price_name: str
    price_gbp_mwh: float
    observed_at_utc: datetime
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    bar_minutes: int | None = None
    price_type: str = "mid"
    source_reference: str = ""


class StrategyResourceContext(BaseModel):
    resource_id: str
    resource_name: str
    available_quantity_mwh_per_day: float
    all_in_cost_gbp_mwh: float
    delivery_tolerance_pct: float | None = None
    nomination_tolerance_pct: float | None = None
    booked_entry_capacity_mwh_per_day: float | None = None
    balancing_allowance_gbp_mwh: float = 0.0
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None


class StrategyComponent(BaseModel):
    component_id: str
    component_type: StrategyComponentType
    weight: float = 1.0
    day_ahead_price_names: list[str] = Field(
        default_factory=lambda: ["SAP", "ICIS_HEREN_DAY_AHEAD", "EEX_DAY_AHEAD"]
    )
    intraday_price_names: list[str] = Field(default_factory=lambda: ["ICE_OCM"])
    positive_spread_threshold_gbp_mwh: float = 0.0
    negative_spread_threshold_gbp_mwh: float = 0.0
    time_window_start: str | None = None
    time_window_end: str | None = None
    target_bar_minutes: int | None = 5


class StrategyRiskControl(BaseModel):
    max_ocm_allocation_pct: float = 80.0
    min_day_ahead_allocation_pct: float = 10.0
    max_single_market_volume_mwh_per_day: float | None = None
    min_expected_margin_gbp_mwh: float | None = None
    stop_shadow_run_loss_gbp: float | None = None
    require_tso_access: bool = True


class StrategyLabScenario(BaseModel):
    strategy_id: str
    strategy_name: str
    run_mode: StrategyRunMode
    resource_contexts: list[StrategyResourceContext]
    price_observations: list[StrategyPriceObservation]
    components: list[StrategyComponent]
    risk_control: StrategyRiskControl = Field(default_factory=StrategyRiskControl)
    existing_shadow_pnl_gbp: float = 0.0
    research_only: bool = True


class StrategyAllocationTarget(BaseModel):
    market_bucket: str
    target_allocation_pct: float
    target_quantity_mwh_per_day: float
    reference_price_gbp_mwh: float | None = None
    expected_margin_gbp_mwh: float | None = None
    rationale: list[str] = Field(default_factory=list)


class StrategyLabResult(BaseModel):
    strategy_id: str
    strategy_name: str
    run_mode: StrategyRunMode
    status: str
    weighted_score: float
    day_ahead_average_gbp_mwh: float | None = None
    intraday_average_gbp_mwh: float | None = None
    intraday_vs_day_ahead_spread_gbp_mwh: float | None = None
    allocation_targets: list[StrategyAllocationTarget] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    candidate_action_for_review: str = "REVIEW_STRATEGY_OUTPUT"
    research_only: bool = True
    human_review_required: bool = True


def evaluate_strategy_lab(scenario: StrategyLabScenario) -> StrategyLabResult:
    """Evaluate strategy signals without creating orders, trades, or nominations."""

    missing_inputs: list[str] = []
    warnings: list[str] = []
    source_refs = _source_refs(scenario.price_observations)

    if not scenario.resource_contexts:
        missing_inputs.append("RESOURCE_CONTEXTS_MISSING")
    if not scenario.price_observations:
        missing_inputs.append("PRICE_OBSERVATIONS_MISSING")
    if not scenario.components:
        missing_inputs.append("STRATEGY_COMPONENTS_MISSING")

    if scenario.risk_control.require_tso_access:
        for resource in scenario.resource_contexts:
            inaccessible = _inaccessible_tsos(
                resource.required_tso_access,
                resource.company_accessible_tsos,
            )
            if inaccessible:
                missing_inputs.extend(
                    f"TSO_ACCESS_MISSING:{resource.resource_id}:{tso}"
                    for tso in inaccessible
                )

    if (
        scenario.risk_control.stop_shadow_run_loss_gbp is not None
        and scenario.existing_shadow_pnl_gbp <= -abs(scenario.risk_control.stop_shadow_run_loss_gbp)
    ):
        warnings.append("SHADOW_RUN_STOP_LOSS_TRIGGERED")

    day_ahead_prices: list[float] = []
    intraday_prices: list[float] = []
    weighted_score = 0.0
    weight_sum = 0.0

    for component in scenario.components:
        component_observations = _filter_time_window(
            scenario.price_observations,
            component.time_window_start,
            component.time_window_end,
        )
        if component.target_bar_minutes is not None:
            component_observations = [
                obs
                for obs in component_observations
                if obs.bar_minutes in {None, component.target_bar_minutes}
            ]
        day_values = [
            obs.price_gbp_mwh
            for obs in component_observations
            if obs.price_name.upper() in {name.upper() for name in component.day_ahead_price_names}
        ]
        intraday_values = [
            obs.price_gbp_mwh
            for obs in component_observations
            if obs.price_name.upper() in {name.upper() for name in component.intraday_price_names}
        ]
        day_ahead_prices.extend(day_values)
        intraday_prices.extend(intraday_values)
        component_score = _component_score(component, day_values, intraday_values)
        weighted_score += component_score * component.weight
        weight_sum += component.weight

    weighted_score = round(weighted_score / weight_sum, 4) if weight_sum else 0.0
    day_average = _average(day_ahead_prices)
    intraday_average = _average(intraday_prices)
    spread = (
        round(intraday_average - day_average, 4)
        if intraday_average is not None and day_average is not None
        else None
    )
    if day_average is None:
        missing_inputs.append("DAY_AHEAD_REFERENCE_PRICE_MISSING")
    if intraday_average is None:
        missing_inputs.append("INTRADAY_REFERENCE_PRICE_MISSING")

    allocation_targets = _allocation_targets(
        scenario,
        day_average=day_average,
        intraday_average=intraday_average,
        weighted_score=weighted_score,
        warnings=warnings,
    )
    if not allocation_targets:
        warnings.append("NO_POSITIVE_STRATEGY_ALLOCATION_TARGET")

    status = "SUCCESS"
    if missing_inputs:
        status = "BLOCKED" if not allocation_targets else "PARTIAL"
    if "SHADOW_RUN_STOP_LOSS_TRIGGERED" in warnings:
        status = "BLOCKED"

    return StrategyLabResult(
        strategy_id=scenario.strategy_id,
        strategy_name=scenario.strategy_name,
        run_mode=scenario.run_mode,
        status=status,
        weighted_score=weighted_score,
        day_ahead_average_gbp_mwh=day_average,
        intraday_average_gbp_mwh=intraday_average,
        intraday_vs_day_ahead_spread_gbp_mwh=spread,
        allocation_targets=allocation_targets,
        missing_inputs=_unique(missing_inputs),
        warnings=_unique(warnings),
        source_refs=source_refs,
        candidate_action_for_review=_candidate_action(weighted_score, status),
        research_only=True,
        human_review_required=True,
    )


def _component_score(
    component: StrategyComponent,
    day_ahead_prices: Sequence[float],
    intraday_prices: Sequence[float],
) -> float:
    day_average = _average(day_ahead_prices)
    intraday_average = _average(intraday_prices)
    if day_average is None or intraday_average is None:
        return 0.0
    spread = intraday_average - day_average
    if spread > component.positive_spread_threshold_gbp_mwh:
        return min(spread, 5.0) / 5.0
    if spread < -abs(component.negative_spread_threshold_gbp_mwh):
        return max(spread, -5.0) / 5.0
    return 0.0


def _allocation_targets(
    scenario: StrategyLabScenario,
    *,
    day_average: float | None,
    intraday_average: float | None,
    weighted_score: float,
    warnings: list[str],
) -> list[StrategyAllocationTarget]:
    total_quantity = sum(
        resource.available_quantity_mwh_per_day
        for resource in scenario.resource_contexts
    )
    if total_quantity <= 0:
        return []
    average_cost = _weighted_resource_cost(scenario.resource_contexts)
    if intraday_average is None or day_average is None or average_cost is None:
        return []

    ocm_pct = 50.0 + weighted_score * 30.0
    ocm_pct = min(max(ocm_pct, 0.0), scenario.risk_control.max_ocm_allocation_pct)
    day_pct = max(100.0 - ocm_pct, scenario.risk_control.min_day_ahead_allocation_pct)
    if day_pct + ocm_pct > 100:
        ocm_pct = 100.0 - day_pct
    targets = [
        _target("ICE_OCM", ocm_pct, total_quantity, intraday_average, average_cost),
        _target("DAY_AHEAD", day_pct, total_quantity, day_average, average_cost),
    ]
    max_single_market_volume = scenario.risk_control.max_single_market_volume_mwh_per_day
    if max_single_market_volume is not None:
        for target in targets:
            if target.target_quantity_mwh_per_day > max_single_market_volume:
                warnings.append("MAX_SINGLE_MARKET_VOLUME_CLAMP_REQUIRED")
                target.target_quantity_mwh_per_day = max_single_market_volume
    if scenario.risk_control.min_expected_margin_gbp_mwh is not None:
        min_margin = scenario.risk_control.min_expected_margin_gbp_mwh
        targets = [
            target
            for target in targets
            if (target.expected_margin_gbp_mwh or 0) >= min_margin
        ]
    return targets


def _target(
    bucket: str,
    pct: float,
    total_quantity: float,
    price: float,
    average_cost: float,
) -> StrategyAllocationTarget:
    margin = round(price - average_cost, 4)
    return StrategyAllocationTarget(
        market_bucket=bucket,
        target_allocation_pct=round(pct, 2),
        target_quantity_mwh_per_day=round(total_quantity * pct / 100, 4),
        reference_price_gbp_mwh=price,
        expected_margin_gbp_mwh=margin,
        rationale=[
            "Paper target derived from configured strategy components.",
            "Human review is required before any external trading or operational action.",
        ],
    )


def _weighted_resource_cost(resources: Sequence[StrategyResourceContext]) -> float | None:
    total_quantity = sum(resource.available_quantity_mwh_per_day for resource in resources)
    if total_quantity <= 0:
        return None
    total_cost = sum(
        resource.available_quantity_mwh_per_day
        * (resource.all_in_cost_gbp_mwh + resource.balancing_allowance_gbp_mwh)
        for resource in resources
    )
    return round(total_cost / total_quantity, 4)


def _filter_time_window(
    observations: Sequence[StrategyPriceObservation],
    start: str | None,
    end: str | None,
) -> list[StrategyPriceObservation]:
    if not start or not end:
        return list(observations)
    start_time = _parse_hh_mm(start)
    end_time = _parse_hh_mm(end)
    return [
        obs
        for obs in observations
        if _time_in_window(obs.observed_at_utc.time(), start_time, end_time)
    ]


def _parse_hh_mm(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _time_in_window(value: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _inaccessible_tsos(
    required_tso_access: Sequence[str],
    company_accessible_tsos: Sequence[str] | None,
) -> list[str]:
    if company_accessible_tsos is None:
        return []
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    return [
        tso
        for tso in required_tso_access
        if tso.strip() and tso.strip().lower() not in allowed
    ]


def _source_refs(observations: Sequence[StrategyPriceObservation]) -> list[str]:
    return _unique(
        [obs.source_reference for obs in observations if obs.source_reference]
    )


def _candidate_action(weighted_score: float, status: str) -> str:
    if status == "BLOCKED":
        return "REVIEW_BLOCKED_STRATEGY"
    if weighted_score > 0:
        return "REVIEW_HIGHER_OCM_ALLOCATION"
    if weighted_score < 0:
        return "REVIEW_HIGHER_DAY_AHEAD_ALLOCATION"
    return "REVIEW_BALANCED_ALLOCATION"


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))
