"""Maker-checker on limits and reference data (P-17, slice GOV-1; ADR Decision 32).

- ``change_requests``: one proposed change to a limit or a piece of reference data, waiting
  for a second person; who proposed, what (each field before and after), why, since when, and
  who approved, rejected or withdrew it.
- ``change_id`` on ``credit_lines``, ``trader_mandates``, ``hedge_approvals``,
  ``lng_terminal_terms``, ``firm_marks`` and ``freight_route``: the approved proposal that set
  the row (``NULL`` when set without a second person), for the figure's provenance.

Expand-only; the downgrade drops only what this migration adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0081_change_requests"
down_revision = "0080_lng_eta_basis"
branch_labels = None
depends_on = None

PROVENANCE_TABLES = (
    "credit_lines",
    "trader_mandates",
    "hedge_approvals",
    "lng_terminal_terms",
    "firm_marks",
    "freight_route",
)


def upgrade() -> None:
    op.create_table(
        "change_requests",
        sa.Column("change_id", sa.String(40), primary_key=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("resource", sa.String(160), nullable=False),
        sa.Column("target_key", sa.String(160), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("proposed_by", sa.String(128), nullable=False),
        sa.Column("proposed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("decided_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
    )
    op.create_index("ix_change_requests_state", "change_requests", ["state", "proposed_at_utc"])
    op.create_index("ix_change_requests_resource", "change_requests", ["resource", "state"])
    for table in PROVENANCE_TABLES:
        op.add_column(table, sa.Column("change_id", sa.String(40), nullable=True))


def downgrade() -> None:
    for table in reversed(PROVENANCE_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("change_id")
    op.drop_index("ix_change_requests_resource", table_name="change_requests")
    op.drop_index("ix_change_requests_state", table_name="change_requests")
    op.drop_table("change_requests")
