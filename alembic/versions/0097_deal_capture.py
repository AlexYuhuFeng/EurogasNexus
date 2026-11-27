"""Deal capture from exchange exports, the end-of-day close, daily packs, credit guarantees.

- ``deal_import_files``: one export file received and what it gave.
- ``deal_import_problems``: each row of a file that could not be read, with the reason.
- ``captured_deals``: every version of every captured deal (exact decimals; nothing deleted).
- ``deal_day_closes``: a business day closed for a book, with the acknowledged differences.
- ``daily_packs``: the files of a daily pack queued for e-mail.
- ``credit_lines``: ``guarantee_amount`` (exact) and ``guarantee_expiry``.

Expand-only; the downgrade drops what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0097_deal_capture"
down_revision = "0096_retention_by_class"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"
reversibility_note = (
    "The downgrade drops the captured deals, their import files and problems, the day closes, "
    "the queued daily packs and the credit lines' guarantee amount and expiry. Export them "
    "first (the blotter's CSV, the ETRM entry sheet) or restore the pre-upgrade backup; the "
    "ETRM keeps the official record of the deals."
)


def upgrade() -> None:
    op.create_table(
        "deal_import_files",
        sa.Column("file_id", sa.String(32), primary_key=True),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("format_name", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("received_by", sa.String(128), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_new", sa.Integer(), nullable=False),
        sa.Column("rows_amended", sa.Integer(), nullable=False),
        sa.Column("rows_cancelled", sa.Integer(), nullable=False),
        sa.Column("rows_duplicate", sa.Integer(), nullable=False),
        sa.Column("rows_unreadable", sa.Integer(), nullable=False),
    )
    op.create_table(
        "deal_import_problems",
        sa.Column("problem_id", sa.String(32), primary_key=True),
        sa.Column("file_id", sa.String(32), nullable=False),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("field_name", sa.String(48), nullable=True),
        sa.Column("raw_value", sa.String(200), nullable=True),
        sa.Column("raw_row", sa.String(2000), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(128), nullable=True),
    )
    op.create_index("ix_deal_import_problems_file_id", "deal_import_problems", ["file_id"])
    op.create_index("ix_deal_import_problems_day", "deal_import_problems", ["business_date"])
    op.create_table(
        "captured_deals",
        sa.Column("version_id", sa.String(32), primary_key=True),
        sa.Column("deal_key", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("venue_trade_id", sa.String(128), nullable=False),
        sa.Column("leg_id", sa.String(16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("trade_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trader", sa.String(128), nullable=False),
        sa.Column("counterparty", sa.String(160), nullable=False),
        sa.Column("cleared", sa.Boolean(), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("product", sa.String(32), nullable=False),
        sa.Column("delivery_start", sa.Date(), nullable=False),
        sa.Column("delivery_end", sa.Date(), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("volume", sa.Numeric(20, 6), nullable=False),
        sa.Column("volume_unit", sa.String(16), nullable=False),
        sa.Column("total_mwh", sa.Numeric(20, 6), nullable=False),
        sa.Column("price", sa.Numeric(28, 10), nullable=False),
        sa.Column("price_currency", sa.String(3), nullable=False),
        sa.Column("price_unit", sa.String(16), nullable=False),
        sa.Column("physical", sa.Boolean(), nullable=False),
        sa.Column("instrument", sa.String(16), nullable=False),
        sa.Column("fees", sa.Numeric(28, 10), nullable=True),
        sa.Column("fee_currency", sa.String(3), nullable=True),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("origin", sa.String(8), nullable=False),
        sa.Column("file_id", sa.String(32), nullable=True),
        sa.Column("file_name", sa.String(256), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("entered_by_hand", sa.JSON(), nullable=True),
        sa.Column("entered_by", sa.String(128), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_reason", sa.String(200), nullable=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.UniqueConstraint("deal_key", "version", name="uq_captured_deals_version"),
    )
    op.create_index("ix_captured_deals_day", "captured_deals",
                    ["trade_date", "superseded_at_utc"])
    op.create_index("ix_captured_deals_key", "captured_deals", ["deal_key"])
    op.create_table(
        "deal_day_closes",
        sa.Column("close_id", sa.String(32), primary_key=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("closed_by", sa.String(128), nullable=False),
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("etrm_file_name", sa.String(256), nullable=False),
        sa.Column("etrm_sha256", sa.String(64), nullable=False),
        sa.Column("differences", sa.JSON(), nullable=False),
        sa.Column("figures", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("superseded_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_deal_day_closes_day", "deal_day_closes", ["business_date", "book_id"])
    op.create_table(
        "daily_packs",
        sa.Column("pack_id", sa.String(32), primary_key=True),
        sa.Column("notification_id", sa.String(64), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("trigger", sa.String(16), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scope_note", sa.String(500), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("pdf", sa.LargeBinary(), nullable=False),
        sa.Column("xlsx", sa.LargeBinary(), nullable=False),
        sa.Column("sent_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_daily_packs_notification_id", "daily_packs", ["notification_id"])
    with op.batch_alter_table("credit_lines") as batch:
        batch.add_column(sa.Column("guarantee_amount", sa.Numeric(28, 10), nullable=True))
        batch.add_column(sa.Column("guarantee_expiry", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("credit_lines") as batch:
        batch.drop_column("guarantee_expiry")
        batch.drop_column("guarantee_amount")
    op.drop_index("ix_daily_packs_notification_id", table_name="daily_packs")
    op.drop_table("daily_packs")
    op.drop_index("ix_deal_day_closes_day", table_name="deal_day_closes")
    op.drop_table("deal_day_closes")
    op.drop_index("ix_captured_deals_key", table_name="captured_deals")
    op.drop_index("ix_captured_deals_day", table_name="captured_deals")
    op.drop_table("captured_deals")
    op.drop_index("ix_deal_import_problems_day", table_name="deal_import_problems")
    op.drop_index("ix_deal_import_problems_file_id", table_name="deal_import_problems")
    op.drop_table("deal_import_problems")
    op.drop_table("deal_import_files")
