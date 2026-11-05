"""Contract price currency: a supply contract's price is recorded in its own currency."""

import sqlalchemy as sa

from alembic import op

revision = "0057_contract_price_currency"
down_revision = "0056_hedge_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every contract recorded so far was priced in GBP/MWh, so existing rows read GBP.
    op.add_column(
        "upstream_resource_contracts",
        sa.Column(
            "contract_price_currency",
            sa.String(3),
            nullable=False,
            server_default="GBP",
        ),
    )


def downgrade() -> None:
    op.drop_column("upstream_resource_contracts", "contract_price_currency")
