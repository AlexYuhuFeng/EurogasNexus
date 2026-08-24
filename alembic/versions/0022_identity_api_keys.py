"""Local identity principals and hashed API keys (R32)."""

import sqlalchemy as sa

from alembic import op

revision = "0022_identity_api_keys"
down_revision = "0021_raw_payload_archives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_principals",
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("principal_type", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("data_scopes", sa.JSON(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("principal_id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_identity_principals_role_status",
        "identity_principals",
        ["role", "status"],
    )
    op.create_table(
        "identity_api_keys",
        sa.Column("key_id", sa.String(32), primary_key=True),
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("identity_principals.principal_id"),
            nullable=False,
        ),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_bootstrap", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("key_id"),
    )
    op.create_index(
        "ix_identity_api_keys_principal",
        "identity_api_keys",
        ["principal_id", "revoked_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_api_keys_principal", table_name="identity_api_keys")
    op.drop_table("identity_api_keys")
    op.drop_index(
        "ix_identity_principals_role_status", table_name="identity_principals"
    )
    op.drop_table("identity_principals")
