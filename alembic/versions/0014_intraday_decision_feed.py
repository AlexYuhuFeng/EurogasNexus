"""Add normalized intraday market quotes and decision snapshots.

Revision ID: 0014_intraday_decision_feed
Revises: 0013_gie_lng_dtmi_energy
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_intraday_decision_feed"
down_revision: str | None = "0013_gie_lng_dtmi_energy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_quotes",
        sa.Column("quote_id", sa.String(128), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        sa.Column("venue", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.String(128), nullable=False),
        sa.Column("hub", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("delivery_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bid_price", sa.Float(), nullable=True),
        sa.Column("ask_price", sa.Float(), nullable=True),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("bid_quantity_mwh", sa.Float(), nullable=True),
        sa.Column("ask_quantity_mwh", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("freshness", sa.String(32), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("quote_id"),
    )
    op.create_index(
        "ix_market_quotes_lookup",
        "market_quotes",
        ["hub", "product", "source_system", "observed_at_utc"],
    )
    op.create_index(
        "ix_market_quotes_observed_at",
        "market_quotes",
        ["observed_at_utc"],
    )

    op.create_table(
        "company_tso_access",
        sa.Column("access_id", sa.String(128), nullable=False),
        sa.Column("tso", sa.String(128), nullable=False),
        sa.Column("market_area", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("access_id"),
    )
    op.create_index(
        "ix_company_tso_access_lookup",
        "company_tso_access",
        ["tso", "status", "valid_from_utc"],
    )

    op.create_table(
        "intraday_opportunities",
        sa.Column("opportunity_id", sa.String(128), nullable=False),
        sa.Column("scan_id", sa.String(128), nullable=False),
        sa.Column("opportunity_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("buy_quote_id", sa.String(128), nullable=False),
        sa.Column("sell_quote_id", sa.String(128), nullable=False),
        sa.Column("route_id", sa.String(128), nullable=False),
        sa.Column("route_name", sa.String(256), nullable=False),
        sa.Column("buy_venue", sa.String(64), nullable=False),
        sa.Column("sell_venue", sa.String(64), nullable=False),
        sa.Column("buy_hub", sa.String(32), nullable=False),
        sa.Column("sell_hub", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("delivery_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comparison_currency", sa.String(8), nullable=False),
        sa.Column("comparison_unit", sa.String(32), nullable=False),
        sa.Column("buy_ask", sa.Float(), nullable=False),
        sa.Column("sell_bid", sa.Float(), nullable=False),
        sa.Column("gross_spread", sa.Float(), nullable=False),
        sa.Column("route_cost", sa.Float(), nullable=True),
        sa.Column("trading_cost", sa.Float(), nullable=False),
        sa.Column("risk_buffer", sa.Float(), nullable=False),
        sa.Column("net_margin", sa.Float(), nullable=True),
        sa.Column("max_quantity_mwh", sa.Float(), nullable=True),
        sa.Column("indicative_net_value", sa.Float(), nullable=True),
        sa.Column("quote_age_seconds", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("cost_components", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("missing_inputs", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("detected_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("opportunity_id"),
    )
    op.create_index(
        "ix_intraday_opportunities_status_time",
        "intraday_opportunities",
        ["status", "detected_at_utc"],
    )
    op.create_index(
        "ix_intraday_opportunities_route_product",
        "intraday_opportunities",
        ["route_id", "product", "detected_at_utc"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intraday_opportunities_route_product",
        table_name="intraday_opportunities",
    )
    op.drop_index(
        "ix_intraday_opportunities_status_time",
        table_name="intraday_opportunities",
    )
    op.drop_table("intraday_opportunities")
    op.drop_index("ix_company_tso_access_lookup", table_name="company_tso_access")
    op.drop_table("company_tso_access")
    op.drop_index("ix_market_quotes_observed_at", table_name="market_quotes")
    op.drop_index("ix_market_quotes_lookup", table_name="market_quotes")
    op.drop_table("market_quotes")
