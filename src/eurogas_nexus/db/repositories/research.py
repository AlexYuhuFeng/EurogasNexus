"""Persistence repository for the CR-14 research data foundation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    DatasetArtifactRecord,
    DatasetBuildIssueRecord,
    DatasetSnapshotDependencyRecord,
    DatasetSnapshotRecord,
    DatasetSpecRecord,
    FeatureDefinitionRecord,
    ForecastObservationRecord,
    ObservationTemporalMetadataRecord,
    ResamplingPolicyRecord,
    SeriesDefinitionRecord,
    SourceEntityMappingRecord,
    TargetDefinitionRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        return _as_utc(datetime.fromisoformat(value))
    return _as_utc(value)


def upsert_canonical_entity(
    session: Session,
    *,
    canonical_entity_id: str,
    entity_type: str,
    canonical_code: str,
    display_name: str,
    description: str = "",
    metadata_json: dict[str, Any] | None = None,
) -> CanonicalEntityRecord:
    row = session.get(CanonicalEntityRecord, canonical_entity_id)
    if row is None:
        row = CanonicalEntityRecord(
            canonical_entity_id=canonical_entity_id,
            entity_type=entity_type,
            canonical_code=canonical_code,
            display_name=display_name,
            description=description,
            metadata_json=metadata_json,
            created_at_utc=_now(),
        )
        session.add(row)
    else:
        row.entity_type = entity_type
        row.canonical_code = canonical_code
        row.display_name = display_name
        row.description = description
        row.metadata_json = metadata_json
    return row


def upsert_source_entity_mapping(
    session: Session,
    *,
    mapping_id: str,
    canonical_entity_id: str,
    source_id: str,
    source_entity_type: str,
    source_identifier: str,
    valid_from_utc: datetime,
    valid_to_utc: datetime | None = None,
    mapping_status: str = "ACTIVE",
    confidence: str = "CONFIRMED",
    evidence: str = "",
) -> SourceEntityMappingRecord:
    row = session.get(SourceEntityMappingRecord, mapping_id)
    if row is None:
        row = SourceEntityMappingRecord(
            mapping_id=mapping_id,
            canonical_entity_id=canonical_entity_id,
            source_id=source_id,
            source_entity_type=source_entity_type,
            source_identifier=source_identifier,
            valid_from_utc=valid_from_utc,
            valid_to_utc=valid_to_utc,
            mapping_status=mapping_status,
            confidence=confidence,
            evidence=evidence,
            created_at_utc=_now(),
        )
        session.add(row)
    else:
        row.canonical_entity_id = canonical_entity_id
        row.valid_from_utc = valid_from_utc
        row.valid_to_utc = valid_to_utc
        row.mapping_status = mapping_status
        row.confidence = confidence
        row.evidence = evidence
    return row


def resolve_canonical_entity(
    session: Session,
    *,
    source_id: str,
    source_entity_type: str,
    source_identifier: str,
    at_utc: datetime,
) -> CanonicalEntityRecord | None:
    """Resolve a source identity at a point in time; reject ambiguity."""

    statement = (
        select(SourceEntityMappingRecord)
        .where(
            SourceEntityMappingRecord.source_id == source_id,
            SourceEntityMappingRecord.source_entity_type == source_entity_type,
            SourceEntityMappingRecord.source_identifier == source_identifier,
        )
        .order_by(SourceEntityMappingRecord.valid_from_utc.desc())
    )
    cutoff = _as_utc(at_utc)
    candidates = []
    for mapping in session.scalars(statement).all():
        if _as_utc(mapping.valid_from_utc) > cutoff:
            continue
        if mapping.valid_to_utc is not None and _as_utc(mapping.valid_to_utc) < cutoff:
            continue
        candidates.append(mapping)
    if len(candidates) != 1:
        return None
    return session.get(CanonicalEntityRecord, candidates[0].canonical_entity_id)


def upsert_series_definition(
    session: Session, definition: SeriesDefinitionRecord
) -> SeriesDefinitionRecord:
    row = session.get(SeriesDefinitionRecord, definition.series_id)
    if row is None:
        session.add(definition)
        return definition
    for field in (
        "name",
        "metric_type",
        "entity_type",
        "entity_id",
        "product_id",
        "direction",
        "source_class",
        "native_frequency",
        "native_unit",
        "currency",
        "temporal_type",
        "availability_semantics",
        "schema_version",
    ):
        setattr(row, field, getattr(definition, field))
    return row


def upsert_feature_definition(
    session: Session,
    *,
    feature_id: str,
    definition_json: dict[str, Any],
    content_hash: str,
    status: str = "active",
) -> FeatureDefinitionRecord:
    row = session.get(FeatureDefinitionRecord, feature_id)
    if row is None:
        row = FeatureDefinitionRecord(
            feature_id=feature_id,
            definition_json=definition_json,
            content_hash=content_hash,
            status=status,
            created_at_utc=_now(),
        )
        session.add(row)
    else:
        row.definition_json = definition_json
        row.content_hash = content_hash
        row.status = status
    return row


def list_feature_definitions(session: Session) -> list[FeatureDefinitionRecord]:
    return list(session.scalars(select(FeatureDefinitionRecord)).all())


def upsert_target_definition(
    session: Session,
    *,
    target_id: str,
    definition_json: dict[str, Any],
    content_hash: str,
    status: str = "active",
) -> TargetDefinitionRecord:
    row = session.get(TargetDefinitionRecord, target_id)
    if row is None:
        row = TargetDefinitionRecord(
            target_id=target_id,
            definition_json=definition_json,
            content_hash=content_hash,
            status=status,
            created_at_utc=_now(),
        )
        session.add(row)
    else:
        row.definition_json = definition_json
        row.content_hash = content_hash
        row.status = status
    return row


def list_target_definitions(session: Session) -> list[TargetDefinitionRecord]:
    return list(session.scalars(select(TargetDefinitionRecord)).all())


def upsert_resampling_policy(
    session: Session,
    *,
    policy_id: str,
    definition_json: dict[str, Any],
    content_hash: str,
) -> ResamplingPolicyRecord:
    row = session.get(ResamplingPolicyRecord, policy_id)
    if row is None:
        row = ResamplingPolicyRecord(
            policy_id=policy_id,
            definition_json=definition_json,
            content_hash=content_hash,
            created_at_utc=_now(),
        )
        session.add(row)
    else:
        row.definition_json = definition_json
        row.content_hash = content_hash
    return row


def upsert_dataset_spec(
    session: Session,
    *,
    dataset_spec_id: str,
    definition_json: dict[str, Any],
    content_hash: str,
    status: str = "active",
) -> DatasetSpecRecord:
    row = session.get(DatasetSpecRecord, dataset_spec_id)
    if row is None:
        row = DatasetSpecRecord(
            dataset_spec_id=dataset_spec_id,
            definition_json=definition_json,
            content_hash=content_hash,
            status=status,
            created_at_utc=_now(),
        )
        session.add(row)
    else:
        row.definition_json = definition_json
        row.content_hash = content_hash
        row.status = status
    return row


def persist_dataset_snapshot(
    session: Session,
    *,
    metadata: dict[str, Any],
    dependencies: list[dict[str, str]],
    issues: list[dict[str, str]],
    artifacts: list[dict[str, str]],
) -> DatasetSnapshotRecord:
    row = DatasetSnapshotRecord(
        dataset_snapshot_id=metadata["dataset_snapshot_id"],
        dataset_spec_id=metadata["dataset_spec_id"],
        spec_hash=metadata["dataset_spec_version"].split("@")[-1],
        ontology_version=metadata["ontology_version"],
        source_cutoff_utc=_coerce_datetime(metadata["source_cutoff_utc"]),
        row_count=metadata["row_count"],
        column_count=metadata["column_count"],
        coverage=metadata["quality_report"]["coverage"],
        temporal_integrity=metadata["quality_report"]["temporal_integrity"],
        content_hash=metadata["content_hash"],
        entitlement_envelope=metadata["entitlement_envelope"],
        metadata_json=metadata,
        artifact_ref=artifacts[0]["artifact_path"] if artifacts else None,
        created_at_utc=_now(),
        created_by="research",
        status="COMPLETE",
    )
    session.add(row)
    session.flush()
    for dependency in dependencies:
        session.add(
            DatasetSnapshotDependencyRecord(
                dependency_id=dependency["dependency_id"],
                dataset_snapshot_id=metadata["dataset_snapshot_id"],
                dependency_type=dependency["dependency_type"],
                dependency_id_ref=dependency["dependency_id_ref"],
                version_ref=dependency["version_ref"],
            )
        )
    for issue in issues:
        session.add(
            DatasetBuildIssueRecord(
                issue_id=issue["issue_id"],
                dataset_snapshot_id=metadata["dataset_snapshot_id"],
                severity=issue["severity"],
                code=issue["code"],
                detail=issue["detail"],
            )
        )
    for artifact in artifacts:
        session.add(
            DatasetArtifactRecord(
                artifact_id=artifact["artifact_id"],
                dataset_snapshot_id=metadata["dataset_snapshot_id"],
                format=artifact["format"],
                artifact_path=artifact["artifact_path"],
                sha256=artifact["sha256"],
                created_at_utc=_now(),
            )
        )
    session.flush()
    return row


def list_dataset_snapshots(session: Session) -> list[DatasetSnapshotRecord]:
    return list(session.scalars(select(DatasetSnapshotRecord)).all())


def get_dataset_snapshot(
    session: Session, dataset_snapshot_id: str
) -> DatasetSnapshotRecord | None:
    return session.get(DatasetSnapshotRecord, dataset_snapshot_id)


def upsert_forecast_observation(
    session: Session,
    *,
    forecast_observation_id: str,
    series_id: str,
    entity_id: str,
    forecast_issued_at: datetime,
    forecast_valid_start: datetime,
    forecast_valid_end: datetime,
    horizon: str,
    value: float,
    unit: str,
    source_system: str,
    available_at_utc: datetime,
    model_provider: str | None = None,
    provenance: dict[str, Any] | None = None,
    quality_state: str = "OBSERVED",
) -> ForecastObservationRecord:
    row = session.get(ForecastObservationRecord, forecast_observation_id)
    if row is None:
        row = ForecastObservationRecord(
            forecast_observation_id=forecast_observation_id,
            series_id=series_id,
            entity_id=entity_id,
            forecast_issued_at=forecast_issued_at,
            forecast_valid_start=forecast_valid_start,
            forecast_valid_end=forecast_valid_end,
            horizon=horizon,
            value=value,
            unit=unit,
            source_system=source_system,
            model_provider=model_provider,
            available_at_utc=available_at_utc,
            ingested_at_utc=_now(),
            provenance=provenance or {},
            quality_state=quality_state,
        )
        session.add(row)
    else:
        row.value = value
        row.available_at_utc = available_at_utc
        row.ingested_at_utc = _now()
        row.provenance = provenance or {}
        row.quality_state = quality_state
    return row


def upsert_observation_temporal_metadata(
    session: Session,
    *,
    observation_id: str,
    observation_table: str,
    observed_at_utc: datetime,
    available_at_utc: datetime | None,
    ingested_at_utc: datetime | None,
    temporal_integrity: str,
    provenance: dict[str, Any] | None = None,
) -> ObservationTemporalMetadataRecord:
    row = session.get(ObservationTemporalMetadataRecord, observation_id)
    if row is None:
        row = ObservationTemporalMetadataRecord(
            observation_id=observation_id,
            observation_table=observation_table,
            observed_at_utc=observed_at_utc,
            available_at_utc=available_at_utc,
            ingested_at_utc=ingested_at_utc,
            temporal_integrity=temporal_integrity,
            provenance=provenance or {},
        )
        session.add(row)
    else:
        row.observed_at_utc = observed_at_utc
        row.available_at_utc = available_at_utc
        row.ingested_at_utc = ingested_at_utc
        row.temporal_integrity = temporal_integrity
        row.provenance = provenance or {}
    return row
