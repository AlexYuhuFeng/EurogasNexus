"""Internal R32 identity and audit-governance administration routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from eurogas_nexus.security.identity import IdentityAuthError, role_value
from eurogas_nexus.security.internal_api import (
    InternalApiAuthError,
    validate_internal_operator_headers,
)

router = APIRouter(tags=["internal-identity"])


class IdentityCreateRequest(BaseModel):
    """Create a local identity principal (no key issued here)."""

    name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="", max_length=128)
    principal_type: str = Field(default="USER", pattern="^(USER|SERVICE)$")
    role: str = Field(default="VIEWER", pattern="^(VIEWER|ANALYST|OPERATOR|ADMIN)$")
    data_scopes: list[str] = Field(default_factory=list)


class ApiKeyCreateRequest(BaseModel):
    """Issue one hashed API key for an active principal."""

    display_name: str = Field(default="default", min_length=1, max_length=128)
    expires_at_utc: datetime | None = None


class AuditPruneRequest(BaseModel):
    """Operator-controlled audit retention prune (dry-run by default)."""

    retention_days: int = Field(default=365, ge=30, le=3650)
    dry_run: bool = True


def _operator_principal(
    x_eurogas_principal: str | None,
    x_eurogas_internal_token: str | None,
) -> str:
    try:
        return validate_internal_operator_headers(
            token=x_eurogas_internal_token,
            principal=x_eurogas_principal,
        )
    except InternalApiAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("/identities")
def list_identities(
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """List local identity principals and key metadata (never hashes)."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.db.repositories.identity import list_identity_principals
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = list_identity_principals(session)
            _audit(
                session,
                principal=operator,
                action="identity.list",
                resource="identity_principals",
                outcome="listed",
            )
            session.commit()
        return {"data": rows, "meta": {"human_review_required": True}}
    except IdentityAuthError as exc:
        raise _identity_error(exc) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/identities")
def post_identity(
    body: IdentityCreateRequest,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Create one USER or SERVICE identity with explicit role and data scopes."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    role_value(body.role)
    try:
        from eurogas_nexus.db.repositories.identity import create_identity_principal
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = create_identity_principal(
                session,
                name=body.name,
                display_name=body.display_name,
                role=body.role,
                principal_type=body.principal_type,
                data_scopes=body.data_scopes,
            )
            _audit(
                session,
                principal=operator,
                action="identity.create",
                resource=f"identity_principal:{row.principal_id}",
                outcome="created",
                detail=f"name={row.name}; role={row.role}",
            )
            session.commit()
            return {"data": _principal_payload(row), "meta": {"human_review_required": True}}
    except IdentityAuthError as exc:
        raise _identity_error(exc) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/identities/{principal_id}/keys")
def post_identity_key(
    principal_id: str,
    body: ApiKeyCreateRequest,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Issue one bearer API key; plaintext is returned exactly once."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.db.repositories.identity import create_identity_api_key
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            key, bearer = create_identity_api_key(
                session,
                principal_id,
                display_name=body.display_name,
                expires_at_utc=body.expires_at_utc,
            )
            _audit(
                session,
                principal=operator,
                action="identity.key.issue",
                resource=f"identity_api_key:{key.key_id}",
                outcome="issued",
                detail=f"principal_id={principal_id}",
            )
            session.commit()
            return {
                "data": {"key": _key_payload(key), "api_key": bearer},
                "meta": {"human_review_required": True},
            }
    except IdentityAuthError as exc:
        raise _identity_error(exc) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/identities/{principal_id}/keys/{key_id}/rotate")
def post_identity_key_rotate(
    principal_id: str,
    key_id: str,
    body: ApiKeyCreateRequest,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Revoke an existing key and issue a replacement (plaintext once)."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.db.repositories.identity import rotate_identity_api_key
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rotated = rotate_identity_api_key(
                session,
                principal_id,
                key_id,
                display_name=body.display_name,
                expires_at_utc=body.expires_at_utc,
            )
            if rotated is None:
                raise IdentityAuthError(
                    code="identity_key_not_found",
                    status_code=404,
                    message="Identity key was not found for this principal.",
                )
            key, bearer = rotated
            _audit(
                session,
                principal=operator,
                action="identity.key.rotate",
                resource=f"identity_api_key:{key.key_id}",
                outcome="rotated",
                detail=f"principal_id={principal_id}; revoked_key_id={key_id}",
            )
            session.commit()
            return {
                "data": {"key": _key_payload(key), "api_key": bearer},
                "meta": {"human_review_required": True},
            }
    except IdentityAuthError as exc:
        raise _identity_error(exc) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/identities/{principal_id}/keys/{key_id}/revoke")
def post_identity_key_revoke(
    principal_id: str,
    key_id: str,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Revoke one API key; it stops authenticating immediately."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.db.repositories.identity import revoke_identity_api_key
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            key = revoke_identity_api_key(session, principal_id, key_id)
            if key is None:
                raise IdentityAuthError(
                    code="identity_key_not_found",
                    status_code=404,
                    message="Identity key was not found for this principal.",
                )
            _audit(
                session,
                principal=operator,
                action="identity.key.revoke",
                resource=f"identity_api_key:{key.key_id}",
                outcome="revoked",
                detail=f"principal_id={principal_id}",
            )
            session.commit()
            return {"data": {"key": _key_payload(key)}, "meta": {"human_review_required": True}}
    except IdentityAuthError as exc:
        raise _identity_error(exc) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/identities/{principal_id}/disable")
def post_identity_disable(
    principal_id: str,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Disable a principal; all of its keys stop authenticating."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.db.repositories.identity import disable_identity_principal
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            row = disable_identity_principal(session, principal_id)
            if row is None:
                raise IdentityAuthError(
                    code="identity_principal_not_found",
                    status_code=404,
                    message="Identity principal was not found.",
                )
            _audit(
                session,
                principal=operator,
                action="identity.disable",
                resource=f"identity_principal:{row.principal_id}",
                outcome="disabled",
            )
            session.commit()
            return {"data": _principal_payload(row), "meta": {"human_review_required": True}}
    except IdentityAuthError as exc:
        raise _identity_error(exc) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.get("/audit/events")
def get_audit_events(
    limit: int = Query(default=200, ge=1, le=1000),
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Export bounded audit-event rows for governance review (no secrets)."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.db.models import AuditEventRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = (
                session.query(AuditEventRecord)
                .order_by(AuditEventRecord.event_ts_utc.desc())
                .limit(limit)
                .all()
            )
            _audit(
                session,
                principal=operator,
                action="audit.export",
                resource="audit_events",
                outcome="exported",
                detail=f"limit={limit}",
            )
            session.commit()
            return {
                "data": [
                    {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    for row in rows
                ],
                "meta": {"human_review_required": True, "limit": limit},
            }
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.post("/audit/prune")
def post_audit_prune(
    body: AuditPruneRequest,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None, alias="X-Eurogas-Internal-Token"
    ),
) -> dict:
    """Prune audit rows older than the retention policy (dry-run default)."""

    operator = _operator_principal(x_eurogas_principal, x_eurogas_internal_token)
    _require_db()
    try:
        from eurogas_nexus.application.audit_retention import prune_expired_audit_events
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            summary = prune_expired_audit_events(
                session,
                retention_days=body.retention_days,
                dry_run=body.dry_run,
            )
            _audit(
                session,
                principal=operator,
                action="audit.retention.prune",
                resource="audit_events",
                outcome="dry_run" if body.dry_run else "pruned",
                detail=f"retention_days={body.retention_days}",
            )
            session.commit()
            return {"data": summary, "meta": {"human_review_required": True}}
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


def _audit(
    session,
    *,
    principal: str,
    action: str,
    resource: str,
    outcome: str,
    detail: str = "",
) -> None:
    try:
        from eurogas_nexus.db.repositories.audit import record_audit_event

        record_audit_event(
            session,
            event_type="governance.identity",
            principal=principal,
            action=action,
            resource=resource,
            outcome=outcome,
            severity="info",
            detail=detail,
            source_system="internal-api",
            now_utc=datetime.now(UTC),
        )
    except Exception:
        return


def _principal_payload(row, keys: list | None = None) -> dict:
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
        "keys": [_key_payload(key) for key in (keys or [])],
    }


def _key_payload(key) -> dict:
    return {
        "key_id": key.key_id,
        "principal_id": key.principal_id,
        "key_prefix": key.key_prefix,
        "display_name": key.display_name,
        "expires_at_utc": key.expires_at_utc.isoformat() if key.expires_at_utc else None,
        "last_used_at_utc": (
            key.last_used_at_utc.isoformat() if key.last_used_at_utc else None
        ),
        "created_at_utc": key.created_at_utc.isoformat(),
        "revoked_at_utc": key.revoked_at_utc.isoformat() if key.revoked_at_utc else None,
    }


def _require_db() -> None:
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_required",
                "message": "Identity/audit administration requires the runtime DB.",
            },
        )


def _identity_error(exc: IdentityAuthError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime DB is unavailable for identity/audit administration.",
            "error_class": exc.__class__.__name__,
        },
    )
