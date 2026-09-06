"""Research data foundation tables (CR-14).

These tables hold semantic definitions and immutable dataset snapshots. They
are not a training platform and do not expose raw licensed data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class CanonicalEntityRecord(Base):
    __tablename__ = "canonical_entities"

    canonical_entity_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("uq_canonical_entities_type_code", "entity_type", "canonical_code", unique=True),
    )


class SourceEntityMappingRecord(Base):
    __tablename__ = "source_entity_mappings"

    mapping_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    canonical_entity_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("canonical_entities.canonical_entity_id"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    valid_from_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    confidence: Mapped[str] = mapped_column(String(32), default="CONFIRMED")
    evidence: Mapped[str] = mapped_column(String(512), default="")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index(
            "uq_source_entity_mapping_active",
            "source_id",
            "source_entity_type",
            "source_identifier",
            "valid_from_utc",
            unique=True,
        ),
        Index("ix_source_entity_mappings_canonical", "canonical_entity_id"),
    )


class SeriesDefinitionRecord(Base):
    __tablename__ = "series_definitions"

    series_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_class: Mapped[str] = mapped_column(String(64), nullable=False)
    native_frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    native_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    temporal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    availability_semantics: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="series/v1")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FeatureDefinitionRecord(Base):
    __tablename__ = "feature_definitions"

    feature_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TargetDefinitionRecord(Base):
    __tablename__ = "target_definitions"

    target_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ResamplingPolicyRecord(Base):
    __tablename__ = "resampling_policies"

    policy_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DatasetSpecRecord(Base):
    __tablename__ = "dataset_specs"

    dataset_spec_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    definition_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DatasetSnapshotRecord(Base):
    __tablename__ = "dataset_snapshots"

    dataset_snapshot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_spec_id: Mapped[str] = mapped_column(String(128), nullable=False)
    spec_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ontology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_cutoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage: Mapped[float] = mapped_column(Float, nullable=False)
    temporal_integrity: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entitlement_envelope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str] = mapped_column(String(64), default="research")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETE")

    __table_args__ = (Index("ix_dataset_snapshots_spec", "dataset_spec_id"),)


class DatasetSnapshotDependencyRecord(Base):
    __tablename__ = "dataset_snapshot_dependencies"

    dependency_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("dataset_snapshots.dataset_snapshot_id"), nullable=False
    )
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_id_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    version_ref: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (Index("ix_dataset_snapshot_deps_snapshot", "dataset_snapshot_id"),)


class DatasetBuildIssueRecord(Base):
    __tablename__ = "dataset_build_issues"

    issue_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("dataset_snapshots.dataset_snapshot_id"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(String(512), nullable=False)

    __table_args__ = (Index("ix_dataset_build_issues_snapshot", "dataset_snapshot_id"),)


class DatasetArtifactRecord(Base):
    __tablename__ = "dataset_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_snapshot_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("dataset_snapshots.dataset_snapshot_id"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_dataset_artifacts_snapshot", "dataset_snapshot_id"),)


class ForecastObservationRecord(Base):
    __tablename__ = "forecast_observations"

    forecast_observation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    series_id: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    forecast_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_valid_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_valid_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    available_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_state: Mapped[str] = mapped_column(String(32), nullable=False, default="OBSERVED")

    __table_args__ = (
        Index("ix_forecast_observations_series_issued", "series_id", "forecast_issued_at"),
    )


class ObservationTemporalMetadataRecord(Base):
    __tablename__ = "observation_temporal_metadata"

    observation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    observation_table: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    temporal_integrity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="TEMPORAL_APPROXIMATE"
    )
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_observation_temporal_metadata_table", "observation_table", "observation_id"),
    )
