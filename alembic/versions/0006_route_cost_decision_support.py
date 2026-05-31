"""Add route-cost decision-support tables."""

import sqlalchemy as sa

from alembic import op

revision = "0006_route_cost_decision_support"
down_revision = "0005_public_source_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fx_observations",
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("pair", sa.String(16), nullable=False),
        sa.Column("base_currency", sa.String(8), nullable=False),
        sa.Column("quote_currency", sa.String(8), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("rate_type", sa.String(32), nullable=False),
        sa.Column("value_date", sa.String(16), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_table(
        "tso_tariffs",
        sa.Column("tariff_id", sa.String(128), nullable=False),
        sa.Column("document_id", sa.String(128), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("tso", sa.String(128), nullable=False),
        sa.Column("market_area", sa.String(64), nullable=False),
        sa.Column("gas_year", sa.String(16), nullable=False),
        sa.Column("point_id", sa.String(128), nullable=False),
        sa.Column("source_point_name", sa.String(256), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("capacity_product", sa.String(32), nullable=False),
        sa.Column("firmness", sa.String(32), nullable=False),
        sa.Column("tariff_value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tariff_status", sa.String(32), nullable=False),
        sa.Column("source_table", sa.String(256), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tariff_id"),
    )
    op.create_table(
        "upstream_resource_contracts",
        sa.Column("contract_id", sa.String(128), nullable=False),
        sa.Column("contract_name", sa.String(256), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("delivery_point_name", sa.String(256), nullable=False),
        sa.Column("gas_year", sa.String(16), nullable=False),
        sa.Column("delivery_quantity_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("contract_price_gbp_mwh", sa.Float(), nullable=False),
        sa.Column("settlement_frequency", sa.String(32), nullable=False),
        sa.Column("upstream_payment_lag_days", sa.Integer(), nullable=False),
        sa.Column("screen_sale_cash_lag_days", sa.Integer(), nullable=False),
        sa.Column("delivery_tolerance_pct", sa.Float(), nullable=False),
        sa.Column("nomination_tolerance_pct", sa.Float(), nullable=False),
        sa.Column("tolerance_risk_allowance_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("annual_financing_rate_pct", sa.Float(), nullable=False),
        sa.Column("owned_entry_capacity_mwh_per_day", sa.Float(), nullable=True),
        sa.Column("owned_exit_capacity_mwh_per_day", sa.Float(), nullable=True),
        sa.Column("allowed_exit_points", sa.JSON(), nullable=False),
        sa.Column("eligible_sale_modes", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("contract_id"),
    )
    op.create_table(
        "capacity_profiles",
        sa.Column("capacity_profile_id", sa.String(128), nullable=False),
        sa.Column("contract_id", sa.String(128), nullable=False),
        sa.Column("point_name", sa.String(256), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("capacity_mwh_per_day", sa.Float(), nullable=False),
        sa.Column("firmness", sa.String(32), nullable=False),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("capacity_profile_id"),
    )
    op.create_table(
        "route_candidates",
        sa.Column("route_id", sa.String(128), nullable=False),
        sa.Column("route_name", sa.String(256), nullable=False),
        sa.Column("start_point_name", sa.String(256), nullable=False),
        sa.Column("target_point_name", sa.String(256), nullable=False),
        sa.Column("business_model", sa.String(64), nullable=False),
        sa.Column("route_legs", sa.JSON(), nullable=False),
        sa.Column("required_entry_point_name", sa.String(256), nullable=True),
        sa.Column("required_exit_point_name", sa.String(256), nullable=True),
        sa.Column("required_tso_access", sa.JSON(), nullable=False),
        sa.Column("source_systems", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("route_id"),
    )
    op.create_table(
        "live_market_marks",
        sa.Column("mark_id", sa.String(128), nullable=False),
        sa.Column("venue", sa.String(64), nullable=False),
        sa.Column("hub", sa.String(64), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("bid_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("ask_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("last_gbp_mwh", sa.Float(), nullable=True),
        sa.Column("mark_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(128), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("mark_id"),
    )
    op.create_table(
        "glossary_terms",
        sa.Column("term_id", sa.String(128), nullable=False),
        sa.Column("term", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("definition_en", sa.Text(), nullable=False),
        sa.Column("definition_zh_cn", sa.Text(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("related_terms", sa.JSON(), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("term_id"),
        sa.UniqueConstraint("term"),
    )


def downgrade() -> None:
    op.drop_table("glossary_terms")
    op.drop_table("live_market_marks")
    op.drop_table("route_candidates")
    op.drop_table("capacity_profiles")
    op.drop_table("upstream_resource_contracts")
    op.drop_table("tso_tariffs")
    op.drop_table("fx_observations")
