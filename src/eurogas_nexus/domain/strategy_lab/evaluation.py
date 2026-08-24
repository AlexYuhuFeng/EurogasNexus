"""Strategy-lab models for backtest, shadow-run, and live monitoring.

策略实验室评估的唯一实现：组件信号打分 → 加权评分 → OCM/日前分配
→ 纸面 PnL 与止损判定。全程只产生"供人工复核"的纸面目标，
绝不生成订单、交易或提名。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time

from pydantic import BaseModel, Field

from eurogas_nexus.domain.constraints.access import inaccessible_tsos as _inaccessible_tsos
from eurogas_nexus.domain.constraints.risk import ocm_day_split, stop_loss_triggered
from eurogas_nexus.domain.ontology.vocabulary import (
    CandidateAction,
    StrategyComponentType,
    StrategyRunMode,
)


class StrategyPriceObservation(BaseModel):
    """One price observation consumed by strategy components.

    Attributes:
        observation_id: Stable observation id.
        source_system: Source system.
        venue: Venue of the observation.
        hub: Hub.
        product: Product label.
        price_name: Price series name (matched against component names).
        price_gbp_mwh: Price in GBP/MWh.
        observed_at_utc: Observation time.
        delivery_start_utc: Delivery window start.
        delivery_end_utc: Delivery window end.
        bar_minutes: Bar aggregation in minutes, or None.
        price_type: Side/type tag (e.g. ``mid``).
        source_reference: Provenance reference.
    """

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
    """One resource's context for strategy allocation sizing.

    Attributes:
        resource_id: Stable resource id.
        resource_name: Display name.
        available_quantity_mwh_per_day: Volume available, MWh/d.
        all_in_cost_gbp_mwh: All-in cost per MWh.
        delivery_tolerance_pct: Delivery tolerance, or None.
        nomination_tolerance_pct: Nomination tolerance, or None.
        booked_entry_capacity_mwh_per_day: Booked entry capacity, or None.
        balancing_allowance_gbp_mwh: Balancing allowance per MWh.
        required_tso_access: TSO access codes required.
        company_accessible_tsos: Company's accessible TSOs, or None.
    """

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
    """One signal component with price names, thresholds and window.

    Attributes:
        component_id: Stable component id.
        component_type: Component family (scoring/best buckets/...).
        weight: Weight in the weighted score.
        day_ahead_price_names: Day-ahead price series names.
        intraday_price_names: Intraday price series names.
        positive_spread_threshold_gbp_mwh: Threshold for positive score.
        negative_spread_threshold_gbp_mwh: Threshold for negative score.
        time_window_start: Local time window start (``HH:MM``), or None.
        time_window_end: Local time window end (``HH:MM``), or None.
        target_bar_minutes: Bar filter, or None.
    """

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
    """Risk controls applied to the strategy evaluation.

    Attributes:
        max_ocm_allocation_pct: Upper clamp for OCM share.
        min_day_ahead_allocation_pct: Floor for day-ahead share.
        max_single_market_volume_mwh_per_day: Volume cap per market, or None.
        min_expected_margin_gbp_mwh: Margin floor for targets, or None.
        stop_shadow_run_loss_gbp: Cumulative stop-loss threshold, or None.
        require_tso_access: Whether TSO access is mandatory.
    """

    max_ocm_allocation_pct: float = 80.0
    min_day_ahead_allocation_pct: float = 10.0
    max_single_market_volume_mwh_per_day: float | None = None
    min_expected_margin_gbp_mwh: float | None = None
    stop_shadow_run_loss_gbp: float | None = None
    require_tso_access: bool = True


class StrategyLabScenario(BaseModel):
    """Input scenario for one strategy-lab evaluation.

    Attributes:
        strategy_id: Stable strategy id.
        strategy_name: Display name.
        run_mode: BACKTEST / SHADOW_RUN / LIVE_MONITOR.
        resource_contexts: Resource contexts for sizing.
        price_observations: Price series observations.
        components: Signal components.
        risk_control: Risk controls.
        existing_shadow_pnl_gbp: Cumulative PnL carried into this run.
        research_only: Always True.
    """

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
    """One paper allocation target (never executed).

    Attributes:
        market_bucket: Market bucket (``ICE_OCM`` / ``DAY_AHEAD``).
        target_allocation_pct: Share of the portfolio, percent.
        target_quantity_mwh_per_day: Volume, MWh/d.
        reference_price_gbp_mwh: Reference price used, or None.
        expected_margin_gbp_mwh: Expected margin per MWh, or None.
        rationale: Machine-readable rationale tags.
    """

    market_bucket: str
    target_allocation_pct: float
    target_quantity_mwh_per_day: float
    reference_price_gbp_mwh: float | None = None
    expected_margin_gbp_mwh: float | None = None
    rationale: list[str] = Field(default_factory=list)


class StrategyLabResult(BaseModel):
    """Evaluation result of one strategy-lab run.

    Attributes:
        strategy_id / strategy_name: Echoed identity.
        run_mode: Echoed run mode.
        status: SUCCESS / PARTIAL / BLOCKED.
        weighted_score: Weighted component score in [-1, 1].
        day_ahead_average_gbp_mwh: Day-ahead average, or None.
        intraday_average_gbp_mwh: Intraday average, or None.
        intraday_vs_day_ahead_spread_gbp_mwh: Spread, or None.
        allocation_targets: Paper targets.
        missing_inputs: Inputs that limited the run.
        warnings: Aggregated warnings.
        source_refs: Provenance of observations.
        candidate_action_for_review: Trader-review action tag.
        paper_pnl_gbp: Paper PnL of this run.
        cumulative_pnl_gbp: Existing + paper PnL.
        hit: Whether paper PnL is positive.
        research_only / human_review_required: Always True.
    """

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
    paper_pnl_gbp: float = 0.0
    cumulative_pnl_gbp: float = 0.0
    hit: bool = False
    research_only: bool = True
    human_review_required: bool = True


def evaluate_strategy_lab(scenario: StrategyLabScenario) -> StrategyLabResult:
    """Evaluate strategy signals without creating orders, trades, or nominations.

    评估策略信号：组件打分 → 加权评分 → OCM/日前纸面分配 → 纸面 PnL
    与止损判定（全程无执行动作）。

    Args:
        scenario: Strategy-lab scenario with resources, prices, components
            and risk controls.

    Returns:
        A StrategyLabResult with score, averages, spread, allocation
        targets, paper PnL and a review action. Missing inputs degrade
        the status; a triggered stop-loss blocks the run.

    Raises:
        No exceptions; gaps are reported in the result.
    """

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
        # TSO 准入是硬要求：任一资源有不可达 TSO 即记缺失（fail-closed）。
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

    day_ahead_prices: list[float] = []
    intraday_prices: list[float] = []
    weighted_score = 0.0
    weight_sum = 0.0

    for component in scenario.components:
        component_observations = list(scenario.price_observations)
        if component.target_bar_minutes is not None:
            component_observations = [
                obs
                for obs in component_observations
                if obs.bar_minutes in {None, component.target_bar_minutes}
            ]
        window_observations = _filter_time_window(
            component_observations,
            component.time_window_start,
            component.time_window_end,
        )
        day_ahead_names = {name.upper() for name in component.day_ahead_price_names}
        intraday_names = {name.upper() for name in component.intraday_price_names}
        day_values = [
            obs.price_gbp_mwh
            for obs in component_observations
            if obs.price_name.upper() in day_ahead_names
        ]
        intraday_values = [
            obs.price_gbp_mwh
            for obs in window_observations
            if obs.price_name.upper() in intraday_names
        ]
        if not intraday_values and component.time_window_start and component.time_window_end:
            # 窗口内无日内数据：回退到窗口外最新日内数据并显式告警。
            latest_intraday_values = [
                obs.price_gbp_mwh
                for obs in component_observations
                if obs.price_name.upper() in intraday_names
            ]
            if latest_intraday_values:
                intraday_values = latest_intraday_values
                warnings.append(
                    f"LATEST_INTRADAY_OUTSIDE_CONFIGURED_WINDOW:{component.component_id}"
                )
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

    # 纸面 PnL：目标量 × 预期边际之和（纯纸面，不触发任何执行）。
    paper_pnl_gbp = round(
        sum(
            (target.expected_margin_gbp_mwh or 0.0) * target.target_quantity_mwh_per_day
            for target in allocation_targets
        ),
        4,
    )
    cumulative_pnl_gbp = round(scenario.existing_shadow_pnl_gbp + paper_pnl_gbp, 4)
    hit = paper_pnl_gbp > 0

    if stop_loss_triggered(
        cumulative_pnl_gbp,
        scenario.risk_control.stop_shadow_run_loss_gbp,
    ):
        warnings.append("SHADOW_RUN_STOP_LOSS_TRIGGERED")

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
        paper_pnl_gbp=paper_pnl_gbp,
        cumulative_pnl_gbp=cumulative_pnl_gbp,
        hit=hit,
        research_only=True,
        human_review_required=True,
    )


def _component_score(
    component: StrategyComponent,
    day_ahead_prices: Sequence[float],
    intraday_prices: Sequence[float],
) -> float:
    """Score one component from its day-ahead vs intraday spread.

    组件打分：价差超过正向阈值得正分（上限 +1），低于负向阈值得负分
    （下限 -1），在阈值内得 0。
    """

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
    """Derive paper allocation targets with risk-control clamps.

    纸面分配推导：OCM/日前按评分拆分（ocm_day_split），再施加单一市场
    量上限与最小预期边际过滤。
    """

    total_quantity = sum(
        resource.available_quantity_mwh_per_day
        for resource in scenario.resource_contexts
    )
    if total_quantity <= 0:
        return []
    average_cost = _weighted_resource_cost(scenario.resource_contexts)
    if intraday_average is None or day_average is None or average_cost is None:
        return []

    ocm_pct, day_pct = ocm_day_split(
        weighted_score,
        scenario.risk_control.max_ocm_allocation_pct,
        scenario.risk_control.min_day_ahead_allocation_pct,
    )
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
    """Build one allocation target (quantity = pct × portfolio volume)."""

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
    """Volume-weighted average resource cost incl. balancing allowance.

    按可用量加权的资源平均成本（含平衡补贴）；总可用量为 0 时无法计算。
    """

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
    """Filter observations to the configured local time window.

    时间窗过滤：窗口跨午夜（start > end）时按"≥start 或 ≤end"处理。
    """

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
    """Parse ``HH:MM`` into a time."""

    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _time_in_window(value: time, start: time, end: time) -> bool:
    """Whether a time falls in [start, end], handling overnight windows."""

    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


def _average(values: Sequence[float]) -> float | None:
    """Round(4) average, or None for an empty sequence."""

    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _source_refs(observations: Sequence[StrategyPriceObservation]) -> list[str]:
    """Deduplicated provenance references of the observations."""

    return _unique(
        [obs.source_reference for obs in observations if obs.source_reference]
    )


def _candidate_action(weighted_score: float, status: str) -> CandidateAction:
    """Map the run outcome to a trader-review action tag.

    状态映射：BLOCKED/PARTIAL 直接对应复核动作；否则按评分正负给出
    OCM/日前倾斜建议，零分给平衡建议。
    """

    if status == "BLOCKED":
        return CandidateAction.REVIEW_BLOCKED_STRATEGY
    if status == "PARTIAL":
        return CandidateAction.REVIEW_PARTIAL_STRATEGY
    if weighted_score > 0:
        return CandidateAction.REVIEW_HIGHER_OCM_ALLOCATION
    if weighted_score < 0:
        return CandidateAction.REVIEW_HIGHER_DAY_AHEAD_ALLOCATION
    return CandidateAction.REVIEW_BALANCED_ALLOCATION


def _unique(values: Sequence[str]) -> list[str]:
    """Deduplicate preserving first-seen order."""

    return list(dict.fromkeys(values))
