"""Add market positioning observation tables."""

import sqlalchemy as sa

from alembic import op

revision = "0009_market_positioning_foundation"
down_revision = "0008_analysis_reporting_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "screen_order_observations",
        sa.Column("order_observation_id", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("venue", sa.String(64), nullable=False),
        sa.Column("account_label", sa.String(128), nullable=False),
        sa.Column("external_order_id", sa.String(128), nullable=False),
        sa.Column("side", sa.String(16), nullable=False),
        sa.Column("order_type", sa.String(32), nullable=False),
        sa.Column("hub", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("contract_code", sa.String(128), nullable=False),
        sa.Column("delivery_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quantity_mwh", sa.Float(), nullable=False),
        sa.Column("filled_quantity_mwh", sa.Float(), nullable=False),
        sa.Column("remaining_quantity_mwh", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("linked_strategy_id", sa.String(128), nullable=True),
        sa.Column("linked_resource_id", sa.String(128), nullable=True),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("order_observation_id"),
    )
    op.create_index(
        "ix_screen_order_observations_venue_hub_product",
        "screen_order_observations",
        ["venue", "hub", "product"],
    )
    op.create_index(
        "ix_screen_order_observations_observed_at",
        "screen_order_observations",
        ["observed_at_utc"],
    )

    op.create_table(
        "portfolio_pnl_snapshots",
        sa.Column("pnl_snapshot_id", sa.String(128), nullable=False),
        sa.Column("portfolio_id", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("strategy_id", sa.String(128), nullable=True),
        sa.Column("valuation_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("realized_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("unrealized_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("indicative_pnl_gbp", sa.Float(), nullable=False),
        sa.Column("cash_value_gbp", sa.Float(), nullable=False),
        sa.Column("market_value_gbp", sa.Float(), nullable=False),
        sa.Column("quantity_mwh", sa.Float(), nullable=False),
        sa.Column("valuation_basis", sa.String(64), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("pnl_snapshot_id"),
    )
    op.create_index(
        "ix_portfolio_pnl_snapshots_portfolio_time",
        "portfolio_pnl_snapshots",
        ["portfolio_id", "valuation_time_utc"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_pnl_snapshots_portfolio_time",
        table_name="portfolio_pnl_snapshots",
    )
    op.drop_table("portfolio_pnl_snapshots")
    op.drop_index(
        "ix_screen_order_observations_observed_at",
        table_name="screen_order_observations",
    )
    op.drop_index(
        "ix_screen_order_observations_venue_hub_product",
        table_name="screen_order_observations",
    )
    op.drop_table("screen_order_observations")
