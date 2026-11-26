"""LNG voyage distances: ``freight_route``, versioned (CP-12, design C.5).

One row per version of one route (load port, discharge port, routing direct/suez/panama/cape,
distance in nautical miles, canal, where the distance came from, who recorded it and when). A
change adds a version; nothing is overwritten. Shipped empty: the firm enters its routes
(no openly licensed sea-distance table has been chosen yet). Expand-only; the downgrade drops
only this table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0070_freight_route"
down_revision = "0069_lng_terminal_tariff"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "freight_route",
        sa.Column("row_id", sa.String(64), primary_key=True),
        sa.Column("route_id", sa.String(96), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("load_port", sa.String(96), nullable=False),
        sa.Column("discharge_port", sa.String(96), nullable=False),
        sa.Column("discharge_terminal_id", sa.String(64), nullable=True),
        sa.Column("routing", sa.String(16), nullable=False),
        sa.Column("distance_nm", sa.Float(), nullable=False),
        sa.Column("canal", sa.String(16), nullable=False, server_default="none"),
        sa.Column("source", sa.String(256), nullable=False),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("route_id", "version", name="uq_freight_route_version"),
        sa.CheckConstraint(
            "routing IN ('direct', 'suez', 'panama', 'cape')", name="ck_freight_route_routing"
        ),
        sa.CheckConstraint("distance_nm > 0", name="ck_freight_route_distance"),
    )
    op.create_index("ix_freight_route_route", "freight_route", ["route_id"])


def downgrade() -> None:
    op.drop_index("ix_freight_route_route", table_name="freight_route")
    op.drop_table("freight_route")
