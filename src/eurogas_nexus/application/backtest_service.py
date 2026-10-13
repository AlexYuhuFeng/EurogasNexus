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
    TARGET_BACKTEST_ENGINE_VERSION,
    BacktestDecisionEvent,
    BacktestPeriod,
    BacktestResult,
    BacktestRunDefinition,
)
from eurogas_nexus.domain.backtest.engine import (
    build_backtest_manifest,
    run_target_backtest,
)
from eurogas_nexus.domain.backtest.target_selection import (
    COMPONENT_REQUIRED_PRICE_NAME_KEYS,
    component_declaration_gaps,
    required_price_names,
    selection_rules_block,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    StrategyComponentSpec,
    StrategyVersionDefinition,
)
from eurogas_nexus.domain.strategy_lab.run_orchestration import (
    _application_version,
    _engine_version,
    _git_commit_sha,
)

TARGET_DELIVERY_NOT_DECLARED = "target_delivery_not_declared"
#: Bounded first engine/2 scope: exactly one ``OCM_VS_DAY_AHEAD`` component. The
#: engine flattens observations across components and evaluates by
#: ``price_name``, so two components reusing a name with different hubs or
#: targets could cross-pollinate. Multi-component target economics is not built
#: here; the run is refused before any evidence pool, snapshot or run row.
TARGET_COMPONENT_SCOPE_UNSUPPORTED = "target_component_scope_unsupported"
#: The single component must not list the same price name under both the
#: day-ahead and intraday role groups: the evaluation keys evidence by
#: ``price_name`` only and cannot represent one name as two leg roles.
TARGET_EVIDENCE_MAPPING_AMBIGUOUS = "target_evidence_mapping_ambiguous"


class BacktestTemporalTargetError(ValueError):
    """Structured, stable-code refusal of a historical BACKTEST run.

    A historical run is refused when the frozen definition does not declare a
    complete per-leg evidence target mapping. The refusal never falls back to
    the legacy engine/1 selection and never claims engine/2: the operator forks
    the version and declares the target, then freezes and reruns.
    """

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _raise_target_delivery_not_declared(detail: str) -> None:
    raise BacktestTemporalTargetError(
        TARGET_DELIVERY_NOT_DECLARED,
        "this frozen strategy version declares no complete per-leg evidence "
        "target for historical selection, and a target is never inferred from "
        "a series name or product label. Fork the version, declare the target "
        f"delivery interval for each leg, freeze it, and run again. {detail}",
    )


def _raise_component_scope_unsupported(component_count: int) -> None:
    raise BacktestTemporalTargetError(
        TARGET_COMPONENT_SCOPE_UNSUPPORTED,
        "this first target-aware backtest engine supports exactly one "
        "OCM_VS_DAY_AHEAD component; the frozen version declares "
        f"{component_count}. Multi-component target economics is not "
        "implemented, so the run is refused before any evidence pool, "
        "snapshot or run row is written.",
    )


def _raise_evidence_mapping_ambiguous(
    component_id: str, price_name: str, first_key: str, second_key: str
) -> None:
    raise BacktestTemporalTargetError(
        TARGET_EVIDENCE_MAPPING_AMBIGUOUS,
        f"component {component_id} lists price name {price_name} under both "
        f"{first_key} and {second_key}; the evaluation keys evidence by "
        "price_name only and cannot represent the same name as two different "
        "leg roles. Resolve the mapping before running.",
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
    # Refuse a window that has not happened yet before any snapshot or run row is
    # written. The pure domain engine still carries no wall clock: the boundary is
    # the application's request instant, which callers and tests can inject.
    _require_historical_period(definition.period, requested_at)
    # CR-04: a historical backtest needs a complete frozen per-leg target
    # mapping. This refuses an undeclared frozen version before any evidence
    # pool load, snapshot or run row; a complete mapping runs engine/2.
    target_definition = _require_declared_evidence_targets(version)
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
    result = run_target_backtest(
        version=version,
        pool=pool,
        definition=definition,
        run_id=resolved_run_id,
        requested_by=requested_by,
        target_definition=target_definition,
    )
    manifest = build_backtest_manifest(
        version=version,
        definition=definition,
        pool=pool,
        run_id=resolved_run_id,
        snapshot_id=snapshot_id,
        requested_by=requested_by,
        engine_version=TARGET_BACKTEST_ENGINE_VERSION,
        application_version=_application_version(),
        git_commit_sha=_git_commit_sha(),
        evidence_selection=selection_rules_block(
            definition=target_definition,
            assumptions=definition.economic_assumptions,
        ),
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
        engine_version=TARGET_BACKTEST_ENGINE_VERSION,
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
    engine_version: str,
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
        backtest_engine_version=engine_version,
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
                attribution=_event_attribution_json(event),
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


def _event_attribution_json(event: BacktestDecisionEvent) -> list[dict]:
    """Persist the evidence-selection trace inside the existing event JSON.

    CR-04 provenance is stored under a clearly named ``evidence_selection``
    entry in the event's existing ``attribution`` JSON column: no migration, no
    fake cost rows, and the financial attribution rows are untouched. Readers
    split it back out in ``backtest_repository``.
    """

    rows = list(event.attribution)
    if event.evidence_selection_trace:
        rows.append(
            {
                "dimension": "evidence_selection",
                "trace": list(event.evidence_selection_trace),
            }
        )
    return rows


def _require_historical_period(period: BacktestPeriod, requested_at: datetime) -> None:
    """Refuse an evaluation window that extends past the request instant.

    A professional backtest reconstructs what a frozen strategy would have done
    over a historical period using only information available at each decision
    time (BACKTEST_ENGINE_SPEC section 1). A window ending after the request is
    not historical, and the evidence pool cannot contain a future the sources
    have not published: the run would replay the newest available rows across a
    period that never happened and present it as that period's result.

    Equality is allowed, so a request may cover the instant it is made. This is
    an application-boundary rule only; the deterministic domain engine takes no
    wall clock of its own.
    """

    period_end = _as_utc(period.end_utc)
    if period_end > requested_at:
        raise ValueError(
            f"backtest period end {period_end.isoformat()} is after the request "
            f"time {requested_at.isoformat()}; a historical backtest cannot "
            "evaluate a period that has not yet occurred"
        )


def _require_declared_evidence_targets(version: StrategyVersionRecord) -> None:
    """Validate and return the frozen target mapping for a historical run.

    CR-04 requires historical evidence selection to resolve an explicit
    per-leg delivery target instead of reusing whichever quotes carry the
    right product name. The frozen definition - never a request override - is
    the only source of that declaration.

    The refusals here are ``target_delivery_not_declared`` (the definition does
    not declare a complete target for every required price name, so no target
    could be resolved), ``target_component_scope_unsupported`` (this bounded
    first engine/2 supports exactly one OCM_VS_DAY_AHEAD component) and
    ``target_evidence_mapping_ambiguous`` (one price name is declared in two leg
    roles the price-name-keyed evaluation cannot separate). A complete mapping
    is returned so the caller can run engine/2 against it. This function only
    reads; it runs before the evidence pool, the snapshot and the run row, so a
    refusal writes nothing.
    """

    raw_definition = version.definition_json or {}
    components = raw_definition.get("components")
    if not isinstance(components, list) or not components:
        _raise_target_delivery_not_declared(
            f"strategy version {version.strategy_version_id} has no readable components."
        )

    try:
        parsed = StrategyVersionDefinition.model_validate(raw_definition)
    except Exception as exc:
        # Any unreadable definition fails closed: a declaration that cannot be
        # parsed is not evidence that no target is needed.
        _raise_target_delivery_not_declared(
            f"strategy version {version.strategy_version_id} has no readable "
            f"evidence-target declaration ({type(exc).__name__})."
        )

    # Bounded first engine/2 scope: the engine flattens every component's
    # observations and evaluates by price_name, so more than one component could
    # let two different hubs/targets cross-pollinate. Refuse rather than claim a
    # per-component engine that is not built.
    if len(parsed.components) != 1:
        _raise_component_scope_unsupported(len(parsed.components))

    component = parsed.components[0]
    _require_component_targets(component)
    _require_unambiguous_leg_names(component)
    return parsed


def _require_component_targets(component: StrategyComponentSpec) -> None:
    """Refuse the whole run unless one component's targets are complete."""

    if COMPONENT_REQUIRED_PRICE_NAME_KEYS.get(component.component_type) is None:
        _raise_target_delivery_not_declared(
            f"component {component.component_id} has type "
            f"{component.component_type}, whose required price names are not "
            "mapped to an evidence target."
        )
    required_names = required_price_names(component)
    if not required_names:
        _raise_target_delivery_not_declared(
            f"component {component.component_id} declares no price names, so its "
            "evidence targets cannot be mapped."
        )
    if not (component.evidence_targets or []):
        _raise_target_delivery_not_declared(
            f"component {component.component_id} declares no evidence targets."
        )

    missing = component_declaration_gaps(component)
    if missing:
        _raise_target_delivery_not_declared(
            f"component {component.component_id} declares no evidence target for: "
            + ", ".join(missing)
        )


def _require_unambiguous_leg_names(component: StrategyComponentSpec) -> None:
    """Refuse a component that lists one price name in two leg role groups.

    The engine keys evidence by ``price_name``; if the same name appears as both
    the day-ahead and the intraday name, one row would be readable as either
    role and the evaluation cannot represent that. This is checked against the
    frozen declaration, not the request, before any evidence is loaded.
    """

    keys = COMPONENT_REQUIRED_PRICE_NAME_KEYS.get(component.component_type) or ()
    extension = component.extension_json or {}
    first_key_by_name: dict[str, str] = {}
    for key in keys:
        value = extension.get(key)
        if not isinstance(value, list):
            continue
        for name in value:
            if not isinstance(name, str) or not name.strip():
                continue
            normalized = name.strip().upper()
            previous = first_key_by_name.get(normalized)
            if previous is not None and previous != key:
                _raise_evidence_mapping_ambiguous(
                    component.component_id, normalized, previous, key
                )
            first_key_by_name[normalized] = key


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
