"""LNG berth priority: each terminal's berth access rule, and another company's quote on a call.

ADR Decision 37, addendum of 2026-11-26 (the owner's decisions on berth priority and on another
company's demurrage). Expand-only (``db/models/lng_disruption.py``):

* a new table ``lng_terminal_berth_rules``: a terminal's berth access rule where the firm
  records one (the arrival window in gas days, where a late ship's laytime starts, whether a
  swap of berth turn needs the terminal's approval), with its citation and basis
  (``terminal_code``, ``example`` or ``assumption``). Without a row the engine's default rule
  applies and says so;
* nullable columns on ``lng_berth_calls``: ``counterparty`` (the company whose ship it is) and
  its negotiated quote to give up its berth turn, one total (``quote_amount``,
  ``quote_currency``, ``quote_reference``).

Nothing is dropped or altered: the call's laytime, demurrage and boil-off columns stay as they
were written, but are no longer read. The downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0092_lng_berth_rules"
down_revision = "0091_hub_one_identity"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("lng_berth_calls", "counterparty", sa.String(160)),
    ("lng_berth_calls", "quote_amount", sa.Float()),
    ("lng_berth_calls", "quote_currency", sa.String(3)),
    ("lng_berth_calls", "quote_reference", sa.String(160)),
)


def upgrade() -> None:
    op.create_table(
        "lng_terminal_berth_rules",
        sa.Column("terminal_name", sa.String(128), primary_key=True),
        sa.Column("arrival_window_days", sa.Integer(), nullable=False),
        sa.Column("late_laytime_from", sa.String(16), nullable=False),
        sa.Column("swap_needs_terminal_approval", sa.Boolean(), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("citation", sa.String(256), nullable=True),
        sa.Column("rule_text", sa.Text(), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    for table, name, kind in _COLUMNS:
        op.add_column(table, sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("lng_berth_calls") as batch:
        for _table, name, _kind in reversed(_COLUMNS):
            batch.drop_column(name)
    op.drop_table("lng_terminal_berth_rules")
