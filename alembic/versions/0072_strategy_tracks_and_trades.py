"""Tracked strategies (paper shadow run), exchange trade prints and quote session fields.

- ``market_quotes``: nullable session fields a licensed feed may carry with a quote (last trade
  size, session open/high/low, VWAP, volume, number of trades, settlement and prior settlement,
  open interest). Existing rows keep them empty.
- ``market_trades``: executed trades as the customer's feed printed them (price, size, trade
  type, aggressor, broker, venue and receipt times), under the source family.
- ``strategy_tracks`` / ``strategy_track_events``: a saved StrategySpec tracked daily on new
  closes or intraday on arriving quotes, with a paper book; nothing can be sent anywhere.

Expand-only; the downgrade drops only what this revision adds.
"""

import sqlalchemy as sa

from alembic import op

revision = "0072_strategy_tracks_and_trades"
down_revision = "0071_opportunity_pending_inputs"
branch_labels = None
depends_on = None
# Reversibility, printed by the gated upgrade (scripts/ops/upgrade_database.py).
reversibility = "reversible"

_QUOTE_FLOATS = (
    "last_quantity_mwh", "session_open", "session_high", "session_low", "vwap", "volume_mwh",
    "settlement_price", "prior_settlement_price", "open_interest_mwh",
)


def upgrade() -> None:
    for name in _QUOTE_FLOATS:
        op.add_column("market_quotes", sa.Column(name, sa.Float(), nullable=True))
    op.add_column("market_quotes", sa.Column("trade_count", sa.Integer(), nullable=True))

    op.create_table(
        "market_trades",
        sa.Column("trade_id", sa.String(128), primary_key=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("venue", sa.String(64), nullable=False),
        sa.Column("instrument_id", sa.String(128), nullable=False),
        sa.Column("hub", sa.String(32), nullable=False),
        sa.Column("product", sa.String(64), nullable=False),
        sa.Column("delivery_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("quantity_mwh", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("trade_type", sa.String(16), nullable=False),
        sa.Column("aggressor", sa.String(8), nullable=True),
        sa.Column("broker", sa.String(64), nullable=True),
        sa.Column("traded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_market_trades_lookup", "market_trades",
                    ["hub", "product", "source_system", "traded_at_utc"])
    op.create_index("ix_market_trades_traded_at", "market_trades", ["traded_at_utc"])

    op.create_table(
        "strategy_tracks",
        sa.Column("track_id", sa.String(64), primary_key=True),
        sa.Column("owner_principal_id", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("rule_json", sa.JSON(), nullable=False),
        sa.Column("instruments", sa.JSON(), nullable=False),
        sa.Column("book_state", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_evaluated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_changed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluations", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_strategy_tracks_owner", "strategy_tracks",
                    ["owner_principal_id", "state"])
    op.create_index("ix_strategy_tracks_mode_state", "strategy_tracks", ["mode", "state"])
    op.create_table(
        "strategy_track_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("track_id", sa.String(64),
                  sa.ForeignKey("strategy_tracks.track_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_strategy_track_events_track", "strategy_track_events",
                    ["track_id", "at_utc"])


def downgrade() -> None:
    op.drop_index("ix_strategy_track_events_track", table_name="strategy_track_events")
    op.drop_table("strategy_track_events")
    op.drop_index("ix_strategy_tracks_mode_state", table_name="strategy_tracks")
    op.drop_index("ix_strategy_tracks_owner", table_name="strategy_tracks")
    op.drop_table("strategy_tracks")
    op.drop_index("ix_market_trades_traded_at", table_name="market_trades")
    op.drop_index("ix_market_trades_lookup", table_name="market_trades")
    op.drop_table("market_trades")
    op.drop_column("market_quotes", "trade_count")
    for name in reversed(_QUOTE_FLOATS):
        op.drop_column("market_quotes", name)
