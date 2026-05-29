"""Create reference network tables (R3)."""

import sqlalchemy as sa

from alembic import op

revision = "0003_r3_reference_network"
down_revision = "0002_m4_create_ingestion_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create reference network domain tables."""

    op.create_table(
        "reference_nodes",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("capacity_boe_d", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "reference_facilities",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("facility_type", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("capacity_boe_d", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "reference_market_hubs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("hub_code", sa.String(length=16), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hub_code"),
    )

    op.create_table(
        "reference_edges",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("from_node_id", sa.String(length=64), nullable=False),
        sa.Column("to_node_id", sa.String(length=64), nullable=False),
        sa.Column("edge_type", sa.String(length=32), nullable=False),
        sa.Column("length_km", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["from_node_id"], ["reference_nodes.id"]),
        sa.ForeignKeyConstraint(["to_node_id"], ["reference_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "node_facility_mappings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("facility_id", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("eligibility", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["facility_id"], ["reference_facilities.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["reference_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "topology_market_mappings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("node_id", sa.String(length=64), nullable=False),
        sa.Column("market_hub_id", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("eligibility", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["market_hub_id"], ["reference_market_hubs.id"]),
        sa.ForeignKeyConstraint(["node_id"], ["reference_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop reference network domain tables."""

    op.drop_table("topology_market_mappings")
    op.drop_table("node_facility_mappings")
    op.drop_table("reference_edges")
    op.drop_table("reference_market_hubs")
    op.drop_table("reference_facilities")
    op.drop_table("reference_nodes")
