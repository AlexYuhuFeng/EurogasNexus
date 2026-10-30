"""Store power-system observations: day-ahead prices, load, wind, solar, gas generation.

Gas burned for power is a large and weather-sensitive share of European gas demand. These
series are its drivers; they enter point-in-time datasets with the source document's
creation time as availability.
"""

import sqlalchemy as sa

from alembic import op

revision = "0049_power_observations"
down_revision = "0048_observation_time_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "power_observations",
        sa.Column("observation_id", sa.String(96), primary_key=True),
        sa.Column("zone", sa.String(32), nullable=False),
        sa.Column("metric", sa.String(48), nullable=False),
        sa.Column("process_type", sa.String(8), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_power_observations_zone_metric_period",
        "power_observations",
        ["zone", "metric", sa.text("period_start_utc DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_power_observations_zone_metric_period", table_name="power_observations")
    op.drop_table("power_observations")
