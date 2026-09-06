"""Professional strategy-run orchestration.

Run-level workflow for the versioned strategy registry: resolve a frozen
version into the legacy evaluation scenario, evaluate it, build a reproducible
run manifest and persist the run with full provenance. This module is
intentionally research-only: it never creates orders, trades or nominations.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus import __version__ as package_version
from eurogas_nexus.db.models import (
    StrategyAllocationTargetRecord,
    StrategyRunRecord,
    StrategyVersionRecord,
)
from eurogas_nexus.domain.ontology.vocabulary import StrategyComponentType, StrategyRunMode
from eurogas_nexus.domain.strategy_lab.evaluation import (
    StrategyComponent,
    StrategyLabResult,
    StrategyLabScenario,
    StrategyPriceObservation,
    StrategyResourceContext,
    StrategyRiskControl,
    evaluate_strategy_lab,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    RUN_SCHEMA_VERSION,
    STRATEGY_SCHEMA_VERSION,
    StrategyRunManifest,
    StrategyRunType,
)


class StrategyVersionExecutionError(ValueError):
    """A frozen version cannot be executed exactly as defined."""


def evaluation_scenario_from_version(
    version: StrategyVersionRecord,
) -> StrategyLabScenario:
    """Reconstruct the legacy evaluation scenario from an immutable version.

    Only components of the known legacy component families are executed.
    Unknown families fail closed because the current engine has no executor
    for them; a run is never recorded against a version that cannot be
    executed exactly as defined.
    """

    definition = version.definition_json or {}
    run_mode = definition.get("run_mode") or "SHADOW_RUN"
    try:
        parsed_run_mode = StrategyRunMode(str(run_mode).upper())
    except ValueError:
        parsed_run_mode = StrategyRunMode.SHADOW_RUN

    known_component_types = {item.value for item in StrategyComponentType}
    components: list[StrategyComponent] = []
    for item in definition.get("components", []):
        item = dict(item)
        extension = dict(item.get("extension_json") or {})
        raw = {**extension, **item}
        component_type = raw.get("component_type") or "OCM_VS_DAY_AHEAD"
        if component_type not in known_component_types:
            raise StrategyVersionExecutionError(
                f"Unsupported strategy component type: {component_type}"
            )
        components.append(
            StrategyComponent(
                component_id=raw.get("component_id") or raw.get("name") or "",
                component_type=StrategyComponentType(component_type),
                weight=float(raw.get("weight") or 0.0),
                day_ahead_price_names=raw.get("day_ahead_price_names")
                or ["SAP", "ICIS_HEREN_DAY_AHEAD", "EEX_DAY_AHEAD"],
                intraday_price_names=raw.get("intraday_price_names") or ["ICE_OCM"],
                positive_spread_threshold_gbp_mwh=float(
                    raw.get("positive_spread_threshold_gbp_mwh") or 0.0
                ),
                negative_spread_threshold_gbp_mwh=float(
                    raw.get("negative_spread_threshold_gbp_mwh") or 0.0
                ),
                time_window_start=raw.get("time_window_start"),
                time_window_end=raw.get("time_window_end"),
                target_bar_minutes=(
                    int(raw["target_bar_minutes"])
                    if raw.get("target_bar_minutes") is not None
                    else 5
                ),
            )
        )

    risk_control_raw = (
        definition.get("risk_controls") or definition.get("risk_control") or {}
    )
    risk_control = StrategyRiskControl(
        max_ocm_allocation_pct=float(
            risk_control_raw.get("max_ocm_allocation_pct", 80.0)
        ),
        min_day_ahead_allocation_pct=float(
            risk_control_raw.get("min_day_ahead_allocation_pct", 10.0)
        ),
        max_single_market_volume_mwh_per_day=_optional_float(
            risk_control_raw.get("max_single_market_volume_mwh_per_day")
        ),
        min_expected_margin_gbp_mwh=_optional_float(
            risk_control_raw.get("min_expected_margin_gbp_mwh")
        ),
        stop_shadow_run_loss_gbp=_optional_float(
            risk_control_raw.get("stop_shadow_run_loss_gbp")
        ),
        require_tso_access=bool(risk_control_raw.get("require_tso_access", True)),
    )

    resources = [
        StrategyResourceContext(
            resource_id=_required(raw, "resource_id"),
            resource_name=raw.get("resource_name") or _required(raw, "resource_id"),
            available_quantity_mwh_per_day=float(
                raw.get("available_quantity_mwh_per_day") or 0.0
            ),
            all_in_cost_gbp_mwh=float(raw.get("all_in_cost_gbp_mwh") or 0.0),
            delivery_tolerance_pct=_optional_float(raw.get("delivery_tolerance_pct")),
            nomination_tolerance_pct=_optional_float(
                raw.get("nomination_tolerance_pct")
            ),
            booked_entry_capacity_mwh_per_day=_optional_float(
                raw.get("booked_entry_capacity_mwh_per_day")
            ),
            balancing_allowance_gbp_mwh=float(
                raw.get("balancing_allowance_gbp_mwh") or 0.0
            ),
            required_tso_access=raw.get("required_tso_access") or [],
            company_accessible_tsos=raw.get("company_accessible_tsos"),
        )
        for raw in definition.get("resource_contexts", [])
    ]

    prices = [
        StrategyPriceObservation(
            observation_id=raw.get("observation_id") or "",
            source_system=raw.get("source_system") or "",
            venue=raw.get("venue") or "",
            hub=raw.get("hub") or "",
            product=raw.get("product") or "",
            price_name=raw.get("price_name") or "",
            price_gbp_mwh=float(raw.get("price_gbp_mwh") or 0.0),
            observed_at_utc=_parse_datetime(_required(raw, "observed_at_utc")),
            delivery_start_utc=_parse_datetime(_required(raw, "delivery_start_utc")),
            delivery_end_utc=_parse_datetime(_required(raw, "delivery_end_utc")),
            bar_minutes=(
                int(raw["bar_minutes"])
                if raw.get("bar_minutes") is not None
                else None
            ),
            price_type=raw.get("price_type") or "mid",
            source_reference=raw.get("source_reference") or "",
        )
        for raw in definition.get("price_observations", [])
    ]

    return StrategyLabScenario(
        strategy_id=version.strategy_id,
        strategy_name=definition.get("strategy_name") or version.strategy_id,
        run_mode=parsed_run_mode,
        resource_contexts=resources,
        price_observations=prices,
        components=components,
        risk_control=risk_control,
        existing_shadow_pnl_gbp=float(
            definition.get("existing_shadow_pnl_gbp") or 0.0
        ),
        research_only=True,
    )


def execute_evaluation_run(
    session: Session,
    *,
    version: StrategyVersionRecord,
    requested_by: str,
    run_id: str | None = None,
    requested_at_utc: datetime | None = None,
    deterministic_seed: str | None = None,
    trigger_type: str = "MANUAL",
    correlation_request_id: str | None = None,
) -> StrategyRunRecord:
    """Evaluate one frozen strategy version and persist a reproducible run.

    Only ``EVALUATION`` is executable in the current release; other run types
    are refused by the API layer before any evaluation starts. Only frozen
    versions may be executed so the recorded manifest is immutable.
    """

    if version.status != "FROZEN":
        raise StrategyVersionExecutionError(
            f"Strategy version {version.strategy_version_id} is {version.status}, "
            "not FROZEN"
        )
    requested_at = (
        _as_utc(requested_at_utc) if requested_at_utc else datetime.now(UTC)
    )
    resolved_run_id = run_id or f"strategy-run-{uuid4().hex[:24]}"
    resolved_seed = deterministic_seed or resolved_run_id
    scenario = evaluation_scenario_from_version(version)
    evaluation_started_at = _as_utc(datetime.now(UTC))
    result = evaluate_strategy_lab(scenario)
    evaluation_completed_at = _as_utc(datetime.now(UTC))

    data_cutoff_utc = _data_cutoff(scenario, requested_at)
    snapshot = _persist_data_snapshot(
        session,
        scenario=scenario,
        data_cutoff_utc=data_cutoff_utc,
        now_utc=evaluation_completed_at,
    )
    manifest = _build_run_manifest(
        run_id=resolved_run_id,
        version=version,
        scenario=scenario,
        data_cutoff_utc=data_cutoff_utc,
        snapshot_id=snapshot.snapshot_id,
        requested_at_utc=requested_at,
        evaluation_start_utc=evaluation_started_at,
        evaluation_end_utc=evaluation_completed_at,
        deterministic_seed=resolved_seed,
        requested_by=requested_by,
        trigger_type=trigger_type,
        correlation_request_id=correlation_request_id or resolved_run_id,
        source_refs=_unique(
            obs.source_reference
            for obs in scenario.price_observations
            if obs.source_reference
        ),
        resource_snapshot_refs=_unique(
            resource.resource_id for resource in scenario.resource_contexts
        ),
    )

    run = StrategyRunRecord(
        run_id=resolved_run_id,
        strategy_id=version.strategy_id,
        strategy_version_id=version.strategy_version_id,
        run_type=str(StrategyRunType.EVALUATION.value),
        run_mode=str(scenario.run_mode.value),
        status=result.status,
        requested_at_utc=requested_at,
        started_at_utc=evaluation_started_at,
        completed_at_utc=evaluation_completed_at,
        finished_at_utc=evaluation_completed_at,
        evaluation_start_utc=evaluation_started_at,
        evaluation_end_utc=evaluation_completed_at,
        data_cutoff_utc=data_cutoff_utc,
        dataset_snapshot_id=snapshot.snapshot_id,
        manifest_json=manifest.model_dump(mode="json"),
        manifest_hash=manifest.content_hash(),
        engine_version=_engine_version(),
        application_version=_application_version(),
        git_commit_sha=_git_commit_sha(),
        strategy_schema_version=STRATEGY_SCHEMA_VERSION,
        run_schema_version=RUN_SCHEMA_VERSION,
        deterministic_seed=resolved_seed,
        requested_by=requested_by,
        trigger_type=trigger_type,
        correlation_request_id=correlation_request_id or resolved_run_id,
        input_snapshot=scenario.model_dump(mode="json"),
        result_snapshot=result.model_dump(mode="json"),
        source_refs=result.source_refs,
        warnings=result.warnings,
        missing_inputs=result.missing_inputs,
        research_only=True,
        human_review_required=True,
    )
    session.add(run)
    _persist_allocation_targets(
        session,
        run_id=resolved_run_id,
        result=result,
        now_utc=evaluation_completed_at,
    )
    session.flush()
    return run


def _persist_allocation_targets(
    session: Session,
    *,
    run_id: str,
    result: StrategyLabResult,
    now_utc: datetime,
) -> None:
    """Persist paper allocation targets; no execution artifacts are created."""

    for target in result.allocation_targets:
        session.add(
            StrategyAllocationTargetRecord(
                target_id=f"target-{uuid4().hex[:16]}",
                run_id=run_id,
                market_bucket=target.market_bucket,
                target_allocation_pct=target.target_allocation_pct,
                target_quantity_mwh_per_day=target.target_quantity_mwh_per_day,
                reference_price_gbp_mwh=target.reference_price_gbp_mwh,
                expected_margin_gbp_mwh=target.expected_margin_gbp_mwh,
                rationale=target.rationale,
                created_at_utc=now_utc,
            )
        )


def _persist_data_snapshot(
    session: Session,
    *,
    scenario: StrategyLabScenario,
    data_cutoff_utc: datetime,
    now_utc: datetime,
):
    """Create the evidence-bundle reference consumed by one run manifest."""

    from eurogas_nexus.db.repositories import strategy_registry
    from eurogas_nexus.domain.strategy_lab.registry import canonical_content_hash

    observation_refs = sorted(
        _unique(
            obs.source_reference
            for obs in scenario.price_observations
            if obs.source_reference
        )
    )
    resource_snapshot_refs = sorted(
        _unique(resource.resource_id for resource in scenario.resource_contexts)
    )
    source_systems = sorted(
        _unique(
            obs.source_system
            for obs in scenario.price_observations
            if obs.source_system
        )
    )
    row_counts = {
        "price_observations": len(scenario.price_observations),
        "resource_contexts": len(scenario.resource_contexts),
    }
    quality_state = (
        "COMPLETE"
        if scenario.price_observations and scenario.resource_contexts
        else "INCOMPLETE"
    )
    snapshot_content = {
        "schema_version": "strategy-data-snapshot/v1",
        "data_cutoff_utc": _iso(data_cutoff_utc),
        "observation_refs": observation_refs,
        "fx_observation_refs": [],
        "resource_snapshot_refs": resource_snapshot_refs,
        "source_systems": source_systems,
        "row_counts": row_counts,
        "quality_state": quality_state,
    }
    return strategy_registry.create_data_snapshot(
        session,
        snapshot_id=None,
        data_cutoff_utc=data_cutoff_utc,
        observation_refs=observation_refs,
        fx_observation_refs=[],
        resource_snapshot_refs=resource_snapshot_refs,
        source_systems=source_systems,
        row_counts=row_counts,
        quality_state=quality_state,
        content_hash=canonical_content_hash(snapshot_content),
        now_utc=now_utc,
    )


def _build_run_manifest(
    *,
    run_id: str,
    version: StrategyVersionRecord,
    scenario: StrategyLabScenario,
    data_cutoff_utc: datetime,
    snapshot_id: str,
    requested_at_utc: datetime,
    evaluation_start_utc: datetime,
    evaluation_end_utc: datetime,
    deterministic_seed: str,
    requested_by: str,
    trigger_type: str,
    correlation_request_id: str,
    source_refs: list[str],
    resource_snapshot_refs: list[str],
) -> StrategyRunManifest:
    """Assemble the versioned, hash-addressable run manifest."""

    definition = version.definition_json or {}
    parameters = dict(definition)
    assumptions = dict(definition.get("assumptions") or {})
    return StrategyRunManifest(
        schema_version=RUN_SCHEMA_VERSION,
        run_id=run_id,
        run_type=str(StrategyRunType.EVALUATION.value),
        run_mode=str(scenario.run_mode.value),
        strategy_id=version.strategy_id,
        strategy_name=definition.get("strategy_name") or version.strategy_id,
        strategy_version_id=version.strategy_version_id,
        version_number=version.version_number,
        strategy_version_content_hash=version.content_hash,
        strategy_definition=definition,
        parameters=parameters,
        assumptions=assumptions,
        parameter_values=parameters,
        economic_assumptions=assumptions,
        evidence={
            "dataset_snapshot_id": snapshot_id,
            "data_cutoff_utc": _iso(data_cutoff_utc),
            "price_observation_refs": _unique(
                obs.source_reference
                for obs in scenario.price_observations
                if obs.source_reference
            ),
            "resource_snapshot_refs": _unique(
                resource.resource_id for resource in scenario.resource_contexts
            ),
            "source_systems": _unique(
                obs.source_system
                for obs in scenario.price_observations
                if obs.source_system
            ),
            "row_counts": {
                "price_observations": len(scenario.price_observations),
                "resource_contexts": len(scenario.resource_contexts),
            },
        },
        time_boundary={
            "requested_at_utc": _iso(requested_at_utc),
            "evaluation_start_utc": _iso(evaluation_start_utc),
            "evaluation_end_utc": _iso(evaluation_end_utc),
            "data_cutoff_utc": _iso(data_cutoff_utc),
        },
        engine={
            "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
            "run_schema_version": RUN_SCHEMA_VERSION,
            "engine_version": _engine_version(),
            "application_version": _application_version(),
            "git_commit_sha": _git_commit_sha(),
            "deterministic_seed": deterministic_seed,
        },
        evaluation_start_utc=evaluation_start_utc,
        evaluation_end_utc=evaluation_end_utc,
        data_cutoff_utc=data_cutoff_utc,
        dataset_snapshot_id=snapshot_id,
        source_refs=source_refs,
        resource_snapshot_refs=resource_snapshot_refs,
        engine_version=_engine_version(),
        application_version=_application_version(),
        git_commit_sha=_git_commit_sha(),
        requested_by=requested_by,
        trigger_type=trigger_type,
        correlation_request_id=correlation_request_id,
        research_only=True,
        human_review_required=True,
    )


def _required(raw: dict, field: str) -> str:
    value = raw.get(field)
    if value is None or str(value).strip() == "":
        raise StrategyVersionExecutionError(
            f"Missing required strategy definition field: {field}"
        )
    return str(value)


def _data_cutoff(scenario: StrategyLabScenario, fallback: datetime) -> datetime:
    """Latest observation time, falling back to the request time."""

    observed = [obs.observed_at_utc for obs in scenario.price_observations]
    return max(observed) if observed else fallback


def _engine_version() -> str:
    try:
        return importlib.metadata.version("eurogas-nexus")
    except importlib.metadata.PackageNotFoundError:
        return package_version


def _application_version() -> str:
    return _engine_version()


def _git_commit_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parents[4]),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        value = completed.stdout.strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_datetime(value: str) -> datetime:
    return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _unique(values: object) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered
