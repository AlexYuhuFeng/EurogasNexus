"""TAR-2: capacity the firm holds, and the tariff year of each tariff version (ADR Decision 38).

Expand-only:

* ``capacity_bookings`` (``db/models/capacity_bookings.py``): pipeline entry and exit
  capacity, LNG slots, regasification, send-out and storage the firm holds, with the
  contracted price, imported through ``etrm.capacity_bookings.v1``; the contracted cost
  prices what a booking covers before any public tariff (``domain/tariffs/precedence.py``);
* ``tariff_versions.tariff_year`` (nullable): the tariff year as the publisher defines it
  (``GY 2027/28``, ``CY 2027``, ``TY 2027/28 Apr-Mar``). Versions recorded before TAR-2 keep
  NULL and readers work the year out from the period; no row is rewritten.

The downgrade drops only the new table and the new column.
"""

import sqlalchemy as sa

from alembic import op

revision = "0088_tar2_capacity_bookings"
down_revision = "0086_lng_disruption"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "capacity_bookings",
        sa.Column("booking_id", sa.String(96), primary_key=True),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("facility_kind", sa.String(16), nullable=False),
        sa.Column("facility_id", sa.String(128), nullable=False),
        sa.Column("facility_name", sa.String(256), nullable=True),
        sa.Column("operator", sa.String(128), nullable=True),
        sa.Column("direction", sa.String(8), nullable=True),
        sa.Column("product", sa.String(32), nullable=True),
        sa.Column("firmness", sa.String(16), nullable=False),
        sa.Column("acquired_via", sa.String(16), nullable=False),
        sa.Column("first_gas_day", sa.Date(), nullable=False),
        sa.Column("last_gas_day", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("quantity_unit", sa.String(16), nullable=False),
        sa.Column("quantity_basis", sa.String(12), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("price_unit", sa.String(32), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("counterparty", sa.String(128), nullable=True),
        sa.Column("source_reference", sa.String(256), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("recorded_at_utc", _TS, nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
        sa.Column("released_at_utc", _TS, nullable=True),
        sa.CheckConstraint(
            "kind IN ('entry', 'exit', 'lng_slot', 'regas', 'send_out', 'storage')",
            name="ck_capacity_bookings_kind",
        ),
        sa.CheckConstraint(
            "quantity_basis IN ('per_day', 'pool')", name="ck_capacity_bookings_basis"
        ),
    )
    op.create_index(
        "ix_capacity_bookings_facility", "capacity_bookings", ["facility_id", "kind"]
    )
    op.create_index("ix_capacity_bookings_book", "capacity_bookings", ["book_id"])
    with op.batch_alter_table("tariff_versions") as batch:
        batch.add_column(sa.Column("tariff_year", sa.String(40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tariff_versions") as batch:
        batch.drop_column("tariff_year")
    op.drop_index("ix_capacity_bookings_book", table_name="capacity_bookings")
    op.drop_index("ix_capacity_bookings_facility", table_name="capacity_bookings")
    op.drop_table("capacity_bookings")
