"""Production identity persistence models (R32).

Identities are local PostgreSQL principals (USER or SERVICE) authenticated by
hashed bearer API keys. No password, SSO, or browser-session material is stored
in this schema. Key plaintext is returned exactly once by the internal
administration endpoint and only its SHA-256 hash is persisted.
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
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    data_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
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
