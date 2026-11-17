"""Local accounts: a password for principals that sign in without company SSO.

- ``identity_local_credentials``: one row per local account (firms without SSO, demo test
  accounts). A salted scrypt derivation with its KDF name and parameters recorded, the
  one-time temporary password state (``must_change_password``, expiry), the per-account
  back-off (failed attempts, locked until), the single-use password-change token as
  SHA-256, and the demo marker. Nothing stored is reversible.

Expand-only; SQLite and PostgreSQL. The downgrade drops only what this revision added
(and with it every local password: those accounts can no longer sign in).
"""

import sqlalchemy as sa

from alembic import op

revision = "0065_local_accounts"
down_revision = "0064_market_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_local_credentials",
        sa.Column(
            "principal_id",
            sa.String(64),
            sa.ForeignKey("identity_principals.principal_id"),
            primary_key=True,
        ),
        sa.Column("kdf", sa.String(16), nullable=False),
        sa.Column("kdf_params", sa.JSON(), nullable=False),
        sa.Column("salt_b64", sa.String(64), nullable=False),
        sa.Column("password_hash_b64", sa.String(128), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("temporary_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("password_set_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_token_hash", sa.String(64), nullable=True),
        sa.Column("change_token_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(80), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("identity_local_credentials")
