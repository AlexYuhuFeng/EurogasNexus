"""TAR-1 tariff book: versions of public tariffs, and capacity notices (ADR Decision 34).

``tariff_versions``: one row per version of one public tariff (an ENTSOG reserve price, an
administrator's reviewed entry, a terminal's published charge), with publisher, facility,
product, unit, currency, period, status INDICATIVE or FINAL and why, publication and retrieval
times, source URL and content hash. Append-only except ``superseded_at_utc``, stamped on the
version a newer one replaces, so a read as of an instant takes the version current then.

``capacity_notices``: upcoming capacity windows (standard auctions derived from the CAM
network code, LNG slot offers and secondary-capacity windows imported from a publisher's
notice), one row per notice key with its content hash and revision.

Expand-only: two new tables and their indexes; the downgrade drops only those.
"""

import sqlalchemy as sa

from alembic import op

revision = "0083_tar1_tariff_book"
down_revision = "0082_data1_integration"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "tariff_versions",
        sa.Column("version_id", sa.String(64), primary_key=True),
        sa.Column("tariff_key", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_kind", sa.String(16), nullable=False),
        sa.Column("status_change", sa.String(32), nullable=True),
        sa.Column("publisher_id", sa.String(64), nullable=False),
        sa.Column("facility_kind", sa.String(16), nullable=False),
        sa.Column("facility_id", sa.String(128), nullable=False),
        sa.Column("facility_name", sa.String(256), nullable=False),
        sa.Column("operator", sa.String(128), nullable=False),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("market_area", sa.String(64), nullable=True),
        sa.Column("direction", sa.String(16), nullable=True),
        sa.Column("product", sa.String(32), nullable=False),
        sa.Column("duration", sa.String(16), nullable=True),
        sa.Column("firmness", sa.String(16), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("by_class", sa.JSON(), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("status_basis", sa.String(32), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_ref", sa.String(256), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_id", sa.String(64), nullable=True),
        sa.UniqueConstraint("tariff_key", "version", name="uq_tariff_versions_key_version"),
        sa.CheckConstraint("status IN ('INDICATIVE', 'FINAL')", name="ck_tariff_versions_status"),
        sa.CheckConstraint(
            "change_kind IN ('first', 'revised', 'status_change', 'withdrawn')",
            name="ck_tariff_versions_change_kind",
        ),
    )
    op.create_index(
        "ix_tariff_versions_current", "tariff_versions", ["superseded_at_utc", "publisher_id"]
    )
    op.create_index(
        "ix_tariff_versions_facility", "tariff_versions", ["facility_id", "period_from"]
    )
    op.create_index("ix_tariff_versions_recorded", "tariff_versions", ["recorded_at_utc"])
    op.create_table(
        "capacity_notices",
        sa.Column("notice_key", sa.String(160), primary_key=True),
        sa.Column("publisher_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("facility_kind", sa.String(16), nullable=True),
        sa.Column("facility_id", sa.String(128), nullable=True),
        sa.Column("facility_name", sa.String(256), nullable=True),
        sa.Column("product", sa.String(32), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("opens_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offers_from", sa.Date(), nullable=True),
        sa.Column("offers_to", sa.Date(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("quantity_unit", sa.String(32), nullable=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retrieved_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("first_recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('auction', 'lng_slot', 'secondary_capacity')",
            name="ck_capacity_notices_kind",
        ),
        sa.CheckConstraint(
            "basis IN ('rule_derived', 'published')", name="ck_capacity_notices_basis"
        ),
    )
    op.create_index("ix_capacity_notices_opens", "capacity_notices", ["opens_at_utc"])
    op.create_index("ix_capacity_notices_publisher", "capacity_notices", ["publisher_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_capacity_notices_publisher", table_name="capacity_notices")
    op.drop_index("ix_capacity_notices_opens", table_name="capacity_notices")
    op.drop_table("capacity_notices")
    op.drop_index("ix_tariff_versions_recorded", table_name="tariff_versions")
    op.drop_index("ix_tariff_versions_facility", table_name="tariff_versions")
    op.drop_index("ix_tariff_versions_current", table_name="tariff_versions")
    op.drop_table("tariff_versions")
