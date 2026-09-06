"""Add production-grade shadow research runtime tables.

Revision ID: 0027_shadow_runtime_v1
Revises: 0026_backtest_engine_v1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0027_shadow_runtime_v1"
down_revision: str | None = "0026_backtest_engine_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _shadow_monitors() -> None:
    op.create_table(
        "strategy_shadow_monitors",
        sa.Column("shadow_monitor_id", sa.String(128), nullable=False),
        sa.Column("strategy_id", sa.String(128), nullable=False),
        sa.Column("strategy_version_id", sa.String(128), nullable=False),
        sa.Column("baseline_run_id", sa.String(128), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("schedule_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_evaluation_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_evaluation_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_evaluation_id", sa.String(128), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("health_state", sa.String(32), nullable=False),
        sa.Column("cumulative_shadow_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("current_exposure_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.strategy_id"]),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.strategy_version_id"]
        ),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["strategy_runs.run_id"]),
        sa.PrimaryKeyConstraint("shadow_monitor_id"),
    )
    op.create_index(
        "ix_shadow_monitors_state_next",
        "strategy_shadow_monitors",
        ["state", "next_evaluation_at_utc"],
    )
    op.create_index(
        "ix_shadow_monitors_strategy_id",
        "strategy_shadow_monitors",
        ["strategy_id"],
    )


def _shadow_evaluations() -> None:
    op.create_table(
        "strategy_shadow_evaluations",
        sa.Column("shadow_evaluation_id", sa.String(128), nullable=False),
        sa.Column("shadow_monitor_id", sa.String(128), nullable=False),
        sa.Column("strategy_version_id", sa.String(128), nullable=False),
        sa.Column("scheduled_for_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("gas_day", sa.String(16), nullable=True),
        sa.Column("gas_day_start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gas_day_end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", sa.String(128), nullable=True),
        sa.Column("candidate_id", sa.String(128), nullable=True),
        sa.Column("price_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("fx_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("resource_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("source_systems", sa.JSON(), nullable=False),
        sa.Column("freshness_json", sa.JSON(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("failure_class", sa.String(40), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shadow_monitor_id"], ["strategy_shadow_monitors.shadow_monitor_id"]
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"], ["strategy_versions.strategy_version_id"]
        ),
        sa.PrimaryKeyConstraint("shadow_evaluation_id"),
        sa.UniqueConstraint(
            "shadow_monitor_id",
            "scheduled_for_utc",
            name="uq_shadow_evaluation_schedule",
        ),
    )
    op.create_index(
        "ix_shadow_evaluations_monitor_time",
        "strategy_shadow_evaluations",
        ["shadow_monitor_id", "scheduled_for_utc"],
    )
    op.create_index(
        "ix_shadow_evaluations_state", "strategy_shadow_evaluations", ["state"]
    )


def _shadow_candidates() -> None:
    op.create_table(
        "strategy_shadow_candidates",
        sa.Column("candidate_id", sa.String(128), nullable=False),
        sa.Column("shadow_evaluation_id", sa.String(128), nullable=False),
        sa.Column("shadow_monitor_id", sa.String(128), nullable=False),
        sa.Column("strategy_version_id", sa.String(128), nullable=False),
        sa.Column("decision_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gas_day", sa.String(16), nullable=False),
        sa.Column("candidate_type", sa.String(64), nullable=False),
        sa.Column("market_context", sa.JSON(), nullable=False),
        sa.Column("hypothetical_direction", sa.String(32), nullable=False),
        sa.Column("hypothetical_quantity_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("expected_indicative_margin_gbp_mwh", sa.Float(), nullable=False),
        sa.Column("expected_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("reference_price_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("all_in_cost_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("risk_state", sa.String(32), nullable=False),
        sa.Column("evidence_state", sa.String(32), nullable=False),
        sa.Column("explanation_codes", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("blocker_references", sa.JSON(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shadow_evaluation_id"],
            ["strategy_shadow_evaluations.shadow_evaluation_id"],
        ),
        sa.PrimaryKeyConstraint("candidate_id"),
    )
    op.create_index(
        "ix_shadow_candidates_evaluation",
        "strategy_shadow_candidates",
        ["shadow_evaluation_id"],
    )
    op.create_index(
        "ix_shadow_candidates_decision_time",
        "strategy_shadow_candidates",
        ["decision_time_utc"],
    )


def _shadow_risk_checks() -> None:
    op.create_table(
        "strategy_shadow_risk_checks",
        sa.Column("risk_check_id", sa.String(128), nullable=False),
        sa.Column("shadow_evaluation_id", sa.String(128), nullable=False),
        sa.Column("control_id", sa.String(64), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=True),
        sa.Column("limit_value", sa.Float(), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shadow_evaluation_id"],
            ["strategy_shadow_evaluations.shadow_evaluation_id"],
        ),
        sa.PrimaryKeyConstraint("risk_check_id"),
    )
    op.create_index(
        "ix_shadow_risk_checks_evaluation",
        "strategy_shadow_risk_checks",
        ["shadow_evaluation_id"],
    )


def _shadow_outcomes() -> None:
    op.create_table(
        "strategy_shadow_outcomes",
        sa.Column("outcome_id", sa.String(128), nullable=False),
        sa.Column("candidate_id", sa.String(128), nullable=False),
        sa.Column("shadow_evaluation_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("pnl_basis", sa.String(40), nullable=False),
        sa.Column("gross_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("modeled_costs_gbp", sa.Float(), nullable=False),
        sa.Column("net_indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("settlement_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("maturation_note", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("matured_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["strategy_shadow_candidates.candidate_id"]
        ),
        sa.PrimaryKeyConstraint("outcome_id"),
    )
    op.create_index("ix_shadow_outcomes_state", "strategy_shadow_outcomes", ["state"])


def _shadow_alerts() -> None:
    op.create_table(
        "strategy_shadow_alerts",
        sa.Column("alert_id", sa.String(128), nullable=False),
        sa.Column("shadow_monitor_id", sa.String(128), nullable=False),
        sa.Column("shadow_evaluation_id", sa.String(128), nullable=True),
        sa.Column("alert_type", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("fingerprint", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("first_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("acknowledged_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(64), nullable=True),
        sa.Column("resolved_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shadow_monitor_id"], ["strategy_shadow_monitors.shadow_monitor_id"]
        ),
        sa.PrimaryKeyConstraint("alert_id"),
        sa.UniqueConstraint("fingerprint", name="uq_shadow_alert_fingerprint"),
    )
    op.create_index(
        "ix_shadow_alerts_monitor_state",
        "strategy_shadow_alerts",
        ["shadow_monitor_id", "state"],
    )


def _shadow_drift_and_heartbeat() -> None:
    op.create_table(
        "strategy_shadow_drift_snapshots",
        sa.Column("drift_snapshot_id", sa.String(128), nullable=False),
        sa.Column("shadow_monitor_id", sa.String(128), nullable=False),
        sa.Column("baseline_run_id", sa.String(128), nullable=True),
        sa.Column("observation_window_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shadow_monitor_id"], ["strategy_shadow_monitors.shadow_monitor_id"]
        ),
        sa.PrimaryKeyConstraint("drift_snapshot_id"),
    )
    op.create_index(
        "ix_shadow_drift_monitor_time",
        "strategy_shadow_drift_snapshots",
        ["shadow_monitor_id", "created_at_utc"],
    )
    op.create_table(
        "strategy_shadow_scheduler_heartbeat",
        sa.Column("heartbeat_id", sa.String(64), nullable=False),
        sa.Column("last_heartbeat_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scan_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_count", sa.Integer(), nullable=False),
        sa.Column("claimed_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_claim_count", sa.Integer(), nullable=False),
        sa.Column("active_monitor_count", sa.Integer(), nullable=False),
        sa.Column("oldest_overdue_seconds", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("heartbeat_id"),
    )


def upgrade() -> None:
    _shadow_monitors()
    _shadow_evaluations()
    _shadow_candidates()
    _shadow_risk_checks()
    _shadow_outcomes()
    _shadow_alerts()
    _shadow_drift_and_heartbeat()


def downgrade() -> None:
    op.drop_table("strategy_shadow_scheduler_heartbeat")
    op.drop_index(
        "ix_shadow_drift_monitor_time", table_name="strategy_shadow_drift_snapshots"
    )
    op.drop_table("strategy_shadow_drift_snapshots")
    op.drop_index(
        "ix_shadow_alerts_monitor_state", table_name="strategy_shadow_alerts"
    )
    op.drop_table("strategy_shadow_alerts")
    op.drop_index("ix_shadow_outcomes_state", table_name="strategy_shadow_outcomes")
    op.drop_table("strategy_shadow_outcomes")
    op.drop_index(
        "ix_shadow_risk_checks_evaluation", table_name="strategy_shadow_risk_checks"
    )
    op.drop_table("strategy_shadow_risk_checks")
    op.drop_index(
        "ix_shadow_candidates_decision_time", table_name="strategy_shadow_candidates"
    )
    op.drop_index(
        "ix_shadow_candidates_evaluation", table_name="strategy_shadow_candidates"
    )
    op.drop_table("strategy_shadow_candidates")
    op.drop_index(
        "ix_shadow_evaluations_state", table_name="strategy_shadow_evaluations"
    )
    op.drop_index(
        "ix_shadow_evaluations_monitor_time",
        table_name="strategy_shadow_evaluations",
    )
    op.drop_table("strategy_shadow_evaluations")
    op.drop_index(
        "ix_shadow_monitors_strategy_id", table_name="strategy_shadow_monitors"
    )
    op.drop_index(
        "ix_shadow_monitors_state_next", table_name="strategy_shadow_monitors"
    )
    op.drop_table("strategy_shadow_monitors")
