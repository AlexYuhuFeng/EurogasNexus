"""Hedges the desk holds against its LNG cargoes (cargo in transit, ADR Decision 29).

- ``lng_cargo_hedges``: hub, delivery month and signed MWh per cargo; a replaced set is
  retired, never deleted.

Expand-only; the downgrade drops only this table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0078_lng_cargo_hedges"
down_revision = "0077_market_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lng_cargo_hedges",
        sa.Column("link_id", sa.String(64), primary_key=True),
        sa.Column("cargo_id", sa.String(96), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("delivery_month", sa.String(7), nullable=False),
        sa.Column("mwh", sa.Numeric(18, 3), nullable=False),
        sa.Column("reference", sa.String(160), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("retired_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(128), nullable=True),
    )
    op.create_index(
        "ix_lng_cargo_hedges_cargo", "lng_cargo_hedges", ["cargo_id", "retired_at_utc"]
    )


def downgrade() -> None:
    op.drop_index("ix_lng_cargo_hedges_cargo", table_name="lng_cargo_hedges")
    op.drop_table("lng_cargo_hedges")
