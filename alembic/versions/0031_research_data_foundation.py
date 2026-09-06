"""Add CR-14 research data foundation tables.

Revision ID: 0031_research_data_foundation
Revises: 0030_reliability_indexes
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0031_research_data_foundation"
down_revision = "0030_reliability_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_entities",
        sa.Column("canonical_entity_id", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("canonical_entity_id"),
        sa.UniqueConstraint(
            "entity_type", "canonical_code", name="uq_canonical_entities_type_code"
        ),
    )

    op.create_table(
        "source_entity_mappings",
        sa.Column("mapping_id", sa.String(length=128), nullable=False),
        sa.Column("canonical_entity_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source_entity_type", sa.String(length=64), nullable=False),
        sa.Column("source_identifier", sa.String(length=160), nullable=False),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mapping_status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("evidence", sa.String(length=512), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_entity_id"], ["canonical_entities.canonical_entity_id"]
        ),
        sa.PrimaryKeyConstraint("mapping_id"),
        sa.UniqueConstraint(
            "source_id",
            "source_entity_type",
            "source_identifier",
            "valid_from_utc",
            name="uq_source_entity_mapping_active",
        ),
    )
    op.create_index(
        "ix_source_entity_mappings_canonical", "source_entity_mappings", ["canonical_entity_id"]
    )

    op.create_table(
        "series_definitions",
        sa.Column("series_id", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=True),
        sa.Column("source_class", sa.String(length=64), nullable=False),
        sa.Column("native_frequency", sa.String(length=32), nullable=False),
        sa.Column("native_unit", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("temporal_type", sa.String(length=32), nullable=False),
        sa.Column("availability_semantics", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("series_id"),
    )

    op.create_table(
        "feature_definitions",
        sa.Column("feature_id", sa.String(length=128), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("feature_id"),
    )

    op.create_table(
        "target_definitions",
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("target_id"),
    )

    op.create_table(
        "resampling_policies",
        sa.Column("policy_id", sa.String(length=128), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("policy_id"),
    )

    op.create_table(
        "dataset_specs",
        sa.Column("dataset_spec_id", sa.String(length=128), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_spec_id"),
    )

    op.create_table(
        "dataset_snapshots",
        sa.Column("dataset_snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_spec_id", sa.String(length=128), nullable=False),
        sa.Column("spec_hash", sa.String(length=64), nullable=False),
        sa.Column("ontology_version", sa.String(length=32), nullable=False),
        sa.Column("source_cutoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("temporal_integrity", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("entitlement_envelope", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("artifact_ref", sa.String(length=512), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("dataset_snapshot_id"),
    )
    op.create_index("ix_dataset_snapshots_spec", "dataset_snapshots", ["dataset_spec_id"])

    op.create_table(
        "dataset_snapshot_dependencies",
        sa.Column("dependency_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("dependency_type", sa.String(length=64), nullable=False),
        sa.Column("dependency_id_ref", sa.String(length=160), nullable=False),
        sa.Column("version_ref", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.dataset_snapshot_id"]),
        sa.PrimaryKeyConstraint("dependency_id"),
    )
    op.create_index(
        "ix_dataset_snapshot_deps_snapshot",
        "dataset_snapshot_dependencies",
        ["dataset_snapshot_id"],
    )

    op.create_table(
        "dataset_build_issues",
        sa.Column("issue_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.dataset_snapshot_id"]),
        sa.PrimaryKeyConstraint("issue_id"),
    )
    op.create_index(
        "ix_dataset_build_issues_snapshot", "dataset_build_issues", ["dataset_snapshot_id"]
    )

    op.create_table(
        "dataset_artifacts",
        sa.Column("artifact_id", sa.String(length=128), nullable=False),
        sa.Column("dataset_snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("artifact_path", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_snapshot_id"], ["dataset_snapshots.dataset_snapshot_id"]),
        sa.PrimaryKeyConstraint("artifact_id"),
    )
    op.create_index("ix_dataset_artifacts_snapshot", "dataset_artifacts", ["dataset_snapshot_id"])

    op.create_table(
        "forecast_observations",
        sa.Column("forecast_observation_id", sa.String(length=128), nullable=False),
        sa.Column("series_id", sa.String(length=160), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("forecast_issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_valid_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_valid_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=True),
        sa.Column("available_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("quality_state", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("forecast_observation_id"),
    )
    op.create_index(
        "ix_forecast_observations_series_issued",
        "forecast_observations",
        ["series_id", "forecast_issued_at"],
    )

    op.create_table(
        "observation_temporal_metadata",
        sa.Column("observation_id", sa.String(length=128), nullable=False),
        sa.Column("observation_table", sa.String(length=64), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temporal_integrity", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_index(
        "ix_observation_temporal_metadata_table",
        "observation_temporal_metadata",
        ["observation_table", "observation_id"],
    )


def downgrade() -> None:
    for table in (
        "observation_temporal_metadata",
        "forecast_observations",
        "dataset_artifacts",
        "dataset_build_issues",
        "dataset_snapshot_dependencies",
        "dataset_snapshots",
        "dataset_specs",
        "resampling_policies",
        "target_definitions",
        "feature_definitions",
        "series_definitions",
        "source_entity_mappings",
        "canonical_entities",
    ):
        op.drop_table(table)
