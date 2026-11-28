"""Captured deals in the one position source: the exchange reference on ETRM trades, and a
per-deal physical or financial choice entered by hand.

- ``screen_order_observations.exchange_reference``: the exchange's trade id an ETRM extract
  carries for a trade (the layout file's ``etrm_reference_column``), so a captured deal and the
  same deal loaded from the ETRM are recognised as one deal by that reference first.
- ``deal_position_kinds``: a person's choice that a captured deal counts as physical or
  financial in the position, overriding the rule file (``reference_data/desk``); every choice
  is kept (a later one supersedes it), with who made it and when.

Expand-only; the downgrade drops what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0098_deal_position_source"
down_revision = "0097_deal_capture"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"
reversibility_note = (
    "The downgrade drops the exchange reference held on ETRM trades (reload the ETRM extract "
    "to restore it) and the per-deal physical or financial choices entered by hand (they are "
    "also in the audit trail); the deals themselves are untouched."
)


def upgrade() -> None:
    with op.batch_alter_table("screen_order_observations") as batch:
        batch.add_column(sa.Column("exchange_reference", sa.String(128), nullable=True))
    op.create_table(
        "deal_position_kinds",
        sa.Column("choice_id", sa.String(32), primary_key=True),
        sa.Column("deal_key", sa.String(200), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("entered_by", sa.String(128), nullable=False),
        sa.Column("entered_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deal_position_kinds_key", "deal_position_kinds",
                    ["deal_key", "superseded_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_deal_position_kinds_key", table_name="deal_position_kinds")
    op.drop_table("deal_position_kinds")
    with op.batch_alter_table("screen_order_observations") as batch:
        batch.drop_column("exchange_reference")
