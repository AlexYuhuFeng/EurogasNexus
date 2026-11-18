"""Scheduled opportunity evaluation: the input classes that changed (CP-13).

``opportunity_pending_inputs``: one row per input class (prices, tariffs, outages, book,
marks, assumptions, limits, fx, rates, capacity, freight) changed since the last scheduled
evaluation, with when it was first and last noted, how many changes and the last reason.
The job runner runs a debounced full evaluation while rows are pending. Expand-only; the
downgrade drops only this table.
"""

import sqlalchemy as sa

from alembic import op

revision = "0071_opportunity_pending_inputs"
down_revision = "0070_freight_route"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_pending_inputs",
        sa.Column("input_class", sa.String(32), primary_key=True),
        sa.Column("first_noted_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_noted_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changes", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_reason", sa.String(128), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("opportunity_pending_inputs")
