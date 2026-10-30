"""Trading books, and a book on each contract and screen trade, for portfolio roll-ups."""

import sqlalchemy as sa

from alembic import op

revision = "0052_trading_books"
down_revision = "0051_market_data_licences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_books",
        sa.Column("book_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("legal_entity", sa.String(64), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("business", sa.String(128), nullable=False),
        sa.Column("base_currency", sa.String(8), nullable=False),
        sa.Column("commodities", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("upstream_resource_contracts", sa.Column("book_id", sa.String(64), nullable=True))
    op.add_column("screen_order_observations", sa.Column("book_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("screen_order_observations", "book_id")
    op.drop_column("upstream_resource_contracts", "book_id")
    op.drop_table("trading_books")
