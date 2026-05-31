"""Add strategy-lab persistence tables."""

import sqlalchemy as sa

from alembic import op

revision = "0007_strategy_lab_foundation"
down_revision = "0006_route_cost_decision_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_definitions",
        sa.Column("strategy_id", sa.String(128), nullable=False),
        sa.Column("strategy_name", sa.String(256), nullable=False),
        sa.Column("strategy_family", sa.String(64), nullable=False),
        sa.Column("supported_run_modes", sa.JSON(), nullable=False),
        sa.Column("resource_filter", sa.JSON(), nullable=False),
        sa.Column("components", sa.JSON(), nullable=False),
        sa.Column("risk_control", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("strategy_id"),
    )
    op.create_table(
        "strategy_runs",
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("strategy_id", sa.String(128), nullable=False),
        sa.Column("run_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("result_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "strategy_allocation_targets",
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("market_bucket", sa.String(64), nullable=False),
        sa.Column("target_allocation_pct", sa.Float(), nullable=False),
        sa.Column("target_quantity_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("reference_price_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("expected_margin_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("target_id"),
    )
    op.create_table(
        "strategy_alerts",
        sa.Column("alert_id", sa.String(128), nullable=False),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("message_en", sa.Text(), nullable=False),
        sa.Column("message_zh_cn", sa.Text(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("alert_id"),
    )


def downgrade() -> None:
    op.drop_table("strategy_alerts")
    op.drop_table("strategy_allocation_targets")
    op.drop_table("strategy_runs")
    op.drop_table("strategy_definitions")
