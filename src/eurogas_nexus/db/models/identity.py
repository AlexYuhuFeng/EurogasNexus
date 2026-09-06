"""Production identity persistence models (R32 + CR-10).

Local USER/SERVICE principals are authenticated by hashed bearer API keys,
interactive OIDC sessions, or validated OIDC access tokens. No local password
material is stored. API-key plaintext is returned exactly once and only its
SHA-256 hash is persisted; session tokens are likewise stored only as hashes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class IdentityPrincipalRecord(Base):
    """One local identity principal and its role/data-scope grants."""

    __tablename__ = "identity_principals"
    __table_args__ = (
        Index("ix_identity_principals_role_status", "role", "status"),
    )

    principal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    roles: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    identity_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="LOCAL", server_default="LOCAL"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    data_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_login_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )



class IdentityApiKeyRecord(Base):
    """One hashed bearer API key bound to a principal.

    ``key_hash`` is the SHA-256 hex digest of the generated secret; the full
    bearer token is ``nexus_<key_id>_<secret>``.
    """

    __tablename__ = "identity_api_keys"
    __table_args__ = (
        Index("ix_identity_api_keys_principal", "principal_id", "revoked_at_utc"),
    )

    key_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    principal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("identity_principals.principal_id"),
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_bootstrap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scopes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class IdentityExternalIdRecord(Base):
    """Canonical issuer+subject mapping from an OIDC provider to a principal."""

    __tablename__ = "identity_external_ids"
    __table_args__ = (
        Index("ix_identity_external_ids_principal", "principal_id"),
        Index("ix_identity_external_ids_email", "email"),
    )

    identity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("identity_principals.principal_id"),
        nullable=False,
    )
    issuer: Mapped[str] = mapped_column(String(256), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class UserSessionRecord(Base):
    """One backend-managed interactive session (token stored as SHA-256)."""

    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_principal", "principal_id", "revoked_at_utc"),
        Index("ix_user_sessions_expiry", "expires_at_utc"),
    )

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("identity_principals.principal_id"),
        nullable=False,
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    client_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="browser"
    )
    client_label: Mapped[str | None] = mapped_column(String(128), nullable=True)


class OidcAuthorizationStateRecord(Base):
    """One-time interactive OIDC authorization state (PKCE + nonce)."""

    __tablename__ = "oidc_authorization_states"
    __table_args__ = (
        Index("ix_oidc_auth_states_expiry", "expires_at_utc"),
    )

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    code_challenge_method: Mapped[str] = mapped_column(String(16), nullable=False)
    code_verifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    flow_type: Mapped[str] = mapped_column(String(16), nullable=False, default="browser")
    client_type: Mapped[str] = mapped_column(String(16), nullable=False, default="browser")
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
