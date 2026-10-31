"""Contract lifecycle, hedge policy, tariff register, support reports and notifications."""

import sqlalchemy as sa

from alembic import op

revision = "0055_desk_operations"
down_revision = "0054_risk_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("upstream_resource_contracts") as batch:
        batch.add_column(sa.Column("retired_at_utc", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("retired_by", sa.String(128), nullable=True))
        batch.add_column(sa.Column("retire_reason", sa.String(500), nullable=True))
    with op.batch_alter_table("trader_mandates") as batch:
        batch.add_column(sa.Column("min_hedge_ratio_pct", sa.Float(), nullable=True))
        batch.add_column(sa.Column("max_hedge_ratio_pct", sa.Float(), nullable=True))
        batch.add_column(sa.Column("instruments", sa.JSON(), nullable=True))
    with op.batch_alter_table("lng_terminal_terms") as batch:
        batch.add_column(
            sa.Column("capacity_basis", sa.String(16), nullable=False, server_default="spot")
        )
        batch.add_column(sa.Column("variable_regas_per_mwh", sa.Float(), nullable=True))
    op.create_table(
        "tso_tariff_publications",
        sa.Column("publication_id", sa.String(64), primary_key=True),
        sa.Column("tso", sa.String(128), nullable=False),
        sa.Column("country", sa.String(8), nullable=True),
        sa.Column("gas_year", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("published_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("last_checked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("changed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "support_reports",
        sa.Column("report_id", sa.String(64), primary_key=True),
        sa.Column("reporter", sa.String(128), nullable=False),
        sa.Column("reporter_role", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(4), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("summary", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("page", sa.String(200), nullable=True),
        sa.Column("client_context", sa.JSON(), nullable=True),
        sa.Column("server_context", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assignee", sa.String(128), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notification_channels",
        sa.Column("channel_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("recipients", sa.Text(), nullable=True),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_preview", sa.String(64), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("min_severity", sa.String(16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notification_outbox",
        sa.Column("notification_id", sa.String(64), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("notification_id", sa.String(64), primary_key=True),
        sa.Column("channel_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.String(500), nullable=True),
        sa.Column("attempted_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_table("notification_outbox")
    op.drop_table("notification_channels")
    op.drop_table("support_reports")
    op.drop_table("tso_tariff_publications")
    with op.batch_alter_table("lng_terminal_terms") as batch:
        batch.drop_column("variable_regas_per_mwh")
        batch.drop_column("capacity_basis")
    with op.batch_alter_table("trader_mandates") as batch:
        batch.drop_column("instruments")
        batch.drop_column("max_hedge_ratio_pct")
        batch.drop_column("min_hedge_ratio_pct")
    with op.batch_alter_table("upstream_resource_contracts") as batch:
        batch.drop_column("retire_reason")
        batch.drop_column("retired_by")
        batch.drop_column("retired_at_utc")
