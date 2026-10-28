"""Add the append-only National Gas NTS actual-demand target table.

The revision is additive: it creates one table and two query indexes, and does
not activate a source, scheduler, API surface, or entitlement.
"""

import sqlalchemy as sa

from alembic import op

revision = "0042_national_gas_actual_demand"
down_revision = "0041_job_owner_identity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "national_gas_actual_demand",
        sa.Column("record_id", sa.String(64), primary_key=True),
        sa.Column("source_publication_id", sa.String(64), nullable=False, unique=True),
        sa.Column("provider_item_id", sa.String(32), nullable=False),
        sa.Column("series_key", sa.String(64), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("term", sa.String(8), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("gas_day", sa.Date(), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_text", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applicable_at_raw", sa.String(32), nullable=False),
        sa.Column("generated_at_raw", sa.String(32), nullable=False),
        sa.Column("applicable_at_naive", sa.DateTime(timezone=False), nullable=False),
        sa.Column("generated_at_naive", sa.DateTime(timezone=False), nullable=False),
        sa.Column("quality_indicator", sa.String(8), nullable=True),
        sa.Column("provisional_status", sa.String(40), nullable=False),
        sa.Column("is_provisional", sa.Boolean(), nullable=True),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=False),
        sa.Column("hash_schema", sa.String(64), nullable=False),
        sa.CheckConstraint("region = 'GB_NTS'", name="ck_ng_actual_demand_region"),
        sa.CheckConstraint("unit = 'mscm'", name="ck_ng_actual_demand_unit"),
        sa.CheckConstraint("term IN ('D+1', 'D+6')", name="ck_ng_actual_demand_term"),
        sa.CheckConstraint(
            "length(value_text) > 0 AND length(value_text) <= 64",
            name="ck_ng_actual_demand_value_text",
        ),
        sa.CheckConstraint(
            "quality_indicator IS NULL OR "
            "(length(quality_indicator) > 0 AND length(quality_indicator) <= 8)",
            name="ck_ng_actual_demand_quality",
        ),
    )
    op.create_index(
        "ix_national_gas_actual_demand_series_gas_day",
        "national_gas_actual_demand",
        ["series_key", "gas_day"],
    )
    op.create_index(
        "ix_national_gas_actual_demand_published_utc",
        "national_gas_actual_demand",
        ["published_at_utc"],
    )


def downgrade():
    # Source revisions are immutable evidence; deleting the table loses them.
    raise RuntimeError(
        "National Gas actual-demand migration cannot be downgraded; "
        "restore an approved pre-migration backup instead."
    )
