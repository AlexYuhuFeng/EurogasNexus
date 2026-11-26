"""LNG-3 portfolio disruption re-optimisation (ADR Decision 36).

Seven new tables, all expand-only (``db/models/lng_disruption.py``):

* ``lng_slot_terms``: a held regas slot's product terms (slot days, storage right and its
  profile, indicative release value);
* ``lng_capacity_offers``: in-tank borrowing, extra send-out, extra storage and interruptible
  capacity the desk could take at a terminal, as quoted or entered;
* ``lng_delivery_obligations``: gas the book must deliver at a terminal or point per gas day
  (a firm one is a hard constraint for the optimiser);
* ``lng_voyage_terms``: laytime, demurrage, boil-off and diversion rights per cargo or charter;
* ``pipeline_supplies``: pipeline supply contracts of a book and their curtailed days;
* ``lng_disruption_runs``: each re-optimisation (the recommendation's timeline);
* ``lng_disruption_decisions``: the option a person chose (a record; nothing is booked).

The downgrade drops only these tables.
"""

import sqlalchemy as sa

from alembic import op

revision = "0086_lng_disruption"
down_revision = "0084_news_items"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "lng_slot_terms",
        sa.Column("slot_id", sa.String(96), primary_key=True),
        sa.Column("slot_days", sa.Integer(), nullable=False),
        sa.Column("storage_mwh", sa.Float(), nullable=False),
        sa.Column("storage_profile", sa.String(24), nullable=False),
        sa.Column("release_value_eur_mwh", sa.Float(), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_table(
        "lng_capacity_offers",
        sa.Column("offer_id", sa.String(96), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("terminal_name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("first_gas_day", sa.Date(), nullable=False),
        sa.Column("last_gas_day", sa.Date(), nullable=False),
        sa.Column("price_eur_mwh", sa.Float(), nullable=False),
        sa.Column("max_mwh_per_day", sa.Float(), nullable=True),
        sa.Column("max_mwh", sa.Float(), nullable=True),
        sa.Column("storage_price_eur_mwh_day", sa.Float(), nullable=True),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("counterparty", sa.String(128), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("valid_until_utc", _TS, nullable=True),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_index(
        "ix_lng_capacity_offers_terminal", "lng_capacity_offers", ["terminal_name", "kind"]
    )
    op.create_table(
        "lng_delivery_obligations",
        sa.Column("obligation_id", sa.String(96), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("counterparty", sa.String(128), nullable=False),
        sa.Column("contract_id", sa.String(96), nullable=True),
        sa.Column("point", sa.String(128), nullable=False),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("first_gas_day", sa.Date(), nullable=False),
        sa.Column("last_gas_day", sa.Date(), nullable=False),
        sa.Column("mwh_per_day", sa.Float(), nullable=False),
        sa.Column("firm", sa.Boolean(), nullable=False),
        sa.Column("penalty_eur_mwh", sa.Float(), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_index("ix_lng_delivery_obligations_book", "lng_delivery_obligations", ["book_id"])
    op.create_table(
        "lng_voyage_terms",
        sa.Column("cargo_id", sa.String(96), primary_key=True),
        sa.Column("charter_reference", sa.String(128), nullable=True),
        sa.Column("laytime_hours", sa.Float(), nullable=True),
        sa.Column("demurrage_eur_per_day", sa.Float(), nullable=True),
        sa.Column("boil_off_pct_per_day", sa.Float(), nullable=True),
        sa.Column("diversion_allowed", sa.Boolean(), nullable=True),
        sa.Column("diversion_note", sa.String(256), nullable=True),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_table(
        "pipeline_supplies",
        sa.Column("supply_id", sa.String(96), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("contract_id", sa.String(96), nullable=True),
        sa.Column("hub", sa.String(16), nullable=False),
        sa.Column("point", sa.String(128), nullable=False),
        sa.Column("first_gas_day", sa.Date(), nullable=False),
        sa.Column("last_gas_day", sa.Date(), nullable=False),
        sa.Column("mwh_per_day", sa.Float(), nullable=False),
        sa.Column("cost_eur_mwh", sa.Float(), nullable=True),
        sa.Column("curtailed", sa.JSON(), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", _TS, nullable=False),
    )
    op.create_index("ix_pipeline_supplies_book", "pipeline_supplies", ["book_id"])
    op.create_table(
        "lng_disruption_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("computed_at_utc", _TS, nullable=False),
        sa.Column("trigger", sa.String(160), nullable=False),
        sa.Column("digest", sa.String(40), nullable=False),
        sa.Column("disrupted", sa.JSON(), nullable=False),
        sa.Column("recommended_option_id", sa.String(32), nullable=True),
        sa.Column("recommended_key", sa.Text(), nullable=True),
        sa.Column("recommended_title", sa.Text(), nullable=True),
        sa.Column("recommended_pnl_eur", sa.Float(), nullable=True),
        sa.Column("frontier", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("change", sa.String(16), nullable=True),
        sa.Column("notified", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_lng_disruption_runs_book", "lng_disruption_runs", ["book_id", "computed_at_utc"]
    )
    op.create_table(
        "lng_disruption_decisions",
        sa.Column("decision_id", sa.String(64), primary_key=True),
        sa.Column("book_id", sa.String(64), nullable=False),
        sa.Column("cargo_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("option_id", sa.String(32), nullable=False),
        sa.Column("option_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("recommended_option_id", sa.String(32), nullable=True),
        sa.Column("objectives", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(128), nullable=False),
        sa.Column("decided_at_utc", _TS, nullable=False),
    )
    op.create_index(
        "ix_lng_disruption_decisions_cargo",
        "lng_disruption_decisions",
        ["cargo_id", "decided_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_lng_disruption_decisions_cargo", table_name="lng_disruption_decisions")
    op.drop_table("lng_disruption_decisions")
    op.drop_index("ix_lng_disruption_runs_book", table_name="lng_disruption_runs")
    op.drop_table("lng_disruption_runs")
    op.drop_index("ix_pipeline_supplies_book", table_name="pipeline_supplies")
    op.drop_table("pipeline_supplies")
    op.drop_table("lng_voyage_terms")
    op.drop_index("ix_lng_delivery_obligations_book", table_name="lng_delivery_obligations")
    op.drop_table("lng_delivery_obligations")
    op.drop_index("ix_lng_capacity_offers_terminal", table_name="lng_capacity_offers")
    op.drop_table("lng_capacity_offers")
    op.drop_table("lng_slot_terms")
