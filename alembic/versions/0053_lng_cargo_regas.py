"""LNG cargoes and regasification slots, for the live map."""

import sqlalchemy as sa

from alembic import op

revision = "0053_lng_cargo_regas"
down_revision = "0052_trading_books"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lng_cargoes",
        sa.Column("cargo_id", sa.String(96), primary_key=True),
        sa.Column("vessel_name", sa.String(128), nullable=False),
        sa.Column("vessel_imo", sa.String(16), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("load_port", sa.String(128), nullable=False),
        sa.Column("load_country", sa.String(2), nullable=True),
        sa.Column("load_lat", sa.Float(), nullable=True),
        sa.Column("load_lon", sa.Float(), nullable=True),
        sa.Column("departed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destination_terminal", sa.String(128), nullable=True),
        sa.Column("destination_country", sa.String(2), nullable=True),
        sa.Column("destination_lat", sa.Float(), nullable=True),
        sa.Column("destination_lon", sa.Float(), nullable=True),
        sa.Column("eta_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position_lat", sa.Float(), nullable=True),
        sa.Column("position_lon", sa.Float(), nullable=True),
        sa.Column("position_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("track", sa.JSON(), nullable=True),
        sa.Column("volume_m3", sa.Float(), nullable=True),
        sa.Column("energy_gwh", sa.Float(), nullable=True),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lng_cargoes_eta", "lng_cargoes", ["eta_utc"])
    op.create_table(
        "regas_slots",
        sa.Column("slot_id", sa.String(96), primary_key=True),
        sa.Column("terminal_name", sa.String(128), nullable=False),
        sa.Column("terminal_country", sa.String(2), nullable=True),
        sa.Column("terminal_lat", sa.Float(), nullable=True),
        sa.Column("terminal_lon", sa.Float(), nullable=True),
        sa.Column("window_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_out_gwh_d", sa.Float(), nullable=True),
        sa.Column("energy_gwh", sa.Float(), nullable=True),
        sa.Column("cargo_id", sa.String(96), nullable=True),
        sa.Column("book_id", sa.String(64), nullable=True),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_regas_slots_terminal", "regas_slots", ["terminal_name"])


def downgrade() -> None:
    op.drop_index("ix_regas_slots_terminal", table_name="regas_slots")
    op.drop_table("regas_slots")
    op.drop_index("ix_lng_cargoes_eta", table_name="lng_cargoes")
    op.drop_table("lng_cargoes")
