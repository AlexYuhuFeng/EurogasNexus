"""Application service for professional backtest execution and persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    BacktestAttributionRecord,
    BacktestDecisionEventRecord,
    BacktestSeriesRecord,
    StrategyRunRecord,
    StrategyVersionRecord,
)
from eurogas_nexus.db.repositories import backtest as backtest_repository
from eurogas_nexus.domain.backtest.contracts import (
    BACKTEST_ENGINE_VERSION,
    BacktestResult,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.backtest.engine import (
    build_backtest_manifest,
    run_backtest,
)
from eurogas_nexus.domain.strategy_lab.run_orchestration import (
    _application_version,
    _engine_version,
    _git_commit_sha,
)


def execute_backtest_run(
    session: Session,
    *,
    version: StrategyVersionRecord,
    definition: BacktestRunDefinition,
    requested_by: str,
    run_id: str | None = None,
    requested_at_utc: datetime | None = None,
) -> StrategyRunRecord:
    """Load as-of evidence, evaluate, and persist one immutable backtest run."""

    if version.status != "FROZEN":
        raise ValueError(
            f"Backtest requires FROZEN strategy version; "
            f"{version.strategy_version_id} is {version.status}"
        )
    if definition.experiment_id:
        experiment = backtest_repository.get_experiment(session, definition.experiment_id)
        if experiment is None:
            raise ValueError(f"Unknown experiment: {definition.experiment_id}")
        if experiment.strategy_id != version.strategy_id:
            raise ValueError("Experiment strategy does not match the requested strategy version")

    requested_at = _as_utc(requested_at_utc or datetime.now(UTC))
    resolved_run_id = run_id or f"strategy-run-{uuid4().hex[:24]}"
    pool = backtest_repository.load_backtest_evidence_pool(
        session,
        version=version,
        period=definition.period,
        max_lookback_seconds=definition.economic_assumptions.carry_forward_max_age_seconds,
    )
    snapshot_id = backtest_repository.create_backtest_snapshot(
        session,
        pool=pool,
        period=definition.period,
        now_utc=requested_at,
    )
    result = run_backtest(
        version=version,
        pool=pool,
        definition=definition,
        run_id=resolved_run_id,
        requested_by=requested_by,
    )
    manifest = build_backtest_manifest(
        version=version,
        definition=definition,
        pool=pool,
        run_id=resolved_run_id,
        snapshot_id=snapshot_id,
        requested_by=requested_by,
        engine_version=BACKTEST_ENGINE_VERSION,
        application_version=_application_version(),
        git_commit_sha=_git_commit_sha(),
    )
    run = _persist_run_row(
        session,
        run_id=resolved_run_id,
        version=version,
        definition=definition,
        result=result,
        manifest=manifest,
        snapshot_id=snapshot_id,
        requested_at_utc=requested_at,
        requested_by=requested_by,
    )
    _persist_events_series_attribution(session, run_id=resolved_run_id, result=result)
    if definition.experiment_id:
        backtest_repository.append_run_to_experiment(
            session,
            experiment_id=definition.experiment_id,
            run_id=resolved_run_id,
            now_utc=requested_at,
        )
    session.flush()
    return run


def _persist_run_row(
    session: Session,
    *,
    run_id: str,
    version: StrategyVersionRecord,
    definition: BacktestRunDefinition,
    result: BacktestResult,
    manifest,
    snapshot_id: str,
    requested_at_utc: datetime,
    requested_by: str,
) -> StrategyRunRecord:
    metrics = result.metrics.model_dump(mode="json")
    result_snapshot = {
        "run_type": "BACKTEST",
        "strategy_name": (version.definition_json or {}).get("strategy_name")
        or version.strategy_id,
        "status": result.status,
        "temporal_integrity": result.temporal_integrity.value,
        "metrics": metrics,
        "event_count": len(result.events),
        "paper_pnl_gbp": metrics.get("net_indicative_pnl_gbp", 0.0),
        "cumulative_pnl_gbp": metrics.get("net_indicative_pnl_gbp", 0.0),
        "gross_indicative_pnl_gbp": metrics.get("gross_indicative_pnl_gbp", 0.0),
        "modeled_costs_gbp": metrics.get("modeled_costs_gbp", 0.0),
        "net_indicative_pnl_gbp": metrics.get("net_indicative_pnl_gbp", 0.0),
        "hit": bool((metrics.get("net_indicative_pnl_gbp") or 0.0) > 0),
    }
    run = StrategyRunRecord(
        run_id=run_id,
        strategy_id=version.strategy_id,
        strategy_version_id=version.strategy_version_id,
        run_type="BACKTEST",
        run_mode="BACKTEST",
        status=result.status,
        requested_at_utc=requested_at_utc,
        started_at_utc=requested_at_utc,
        completed_at_utc=requested_at_utc,
        finished_at_utc=requested_at_utc,
        evaluation_start_utc=definition.period.start_utc,
        evaluation_end_utc=definition.period.end_utc,
        data_cutoff_utc=definition.period.end_utc,
        dataset_snapshot_id=snapshot_id,
        manifest_json=manifest.model_dump(mode="json"),
        manifest_hash=manifest.content_hash(),
        engine_version=_engine_version(),
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        experiment_id=definition.experiment_id,
        application_version=_application_version(),
        git_commit_sha=_git_commit_sha(),
        strategy_schema_version=manifest.strategy_schema_version,
        run_schema_version=manifest.schema_version,
        deterministic_seed=definition.deterministic_seed or run_id,
        requested_by=requested_by,
        trigger_type="MANUAL",
        correlation_request_id=run_id,
        input_snapshot={
            "definition": definition.model_dump(mode="json"),
            "strategy_version_id": version.strategy_version_id,
            "strategy_version_content_hash": version.content_hash,
        },
        result_snapshot=result_snapshot,
        source_refs=result.source_refs,
        warnings=result.warnings,
        missing_inputs=result.missing_inputs,
        research_only=True,
        human_review_required=True,
    )
    session.add(run)
    session.flush()
    return run


def _persist_events_series_attribution(
    session: Session,
    *,
    run_id: str,
    result: BacktestResult,
) -> None:
    for event in result.events:
        session.add(
            BacktestDecisionEventRecord(
                event_id=event.event_id,
                run_id=run_id,
                experiment_id=event.experiment_id,
                decision_sequence=event.decision_sequence,
                decision_time_utc=event.decision_time_utc,
                gas_day=event.gas_day,
                gas_day_start_utc=event.gas_day_start_utc,
                gas_day_end_utc=event.gas_day_end_utc,
                outcome=event.outcome,
                candidate_action_for_review=event.candidate_action_for_review,
                weighted_score=event.weighted_score,
                day_ahead_average_gbp_mwh=event.day_ahead_average_gbp_mwh,
                intraday_average_gbp_mwh=event.intraday_average_gbp_mwh,
                intraday_vs_day_ahead_spread_gbp_mwh=(event.intraday_vs_day_ahead_spread_gbp_mwh),
                allocation_targets=event.allocation_targets,
                gross_indicative_pnl_gbp=event.gross_indicative_pnl_gbp,
                modeled_costs_gbp=event.modeled_costs_gbp,
                net_indicative_pnl_gbp=event.net_indicative_pnl_gbp,
                cumulative_net_indicative_pnl_gbp=(event.cumulative_net_indicative_pnl_gbp),
                ending_exposure_mwh_per_day=event.ending_exposure_mwh_per_day,
                missing_inputs=event.missing_inputs,
                warnings=event.warnings,
                price_evidence_refs=event.price_evidence_refs,
                fx_evidence_refs=event.fx_evidence_refs,
                cost_evidence_refs=event.cost_evidence_refs,
                resource_evidence_refs=event.resource_evidence_refs,
                cost_trace=event.cost_trace,
                attribution=event.attribution,
                research_only=True,
                human_review_required=True,
            )
        )
    for point in result.series:
        session.add(
            BacktestSeriesRecord(
                series_point_id=(f"bt-series-{run_id[-24:]}-{point.decision_sequence:06d}"),
                run_id=run_id,
                decision_sequence=point.decision_sequence,
                decision_time_utc=point.decision_time_utc,
                gas_day=point.gas_day,
                gross_indicative_pnl_gbp=point.gross_indicative_pnl_gbp,
                modeled_costs_gbp=point.modeled_costs_gbp,
                net_indicative_pnl_gbp=point.net_indicative_pnl_gbp,
                cumulative_net_indicative_pnl_gbp=(point.cumulative_net_indicative_pnl_gbp),
                ending_exposure_mwh_per_day=point.ending_exposure_mwh_per_day,
                research_only=True,
            )
        )
    # Flush decision events before attribution rows: PostgreSQL enforces the
    # backtest_attribution -> backtest_decision_events foreign key, and the
    # mapper graph has no relationship dependency to order these inserts.
    session.flush()
    for index, row in enumerate(result.attribution):
        session.add(
            BacktestAttributionRecord(
                attribution_id=f"bt-att-{run_id[-24:]}-{index:06d}",
                run_id=run_id,
                event_id=row["event_id"],
                decision_time_utc=datetime.fromisoformat(
                    row["decision_time_utc"].replace("Z", "+00:00")
                ),
                dimension=row["dimension"],
                key=row["key"],
                gross_indicative_pnl_gbp=row["gross_indicative_pnl_gbp"],
                modeled_costs_gbp=row["modeled_costs_gbp"],
                net_indicative_pnl_gbp=row["net_indicative_pnl_gbp"],
                quantity_mwh_per_day=row["quantity_mwh_per_day"],
                source_refs=row["source_refs"],
                research_only=True,
            )
        )
    session.flush()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
