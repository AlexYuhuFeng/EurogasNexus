"""My gas day: the firm's physical schedule per gas day and delegated splits.

- ``gas_day_schedule_lines``: storage injection/withdrawal, customer offtake, exports and imports
  on held capacity for one gas day at one hub, as the firm's scheduling system holds them.
- ``gas_day_delegations``: part or all of a book's position at a hub handed to one trader for a
  span of gas days (checked against that trader's mandate when written; never widens it).

Expand-only; the downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0074_gas_day_schedule"
down_revision = "0073_contract_kinds"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "gas_day_schedule_lines",
        sa.Column("line_id", sa.String(128), primary_key=True),
        sa.Column("gas_day", sa.Date(), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("point", sa.String(160), nullable=True),
        sa.Column("counterparty", sa.String(160), nullable=True),
        sa.Column("contract_id", sa.String(128), nullable=True),
        sa.Column("quantity_mwh", sa.Float(), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gas_day_schedule_day_hub", "gas_day_schedule_lines", ["gas_day", "hub"])
    op.create_table(
        "gas_day_delegations",
        sa.Column("delegation_id", sa.String(64), primary_key=True),
        sa.Column("gas_day_from", sa.Date(), nullable=False),
        sa.Column("gas_day_to", sa.Date(), nullable=False),
        sa.Column("until_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("line_ref", sa.String(160), nullable=True),
        sa.Column("mwh_per_day", sa.Float(), nullable=True),
        sa.Column("trader", sa.String(128), nullable=False),
        sa.Column("mandate_id", sa.String(64), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("assigned_by", sa.String(128), nullable=False),
        sa.Column("assigned_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.String(128), nullable=True),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_gas_day_delegations_span", "gas_day_delegations", ["gas_day_from", "gas_day_to"]
    )


def downgrade() -> None:
    op.drop_index("ix_gas_day_delegations_span", table_name="gas_day_delegations")
    op.drop_table("gas_day_delegations")
    op.drop_index("ix_gas_day_schedule_day_hub", table_name="gas_day_schedule_lines")
    op.drop_table("gas_day_schedule_lines")
