"""Storage and nomination master data for runtime decision composition (R34A)."""

import sqlalchemy as sa

from alembic import op

revision = "0023_storage_nomination_masters"
down_revision = "0022_identity_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storage_facility_masters",
        sa.Column("facility_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("market_hub", sa.String(64), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("minimum_inventory_mwh", sa.Float(), nullable=False),
        sa.Column("maximum_inventory_mwh", sa.Float(), nullable=False),
        sa.Column("maximum_injection_mwh", sa.Float(), nullable=False),
        sa.Column("maximum_withdrawal_mwh", sa.Float(), nullable=False),
        sa.Column("injection_efficiency", sa.Float(), nullable=False),
        sa.Column("withdrawal_efficiency", sa.Float(), nullable=False),
        sa.Column("injection_cost_gbp_mwh", sa.Float(), nullable=False),
        sa.Column("withdrawal_cost_gbp_mwh", sa.Float(), nullable=False),
        sa.Column("terminal_inventory_mwh", sa.Float(), nullable=True),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("facility_id"),
    )
    op.create_table(
        "storage_inventory_observations",
        sa.Column("observation_id", sa.String(128), nullable=False),
        sa.Column("facility_id", sa.String(128), nullable=False),
        sa.Column("inventory_mwh", sa.Float(), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_table(
        "nomination_window_masters",
        sa.Column("window_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.Column("maximum_change_mwh", sa.Float(), nullable=True),
        sa.Column("maximum_change_pct", sa.Float(), nullable=True),
        sa.Column("valid_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("window_id"),
    )


def downgrade() -> None:
    op.drop_table("nomination_window_masters")
    op.drop_table("storage_inventory_observations")
    op.drop_table("storage_facility_masters")
