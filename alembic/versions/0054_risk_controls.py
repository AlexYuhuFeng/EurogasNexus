"""Credit lines, trader mandates, daily contract deliveries and LNG terminal terms."""

import sqlalchemy as sa

from alembic import op

revision = "0054_risk_controls"
down_revision = "0053_lng_cargo_regas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_lines",
        sa.Column("counterparty_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("legal_entity", sa.String(64), nullable=True),
        sa.Column("limit_amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("collateral_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rating", sa.String(16), nullable=True),
        sa.Column("contract_ids", sa.JSON(), nullable=True),
        sa.Column("receivable_days", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trader_mandates",
        sa.Column("mandate_id", sa.String(64), primary_key=True),
        sa.Column("trader", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("book_ids", sa.JSON(), nullable=True),
        sa.Column("hubs", sa.JSON(), nullable=True),
        sa.Column("max_net_mwh_per_month", sa.Float(), nullable=True),
        sa.Column("max_tenor_months", sa.Integer(), nullable=True),
        sa.Column("physical_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("financial_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "contract_daily_deliveries",
        sa.Column("contract_id", sa.String(128), primary_key=True),
        sa.Column("gas_day", sa.Date(), primary_key=True),
        sa.Column("nominated_mwh", sa.Float(), nullable=True),
        sa.Column("allocated_mwh", sa.Float(), nullable=True),
        sa.Column("tso", sa.String(64), nullable=True),
        sa.Column("point", sa.String(160), nullable=True),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "lng_terminal_terms",
        sa.Column("terminal_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("regas_tariff_per_mwh", sa.Float(), nullable=False),
        sa.Column("entry_tariff_per_mwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fuel_retention_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("port_costs_per_cargo", sa.Float(), nullable=False, server_default="0"),
        sa.Column("other_per_mwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("extra_sailing_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_note", sa.String(256), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("lng_terminal_terms")
    op.drop_table("contract_daily_deliveries")
    op.drop_table("trader_mandates")
    op.drop_table("credit_lines")
