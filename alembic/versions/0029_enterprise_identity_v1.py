"""Add CR-10 enterprise identity, sessions, OIDC state and audit columns.

Revision ID: 0029_enterprise_identity_v1
Revises: 0028_data_operations_v1
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_enterprise_identity_v1"
down_revision: str | None = "0028_data_operations_v1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _extend_identity_principals() -> None:
    op.add_column(
        "identity_principals",
        sa.Column("roles", sa.JSON(), nullable=True),
    )
    op.add_column(
        "identity_principals",
        sa.Column("email", sa.String(254), nullable=True),
    )
    op.add_column(
        "identity_principals",
        sa.Column(
            "identity_source",
            sa.String(16),
            nullable=False,
            server_default="LOCAL",
        ),
    )
    op.add_column(
        "identity_principals",
        sa.Column("last_login_at_utc", sa.DateTime(timezone=True), nullable=True),
    )


def _extend_identity_api_keys() -> None:
    op.add_column(
        "identity_api_keys",
        sa.Column("scopes", sa.JSON(), nullable=True),
    )
    op.add_column(
        "identity_api_keys",
        sa.Column("created_by", sa.String(64), nullable=True),
    )


def _external_ids() -> None:
    op.create_table(
        "identity_external_ids",
        sa.Column("identity_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("issuer", sa.String(256), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["identity_principals.principal_id"]),
        sa.PrimaryKeyConstraint("identity_id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_identity_external_ids_issuer_subject"),
    )
    op.create_index(
        "ix_identity_external_ids_principal",
        "identity_external_ids",
        ["principal_id"],
    )
    op.create_index(
        "ix_identity_external_ids_email",
        "identity_external_ids",
        ["email"],
    )


def _sessions() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("session_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_type", sa.String(32), nullable=False),
        sa.Column("client_label", sa.String(128), nullable=True),
        sa.ForeignKeyConstraint(["principal_id"], ["identity_principals.principal_id"]),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        "ix_user_sessions_principal",
        "user_sessions",
        ["principal_id", "revoked_at_utc"],
    )
    op.create_index("ix_user_sessions_expiry", "user_sessions", ["expires_at_utc"])


def _oidc_authorization_states() -> None:
    op.create_table(
        "oidc_authorization_states",
        sa.Column("state", sa.String(128), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("code_challenge_method", sa.String(16), nullable=False),
        sa.Column("code_verifier_hash", sa.String(64), nullable=False),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("redirect_uri", sa.String(512), nullable=False),
        sa.Column("flow_type", sa.String(16), nullable=False),
        sa.Column("client_type", sa.String(16), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        "ix_oidc_auth_states_expiry",
        "oidc_authorization_states",
        ["expires_at_utc"],
    )


def _extend_audit_events() -> None:
    op.add_column(
        "audit_events",
        sa.Column("permission", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("client_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("before_summary", sa.JSON(), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("after_summary", sa.JSON(), nullable=True),
    )


def upgrade() -> None:
    _extend_identity_principals()
    _extend_identity_api_keys()
    _external_ids()
    _sessions()
    _oidc_authorization_states()
    _extend_audit_events()


def downgrade() -> None:
    for column_name in (
        "before_summary",
        "after_summary",
        "client_type",
        "correlation_id",
        "permission",
    ):
        op.drop_column("audit_events", column_name)
    op.drop_index("ix_oidc_auth_states_expiry", table_name="oidc_authorization_states")
    op.drop_table("oidc_authorization_states")
    op.drop_index("ix_user_sessions_expiry", table_name="user_sessions")
    op.drop_index("ix_user_sessions_principal", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_identity_external_ids_email", table_name="identity_external_ids")
    op.drop_index(
        "ix_identity_external_ids_principal", table_name="identity_external_ids"
    )
    op.drop_table("identity_external_ids")
    for column_name in ("created_by", "scopes"):
        op.drop_column("identity_api_keys", column_name)
    for column_name in (
        "last_login_at_utc",
        "identity_source",
        "email",
        "roles",
    ):
        op.drop_column("identity_principals", column_name)
