"""Contract kinds: a discriminator and typed terms on the contract row (CONTRACT_TYPES.md).

Adds to ``upstream_resource_contracts``: ``contract_kind`` (every existing row becomes
``SUPPLY_GSA``, the shape it was entered in, so it keeps feeding the book unchanged),
``contract_kind_reviewed`` (false: the inferred kind waits for a person to confirm it),
``kind_terms`` (JSON), ``unmodelled_terms`` (text) and ``master_contract_id`` (a confirmation's
master, self-referencing, RESTRICT). Expand-only; the downgrade drops the five columns.
"""

import sqlalchemy as sa

from alembic import op

revision = "0072_contract_kinds"
down_revision = "0071_opportunity_pending_inputs"
branch_labels = None
depends_on = None

TABLE = "upstream_resource_contracts"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(
            sa.Column(
                "contract_kind", sa.String(32), nullable=False, server_default="SUPPLY_GSA"
            )
        )
        batch.add_column(
            sa.Column(
                "contract_kind_reviewed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("kind_terms", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("unmodelled_terms", sa.Text(), nullable=True))
        batch.add_column(sa.Column("master_contract_id", sa.String(128), nullable=True))
        batch.create_foreign_key(
            "fk_upstream_contract_master",
            TABLE,
            ["master_contract_id"],
            ["contract_id"],
            ondelete="RESTRICT",
        )
        batch.create_index(
            "ix_upstream_resource_contracts_master_contract_id", ["master_contract_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_index("ix_upstream_resource_contracts_master_contract_id")
        batch.drop_constraint("fk_upstream_contract_master", type_="foreignkey")
        batch.drop_column("master_contract_id")
        batch.drop_column("unmodelled_terms")
        batch.drop_column("kind_terms")
        batch.drop_column("contract_kind_reviewed")
        batch.drop_column("contract_kind")
