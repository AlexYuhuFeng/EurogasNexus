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


def downgrade() -> None:
    with op.batch_alter_table("trader_mandates") as batch:
        batch.drop_column("instruments")
        batch.drop_column("max_hedge_ratio_pct")
        batch.drop_column("min_hedge_ratio_pct")
    with op.batch_alter_table("upstream_resource_contracts") as batch:
        batch.drop_column("retire_reason")
        batch.drop_column("retired_by")
        batch.drop_column("retired_at_utc")
