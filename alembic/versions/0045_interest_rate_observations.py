"""Add overnight benchmark interest-rate fixings (SONIA, €STR, SOFR).

Additive: one new table holding the administrators' published daily fixings, used
to resolve contract financing rates (benchmark + spread) for early-cash value.
Downgrade drops the table; fixings can be re-ingested from the public sources.
"""

import sqlalchemy as sa

from alembic import op

revision = "0045_interest_rate_observations"
down_revision = "0044_entsog_native_rates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interest_rate_observations",
        sa.Column("observation_id", sa.String(64), primary_key=True),
        sa.Column("benchmark_id", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("value_date", sa.Date(), nullable=False),
        sa.Column("rate_pct", sa.Float(), nullable=False),
        sa.Column("day_count", sa.String(16), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(128), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "benchmark_id", "value_date", name="uq_interest_rate_benchmark_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("interest_rate_observations")
