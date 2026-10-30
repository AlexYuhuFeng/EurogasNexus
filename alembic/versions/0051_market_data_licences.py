"""Market-data licence register: data scopes for licensed sources are granted against it."""

import sqlalchemy as sa

from alembic import op

revision = "0051_market_data_licences"
down_revision = "0050_remit_umm_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_data_licences",
        sa.Column("licence_id", sa.String(64), primary_key=True),
        sa.Column("vendor", sa.String(64), nullable=False),
        sa.Column("source_family", sa.String(32), nullable=False),
        sa.Column("licence_type", sa.String(16), nullable=False),
        sa.Column("licensed_use", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("offices", sa.JSON(), nullable=True),
        sa.Column("seats", sa.Integer(), nullable=True),
        sa.Column("contract_reference", sa.String(128), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_market_data_licences_source_family", "market_data_licences", ["source_family"]
    )


def downgrade() -> None:
    op.drop_index("ix_market_data_licences_source_family", table_name="market_data_licences")
    op.drop_table("market_data_licences")
