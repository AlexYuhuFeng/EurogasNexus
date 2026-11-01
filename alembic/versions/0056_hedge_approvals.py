"""Risk-approved hedge band per supply contract."""

import sqlalchemy as sa

from alembic import op

revision = "0056_hedge_approvals"
down_revision = "0055_desk_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hedge_approvals",
        sa.Column("contract_id", sa.String(128), primary_key=True),
        sa.Column("min_hedge_ratio_pct", sa.Float(), nullable=True),
        sa.Column("max_hedge_ratio_pct", sa.Float(), nullable=True),
        sa.Column("approval_ref", sa.String(128), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hedge_approvals")
