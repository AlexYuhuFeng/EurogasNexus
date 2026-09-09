"""Add ordering indexes for bounded market observation reads.

Revision ID: 0033_market_obs_order_indexes
Revises: 0032_agent_capability_layer
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0033_market_obs_order_indexes"
down_revision: str | None = "0032_agent_capability_layer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add only the index that matches the existing global read ordering."""

    op.create_index(
        "ix_market_observations_observed_venue_product",
        "market_observations",
        [sa.text("observed_at_utc DESC"), "market_venue", "product"],
    )


def downgrade() -> None:
    """Remove the ordering index without changing observation rows."""

    op.drop_index(
        "ix_market_observations_observed_venue_product",
        table_name="market_observations",
    )
