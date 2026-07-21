"""Add normalized visible monitoring alerts.

Revision ID: 0015_llm_monitoring_alerts
Revises: 0014_intraday_decision_feed
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_llm_monitoring_alerts"
down_revision: str | None = "0014_intraday_decision_feed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_alerts",
        sa.Column("alert_id", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(256), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("alert_type", sa.String(96), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("title_en", sa.String(256), nullable=False),
        sa.Column("title_zh_cn", sa.String(256), nullable=False),
        sa.Column("message_en", sa.Text(), nullable=False),
        sa.Column("message_zh_cn", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("event_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("llm_provider_id", sa.String(64), nullable=False),
        sa.Column("llm_status", sa.String(64), nullable=False),
        sa.Column("llm_summary_en", sa.Text(), nullable=True),
        sa.Column("llm_summary_zh_cn", sa.Text(), nullable=True),
        sa.Column("llm_last_attempt_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("alert_id"),
        sa.UniqueConstraint("fingerprint", name="uq_monitoring_alerts_fingerprint"),
    )
    op.create_index(
        "ix_monitoring_alerts_status_time",
        "monitoring_alerts",
        ["status", "detected_at_utc"],
    )
    op.create_index(
        "ix_monitoring_alerts_category_severity",
        "monitoring_alerts",
        ["category", "severity", "updated_at_utc"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monitoring_alerts_category_severity",
        table_name="monitoring_alerts",
    )
    op.drop_index("ix_monitoring_alerts_status_time", table_name="monitoring_alerts")
    op.drop_table("monitoring_alerts")
