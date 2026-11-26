"""The market event outbox (M4, ADR Decision 28).

- ``market_events``: append-only canonical events, one row per revision, ordered by ``seq``,
  with the event's identity (``event_key``, ``revision``, ``event_id``), content hash, source,
  type, subject, input class, priority, dependency keys, payload and its market, publication
  and ingestion times.
- ``market_event_deliveries``: one row per event and consumer (status, attempts, next attempt,
  processing and notification times, result).

Expand-only; the downgrade drops only these two tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "0077_market_event_outbox"
down_revision = "0076_gas_day_nominations"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"

SEQ = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "market_events",
        sa.Column("seq", SEQ, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("event_key", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("supersedes_event_id", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("subject_key", sa.String(160), nullable=False),
        sa.Column("input_class", sa.String(16), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("dependency_keys", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("market_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.UniqueConstraint("event_key", "revision", name="uq_market_events_key_revision"),
    )
    op.create_index(
        "ix_market_events_subject", "market_events", ["subject_key", "ingested_at_utc"]
    )
    op.create_index("ix_market_events_source", "market_events", ["source_id", "ingested_at_utc"])
    op.create_table(
        "market_event_deliveries",
        sa.Column("consumer", sa.String(64), primary_key=True),
        sa.Column(
            "event_seq",
            SEQ,
            sa.ForeignKey("market_events.seq", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_market_event_deliveries_due",
        "market_event_deliveries",
        ["consumer", "status", "available_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_market_event_deliveries_due", table_name="market_event_deliveries")
    op.drop_table("market_event_deliveries")
    op.drop_index("ix_market_events_source", table_name="market_events")
    op.drop_index("ix_market_events_subject", table_name="market_events")
    op.drop_table("market_events")
