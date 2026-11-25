"""LNG-4 options with consequences, demurrage by contract, REMIT outages on pipeline supply.

ADR Decision 37. Expand-only (``db/models/lng_disruption.py``):

* ``lng_voyage_terms``: ``demurrage_rate_per_day`` and ``demurrage_currency`` (the rate in
  the currency the contract names) and ``demurrage_terms`` (the laytime and demurrage terms
  as written);
* ``lng_delivery_obligations``: ``penalty_terms`` (a firm obligation's breach terms);
* ``pipeline_supplies``: ``depends_on`` (the assets the supply flows through) and
  ``outage_mode`` (``auto`` or ``manual``, the override);
* ``lng_disruption_runs``: ``recommended_set``;
* ``lng_disruption_decisions``: ``recommended_set``, ``consequences`` and ``fx``;
* ``lng_capacity_offers``: ``hub`` (the hub a spot slot offer's gas reaches);
* ``lng_slot_terms``: ``berth_days`` (the gas days a call holds the berth);
* two new tables: ``pipeline_outage_links`` (a held REMIT message linked to a pipeline
  supply, what matched and why, and the gas days it curtails) and ``lng_berth_calls`` (other
  users' ships due at a terminal's berth, so an option carries the knock-on it causes).

The revision id is shorter than the file name because ``alembic_version.version_num`` holds 32
characters (as 0008, 0016, 0019 and 0020 do). Every new column is nullable, so a row written
before stays valid and an LNG-3 reader is unchanged. The downgrade drops only what this
revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0087_lng4_options_demurrage"
down_revision = "0088_tar2_capacity_bookings"
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)

_COLUMNS = (
    ("lng_voyage_terms", "demurrage_rate_per_day", sa.Float()),
    ("lng_voyage_terms", "demurrage_currency", sa.String(3)),
    ("lng_voyage_terms", "demurrage_terms", sa.String(256)),
    ("lng_delivery_obligations", "penalty_terms", sa.String(256)),
    ("pipeline_supplies", "depends_on", sa.JSON()),
    ("pipeline_supplies", "outage_mode", sa.String(16)),
    ("lng_disruption_runs", "recommended_set", sa.JSON()),
    ("lng_disruption_decisions", "recommended_set", sa.JSON()),
    ("lng_disruption_decisions", "consequences", sa.JSON()),
    ("lng_disruption_decisions", "fx", sa.JSON()),
    ("lng_capacity_offers", "hub", sa.String(16)),
    ("lng_slot_terms", "berth_days", sa.Integer()),
)


def upgrade() -> None:
    for table, name, kind in _COLUMNS:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(name, kind, nullable=True))
    op.create_table(
        "pipeline_outage_links",
        sa.Column("link_id", sa.String(64), primary_key=True),
        sa.Column("supply_id", sa.String(96), nullable=False),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_status", sa.String(16), nullable=False),
        sa.Column("asset_name", sa.String(160), nullable=False),
        sa.Column("asset_eic", sa.String(32), nullable=False),
        sa.Column("matched_on", sa.String(24), nullable=False),
        sa.Column("dependency", sa.JSON(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("fraction", sa.Float(), nullable=True),
        sa.Column("curtailed", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=True),
        sa.Column("first_linked_at_utc", _TS, nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_index(
        "ux_pipeline_outage_links_supply_message",
        "pipeline_outage_links",
        ["supply_id", "message_id"],
        unique=True,
    )
    op.create_index("ix_pipeline_outage_links_book", "pipeline_outage_links", ["book_id"])
    op.create_table(
        "lng_berth_calls",
        sa.Column("call_id", sa.String(96), primary_key=True),
        sa.Column("terminal_name", sa.String(128), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("berth_gas_day", sa.Date(), nullable=False),
        sa.Column("berth_days", sa.Integer(), nullable=False),
        sa.Column("laytime_left_hours", sa.Float(), nullable=True),
        sa.Column("demurrage_rate_per_day", sa.Float(), nullable=True),
        sa.Column("demurrage_currency", sa.String(3), nullable=True),
        sa.Column("boil_off_mwh_per_day", sa.Float(), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_index(
        "ix_lng_berth_calls_terminal", "lng_berth_calls", ["terminal_name", "berth_gas_day"]
    )


def downgrade() -> None:
    op.drop_index("ix_lng_berth_calls_terminal", table_name="lng_berth_calls")
    op.drop_table("lng_berth_calls")
    op.drop_index("ix_pipeline_outage_links_book", table_name="pipeline_outage_links")
    op.drop_index("ux_pipeline_outage_links_supply_message", table_name="pipeline_outage_links")
    op.drop_table("pipeline_outage_links")
    for table, name, _kind in reversed(_COLUMNS):
        with op.batch_alter_table(table) as batch:
            batch.drop_column(name)
