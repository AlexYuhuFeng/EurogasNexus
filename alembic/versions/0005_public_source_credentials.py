"""Add public-source observation and provider credential tables."""

import sqlalchemy as sa

from alembic import op

revision = "0005_public_source_credentials"
down_revision = "0004_r16_observation_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create GIE observation tables and backend-owned credential storage."""

    op.create_table(
        "storage_observations",
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("source_dataset", sa.String(16), nullable=False),
        sa.Column("facility_id", sa.String(64), nullable=False),
        sa.Column("facility_name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("inventory_twh", sa.Float(), nullable=True),
        sa.Column("working_capacity_twh", sa.Float(), nullable=True),
        sa.Column("fill_pct", sa.Float(), nullable=True),
        sa.Column("injection_twh_d", sa.Float(), nullable=True),
        sa.Column("withdrawal_twh_d", sa.Float(), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )

    op.create_table(
        "lng_observations",
        sa.Column("observation_id", sa.String(64), nullable=False),
        sa.Column("source_dataset", sa.String(16), nullable=False),
        sa.Column("terminal_id", sa.String(64), nullable=False),
        sa.Column("terminal_name", sa.String(128), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("inventory_twh", sa.Float(), nullable=True),
        sa.Column("send_out_twh_d", sa.Float(), nullable=True),
        sa.Column("dtmi_pct", sa.Float(), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )

    op.create_table(
        "provider_credentials",
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("redacted_preview", sa.String(32), nullable=False),
        sa.Column("credential_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_tested_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(32), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("provider_id"),
    )


def downgrade() -> None:
    """Drop public-source observation and credential tables."""

    op.drop_table("provider_credentials")
    op.drop_table("lng_observations")
    op.drop_table("storage_observations")
