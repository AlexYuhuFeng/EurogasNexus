"""Regas auction cases: the auctions the desk works and the snapshots it saved of them.

- ``regas_auction_cases``: one row per regas slot auction (terminal, slot, auction window, the
  cargo owner's offer, send-out profile and cost lines with their sources in ``inputs``), its
  book, and how it closed (won, lost, lapsed) with a note and, for a won slot, the position
  seam (recorded, never booked).
- ``regas_auction_snapshots``: the answer as it was each time a trader acted on it (inputs,
  prices with their times and sources, result, the valuation snapshot read through).

Expand-only; the downgrade drops both tables. Chained after ``0100_watched_publications``.
"""

import sqlalchemy as sa

from alembic import op

revision = "0101_regas_auction_cases"
down_revision = "0100_watched_publications"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"
reversibility_note = (
    "The downgrade drops the regas auction cases and their saved snapshots; export them first "
    "(the case report, PDF and XLSX, holds each case and its snapshots). Nothing else reads "
    "them: no deal, slot or hedge was booked from a case."
)


def upgrade() -> None:
    op.create_table(
        "regas_auction_cases",
        sa.Column("case_id", sa.String(40), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("terminal_id", sa.String(128), nullable=False),
        sa.Column("terminal_name", sa.String(200), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("counterparty_id", sa.String(64), nullable=True),
        sa.Column("counterparty_name", sa.String(200), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("auction_opens_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auction_closes_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("offer_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notice_key", sa.String(160), nullable=True),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_by", sa.String(128), nullable=True),
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_note", sa.String(1000), nullable=True),
        sa.Column("position_seam", sa.JSON(), nullable=True),
        sa.CheckConstraint("state IN ('open', 'won', 'lost', 'lapsed')",
                           name="ck_regas_auction_cases_state"),
    )
    op.create_index("ix_regas_auction_cases_book_id", "regas_auction_cases", ["book_id"])
    op.create_index("ix_regas_auction_cases_state", "regas_auction_cases",
                    ["state", "auction_closes_at_utc"])
    op.create_table(
        "regas_auction_snapshots",
        sa.Column("snapshot_id", sa.String(40), primary_key=True),
        sa.Column("case_id", sa.String(40), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("saved_by", sa.String(128), nullable=False),
        sa.Column("saved_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("prices", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("valuation_snapshot_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_regas_auction_snapshots_book_id", "regas_auction_snapshots", ["book_id"])
    op.create_index("ix_regas_auction_snapshots_case", "regas_auction_snapshots",
                    ["case_id", "saved_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_regas_auction_snapshots_case", table_name="regas_auction_snapshots")
    op.drop_index("ix_regas_auction_snapshots_book_id", table_name="regas_auction_snapshots")
    op.drop_table("regas_auction_snapshots")
    op.drop_index("ix_regas_auction_cases_state", table_name="regas_auction_cases")
    op.drop_index("ix_regas_auction_cases_book_id", table_name="regas_auction_cases")
    op.drop_table("regas_auction_cases")
