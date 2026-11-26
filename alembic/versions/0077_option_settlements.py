"""Gas option settlements: end-of-day settlement per strike with its implied volatility.

- ``option_settlements``: one row per source, hub, contract, trade date, strike and call/put,
  from a licensed exchange or vendor export or the demo simulator (``simulated`` true).

Expand-only; the downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0077_option_settlements"
down_revision = "0076_gas_day_nominations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "option_settlements",
        sa.Column("settlement_id", sa.String(64), primary_key=True),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("venue", sa.String(32), nullable=False),
        sa.Column("hub", sa.String(8), nullable=False),
        sa.Column("contract", sa.String(24), nullable=False),
        sa.Column("product_kind", sa.String(16), nullable=False),
        sa.Column("delivery_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("premium_style", sa.String(16), nullable=False),
        sa.Column("option_type", sa.String(1), nullable=False),
        sa.Column("strike", sa.Float(), nullable=False),
        sa.Column("settlement_price", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("underlying_price", sa.Float(), nullable=True),
        sa.Column("underlying_basis", sa.String(24), nullable=True),
        sa.Column("implied_vol", sa.Float(), nullable=True),
        sa.Column("iv_basis", sa.String(16), nullable=True),
        sa.Column("iv_reason", sa.String(32), nullable=True),
        sa.Column("forward_delta", sa.Float(), nullable=True),
        sa.Column("open_interest", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("freshness", sa.String(24), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint(
            "source_system",
            "hub",
            "contract",
            "trade_date",
            "strike",
            "option_type",
            name="uq_option_settlement_key",
        ),
        sa.CheckConstraint("option_type IN ('C', 'P')", name="ck_option_settlement_type"),
        sa.CheckConstraint(
            "premium_style IN ('futures_style', 'premium')", name="ck_option_settlement_style"
        ),
        sa.CheckConstraint("strike > 0", name="ck_option_settlement_strike"),
        sa.CheckConstraint("settlement_price >= 0", name="ck_option_settlement_price"),
    )
    op.create_index("ix_option_settlements_hub_day", "option_settlements", ["hub", "trade_date"])


def downgrade() -> None:
    op.drop_index("ix_option_settlements_hub_day", table_name="option_settlements")
    op.drop_table("option_settlements")
