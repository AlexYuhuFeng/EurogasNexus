"""Default-private local strategies and explicit owner-selected read sharing.

Historical rows remain ownerless PRIVATE. Do not infer ownership from display names.
"""

import sqlalchemy as sa

from alembic import op

revision = "0040_strategy_owner_sharing"
down_revision = "0039_identity_api_key_hash_width"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "identity_groups",
        sa.Column("group_id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
    )
    op.create_table(
        "identity_group_members",
        sa.Column(
            "group_id",
            sa.String(80),
            sa.ForeignKey("identity_groups.group_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "principal_id",
            sa.String(80),
            sa.ForeignKey("identity_principals.principal_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.add_column("strategies", sa.Column("owner_principal_id", sa.String(80), nullable=True))
    op.add_column(
        "strategies",
        sa.Column("visibility", sa.String(16), nullable=False, server_default="PRIVATE"),
    )
    op.create_foreign_key(
        "fk_strategies_owner",
        "strategies",
        "identity_principals",
        ["owner_principal_id"],
        ["principal_id"],
    )
    op.create_check_constraint(
        "ck_strategies_visibility", "strategies", "visibility IN ('PRIVATE', 'PUBLIC', 'GROUPS')"
    )
    op.create_index(
        "ix_strategies_owner_visibility", "strategies", ["owner_principal_id", "visibility"]
    )
    op.create_table(
        "strategy_group_shares",
        sa.Column(
            "strategy_id",
            sa.String(128),
            sa.ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "group_id",
            sa.String(80),
            sa.ForeignKey("identity_groups.group_id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade():
    # Removing the authorization boundary would expose private data to old code.
    raise RuntimeError(
        "Strategy privacy migration cannot be downgraded; "
        "restore an approved pre-migration backup instead."
    )
