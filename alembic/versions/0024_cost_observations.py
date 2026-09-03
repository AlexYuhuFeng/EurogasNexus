"""Generalized time-windowed cost observations."""

import sqlalchemy as sa

from alembic import op

revision = "0024_cost_observations"
down_revision = "0023_storage_nomination_masters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_observations",
        sa.Column("observation_id", sa.String(128), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", sa.String(128), nullable=False),
        sa.Column("observation_type", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("capacity_product", sa.String(32), nullable=True),
        sa.Column("firmness", sa.String(32), nullable=True),
        sa.Column("gas_year", sa.String(16), nullable=True),
        sa.Column("effective_from_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("document_id", sa.String(128), nullable=True),
        sa.Column("entitlement_scope", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False),
        sa.Column("superseded_by", sa.String(128), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("observation_id"),
    )
    op.create_index(
        "ix_cost_observations_scope_window",
        "cost_observations",
        ["scope_type", "scope_id", "effective_from_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_cost_observations_scope_window", table_name="cost_observations")
    op.drop_table("cost_observations")
