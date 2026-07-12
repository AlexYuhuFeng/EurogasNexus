"""Rename GIE ALSI DTMI to its energy-capacity unit.

Revision ID: 0013_gie_lng_dtmi_energy
Revises: 0012_entsog_capacity
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_gie_lng_dtmi_energy"
down_revision: str | None = "0012_entsog_capacity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "lng_observations",
        "dtmi_pct",
        new_column_name="dtmi_twh",
        existing_type=sa.Float(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "lng_observations",
        "dtmi_twh",
        new_column_name="dtmi_pct",
        existing_type=sa.Float(),
        existing_nullable=True,
    )
