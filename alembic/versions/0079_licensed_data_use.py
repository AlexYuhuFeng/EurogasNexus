"""Aggregated usage of licensed source families (GOV-1, lesson P6; ADR Decision 31).

- ``licensed_data_use``: one row per day, principal, source family and surface (route
  template, or ``export:<format> <route>`` for a file), counted up as requests arrive.

Expand-only; the downgrade drops only this table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0079_licensed_data_use"
down_revision = "0078_lng_cargo_hedges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "licensed_data_use",
        sa.Column("usage_day", sa.Date(), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("source_family", sa.String(32), nullable=False),
        sa.Column("surface", sa.String(160), nullable=False),
        sa.Column("reads", sa.Integer(), nullable=False),
        sa.Column("first_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "usage_day", "principal_id", "source_family", "surface",
            name="pk_licensed_data_use",
        ),
    )
    op.create_index(
        "ix_licensed_data_use_family_day", "licensed_data_use", ["source_family", "usage_day"]
    )


def downgrade() -> None:
    op.drop_index("ix_licensed_data_use_family_day", table_name="licensed_data_use")
    op.drop_table("licensed_data_use")
