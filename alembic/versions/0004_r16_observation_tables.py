"""Create observation, audit, and ingestion tracking tables (R16 hardening)."""

import sqlalchemy as sa

from alembic import op

revision = "0004_r16_observation_tables"
down_revision = "0003_r3_reference_network"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create observation domain tables for DB-backed routes."""

    op.create_table(
        "market_observations",
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("market_venue", sa.String(32), nullable=False),
        sa.Column("product", sa.String(32), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )

    op.create_table(
        "flow_observations",
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("point_id", sa.String(64), nullable=False),
        sa.Column("point_name", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("flow_mcm_d", sa.Float(), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )

    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("principal", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(128), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("event_ts_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_event_ts_utc", "audit_events", ["event_ts_utc"])

    op.create_table(
        "entitlement_decisions",
        sa.Column("decision_id", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_dataset", sa.String(128), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evaluated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )


def downgrade() -> None:
    """Drop observation domain tables."""

    op.drop_table("entitlement_decisions")
    op.drop_index("ix_audit_events_event_ts_utc", "audit_events")
    op.drop_index("ix_audit_events_event_type", "audit_events")
    op.drop_table("audit_events")
    op.drop_table("flow_observations")
    op.drop_table("market_observations")
