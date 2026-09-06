"""CR-10 session, external-identity, and OIDC-state persistence.

Session and PKCE secrets are stored as SHA-256 digests only. Authorization
state rows are one-time, expire quickly, and are consumed atomically.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.identity import (
    IdentityExternalIdRecord,
    IdentityPrincipalRecord,
    OidcAuthorizationStateRecord,
    UserSessionRecord,
)
from eurogas_nexus.domain.dataops.contracts import as_utc

SESSION_TTL_HOURS = 12
SESSION_ABSOLUTE_TTL_HOURS = 24


def hash_session_token(token: str) -> str:
    """Return the non-reversible digest for a session token."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_code_verifier(verifier: str) -> str:
    """Return the non-reversible digest for a PKCE verifier."""

    return hashlib.sha256(verifier.encode("utf-8")).hexdigest()


def create_session(
    session: Session,
    *,
    principal_id: str,
    token: str,
    client_type: str = "browser",
    client_label: str | None = None,
    now_utc: datetime | None = None,
) -> UserSessionRecord:
    now = as_utc(now_utc or datetime.now(UTC))
    row = UserSessionRecord(
        session_id=f"session-{uuid4().hex[:20]}",
        principal_id=principal_id,
        session_token_hash=hash_session_token(token),
        created_at_utc=now,
        last_seen_at_utc=now,
        expires_at_utc=now + timedelta(hours=SESSION_TTL_HOURS),
        revoked_at_utc=None,
        client_type=client_type[:32],
        client_label=(client_label or "")[:128] or None,
    )
    session.add(row)
    session.flush()
    return row


def get_active_session_by_token(
    session: Session,
    token: str,
    *,
    now_utc: datetime | None = None,
) -> UserSessionRecord | None:
    now = as_utc(now_utc or datetime.now(UTC))
    row = (
        session.query(UserSessionRecord)
        .filter(UserSessionRecord.session_token_hash == hash_session_token(token))
        .filter(UserSessionRecord.revoked_at_utc.is_(None))
        .one_or_none()
    )
    if row is not None and as_utc(row.expires_at_utc) <= now:
        return None
    if row is None:
        return None
    principal = session.get(IdentityPrincipalRecord, row.principal_id)
    if principal is None or principal.status != "ACTIVE":
        return None
    return row


def touch_session(
    session: Session,
    row: UserSessionRecord,
    *,
    now_utc: datetime | None = None,
) -> None:
    now = as_utc(now_utc or datetime.now(UTC))
    if (now - as_utc(row.last_seen_at_utc)).total_seconds() < 60:
        return
    row.last_seen_at_utc = now
    absolute_expiry = as_utc(row.created_at_utc) + timedelta(
        hours=SESSION_ABSOLUTE_TTL_HOURS
    )
    if now >= absolute_expiry:
        row.revoked_at_utc = now
        return
    row.expires_at_utc = min(now + timedelta(hours=SESSION_TTL_HOURS), absolute_expiry)
    session.flush()


def revoke_session_by_token(
    session: Session,
    token: str,
    *,
    now_utc: datetime | None = None,
) -> bool:
    row = get_active_session_by_token(session, token, now_utc=now_utc)
    if row is None:
        return False
    row.revoked_at_utc = as_utc(now_utc or datetime.now(UTC))
    session.flush()
    return True


def revoke_principal_sessions(
    session: Session,
    principal_id: str,
    *,
    now_utc: datetime | None = None,
) -> int:
    now = as_utc(now_utc or datetime.now(UTC))
    return (
        session.query(UserSessionRecord)
        .filter(
            UserSessionRecord.principal_id == principal_id,
            UserSessionRecord.revoked_at_utc.is_(None),
        )
        .update({"revoked_at_utc": now}, synchronize_session=False)
    )


def create_external_identity(
    session: Session,
    *,
    principal_id: str,
    issuer: str,
    subject: str,
    provider_id: str,
    email: str | None,
    display_name: str,
    now_utc: datetime | None = None,
) -> IdentityExternalIdRecord:
    now = as_utc(now_utc or datetime.now(UTC))
    row = (
        session.query(IdentityExternalIdRecord)
        .filter(
            IdentityExternalIdRecord.issuer == issuer,
            IdentityExternalIdRecord.subject == subject,
        )
        .one_or_none()
    )
    if row is None:
        row = IdentityExternalIdRecord(
            identity_id=f"ext-{uuid4().hex[:20]}",
            principal_id=principal_id,
            issuer=issuer,
            subject=subject,
            provider_id=provider_id,
            email=email,
            display_name=display_name,
            created_at_utc=now,
            last_seen_at_utc=now,
        )
        session.add(row)
    else:
        if row.principal_id != principal_id:
            raise ValueError("external identity is already bound to another principal")
        row.email = email
        row.display_name = display_name
        row.last_seen_at_utc = now
    session.flush()
    return row


def find_external_identity(
    session: Session,
    issuer: str,
    subject: str,
) -> IdentityExternalIdRecord | None:
    return (
        session.query(IdentityExternalIdRecord)
        .filter(
            IdentityExternalIdRecord.issuer == issuer,
            IdentityExternalIdRecord.subject == subject,
        )
        .one_or_none()
    )


def create_oidc_authorization_state(
    session: Session,
    *,
    state: str,
    code_challenge: str,
    code_challenge_method: str,
    code_verifier: str,
    nonce: str,
    redirect_uri: str,
    flow_type: str = "browser",
    client_type: str = "browser",
    ttl_seconds: int = 300,
    now_utc: datetime | None = None,
) -> OidcAuthorizationStateRecord:
    now = as_utc(now_utc or datetime.now(UTC))
    row = OidcAuthorizationStateRecord(
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        code_verifier_hash=hash_code_verifier(code_verifier),
        nonce=nonce,
        redirect_uri=redirect_uri,
        flow_type=flow_type,
        client_type=client_type,
        created_at_utc=now,
        expires_at_utc=now + timedelta(seconds=max(30, ttl_seconds)),
        consumed_at_utc=None,
    )
    session.add(row)
    session.flush()
    return row


def consume_oidc_authorization_state(
    session: Session,
    state: str,
    *,
    now_utc: datetime | None = None,
) -> OidcAuthorizationStateRecord | None:
    now = as_utc(now_utc or datetime.now(UTC))
    row = session.get(OidcAuthorizationStateRecord, state)
    if row is None or row.consumed_at_utc is not None or as_utc(row.expires_at_utc) <= now:
        return None
    row.consumed_at_utc = now
    session.flush()
    return row
