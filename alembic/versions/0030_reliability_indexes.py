"""Add CR-11 evidence-backed reliability indexes.

Revision ID: 0030_reliability_indexes
Revises: 0029_enterprise_identity_v1
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_reliability_indexes"
down_revision: str | None = "0029_enterprise_identity_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_strategy_runs_strategy_started",
        "strategy_runs",
        ["strategy_id", "started_at_utc"],
    )
    op.create_index(
        "ix_strategy_runs_version_started",
        "strategy_runs",
        ["strategy_version_id", "started_at_utc"],
    )
    op.create_index(
        "ix_strategy_runs_type_started",
        "strategy_runs",
        ["run_type", "started_at_utc"],
    )
    op.create_index(
        "uq_user_sessions_token",
        "user_sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_audit_events_actor_action",
        "audit_events",
        ["principal", "action"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_actor_action", table_name="audit_events")
    op.drop_index("uq_user_sessions_token", table_name="user_sessions")
    op.drop_index("ix_strategy_runs_type_started", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_version_started", table_name="strategy_runs")
    op.drop_index("ix_strategy_runs_strategy_started", table_name="strategy_runs")
