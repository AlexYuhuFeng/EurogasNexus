"""Store REMIT urgent market messages: gas production, storage, LNG and transport outages.

Norwegian field and plant outages move NBP and TTF within minutes. Messages are imported from
the operator's inside-information platform export; every version is kept.
"""

import sqlalchemy as sa

from alembic import op

revision = "0050_remit_umm_messages"
down_revision = "0049_power_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remit_umm_messages",
        sa.Column("record_id", sa.String(96), primary_key=True),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_status", sa.String(16), nullable=False),
        sa.Column("unavailability_type", sa.String(16), nullable=False),
        sa.Column("event_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_stop_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asset_name", sa.String(160), nullable=False),
        sa.Column("asset_eic", sa.String(32), nullable=False),
        sa.Column("asset_type", sa.String(16), nullable=False),
        sa.Column("balancing_zone", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("technical_capacity", sa.Float(), nullable=True),
        sa.Column("available_capacity", sa.Float(), nullable=True),
        sa.Column("unavailable_capacity", sa.Float(), nullable=True),
        sa.Column("unavailable_mcm_d", sa.Float(), nullable=True),
        sa.Column("unavailable_gwh_d", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("market_participant", sa.String(160), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=False),
        sa.Column("source_system", sa.String(32), nullable=False),
        sa.Column("source_reference", sa.String(160), nullable=False),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_remit_umm_messages_message_version", "remit_umm_messages", ["message_id", "version"]
    )
    op.create_index("ix_remit_umm_messages_event_stop", "remit_umm_messages", ["event_stop_utc"])


def downgrade() -> None:
    op.drop_index("ix_remit_umm_messages_event_stop", table_name="remit_umm_messages")
    op.drop_index("ix_remit_umm_messages_message_version", table_name="remit_umm_messages")
    op.drop_table("remit_umm_messages")
