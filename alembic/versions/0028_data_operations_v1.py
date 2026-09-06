"""Add CR-09 production data-operations persistence.

Revision ID: 0028_data_operations_v1
Revises: 0027_shadow_runtime_v1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0028_data_operations_v1"
down_revision: str | None = "0027_shadow_runtime_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_ingestion_run_columns() -> None:
    """Extend ingestion_runs without rewriting any historical row."""

    op.add_column(
        "ingestion_runs",
        sa.Column("source_id", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("dataset", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "trigger_type",
            sa.String(length=32),
            nullable=False,
            server_default="MANUAL",
        ),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("requested_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("scheduled_for_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("window_start_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("window_end_utc", sa.DateTime(timezone=True), nullable=True),
    )
    for column_name in (
        "attempt_number",
        "rows_received",
        "rows_accepted",
        "rows_rejected",
        "rows_inserted",
        "rows_updated",
        "duplicate_count",
        "quality_warning_count",
        "quality_error_count",
    ):
        server_default = "1" if column_name == "attempt_number" else "0"
        op.add_column(
            "ingestion_runs",
            sa.Column(
                column_name,
                sa.Integer(),
                nullable=False,
                server_default=server_default,
            ),
        )
    op.add_column(
        "ingestion_runs",
        sa.Column("error_category", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("error_code", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("adapter_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("retry_of_run_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("lineage_refs", sa.JSON(), nullable=True),
    )


def _add_ingestion_run_indexes() -> None:
    op.create_index(
        "ix_ingestion_runs_source_started",
        "ingestion_runs",
        ["source_id", "started_at_utc"],
    )
    op.create_index(
        "ix_ingestion_runs_status_scheduled",
        "ingestion_runs",
        ["status", "scheduled_for_utc"],
    )
    op.create_index(
        "uq_ingestion_runs_scheduled_source",
        "ingestion_runs",
        ["source_id", "scheduled_for_utc"],
        unique=True,
        postgresql_where=sa.text("trigger_type = 'SCHEDULED'"),
    )


def _source_runtime_states() -> None:
    op.create_table(
        "source_runtime_states",
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("dataset", sa.String(128), nullable=False),
        sa.Column("source_class", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("circuit_state", sa.String(32), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_category", sa.String(40), nullable=True),
        sa.Column("last_error_code", sa.String(96), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("activated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_probe_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("freshness_state", sa.String(32), nullable=False),
        sa.Column("source_age_seconds", sa.Float(), nullable=True),
        sa.Column("ingestion_lag_seconds", sa.Float(), nullable=True),
        sa.Column("pipeline_lag_seconds", sa.Float(), nullable=True),
        sa.Column("last_quality_result", sa.String(32), nullable=False),
        sa.Column("quality_warning_count", sa.Integer(), nullable=False),
        sa.Column("quality_error_count", sa.Integer(), nullable=False),
        sa.Column("last_quality_issue_count", sa.Integer(), nullable=False),
        sa.Column("entitlement_state", sa.String(32), nullable=False),
        sa.Column("certification_state", sa.String(32), nullable=False),
        sa.Column("adapter_version", sa.String(64), nullable=False),
        sa.Column("schedule_json", sa.JSON(), nullable=False),
        sa.Column("freshness_policy_json", sa.JSON(), nullable=False),
        sa.Column("retry_policy_json", sa.JSON(), nullable=False),
        sa.Column("rate_limit_policy_json", sa.JSON(), nullable=False),
        sa.Column("circuit_policy_json", sa.JSON(), nullable=False),
        sa.Column("calendar", sa.String(32), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(
        "ix_source_runtime_enabled_next",
        "source_runtime_states",
        ["enabled", "next_run_at_utc"],
    )
    op.create_index(
        "ix_source_runtime_freshness",
        "source_runtime_states",
        ["freshness_state", "updated_at_utc"],
    )
    op.create_index(
        "ix_source_runtime_circuit",
        "source_runtime_states",
        ["circuit_state", "recovery_probe_at_utc"],
    )


def _ingestion_run_issues() -> None:
    op.create_table(
        "ingestion_run_issues",
        sa.Column("issue_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("quality_code", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("field", sa.String(128), nullable=False),
        sa.Column("observation_reference", sa.String(256), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("rule_version", sa.String(48), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["ingestion_runs.run_id"]),
        sa.PrimaryKeyConstraint("issue_id"),
    )
    op.create_index(
        "ix_ingestion_run_issues_run",
        "ingestion_run_issues",
        ["run_id", "created_at_utc"],
    )


def _data_operations_heartbeat() -> None:
    op.create_table(
        "data_operations_heartbeat",
        sa.Column("heartbeat_id", sa.String(64), nullable=False),
        sa.Column("last_heartbeat_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sources_scheduled", sa.Integer(), nullable=False),
        sa.Column("sources_healthy", sa.Integer(), nullable=False),
        sa.Column("sources_late", sa.Integer(), nullable=False),
        sa.Column("sources_stale", sa.Integer(), nullable=False),
        sa.Column("sources_failed", sa.Integer(), nullable=False),
        sa.Column("certification_gaps", sa.Integer(), nullable=False),
        sa.Column("entitlement_failures", sa.Integer(), nullable=False),
        sa.Column("backlog_depth", sa.Integer(), nullable=False),
        sa.Column("oldest_overdue_seconds", sa.Float(), nullable=True),
        sa.Column("due_count", sa.Integer(), nullable=False),
        sa.Column("claimed_count", sa.Integer(), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("heartbeat_id"),
    )


def _extend_provider_certifications() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else "postgresql"
    if dialect == "sqlite":
        with op.batch_alter_table("provider_certifications") as batch:
            batch.drop_constraint(
                "uq_provider_certifications_source_system", type_="unique"
            )
            _certification_columns(batch)
            batch.create_unique_constraint(
                "uq_provider_certifications_scope",
                ["source_system", "dataset", "environment"],
            )
        return
    op.drop_constraint(
        "uq_provider_certifications_source_system",
        "provider_certifications",
        type_="unique",
    )
    _certification_columns(op)
    op.create_unique_constraint(
        "uq_provider_certifications_scope",
        "provider_certifications",
        ["source_system", "dataset", "environment"],
    )


def _certification_columns(target) -> None:
    target.add_column(
        "provider_certifications",
        sa.Column("dataset", sa.String(128), nullable=False, server_default=""),
    )
    target.add_column(
        "provider_certifications",
        sa.Column(
            "environment",
            sa.String(32),
            nullable=False,
            server_default="deployment",
        ),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("adapter_version", sa.String(64), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("credential_label", sa.String(128), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("entitlement_scope", sa.String(64), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("sample_period_start_utc", sa.DateTime(timezone=True), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("sample_period_end_utc", sa.DateTime(timezone=True), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("tests_performed", sa.JSON(), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    target.add_column(
        "provider_certifications",
        sa.Column("evidence_ref", sa.String(256), nullable=True),
    )


def upgrade() -> None:
    _add_ingestion_run_columns()
    _add_ingestion_run_indexes()
    _source_runtime_states()
    _ingestion_run_issues()
    _data_operations_heartbeat()
    _extend_provider_certifications()


def downgrade() -> None:
    op.drop_index(
        "uq_ingestion_runs_scheduled_source", table_name="ingestion_runs"
    )
    op.drop_index(
        "ix_ingestion_runs_status_scheduled", table_name="ingestion_runs"
    )
    op.drop_index(
        "ix_ingestion_runs_source_started", table_name="ingestion_runs"
    )
    op.drop_table("data_operations_heartbeat")
    op.drop_index(
        "ix_ingestion_run_issues_run", table_name="ingestion_run_issues"
    )
    op.drop_table("ingestion_run_issues")
    op.drop_index(
        "ix_source_runtime_circuit", table_name="source_runtime_states"
    )
    op.drop_index(
        "ix_source_runtime_freshness", table_name="source_runtime_states"
    )
    op.drop_index(
        "ix_source_runtime_enabled_next", table_name="source_runtime_states"
    )
    op.drop_table("source_runtime_states")

    for column_name in (
        "source_id",
        "dataset",
        "trigger_type",
        "requested_at_utc",
        "scheduled_for_utc",
        "completed_at_utc",
        "window_start_utc",
        "window_end_utc",
        "attempt_number",
        "rows_received",
        "rows_accepted",
        "rows_rejected",
        "rows_inserted",
        "rows_updated",
        "duplicate_count",
        "quality_warning_count",
        "quality_error_count",
        "error_category",
        "error_code",
        "correlation_id",
        "adapter_version",
        "retry_of_run_id",
        "fallback_used",
        "lineage_refs",
    ):
        op.drop_column("ingestion_runs", column_name)
