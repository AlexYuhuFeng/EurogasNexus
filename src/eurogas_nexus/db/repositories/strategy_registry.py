"""Repository operations for the versioned strategy-research registry."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    StrategyDataSnapshotRecord,
    StrategyRecord,
    StrategyRunRecord,
    StrategyVersionRecord,
)
from eurogas_nexus.domain.strategy_lab.registry import (
    STRATEGY_SCHEMA_VERSION,
    StrategyRunManifest,
    StrategyVersionDefinition,
    canonical_content_hash,
)


class StrategyRegistryError(ValueError):
    """Domain failure in strategy-registry persistence."""


def create_strategy(
    session: Session,
    *,
    strategy_id: str,
    name: str,
    description: str,
    created_by: str,
    now_utc: datetime,
    tags: list[str] | None = None,
) -> StrategyRecord:
    if session.get(StrategyRecord, strategy_id) is not None:
        raise StrategyRegistryError(f"Strategy already exists: {strategy_id}")
    row = StrategyRecord(
        strategy_id=strategy_id,
        name=name,
        description=description,
        lifecycle_status="RESEARCH",
        current_version_id=None,
        created_by=created_by,
        created_at_utc=now_utc,
        updated_at_utc=now_utc,
        retired_at_utc=None,
        tags=tags or [],
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def get_strategy(session: Session, strategy_id: str) -> StrategyRecord | None:
    return session.get(StrategyRecord, strategy_id)


def list_strategies(session: Session, *, limit: int = 200) -> list[StrategyRecord]:
    return list(
        session.scalars(
            select(StrategyRecord)
            .order_by(StrategyRecord.updated_at_utc.desc())
            .limit(max(1, min(limit, 500)))
        )
    )


def next_version_number(session: Session, strategy_id: str) -> int:
    existing = (
        session.scalars(
            select(StrategyVersionRecord.version_number)
            .where(StrategyVersionRecord.strategy_id == strategy_id)
        ).all()
    )
    return max(existing, default=0) + 1


def get_strategy_version(
    session: Session, strategy_version_id: str
) -> StrategyVersionRecord | None:
    return session.get(StrategyVersionRecord, strategy_version_id)


def list_strategy_versions(
    session: Session, strategy_id: str, *, limit: int = 100
) -> list[StrategyVersionRecord]:
    return list(
        session.scalars(
            select(StrategyVersionRecord)
            .where(StrategyVersionRecord.strategy_id == strategy_id)
            .order_by(StrategyVersionRecord.version_number.desc())
            .limit(max(1, min(limit, 500)))
        )
    )


def create_strategy_version(
    session: Session,
    *,
    strategy_id: str,
    definition: StrategyVersionDefinition,
    hypothesis: str,
    created_by: str,
    now_utc: datetime,
    parent_version_id: str | None = None,
    definition_overrides: dict | None = None,
) -> StrategyVersionRecord:
    if get_strategy(session, strategy_id) is None:
        raise StrategyRegistryError(f"Strategy does not exist: {strategy_id}")
    stored_definition = definition.model_dump(mode="json")
    if definition_overrides:
        stored_definition.update(definition_overrides)
    row = StrategyVersionRecord(
        strategy_version_id=f"strategy-version-{uuid4().hex[:20]}",
        strategy_id=strategy_id,
        version_number=next_version_number(session, strategy_id),
        schema_version=STRATEGY_SCHEMA_VERSION,
        status="DRAFT",
        hypothesis=hypothesis,
        definition_json=stored_definition,
        parent_version_id=parent_version_id,
        created_by=created_by,
        created_at_utc=now_utc,
        frozen_at_utc=None,
        content_hash=canonical_content_hash(stored_definition),
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def freeze_strategy_version(
    session: Session,
    *,
    strategy_version_id: str,
    frozen_by: str,
    now_utc: datetime,
) -> StrategyVersionRecord:
    version = get_strategy_version(session, strategy_version_id)
    if version is None:
        raise StrategyRegistryError(
            f"Strategy version does not exist: {strategy_version_id}"
        )
    if version.status != "DRAFT":
        raise StrategyRegistryError(
            f"Only DRAFT versions can be frozen; current status is {version.status}"
        )
    version.status = "FROZEN"
    version.frozen_at_utc = now_utc
    strategy = get_strategy(session, version.strategy_id)
    if strategy is None:
        raise StrategyRegistryError(f"Strategy does not exist: {version.strategy_id}")
    strategy.current_version_id = version.strategy_version_id
    strategy.updated_at_utc = now_utc
    session.flush()
    return version


def fork_strategy_version(
    session: Session,
    *,
    source_version_id: str,
    definition: StrategyVersionDefinition | None,
    hypothesis: str | None,
    created_by: str,
    now_utc: datetime,
) -> StrategyVersionRecord:
    source = get_strategy_version(session, source_version_id)
    if source is None:
        raise StrategyRegistryError(
            f"Strategy version does not exist: {source_version_id}"
        )
    if source.status != "FROZEN":
        raise StrategyRegistryError(
            "Only FROZEN versions may be forked; create a new draft from frozen "
            "research instead of mutating it"
        )
    fork_definition = definition or StrategyVersionDefinition.model_validate(
        source.definition_json
    )
    return create_strategy_version(
        session,
        strategy_id=source.strategy_id,
        definition=fork_definition,
        hypothesis=hypothesis if hypothesis is not None else source.hypothesis,
        created_by=created_by,
        now_utc=now_utc,
        parent_version_id=source.strategy_version_id,
        definition_overrides=_extra_definition_fields(source.definition_json or {}),
    )


def create_data_snapshot(
    session: Session,
    *,
    snapshot_id: str | None,
    data_cutoff_utc: datetime,
    observation_refs: list[str],
    fx_observation_refs: list[str],
    resource_snapshot_refs: list[str],
    source_systems: list[str],
    row_counts: dict,
    quality_state: str,
    content_hash: str,
    now_utc: datetime,
) -> StrategyDataSnapshotRecord:
    row = StrategyDataSnapshotRecord(
        snapshot_id=snapshot_id or f"strategy-snapshot-{uuid4().hex[:20]}",
        data_cutoff_utc=data_cutoff_utc,
        observation_refs=observation_refs,
        fx_observation_refs=fx_observation_refs,
        resource_snapshot_refs=resource_snapshot_refs,
        source_systems=source_systems,
        row_counts=row_counts,
        quality_state=quality_state,
        content_hash=content_hash,
        created_at_utc=now_utc,
        research_only=True,
    )
    session.add(row)
    session.flush()
    return row


def create_strategy_run(
    session: Session,
    *,
    run_id: str,
    strategy: StrategyRecord,
    version: StrategyVersionRecord,
    run_type: str,
    run_mode: str,
    status: str,
    manifest: StrategyRunManifest,
    input_snapshot: dict,
    result_snapshot: dict,
    source_refs: list[str],
    warnings: list[str],
    missing_inputs: list[str],
    now_utc: datetime,
    requested_by: str,
    trigger_type: str,
) -> StrategyRunRecord:
    row = StrategyRunRecord(
        run_id=run_id,
        strategy_id=strategy.strategy_id,
        strategy_version_id=version.strategy_version_id,
        run_type=run_type,
        run_mode=run_mode,
        status=status,
        requested_at_utc=now_utc,
        started_at_utc=now_utc,
        completed_at_utc=now_utc,
        finished_at_utc=now_utc,
        evaluation_start_utc=manifest.evaluation_start_utc,
        evaluation_end_utc=manifest.evaluation_end_utc,
        data_cutoff_utc=manifest.data_cutoff_utc,
        dataset_snapshot_id=manifest.dataset_snapshot_id,
        manifest_json=manifest.model_dump(mode="json"),
        manifest_hash=manifest.content_hash(),
        engine_version=manifest.engine_version,
        application_version=manifest.application_version,
        git_commit_sha=manifest.git_commit_sha,
        strategy_schema_version=manifest.strategy_schema_version,
        run_schema_version=manifest.schema_version,
        deterministic_seed=manifest.deterministic_seed,
        requested_by=requested_by,
        trigger_type=trigger_type,
        correlation_request_id=manifest.correlation_request_id,
        input_snapshot=input_snapshot,
        result_snapshot=result_snapshot,
        source_refs=source_refs,
        warnings=warnings,
        missing_inputs=missing_inputs,
        research_only=True,
        human_review_required=True,
    )
    session.add(row)
    session.flush()
    return row


def list_strategy_runs(
    session: Session,
    *,
    strategy_id: str | None = None,
    strategy_version_id: str | None = None,
    run_type: str | None = None,
    limit: int = 100,
) -> list[StrategyRunRecord]:
    query = select(StrategyRunRecord).order_by(StrategyRunRecord.started_at_utc.desc())
    if strategy_id:
        query = query.where(StrategyRunRecord.strategy_id == strategy_id)
    if strategy_version_id:
        query = query.where(
            StrategyRunRecord.strategy_version_id == strategy_version_id
        )
    if run_type:
        query = query.where(StrategyRunRecord.run_type == run_type)
    return list(session.scalars(query.limit(max(1, min(limit, 500)))))


def strategy_record_payload(row: StrategyRecord) -> dict:
    return {
        "strategy_id": row.strategy_id,
        "name": row.name,
        "description": row.description,
        "lifecycle_status": row.lifecycle_status,
        "current_version_id": row.current_version_id,
        "created_by": row.created_by,
        "created_at_utc": _as_utc(row.created_at_utc).isoformat(),
        "updated_at_utc": _as_utc(row.updated_at_utc).isoformat(),
        "retired_at_utc": (
            _as_utc(row.retired_at_utc).isoformat() if row.retired_at_utc else None
        ),
        "tags": row.tags or [],
        "research_only": row.research_only,
    }


def strategy_version_payload(row: StrategyVersionRecord) -> dict:
    return {
        "strategy_version_id": row.strategy_version_id,
        "strategy_id": row.strategy_id,
        "version_number": row.version_number,
        "schema_version": row.schema_version,
        "status": row.status,
        "hypothesis": row.hypothesis,
        "definition_json": row.definition_json,
        "parent_version_id": row.parent_version_id,
        "created_by": row.created_by,
        "created_at_utc": _as_utc(row.created_at_utc).isoformat(),
        "frozen_at_utc": (
            _as_utc(row.frozen_at_utc).isoformat() if row.frozen_at_utc else None
        ),
        "content_hash": row.content_hash,
        "research_only": row.research_only,
    }


def strategy_data_snapshot_payload(row: StrategyDataSnapshotRecord) -> dict:
    return {
        "snapshot_id": row.snapshot_id,
        "data_cutoff_utc": _as_utc(row.data_cutoff_utc).isoformat(),
        "observation_refs": row.observation_refs or [],
        "fx_observation_refs": row.fx_observation_refs or [],
        "resource_snapshot_refs": row.resource_snapshot_refs or [],
        "source_systems": row.source_systems or [],
        "row_counts": row.row_counts or {},
        "quality_state": row.quality_state,
        "content_hash": row.content_hash,
        "created_at_utc": _as_utc(row.created_at_utc).isoformat(),
        "research_only": row.research_only,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_SEMANTIC_DEFINITION_FIELDS = {
    "components",
    "parameter_definitions",
    "parameter_values",
    "risk_controls",
    "economic_assumptions",
    "data_requirements",
    "evaluation_windows",
}


def _extra_definition_fields(definition_json: dict) -> dict:
    return {
        key: value
        for key, value in definition_json.items()
        if key not in _SEMANTIC_DEFINITION_FIELDS
    }
