"""Add source lineage and TSO access reference metadata."""

import sqlalchemy as sa

from alembic import op

revision = "0011_reference_source_lineage"
down_revision = "0010_source_observation_metadata"
branch_labels = None
depends_on = None


REFERENCE_TABLES = (
    "reference_nodes",
    "reference_edges",
    "reference_facilities",
    "reference_market_hubs",
)


def upgrade() -> None:
    for table in REFERENCE_TABLES:
        op.add_column(table, sa.Column("source_system", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("source_dataset", sa.String(128), nullable=True))
        op.add_column(table, sa.Column("source_reference", sa.String(256), nullable=True))
        op.add_column(table, sa.Column("source_record_id", sa.String(128), nullable=True))
        op.add_column(table, sa.Column("data_quality", sa.String(32), nullable=True))

    op.create_table(
        "reference_tso_access_points",
        sa.Column("access_id", sa.String(128), primary_key=True),
        sa.Column("point_id", sa.String(64), sa.ForeignKey("reference_nodes.id"), nullable=True),
        sa.Column("point_key", sa.String(64), nullable=False),
        sa.Column("point_name", sa.String(256), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("operator_key", sa.String(64), nullable=False),
        sa.Column("operator_name", sa.String(256), nullable=False),
        sa.Column("tso_eic_code", sa.String(32), nullable=True),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("adjacent_country", sa.String(8), nullable=True),
        sa.Column("adjacent_operator_key", sa.String(64), nullable=True),
        sa.Column("connected_operators", sa.Text(), nullable=True),
        sa.Column("booking_platform", sa.String(128), nullable=True),
        sa.Column("booking_platform_url", sa.Text(), nullable=True),
        sa.Column("annual_contracts_available", sa.Boolean(), nullable=False),
        sa.Column("monthly_contracts_available", sa.Boolean(), nullable=False),
        sa.Column("daily_contracts_available", sa.Boolean(), nullable=False),
        sa.Column("day_ahead_contracts_available", sa.Boolean(), nullable=False),
        sa.Column("is_cam_relevant", sa.Boolean(), nullable=False),
        sa.Column("is_cmp_relevant", sa.Boolean(), nullable=False),
        sa.Column("last_update_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_dataset", sa.String(128), nullable=False),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("data_quality", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_reference_nodes_source_record",
        "reference_nodes",
        ["source_system", "source_dataset", "source_record_id"],
    )
    op.create_index(
        "ix_reference_nodes_country_type",
        "reference_nodes",
        ["country", "node_type"],
    )
    op.create_index(
        "ix_reference_facilities_source_record",
        "reference_facilities",
        ["source_system", "source_dataset", "source_record_id"],
    )
    op.create_index(
        "ix_reference_hubs_source_record",
        "reference_market_hubs",
        ["source_system", "source_dataset", "source_record_id"],
    )
    op.create_index(
        "ix_reference_tso_access_point_direction",
        "reference_tso_access_points",
        ["point_id", "direction"],
    )
    op.create_index(
        "ix_reference_tso_access_operator_direction",
        "reference_tso_access_points",
        ["operator_key", "direction"],
    )
    op.create_index(
        "ix_reference_tso_access_country_direction",
        "reference_tso_access_points",
        ["country", "direction"],
    )


def downgrade() -> None:
    op.drop_index("ix_reference_tso_access_country_direction", "reference_tso_access_points")
    op.drop_index("ix_reference_tso_access_operator_direction", "reference_tso_access_points")
    op.drop_index("ix_reference_tso_access_point_direction", "reference_tso_access_points")
    op.drop_index("ix_reference_hubs_source_record", "reference_market_hubs")
    op.drop_index("ix_reference_facilities_source_record", "reference_facilities")
    op.drop_index("ix_reference_nodes_country_type", "reference_nodes")
    op.drop_index("ix_reference_nodes_source_record", "reference_nodes")

    op.drop_table("reference_tso_access_points")

    for table in reversed(REFERENCE_TABLES):
        op.drop_column(table, "data_quality")
        op.drop_column(table, "source_record_id")
        op.drop_column(table, "source_reference")
        op.drop_column(table, "source_dataset")
        op.drop_column(table, "source_system")
