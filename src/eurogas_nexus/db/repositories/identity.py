"""Identity principal and API-key repository (R32)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.identity import IdentityApiKeyRecord, IdentityPrincipalRecord
from eurogas_nexus.domain.identity.principal import normalize_principal
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    IdentityAuthError,
    generate_api_key,
    parse_identity_bearer,
    role_value,
    verify_key_hash,
)


def list_identity_principals(session: Session) -> list[dict]:
    """List active and disabled identities with key metadata (never hashes)."""

    rows = session.query(IdentityPrincipalRecord).order_by(
        IdentityPrincipalRecord.principal_id
    )
    keys_by_principal: dict[str, list[IdentityApiKeyRecord]] = {}
    for key in session.query(IdentityApiKeyRecord).order_by(
        IdentityApiKeyRecord.created_at_utc
    ).all():
        keys_by_principal.setdefault(key.principal_id, []).append(key)
    return [
        _principal_payload(row, keys_by_principal.get(row.principal_id, []))
        for row in rows.all()
    ]


def get_identity_principal(session: Session, principal_id: str) -> IdentityPrincipalRecord | None:
    """Fetch one identity principal by id."""

    return session.get(IdentityPrincipalRecord, principal_id)


def create_identity_principal(
    session: Session,
    *,
    name: str,
    display_name: str,
    role: str,
    principal_type: str = "USER",
    data_scopes: list[str] | None = None,
    now_utc: datetime | None = None,
) -> IdentityPrincipalRecord:
    """Create a local identity principal and return it (no key yet)."""

    normalized_name = normalize_principal(name)
    normalized_type = (principal_type or "USER").strip().upper()
    if normalized_type not in {"USER", "SERVICE"}:
        raise IdentityAuthError(
            code="identity_principal_type_invalid",
            status_code=422,
            message="principal_type must be USER or SERVICE.",
        )
    role_value(role)
    now = _as_utc(now_utc or datetime.now(UTC))
    row = IdentityPrincipalRecord(
        principal_id=f"principal-{uuid4().hex[:12]}",
        principal_type=normalized_type,
        name=normalized_name,
        display_name=(display_name or "").strip() or normalized_name,
        role=role.strip().upper(),
        status="ACTIVE",
        data_scopes=[
            _normalize_scope(scope)
            for scope in (data_scopes or [])
            if _normalize_scope(scope)
        ],
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        raise IdentityAuthError(
            code="identity_principal_exists",
            status_code=409,
            message=f"Identity name {normalized_name!r} already exists.",
        ) from exc
    return row


def disable_identity_principal(
    session: Session,
    principal_id: str,
    *,
    now_utc: datetime | None = None,
) -> IdentityPrincipalRecord | None:
    """Disable a principal; its keys stop authenticating immediately."""

    row = get_identity_principal(session, principal_id)
    if row is None:
        return None
    row.status = "DISABLED"
    row.updated_at_utc = _as_utc(now_utc or datetime.now(UTC))
    session.flush()
    return row


def create_identity_api_key(
    session: Session,
    principal_id: str,
    *,
    display_name: str = "default",
    expires_at_utc: datetime | None = None,
    now_utc: datetime | None = None,
) -> tuple[IdentityApiKeyRecord, str]:
    """Create one hashed bearer key for an active principal.

    Returns the record and the one-time plaintext bearer. The repository and
    DB never see the plaintext again.
    """

    principal = get_identity_principal(session, principal_id)
    if principal is None:
        raise IdentityAuthError(
            code="identity_principal_not_found",
            status_code=404,
            message=f"Identity principal {principal_id!r} not found.",
        )
    if principal.status != "ACTIVE":
        raise IdentityAuthError(
            code="identity_principal_disabled",
            status_code=403,
            message="Identity principal is disabled.",
        )
    now = _as_utc(now_utc or datetime.now(UTC))
    key_id = uuid4().hex[:24]
    key = generate_api_key(key_id=key_id, display_name=(display_name or "default").strip())
    row = IdentityApiKeyRecord(
        key_id=key.key_id,
        principal_id=principal.principal_id,
        key_hash=key.key_hash,
        key_prefix=key.key_prefix,
        display_name=key.display_name,
        expires_at_utc=expires_at_utc,
        last_used_at_utc=None,
        created_at_utc=now,
        revoked_at_utc=None,
        is_bootstrap=False,
    )
    session.add(row)
    session.flush()
    return row, key.bearer


def rotate_identity_api_key(
    session: Session,
    principal_id: str,
    key_id: str,
    *,
    display_name: str = "rotated",
    expires_at_utc: datetime | None = None,
    now_utc: datetime | None = None,
) -> tuple[IdentityApiKeyRecord, str] | None:
    """Revoke an existing key and issue a replacement; old key stops working."""

    now = _as_utc(now_utc or datetime.now(UTC))
    old = session.get(IdentityApiKeyRecord, key_id)
    if old is None or old.principal_id != principal_id:
        return None
    if old.revoked_at_utc is None:
        old.revoked_at_utc = now
        session.flush()
    return create_identity_api_key(
        session,
        principal_id,
        display_name=display_name,
        expires_at_utc=expires_at_utc,
        now_utc=now,
    )


def revoke_identity_api_key(
    session: Session,
    principal_id: str,
    key_id: str,
    *,
    now_utc: datetime | None = None,
) -> IdentityApiKeyRecord | None:
    """Revoke one key; authentication fails immediately."""

    row = session.get(IdentityApiKeyRecord, key_id)
    if row is None or row.principal_id != principal_id:
        return None
    if row.revoked_at_utc is None:
        row.revoked_at_utc = _as_utc(now_utc or datetime.now(UTC))
        session.flush()
    return row


def authenticate_identity_bearer(
    session: Session,
    bearer: str | None,
    *,
    now_utc: datetime | None = None,
) -> AuthenticatedPrincipal:
    """Authenticate an ``X-Eurogas-Identity`` bearer against PostgreSQL."""

    parsed = parse_identity_bearer(bearer)
    if parsed is None:
        raise IdentityAuthError(
            code="identity_bearer_missing",
            status_code=401,
            message="X-Eurogas-Identity must be a nexus_<key_id>_<secret> bearer.",
        )
    key_id, secret = parsed
    key = session.get(IdentityApiKeyRecord, key_id)
    if key is None:
        raise IdentityAuthError(
            code="identity_key_invalid",
            status_code=403,
            message="Identity key is invalid.",
        )
    now = _as_utc(now_utc or datetime.now(UTC))
    if key.revoked_at_utc is not None:
        raise IdentityAuthError(
            code="identity_key_revoked",
            status_code=403,
            message="Identity key has been revoked.",
        )
    if key.expires_at_utc is not None and _as_utc(key.expires_at_utc) <= now:
        raise IdentityAuthError(
            code="identity_key_expired",
            status_code=403,
            message="Identity key has expired.",
        )
    if not verify_key_hash(secret, key.key_hash):
        raise IdentityAuthError(
            code="identity_key_invalid",
            status_code=403,
            message="Identity key is invalid.",
        )
    principal = get_identity_principal(session, key.principal_id)
    if principal is None:
        raise IdentityAuthError(
            code="identity_principal_not_found",
            status_code=403,
            message="Identity principal is missing.",
        )
    if principal.status != "ACTIVE":
        raise IdentityAuthError(
            code="identity_principal_disabled",
            status_code=403,
            message="Identity principal is disabled.",
        )
    key.last_used_at_utc = now
    session.flush()
    return AuthenticatedPrincipal(
        principal_id=principal.principal_id,
        name=principal.name,
        principal_type=principal.principal_type,
        role=principal.role,
        status=principal.status,
        data_scopes=tuple(principal.data_scopes or []),
        auth_method="identity_key",
    )


def _principal_payload(
    row: IdentityPrincipalRecord,
    keys: list[IdentityApiKeyRecord],
) -> dict:
    return {
        "principal_id": row.principal_id,
        "principal_type": row.principal_type,
        "name": row.name,
        "display_name": row.display_name,
        "role": row.role,
        "status": row.status,
        "data_scopes": row.data_scopes,
        "created_at_utc": row.created_at_utc.isoformat(),
        "updated_at_utc": row.updated_at_utc.isoformat(),
        "keys": [_key_payload(key) for key in keys],
    }


def _key_payload(key: IdentityApiKeyRecord) -> dict:
    return {
        "key_id": key.key_id,
        "key_prefix": key.key_prefix,
        "display_name": key.display_name,
        "expires_at_utc": key.expires_at_utc.isoformat() if key.expires_at_utc else None,
        "last_used_at_utc": (
            key.last_used_at_utc.isoformat() if key.last_used_at_utc else None
        ),
        "created_at_utc": key.created_at_utc.isoformat(),
        "revoked_at_utc": key.revoked_at_utc.isoformat() if key.revoked_at_utc else None,
        "is_bootstrap": key.is_bootstrap,
    }


def _normalize_scope(scope: str) -> str:
    return scope.strip().upper()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
