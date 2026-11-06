"""Index audit events by (timestamp, event id) for the keyset investigation walk (#59)."""

from alembic import op

revision = "0061_audit_keyset_index"
down_revision = "0060_decision_due"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_audit_events_ts_id", "audit_events", ["event_ts_utc", "event_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_ts_id", table_name="audit_events")
