"""Add source metadata columns and observation indexes."""

import sqlalchemy as sa

from alembic import op

revision = "0010_source_observation_metadata"
down_revision = "0009_market_positioning"
branch_labels = None
depends_on = None


OBSERVATION_TABLES = (
    "market_observations",
    "fx_observations",
    "flow_observations",
    "storage_observations",
    "lng_observations",
)


def upgrade() -> None:
    for table in OBSERVATION_TABLES:
        op.add_column(table, sa.Column("source_record_id", sa.String(128), nullable=True))
        op.add_column(table, sa.Column("metadata_json", sa.JSON(), nullable=True))

    op.add_column("flow_observations", sa.Column("original_value", sa.Float(), nullable=True))
    op.add_column("flow_observations", sa.Column("original_unit", sa.String(32), nullable=True))

    op.create_index(
        "ix_market_observations_source_time",
        "market_observations",
        ["source_system", "observed_at_utc"],
    )
    op.create_index(
        "ix_fx_observations_pair_value_date",
        "fx_observations",
        ["pair", "value_date"],
    )
    op.create_index(
        "ix_flow_observations_point_period",
        "flow_observations",
        ["point_id", "period_start_utc"],
    )
    op.create_index(
        "ix_storage_observations_facility_period",
        "storage_observations",
        ["facility_id", "period_start_utc"],
    )
    op.create_index(
        "ix_lng_observations_terminal_period",
        "lng_observations",
        ["terminal_id", "period_start_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_lng_observations_terminal_period", "lng_observations")
    op.drop_index("ix_storage_observations_facility_period", "storage_observations")
    op.drop_index("ix_flow_observations_point_period", "flow_observations")
    op.drop_index("ix_fx_observations_pair_value_date", "fx_observations")
    op.drop_index("ix_market_observations_source_time", "market_observations")

    op.drop_column("flow_observations", "original_unit")
    op.drop_column("flow_observations", "original_value")

    for table in reversed(OBSERVATION_TABLES):
        op.drop_column(table, "metadata_json")
        op.drop_column(table, "source_record_id")
