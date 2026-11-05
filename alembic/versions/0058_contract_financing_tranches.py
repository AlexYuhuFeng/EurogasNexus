"""Contract funding segments: a contract may be funded by several lenders (#14)."""

import sqlalchemy as sa

from alembic import op

revision = "0058_contract_financing_tranches"
down_revision = "0057_contract_price_currency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: a contract without segments keeps its single financing rate.
    op.add_column(
        "upstream_resource_contracts",
        sa.Column("financing_tranches", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("upstream_resource_contracts", "financing_tranches")
