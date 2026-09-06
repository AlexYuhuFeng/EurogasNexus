"""Add versioned strategy registry and reproducible run provenance.

Revision ID: 0025_strategy_registry_v1
Revises: 0024_cost_observations
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0025_strategy_registry_v1"
down_revision: str | None = "0024_cost_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("strategy_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("lifecycle_status", sa.String(32), nullable=False),
        sa.Column("current_version_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("strategy_id"),
    )
    op.create_table(
        "strategy_versions",
        sa.Column("strategy_version_id", sa.String(128), nullable=False),
        sa.Column("strategy_id", sa.String(128), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("definition_json", sa.JSON(), nullable=False),
        sa.Column("parent_version_id", sa.String(128), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frozen_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.strategy_id"]),
        sa.PrimaryKeyConstraint("strategy_version_id"),
        sa.UniqueConstraint(
            "strategy_id", "version_number", name="uq_strategy_version_number"
        ),
    )
    op.create_index(
        "ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"]
    )
    op.create_table(
        "strategy_data_snapshots",
        sa.Column("snapshot_id", sa.String(128), nullable=False),
        sa.Column("data_cutoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_refs", sa.JSON(), nullable=False),
        sa.Column("fx_observation_refs", sa.JSON(), nullable=False),
        sa.Column("resource_snapshot_refs", sa.JSON(), nullable=False),
        sa.Column("source_systems", sa.JSON(), nullable=False),
        sa.Column("row_counts", sa.JSON(), nullable=False),
        sa.Column("quality_state", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    for column in [
        sa.Column("strategy_version_id", sa.String(128), nullable=True),
        sa.Column("run_type", sa.String(32), nullable=True),
        sa.Column("requested_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluation_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_cutoff_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dataset_snapshot_id", sa.String(128), nullable=True),
        sa.Column("manifest_json", sa.JSON(), nullable=True),
        sa.Column("manifest_hash", sa.String(128), nullable=True),
        sa.Column("engine_version", sa.String(64), nullable=True),
        sa.Column("application_version", sa.String(64), nullable=True),
        sa.Column("git_commit_sha", sa.String(64), nullable=True),
        sa.Column("strategy_schema_version", sa.String(32), nullable=True),
        sa.Column("run_schema_version", sa.String(32), nullable=True),
        sa.Column("deterministic_seed", sa.String(64), nullable=True),
        sa.Column("requested_by", sa.String(64), nullable=True),
        sa.Column("trigger_type", sa.String(32), nullable=True),
        sa.Column("correlation_request_id", sa.String(64), nullable=True),
    ]:
        op.add_column("strategy_runs", column)
    op.create_foreign_key(
        "fk_strategy_runs_strategy_version_id",
        "strategy_runs",
        "strategy_versions",
        ["strategy_version_id"],
        ["strategy_version_id"],
    )
    op.create_foreign_key(
        "fk_strategy_runs_dataset_snapshot_id",
        "strategy_runs",
        "strategy_data_snapshots",
        ["dataset_snapshot_id"],
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_strategy_runs_dataset_snapshot_id", "strategy_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_strategy_runs_strategy_version_id", "strategy_runs", type_="foreignkey"
    )
    for column in [
        "correlation_request_id",
        "trigger_type",
        "requested_by",
        "deterministic_seed",
        "run_schema_version",
        "strategy_schema_version",
        "git_commit_sha",
        "application_version",
        "engine_version",
        "manifest_hash",
        "manifest_json",
        "dataset_snapshot_id",
        "data_cutoff_utc",
        "evaluation_end_utc",
        "evaluation_start_utc",
        "completed_at_utc",
        "requested_at_utc",
        "run_type",
        "strategy_version_id",
    ]:
        op.drop_column("strategy_runs", column)
    op.drop_table("strategy_data_snapshots")
    op.drop_index("ix_strategy_versions_strategy_id", table_name="strategy_versions")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
