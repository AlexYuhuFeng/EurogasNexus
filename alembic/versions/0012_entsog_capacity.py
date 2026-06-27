"""Add ENTSOG capacity observation storage."""

import sqlalchemy as sa

from alembic import op

revision = "0012_entsog_capacity"
down_revision = "0011_reference_source_lineage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capacity_observations",
        sa.Column("observation_id", sa.String(96), primary_key=True),
        sa.Column("point_id", sa.String(64), nullable=False),
        sa.Column("point_name", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("capacity_type", sa.String(32), nullable=False),
        sa.Column("capacity_mcm_d", sa.Float(), nullable=False),
        sa.Column("original_value", sa.Float(), nullable=True),
        sa.Column("original_unit", sa.String(32), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=True),
        sa.Column("freshness", sa.String(16), nullable=False),
        sa.Column("research_only", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_capacity_observations_point_period",
        "capacity_observations",
        ["point_id", "period_start_utc"],
    )
    op.create_index(
        "ix_capacity_observations_type_period",
        "capacity_observations",
        ["capacity_type", "period_start_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_capacity_observations_type_period", "capacity_observations")
    op.drop_index("ix_capacity_observations_point_period", "capacity_observations")
    op.drop_table("capacity_observations")
