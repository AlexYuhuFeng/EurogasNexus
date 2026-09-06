"""Temporally safe strategy backtest engine.

The engine composes the existing strategy-lab rule evaluator with explicit
as-of evidence selection, an economic cost model, decision events, simulated
exposure state, attribution and backend-generated metrics. It never queries
the database directly and never creates execution artifacts.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, time, timedelta
from typing import Any, Protocol

from eurogas_nexus.domain.backtest.contracts import (
    BACKTEST_ENGINE_VERSION,
    BacktestDecisionEvent,
    BacktestEconomicAssumptions,
    BacktestEvidencePool,
    BacktestMetricSet,
    BacktestObservation,
    BacktestResult,
    BacktestRunDefinition,
    BacktestSeriesPoint,
)
from eurogas_nexus.domain.backtest.temporal import (
    apply_missing_data_policy,
    as_of_cost_observations,
    as_of_fx_rates,
    as_of_price_observations,
    convert_price_to_gbp_mwh,
    gas_day_window,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    BacktestOutcomeStatus,
    CostTreatment,
    MissingDataPolicy,
    StrategyRunMode,
    TemporalIntegrityStatus,
)
from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyLabResult,
    StrategyLabScenario,
    StrategyPriceObservation,
    evaluate_strategy_lab,
)
from eurogas_nexus.domain.strategy_lab.registry import StrategyRunManifest
from eurogas_nexus.domain.strategy_lab.run_orchestration import (
    evaluation_scenario_from_version,
)


class StrategyVersionLike(Protocol):
    """Structural view of a frozen StrategyVersionRecord used by the engine."""

    strategy_version_id: str
    strategy_id: str
    version_number: int
    content_hash: str
    definition_json: dict


def generate_decision_times(
    definition: BacktestRunDefinition,
) -> list[datetime]:
    """Generate explicit decision timestamps; never infer from bar size."""

    schedule = definition.schedule
    hour, minute = _parse_hh_mm(schedule.decision_time_utc)
    decision_time = time(hour=hour, minute=minute)
    timestamps: list[datetime] = []
    current_date = definition.period.start_utc.astimezone(UTC).date()
    end_date = definition.period.end_utc.astimezone(UTC).date()
    while current_date <= end_date:
        candidate = datetime.combine(current_date, decision_time, tzinfo=UTC)
        if definition.period.start_utc <= candidate < definition.period.end_utc:
            timestamps.append(candidate)
        current_date += timedelta(days=1)
    return timestamps


def run_backtest(
    *,
    version: StrategyVersionLike,
    pool: BacktestEvidencePool,
    definition: BacktestRunDefinition,
    run_id: str,
    requested_by: str,
) -> BacktestResult:
    """Execute one full backtest and return the semantic result."""

    decision_times = generate_decision_times(definition)
    events: list[BacktestDecisionEvent] = []
    cumulative_net = 0.0
    exposure = 0.0
    run_missing: list[str] = []
    run_warnings: list[str] = []

    for sequence, decision_time in enumerate(decision_times, start=1):
        event = _evaluate_decision_event(
            version=version,
            pool=pool,
            definition=definition,
            run_id=run_id,
            requested_by=requested_by,
            decision_sequence=sequence,
            decision_time_utc=decision_time,
            previous_cumulative_net=cumulative_net,
            previous_exposure=exposure,
        )
        if event.outcome in {
            BacktestOutcomeStatus.COMPLETED.value,
            BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS.value,
        }:
            cumulative_net = event.cumulative_net_indicative_pnl_gbp
            exposure = event.ending_exposure_mwh_per_day
        elif event.outcome == BacktestOutcomeStatus.BLOCKED.value:
            exposure = 0.0
        # SKIPPED carries previous exposure and cumulative state.
        events.append(event)
        run_missing.extend(event.missing_inputs)
        run_warnings.extend(event.warnings)

    series = [
        BacktestSeriesPoint(
            run_id=run_id,
            decision_sequence=event.decision_sequence,
            decision_time_utc=event.decision_time_utc,
            gas_day=event.gas_day,
            gross_indicative_pnl_gbp=event.gross_indicative_pnl_gbp,
            modeled_costs_gbp=event.modeled_costs_gbp,
            net_indicative_pnl_gbp=event.net_indicative_pnl_gbp,
            cumulative_net_indicative_pnl_gbp=event.cumulative_net_indicative_pnl_gbp,
            ending_exposure_mwh_per_day=event.ending_exposure_mwh_per_day,
        )
        for event in events
    ]
    _populate_series_drawdown(series)
    metrics = aggregate_metrics(events)
    temporal_integrity = _pool_temporal_integrity(pool)
    metrics.temporal_integrity = temporal_integrity.value
    status = _run_status(events)
    attribution = [row for event in events for row in event.attribution]

    return BacktestResult(
        run_id=run_id,
        strategy_id=version.strategy_id,
        strategy_version_id=version.strategy_version_id,
        experiment_id=definition.experiment_id,
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        temporal_integrity=temporal_integrity,
        status=status,
        events=events,
        series=series,
        metrics=metrics,
        attribution=attribution,
        missing_inputs=_unique(run_missing),
        warnings=_unique(run_warnings),
        source_refs=_unique(
            [*pool.observation_refs(), *pool.fx_refs(), *pool.cost_refs()]
        ),
        research_only=True,
        human_review_required=True,
    )


def evaluate_decision_event(
    *,
    version: StrategyVersionLike,
    pool: BacktestEvidencePool,
    definition: BacktestRunDefinition,
    run_id: str,
    requested_by: str,
    decision_sequence: int,
    decision_time_utc: datetime,
    previous_cumulative_net: float,
    previous_exposure: float,
) -> BacktestDecisionEvent:
    """Evaluate one decision with the exact shared shadow/backtest engine."""

    return _evaluate_decision_event(
        version=version,
        pool=pool,
        definition=definition,
        run_id=run_id,
        requested_by=requested_by,
        decision_sequence=decision_sequence,
        decision_time_utc=decision_time_utc,
        previous_cumulative_net=previous_cumulative_net,
        previous_exposure=previous_exposure,
    )


def _evaluate_decision_event(
    *,
    version: StrategyVersionLike,
    pool: BacktestEvidencePool,
    definition: BacktestRunDefinition,
    run_id: str,
    requested_by: str,
    decision_sequence: int,
    decision_time_utc: datetime,
    previous_cumulative_net: float,
    previous_exposure: float,
) -> BacktestDecisionEvent:
    """Evaluate one decision event with as-of evidence and explicit economics."""

    assumptions = definition.economic_assumptions
    gas_day, gas_day_start, gas_day_end = gas_day_window(
        decision_time_utc,
        calendar=definition.schedule.gas_day_calendar,
    )
    missing: list[str] = []
    warnings: list[str] = []
    price_refs: list[str] = []
    fx_refs: list[str] = []
    cost_refs: list[str] = []
    resource_refs = list(pool.resource_refs())

    base_scenario = evaluation_scenario_from_version(version)
    raw_components = (version.definition_json or {}).get("components", [])
    selected_rows: list[BacktestObservation] = []
    for index, component in enumerate(base_scenario.components):
        raw = dict(raw_components[index]) if index < len(raw_components) else {}
        hubs = {str(item).upper() for item in raw.get("hubs") or []}
        tenors = {str(item).lower() for item in raw.get("tenors") or []}
        day_names = {name.upper() for name in component.day_ahead_price_names}
        intraday_names = {name.upper() for name in component.intraday_price_names}
        required = day_names | intraday_names
        eligible = as_of_price_observations(
            pool,
            decision_time_utc,
            required_price_names=required,
            hubs=hubs or None,
            tenors=tenors or None,
            bar_minutes=component.target_bar_minutes,
            fill_price_policy=assumptions.fill_price_policy,
        )
        all_eligible = (
            as_of_price_observations(
                pool,
                decision_time_utc,
                hubs=hubs or None,
                tenors=tenors or None,
                bar_minutes=component.target_bar_minutes,
                fill_price_policy=assumptions.fill_price_policy,
            )
            if assumptions.missing_data_policy
            == MissingDataPolicy.USE_APPROVED_FALLBACK_SOURCE
            else None
        )
        day_selected, day_warnings, day_blockers = apply_missing_data_policy(
            eligible,
            series_names=day_names,
            decision_time_utc=decision_time_utc,
            assumptions=assumptions,
            fallback_rows=all_eligible,
        )
        intraday_selected, intraday_warnings, intraday_blockers = (
            apply_missing_data_policy(
                eligible,
                series_names=intraday_names,
                decision_time_utc=decision_time_utc,
                assumptions=assumptions,
                fallback_rows=all_eligible,
            )
        )
        selected_rows.extend(day_selected)
        selected_rows.extend(intraday_selected)
        warnings.extend(day_warnings)
        warnings.extend(intraday_warnings)
        missing.extend(day_blockers)
        missing.extend(intraday_blockers)

    selected_rows, duplicate_warnings = _dedupe_conflicting_observations(
        selected_rows
    )
    warnings.extend(duplicate_warnings)
    warnings.extend(
        "SOURCE_ENTITLEMENT_SIMULATED"
        for row in selected_rows
        if row.simulated
    )

    fx_eligible = as_of_fx_rates(pool, decision_time_utc)
    fx_refs = [row.source_reference for row in fx_eligible if row.source_reference]

    price_observations: list[StrategyPriceObservation] = []
    for row in _dedupe_observations(selected_rows):
        price_gbp_mwh, fx_warnings, fx_blockers = convert_price_to_gbp_mwh(
            price=row.price,
            currency=row.currency,
            unit=row.unit,
            fx_rates=fx_eligible,
        )
        if fx_blockers:
            missing.extend(fx_blockers)
            continue
        warnings.extend(fx_warnings)
        price_refs.append(row.source_reference)
        price_observations.append(
            StrategyPriceObservation(
                observation_id=row.observation_id,
                source_system=row.source_system,
                venue=row.venue,
                hub=row.hub,
                product=row.product,
                price_name=row.price_name,
                price_gbp_mwh=price_gbp_mwh,
                observed_at_utc=row.observed_at_utc,
                delivery_start_utc=row.delivery_start_utc
                or decision_time_utc,
                delivery_end_utc=row.delivery_end_utc
                or decision_time_utc + timedelta(hours=24),
                bar_minutes=row.bar_minutes,
                price_type=row.price_type,
                source_reference=row.source_reference,
            )
        )

    scenario = StrategyLabScenario(
        strategy_id=version.strategy_id,
        strategy_name=(version.definition_json or {}).get("strategy_name")
        or version.strategy_id,
        run_mode=StrategyRunMode.BACKTEST,
        resource_contexts=base_scenario.resource_contexts,
        price_observations=price_observations,
        components=base_scenario.components,
        risk_control=base_scenario.risk_control,
        existing_shadow_pnl_gbp=previous_cumulative_net,
        research_only=True,
    )
    evaluation = evaluate_strategy_lab(scenario)
    missing.extend(evaluation.missing_inputs)
    warnings.extend(evaluation.warnings)

    if _skip_requested(missing):
        return _event(
            run_id=run_id,
            requested_by=requested_by,
            decision_sequence=decision_sequence,
            decision_time_utc=decision_time_utc,
            gas_day=gas_day,
            gas_day_start=gas_day_start,
            gas_day_end=gas_day_end,
            outcome=BacktestOutcomeStatus.SKIPPED,
            evaluation=evaluation,
            previous_cumulative_net=previous_cumulative_net,
            previous_exposure=previous_exposure,
            missing_inputs=missing,
            warnings=warnings,
            price_refs=price_refs,
            fx_refs=fx_refs,
            cost_refs=cost_refs,
            resource_refs=resource_refs,
            cost_trace=[],
            attribution=[],
            definition=definition,
        )

    cost_trace, modeled_costs, cost_blockers = _modeled_costs(
        evaluation=evaluation,
        assumptions=assumptions,
        fx_eligible=fx_eligible,
    )
    warnings.extend(
        str(item.get("warning"))
        for item in cost_trace
        if item.get("warning")
    )
    if cost_blockers:
        missing.extend(cost_blockers)
    cost_refs = _cost_refs(cost_trace, as_of_cost_observations(pool, decision_time_utc))

    if missing or not evaluation.allocation_targets:
        outcome = BacktestOutcomeStatus.BLOCKED
        gross = 0.0
        modeled = 0.0
        net = 0.0
        cumulative = previous_cumulative_net
        exposure = 0.0
        targets: list[dict[str, Any]] = []
    else:
        outcome = (
            BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS
            if warnings
            else BacktestOutcomeStatus.COMPLETED
        )
        gross = _round4(evaluation.paper_pnl_gbp)
        modeled = _round4(modeled_costs)
        net = _round4(gross - modeled)
        cumulative = _round4(previous_cumulative_net + net)
        exposure = _round4(
            sum(
                target.target_quantity_mwh_per_day
                for target in evaluation.allocation_targets
            )
        )
        targets = [target.model_dump(mode="json") for target in evaluation.allocation_targets]

    attribution = _attribution_rows(
        run_id=run_id,
        event_id=_event_id(run_id, decision_sequence),
        decision_time_utc=decision_time_utc,
        evaluation=evaluation,
        targets=targets,
        cost_trace=cost_trace,
        outcome=outcome.value,
    )
    return _event(
        run_id=run_id,
        requested_by=requested_by,
        decision_sequence=decision_sequence,
        decision_time_utc=decision_time_utc,
        gas_day=gas_day,
        gas_day_start=gas_day_start,
        gas_day_end=gas_day_end,
        outcome=outcome,
        evaluation=evaluation,
        previous_cumulative_net=cumulative,
        previous_exposure=exposure,
        missing_inputs=missing,
        warnings=warnings,
        price_refs=price_refs,
        fx_refs=fx_refs,
        cost_refs=cost_refs,
        resource_refs=resource_refs,
        cost_trace=cost_trace,
        attribution=attribution,
        definition=definition,
        override_targets=targets,
        gross=gross,
        modeled=modeled,
        net=net,
    )


def _event(
    *,
    run_id: str,
    requested_by: str,
    decision_sequence: int,
    decision_time_utc: datetime,
    gas_day: str,
    gas_day_start: datetime,
    gas_day_end: datetime,
    outcome: BacktestOutcomeStatus,
    evaluation: StrategyLabResult,
    previous_cumulative_net: float,
    previous_exposure: float,
    missing_inputs: list[str],
    warnings: list[str],
    price_refs: list[str],
    fx_refs: list[str],
    cost_refs: list[str],
    resource_refs: list[str],
    cost_trace: list[dict[str, Any]],
    attribution: list[dict[str, Any]],
    definition: BacktestRunDefinition,
    override_targets: list[dict[str, Any]] | None = None,
    gross: float = 0.0,
    modeled: float = 0.0,
    net: float = 0.0,
) -> BacktestDecisionEvent:
    """Assemble the structured decision event."""

    targets = (
        override_targets
        if override_targets is not None
        else [target.model_dump(mode="json") for target in evaluation.allocation_targets]
    )
    if outcome in {
        BacktestOutcomeStatus.COMPLETED,
        BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS,
    }:
        cumulative = previous_cumulative_net
        exposure = previous_exposure
        event_gross = gross
        event_modeled = modeled
        event_net = net
    else:
        cumulative = previous_cumulative_net
        exposure = (
            previous_exposure
            if outcome == BacktestOutcomeStatus.SKIPPED
            else 0.0
        )
        event_gross = 0.0
        event_modeled = 0.0
        event_net = 0.0
    return BacktestDecisionEvent(
        event_id=_event_id(run_id, decision_sequence),
        run_id=run_id,
        experiment_id=definition.experiment_id,
        decision_sequence=decision_sequence,
        decision_time_utc=decision_time_utc,
        gas_day=gas_day,
        gas_day_start_utc=gas_day_start,
        gas_day_end_utc=gas_day_end,
        outcome=outcome.value,
        candidate_action_for_review=(
            evaluation.candidate_action_for_review
            if outcome
            in {
                BacktestOutcomeStatus.COMPLETED,
                BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS,
            }
            else None
        ),
        weighted_score=evaluation.weighted_score,
        day_ahead_average_gbp_mwh=evaluation.day_ahead_average_gbp_mwh,
        intraday_average_gbp_mwh=evaluation.intraday_average_gbp_mwh,
        intraday_vs_day_ahead_spread_gbp_mwh=evaluation.intraday_vs_day_ahead_spread_gbp_mwh,
        allocation_targets=targets,
        gross_indicative_pnl_gbp=event_gross,
        modeled_costs_gbp=event_modeled,
        net_indicative_pnl_gbp=event_net,
        cumulative_net_indicative_pnl_gbp=cumulative,
        ending_exposure_mwh_per_day=exposure,
        missing_inputs=_unique(missing_inputs),
        warnings=_unique(warnings),
        price_evidence_refs=_unique(price_refs),
        fx_evidence_refs=_unique(fx_refs),
        cost_evidence_refs=_unique(cost_refs),
        resource_evidence_refs=_unique(resource_refs),
        cost_trace=cost_trace,
        attribution=attribution,
        research_only=True,
        human_review_required=True,
    )


def _modeled_costs(
    *,
    evaluation: StrategyLabResult,
    assumptions: BacktestEconomicAssumptions,
    fx_eligible: list[Any],
) -> tuple[list[dict[str, Any]], float, list[str]]:
    """Apply the explicit cost contract and return a source-attributed trace."""

    total_quantity = _round4(
        sum(
            target.target_quantity_mwh_per_day
            for target in evaluation.allocation_targets
        )
    )
    trace: list[dict[str, Any]] = []
    modeled = 0.0
    blockers: list[str] = []
    for component in assumptions.cost_components:
        amount_gbp_mwh = component.amount_gbp_mwh
        if component.treatment in {
            CostTreatment.KNOWN_COST,
            CostTreatment.MODELED_COST,
        }:
            assert amount_gbp_mwh is not None
            amount_gbp_mwh = _round4(amount_gbp_mwh)
            if component.currency.upper() != "GBP":
                from eurogas_nexus.domain.backtest.temporal import convert_price_to_gbp_mwh

                converted, _warnings, conversion_blockers = convert_price_to_gbp_mwh(
                    price=amount_gbp_mwh,
                    currency=component.currency,
                    unit="GBP/MWh",
                    fx_rates=fx_eligible,
                )
                if conversion_blockers:
                    blockers.extend(conversion_blockers)
                    trace.append(
                        {
                            "code": component.code,
                            "treatment": component.treatment.value,
                            "amount_gbp_mwh": None,
                            "total_gbp": None,
                            "source_refs": component.source_refs,
                            "warning": f"COST_FX_MISSING:{component.code}",
                        }
                    )
                    continue
                amount_gbp_mwh = converted
            total = _round4(amount_gbp_mwh * total_quantity)
            modeled += total
            trace.append(
                {
                    "code": component.code,
                    "treatment": component.treatment.value,
                    "amount_gbp_mwh": amount_gbp_mwh,
                    "total_gbp": total,
                    "source_refs": component.source_refs,
                    "warning": None,
                }
            )
        elif component.treatment == CostTreatment.UNAVAILABLE:
            trace.append(
                {
                    "code": component.code,
                    "treatment": component.treatment.value,
                    "amount_gbp_mwh": None,
                    "total_gbp": None,
                    "source_refs": component.source_refs,
                    "warning": f"COST_UNAVAILABLE:{component.code}",
                }
            )
        else:
            trace.append(
                {
                    "code": component.code,
                    "treatment": component.treatment.value,
                    "amount_gbp_mwh": None,
                    "total_gbp": None,
                    "source_refs": component.source_refs,
                    "warning": None,
                }
            )
    return trace, _round4(modeled), blockers


def aggregate_metrics(events: list[BacktestDecisionEvent]) -> BacktestMetricSet:
    """Aggregate backend-owned metrics from decision events."""

    completed = [
        event
        for event in events
        if event.outcome
        in {
            BacktestOutcomeStatus.COMPLETED.value,
            BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS.value,
        }
    ]
    blocked = [event for event in events if event.outcome == BacktestOutcomeStatus.BLOCKED.value]
    skipped = [event for event in events if event.outcome == BacktestOutcomeStatus.SKIPPED.value]
    total = len(events)
    gross = _round4(sum(event.gross_indicative_pnl_gbp for event in completed))
    modeled = _round4(sum(event.modeled_costs_gbp for event in completed))
    net = _round4(sum(event.net_indicative_pnl_gbp for event in completed))
    drawdown = _drawdown(events)
    candidate_net = [event.net_indicative_pnl_gbp for event in completed]
    volatility = (
        _round4(statistics.stdev(candidate_net))
        if len(candidate_net) >= 2
        else None
    )
    margins = [
        target.get("expected_margin_gbp_mwh")
        for event in completed
        for target in event.allocation_targets
        if target.get("expected_margin_gbp_mwh") is not None
    ]
    quantities = [
        target.get("target_quantity_mwh_per_day")
        for event in completed
        for target in event.allocation_targets
        if target.get("target_quantity_mwh_per_day") is not None
    ]
    average_modeled_cost = None
    if quantities and sum(float(item) for item in quantities) > 0:
        average_modeled_cost = _round4(modeled / sum(float(item) for item in quantities))
    warning_counts: dict[str, int] = {}
    for event in events:
        for warning in event.warnings:
            code = warning.split(":", maxsplit=1)[0]
            warning_counts[code] = warning_counts.get(code, 0) + 1

    return BacktestMetricSet(
        evaluation_count=total,
        candidate_decision_count=len(completed),
        blocked_decision_count=len(blocked),
        skipped_decision_count=len(skipped),
        data_coverage=_round4(len(completed) / total if total else 0.0),
        gross_indicative_pnl_gbp=gross,
        modeled_costs_gbp=modeled,
        net_indicative_pnl_gbp=net,
        max_drawdown_gbp=drawdown["max_drawdown_gbp"],
        peak_timestamp_utc=drawdown["peak_timestamp_utc"],
        trough_timestamp_utc=drawdown["trough_timestamp_utc"],
        recovery_timestamp_utc=drawdown["recovery_timestamp_utc"],
        pnl_volatility_gbp=volatility,
        worst_event_pnl_gbp=min(candidate_net) if candidate_net else None,
        best_event_pnl_gbp=max(candidate_net) if candidate_net else None,
        max_exposure_mwh_per_day=_round4(
            max((event.ending_exposure_mwh_per_day for event in events), default=0.0)
        ),
        average_exposure_mwh_per_day=_round4(
            sum(event.ending_exposure_mwh_per_day for event in events) / total
            if total
            else 0.0
        ),
        hit_ratio=(
            _round4(sum(1 for value in candidate_net if value > 0) / len(candidate_net))
            if candidate_net
            else None
        ),
        turnover=None,
        average_margin_gbp_mwh=(
            _round4(statistics.fmean(float(item) for item in margins))
            if margins
            else None
        ),
        average_modeled_cost_gbp_mwh=average_modeled_cost,
        sharpe_ratio=None,
        sortino_ratio=None,
        risk_metric_not_applicable_reasons=[
            "RISK_METRIC_NOT_APPLICABLE:"
            "event PnL has no defined periodic return/capital denominator"
        ],
        warning_counts=warning_counts,
        temporal_integrity="APPROXIMATE",
    )


def build_backtest_manifest(
    *,
    version: StrategyVersionLike,
    definition: BacktestRunDefinition,
    pool: BacktestEvidencePool,
    run_id: str,
    snapshot_id: str,
    requested_by: str,
    engine_version: str,
    application_version: str,
    git_commit_sha: str | None,
) -> StrategyRunManifest:
    """Build a CR-03 manifest with the complete backtest effective inputs."""

    definition_payload = version.definition_json or {}
    return StrategyRunManifest(
        run_id=run_id,
        run_type="BACKTEST",
        run_mode="BACKTEST",
        strategy_id=version.strategy_id,
        strategy_name=definition_payload.get("strategy_name") or version.strategy_id,
        strategy_version_id=version.strategy_version_id,
        version_number=version.version_number,
        strategy_version_content_hash=version.content_hash,
        strategy_definition=definition_payload,
        parameters=dict(definition_payload.get("parameter_values") or {}),
        assumptions=definition.economic_assumptions.model_dump(mode="json"),
        parameter_values=dict(definition_payload.get("parameter_values") or {}),
        economic_assumptions=definition.economic_assumptions.model_dump(mode="json"),
        evidence={
            "dataset_snapshot_id": snapshot_id,
            "period_start_utc": _iso(definition.period.start_utc),
            "period_end_utc": _iso(definition.period.end_utc),
            "decision_schedule": definition.schedule.model_dump(mode="json"),
            "price_observation_refs": pool.observation_refs(),
            "fx_observation_refs": pool.fx_refs(),
            "resource_snapshot_refs": pool.resource_refs(),
            "cost_observation_refs": pool.cost_refs(),
            "row_counts": {
                "price_observations": len(pool.observations),
                "fx_observations": len(pool.fx_rates),
                "cost_observations": len(pool.cost_observations),
                "resource_contexts": len(pool.resources),
            },
        },
        time_boundary={
            "period_start_utc": _iso(definition.period.start_utc),
            "period_end_utc": _iso(definition.period.end_utc),
            "data_cutoff_utc": _iso(definition.period.end_utc),
        },
        engine={
            "backtest_engine_version": engine_version,
            "application_version": application_version,
            "git_commit_sha": git_commit_sha,
            "deterministic_seed": definition.deterministic_seed,
        },
        evaluation_start_utc=definition.period.start_utc,
        evaluation_end_utc=definition.period.end_utc,
        data_cutoff_utc=definition.period.end_utc,
        dataset_snapshot_id=snapshot_id,
        source_refs=pool.observation_refs(),
        fx_observation_refs=pool.fx_refs(),
        resource_snapshot_refs=pool.resource_refs(),
        engine_version=engine_version,
        backtest_engine_version=engine_version,
        application_version=application_version,
        git_commit_sha=git_commit_sha,
        deterministic_seed=definition.deterministic_seed,
        requested_by=requested_by,
        trigger_type="MANUAL",
        correlation_request_id=run_id,
        research_only=True,
        human_review_required=True,
    )


def _attribution_rows(
    *,
    run_id: str,
    event_id: str,
    decision_time_utc: datetime,
    evaluation: StrategyLabResult,
    targets: list[dict[str, Any]],
    cost_trace: list[dict[str, Any]],
    outcome: str,
) -> list[dict[str, Any]]:
    """Structure market-bucket and cost attribution supported by the engine."""

    rows: list[dict[str, Any]] = []
    if outcome in {
        BacktestOutcomeStatus.COMPLETED.value,
        BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS.value,
    }:
        for target in targets:
            margin = float(target.get("expected_margin_gbp_mwh") or 0.0)
            quantity = float(target.get("target_quantity_mwh_per_day") or 0.0)
            gross = _round4(margin * quantity)
            rows.append(
                {
                    "run_id": run_id,
                    "event_id": event_id,
                    "decision_time_utc": _iso(decision_time_utc),
                    "dimension": "market_bucket",
                    "key": str(target.get("market_bucket")),
                    "gross_indicative_pnl_gbp": gross,
                    "modeled_costs_gbp": 0.0,
                    "net_indicative_pnl_gbp": gross,
                    "quantity_mwh_per_day": quantity,
                    "source_refs": [],
                }
            )
    for item in cost_trace:
        rows.append(
            {
                "run_id": run_id,
                "event_id": event_id,
                "decision_time_utc": _iso(decision_time_utc),
                "dimension": "cost_component",
                "key": str(item.get("code")),
                "gross_indicative_pnl_gbp": 0.0,
                "modeled_costs_gbp": float(item.get("total_gbp") or 0.0),
                "net_indicative_pnl_gbp": -float(item.get("total_gbp") or 0.0),
                "quantity_mwh_per_day": None,
                "source_refs": list(item.get("source_refs") or []),
            }
        )
    return rows


def _drawdown(events: list[BacktestDecisionEvent]) -> dict[str, Any]:
    """Calculate amount drawdown and its peak/trough/recovery timestamps.

    The running peak starts at zero because the simulated state has no
    injected capital. Peak/trough/recovery refer to the deepest drawdown.
    """

    peak = 0.0
    peak_time: datetime | None = None
    max_drawdown = 0.0
    max_peak_value = 0.0
    max_peak_time: datetime | None = None
    trough_time: datetime | None = None
    recovery_time: datetime | None = None
    recovered = True

    for event in events:
        cumulative = event.cumulative_net_indicative_pnl_gbp
        if cumulative > peak:
            if not recovered and cumulative >= max_peak_value:
                recovery_time = event.decision_time_utc
                recovered = True
            peak = cumulative
            peak_time = event.decision_time_utc
        elif cumulative < peak:
            drawdown = _round4(peak - cumulative)
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_peak_value = peak
                max_peak_time = peak_time
                trough_time = event.decision_time_utc
                recovered = cumulative >= max_peak_value
        else:
            if not recovered and abs(cumulative - max_peak_value) < 1e-9:
                recovery_time = event.decision_time_utc
                recovered = True

    return {
        "max_drawdown_gbp": _round4(max_drawdown),
        "peak_timestamp_utc": _iso(max_peak_time) if max_peak_time else None,
        "trough_timestamp_utc": _iso(trough_time) if trough_time else None,
        "recovery_timestamp_utc": _iso(recovery_time) if recovery_time else None,
    }


def _pool_temporal_integrity(pool: BacktestEvidencePool) -> TemporalIntegrityStatus:
    statuses = [
        row.temporal_integrity
        for row in [*pool.observations, *pool.fx_rates]
        if row.temporal_integrity is not None
    ]
    if not statuses or TemporalIntegrityStatus.INSUFFICIENT in statuses:
        return TemporalIntegrityStatus.INSUFFICIENT
    if TemporalIntegrityStatus.APPROXIMATE in statuses:
        return TemporalIntegrityStatus.APPROXIMATE
    return TemporalIntegrityStatus.VERIFIED


def _run_status(events: list[BacktestDecisionEvent]) -> str:
    if not events:
        return BacktestOutcomeStatus.BLOCKED.value
    if any(
        event.outcome
        in {
            BacktestOutcomeStatus.COMPLETED.value,
            BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS.value,
        }
        for event in events
    ):
        return (
            BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS.value
            if any(
                event.outcome == BacktestOutcomeStatus.COMPLETED_WITH_WARNINGS.value
                for event in events
            )
            or any(event.warnings for event in events)
            else BacktestOutcomeStatus.COMPLETED.value
        )
    return BacktestOutcomeStatus.BLOCKED.value


def _skip_requested(missing_inputs: list[str]) -> bool:
    return any(item.startswith("SKIP_DECISION") for item in missing_inputs)


def _event_id(run_id: str, sequence: int) -> str:
    return f"bt-{run_id[-24:]}-{sequence:06d}"


def _dedupe_observations(
    rows: list[BacktestObservation],
) -> list[BacktestObservation]:
    seen: set[str] = set()
    ordered: list[BacktestObservation] = []
    for row in rows:
        if row.observation_id in seen:
            continue
        seen.add(row.observation_id)
        ordered.append(row)
    return ordered


def _dedupe_conflicting_observations(
    rows: list[BacktestObservation],
) -> tuple[list[BacktestObservation], list[str]]:
    """Choose one deterministic row per (series, observation time).

    Duplicate rows at the same series/time with materially different prices
    would otherwise silently double-count in the evaluator; the engine keeps
    the row with the newest receipt/source-reference ordering and emits a
    machine-readable warning.
    """

    by_key: dict[tuple[str, datetime], list[BacktestObservation]] = {}
    for row in rows:
        key = (row.price_name.upper(), _as_utc(row.observed_at_utc))
        by_key.setdefault(key, []).append(row)
    selected: list[BacktestObservation] = []
    warnings: list[str] = []
    for (name, _time), candidates in by_key.items():
        distinct_prices = {round(row.price, 6) for row in candidates}
        ordered = sorted(
            candidates,
            key=lambda row: (
                _as_utc(row.received_at_utc or row.observed_at_utc),
                row.source_reference,
            ),
            reverse=True,
        )
        selected.append(ordered[0])
        if len(distinct_prices) > 1:
            warnings.append(f"DUPLICATE_CONFLICTING_OBSERVATION:{name}")
    selected.sort(key=lambda row: _as_utc(row.observed_at_utc))
    return selected, sorted(set(warnings))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _populate_series_drawdown(series: list[BacktestSeriesPoint]) -> None:
    """Set backend-owned drawdown values on the persisted series contract."""

    peak = 0.0
    for point in series:
        cumulative = point.cumulative_net_indicative_pnl_gbp
        if cumulative > peak:
            peak = cumulative
        point.drawdown_gbp = _round4(max(0.0, peak - cumulative))


def _parse_hh_mm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour), int(minute)


def _cost_refs(cost_trace: list[dict[str, Any]], cost_rows: list[Any]) -> list[str]:
    refs = [
        ref
        for item in cost_trace
        for ref in (item.get("source_refs") or [])
    ]
    refs.extend(row.source_reference for row in cost_rows if row.source_reference)
    return _unique(refs)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _round4(value: float) -> float:
    return round(value, 4)
