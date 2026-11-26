"""Reviewed public transmission tariffs an administrator enters (four eyes).

Adds ``tso_tariff_entry``: an operator-published charge ENTSOG does not carry (operator, point,
direction, product, firmness, value, unit, currency, validity, the operator's status, source
URL, publication date and where in the document), recorded by one person and reviewed by
another; mirrored into ``tso_tariffs`` for pricing. Expand-only; the downgrade drops the table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0075_tso_tariff_entry"
down_revision = "0074_gas_day_schedule"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"


def upgrade() -> None:
    op.create_table(
        "tso_tariff_entry",
        sa.Column("entry_id", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("operator_key", sa.String(32), nullable=True),
        sa.Column("tso", sa.String(128), nullable=False),
        sa.Column("point_id", sa.String(128), nullable=False),
        sa.Column("point_name", sa.String(256), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("market_area", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("capacity_product", sa.String(32), nullable=False),
        sa.Column("firmness", sa.String(32), nullable=False),
        sa.Column("tariff_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=False),
        sa.Column("gas_year", sa.String(16), nullable=False),
        sa.Column("published_status", sa.String(16), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("published_on", sa.Date(), nullable=False),
        sa.Column("source_location", sa.String(256), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("reviewed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(128), nullable=True),
        sa.Column("closed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(256), nullable=True),
        sa.CheckConstraint(
            "state IN ('CANDIDATE', 'REVIEWED', 'RETIRED', 'WITHDRAWN')",
            name="ck_tso_tariff_entry_state",
        ),
        sa.CheckConstraint(
            "direction IN ('ENTRY', 'EXIT')", name="ck_tso_tariff_entry_direction"
        ),
        sa.CheckConstraint(
            "published_status IN ('FINAL', 'INDICATIVE')", name="ck_tso_tariff_entry_status"
        ),
    )
    op.create_index(
        "ix_tso_tariff_entry_leg",
        "tso_tariff_entry",
        ["point_id", "direction", "capacity_product"],
    )


def downgrade() -> None:
    op.drop_index("ix_tso_tariff_entry_leg", table_name="tso_tariff_entry")
    op.drop_table("tso_tariff_entry")
