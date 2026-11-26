"""Alert centre: each person's own read and dismissed marks on monitoring alerts.

- ``monitoring_alert_reader_state``: one row per person and alert, with when they read or
  dismissed it and the alert's event time and severity at that moment, so a recurrence or an
  escalation brings the alert back.

Expand-only; the downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0089_alert_reader_state"
down_revision = "0087_lng4_options_demurrage"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "monitoring_alert_reader_state",
        sa.Column("principal_id", sa.String(64), primary_key=True),
        sa.Column("alert_id", sa.String(128), primary_key=True),
        sa.Column("read_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_event_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_severity", sa.String(16), nullable=True),
        sa.Column("dismissed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_event_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_severity", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("monitoring_alert_reader_state")
