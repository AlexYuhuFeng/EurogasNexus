"""My gas day, stage 2: the nomination checklist.

- ``gas_day_nomination_events``: append-only statuses of each nomination step of a gas day
  (imported from the scheduling system or entered by hand, labelled and audited).
- ``upstream_resource_contracts.nomination_agent``: who nominates the contract's gas, as the
  contract names it (nullable; existing rows stay empty, nothing is invented).

Expand-only; the downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0076_gas_day_nominations"
down_revision = "0075_tso_tariff_entry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gas_day_nomination_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("gas_day", sa.Date(), nullable=False),
        sa.Column("line_ref", sa.String(160), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("quantity_mwh", sa.Float(), nullable=True),
        sa.Column("agent", sa.String(128), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_gas_day_nomination_events_day_ref", "gas_day_nomination_events",
        ["gas_day", "line_ref"],
    )
    with op.batch_alter_table("upstream_resource_contracts") as batch:
        batch.add_column(sa.Column("nomination_agent", sa.String(128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("upstream_resource_contracts") as batch:
        batch.drop_column("nomination_agent")
    op.drop_index("ix_gas_day_nomination_events_day_ref",
                  table_name="gas_day_nomination_events")
    op.drop_table("gas_day_nomination_events")
