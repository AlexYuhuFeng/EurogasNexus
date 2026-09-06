"""Enterprise Access & Identity administration endpoints.

Every route in this module additionally requires ADMIN (or the documented
operator compatibility for audit export via internal profile). Fine-grained
checks are enforced in the handler; the coarse route permission enforces the
ADMIN role floor.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.security.authorization import (
    Permission,
    authorize,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from eurogas_nexus.security.rate_limit import require_admin_rate_limit

router = APIRouter(tags=["access"], dependencies=[Depends(require_admin_rate_limit)])


class AccessUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED|LOCKED)$")
    roles: list[str] | None = None
    data_scopes: list[str] | None = None
    email: str | None = Field(default=None, max_length=254)


class ApiKeyCreateRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="default", min_length=1, max_length=128)
    expires_at_utc: datetime | None = None
    scopes: list[str] = Field(default_factory=list)


def _require_admin(request: Request, permission: Permission) -> AuthenticatedPrincipal:
    principal = getattr(request.state, "identity", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"error": "principal_missing"})
    decision = authorize(principal, permission)
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "permission_denied",
                "permission": decision.permission.value,
                "reason": decision.reason,
                "research_only": True,
                "human_review_required": True,
            },
        )
    return principal


@router.get("/api/access/users")
def list_users(request: Request) -> dict:
    from eurogas_nexus.db.repositories import identity as identity_repository

    admin = _require_admin(request, Permission.IDENTITY_READ)
    _require_db()

    with _session() as session:
        rows = identity_repository.list_identity_principals(session)
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.users.list",
            resource="identity_principals",
            outcome="listed",
        )
        session.commit()
    return _env(rows)


@router.patch("/api/access/users/{principal_id}")
def patch_user(principal_id: str, body: AccessUpdateRequest, request: Request) -> dict:
    from eurogas_nexus.application.enterprise_auth import assign_access, principal_payload
    from eurogas_nexus.db.repositories import identity as identity_repository

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()

    with _session() as session:
        row = identity_repository.get_identity_principal(session, principal_id)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "user_not_found"})
        before = principal_payload(session, row)
        if body.status:
            row.status = body.status
            if body.status in {"DISABLED", "LOCKED"}:
                from eurogas_nexus.db.repositories.security import revoke_principal_sessions

                revoke_principal_sessions(session, principal_id, now_utc=datetime.now(UTC))
        if body.roles is not None:
            assign_access(
                session,
                principal=row,
                roles=body.roles,
                data_scopes=body.data_scopes if body.data_scopes is not None else row.data_scopes,
                actor=admin.principal_id,
            )
        elif body.data_scopes is not None:
            assign_access(
                session,
                principal=row,
                roles=list(row.roles or [row.role]),
                data_scopes=body.data_scopes,
                actor=admin.principal_id,
            )
        if body.email is not None:
            row.email = body.email or None
        row.updated_at_utc = datetime.now(UTC)
        after = principal_payload(session, row)
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.user.update",
            resource=f"identity_principal:{principal_id}",
            outcome="updated",
            before=before,
            after=after,
        )
        session.commit()
        return _env(after)


@router.get("/api/access/roles")
def list_roles(request: Request) -> dict:
    _require_admin(request, Permission.IDENTITY_READ)
    from eurogas_nexus.security.authorization import ROLE_PERMISSIONS

    return _env(
        {
            role.value: sorted(permission.value for permission in permissions)
            for role, permissions in ROLE_PERMISSIONS.items()
        }
    )


@router.get("/api/access/data-scopes")
def list_data_scopes(request: Request) -> dict:
    _require_admin(request, Permission.IDENTITY_READ)
    return _env(
        {
            "public_baseline": ["operator-input", "ENTSOG", "GIE", "ECB", "Weather"],
            "commercial": ["EEX", "ICE_OCM", "TRAYPORT", "ICIS", "PLATTS", "ARGUS", "KPLER"],
            "wildcard": "*",
        }
    )


@router.get("/api/access/api-keys")
def list_api_keys(request: Request) -> dict:
    from eurogas_nexus.db.repositories import identity as identity_repository

    admin = _require_admin(request, Permission.API_KEYS_MANAGE)
    _require_db()

    with _session() as session:
        rows = identity_repository.list_identity_principals(session)
        keys = [
            key
            for row in rows
            for key in row.get("keys", [])
        ]
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.api_keys.list",
            resource="identity_api_keys",
            outcome="listed",
        )
        session.commit()
    return _env(keys)


@router.post("/api/access/api-keys")
def post_api_key(body: ApiKeyCreateRequest, request: Request) -> dict:
    admin = _require_admin(request, Permission.API_KEYS_MANAGE)
    _require_db()
    try:
        from eurogas_nexus.db.repositories import identity as identity_repository

        with _session() as session:
            key, bearer = identity_repository.create_identity_api_key(
                session,
                body.principal_id,
                display_name=body.display_name,
                expires_at_utc=body.expires_at_utc,
                scopes=body.scopes,
                created_by=admin.principal_id,
            )
            _audit_admin(
                session,
                actor=admin.principal_id,
                action="access.api_key.create",
                resource=f"identity_api_key:{key.key_id}",
                outcome="created",
                detail=f"principal_id={body.principal_id}",
            )
            payload = identity_repository._key_payload(key)
            session.commit()
        return _env(
            {
                "key": payload,
                "api_key": bearer,
                "warning": "Copy the key now; it is returned exactly once.",
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=exc.status_code if hasattr(exc, "status_code") else 422,
            detail={"code": getattr(exc, "code", "api_key_create_failed"), "message": str(exc)},
        ) from exc


@router.post("/api/access/api-keys/{key_id}/revoke")
def revoke_api_key(key_id: str, request: Request) -> dict:
    admin = _require_admin(request, Permission.API_KEYS_MANAGE)
    _require_db()
    with _session() as session:
        from eurogas_nexus.db.models import IdentityApiKeyRecord

        key = session.get(IdentityApiKeyRecord, key_id)
        if key is None:
            raise HTTPException(status_code=404, detail={"code": "api_key_not_found"})
        key.revoked_at_utc = datetime.now(UTC)
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.api_key.revoke",
            resource=f"identity_api_key:{key_id}",
            outcome="revoked",
            detail=f"principal_id={key.principal_id}",
        )
        session.commit()
    return _env({"key_id": key_id, "revoked": True})


@router.get("/api/audit")
def list_audit(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    actor: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=64),
    resource: str | None = Query(default=None, max_length=128),
    outcome: str | None = Query(default=None, max_length=32),
) -> dict:
    admin = _require_admin(request, Permission.AUDIT_READ)
    _require_db()
    with _session() as session:
        from eurogas_nexus.db.models import AuditEventRecord

        query = session.query(AuditEventRecord)
        if actor:
            query = query.filter(AuditEventRecord.principal == actor)
        if action:
            query = query.filter(AuditEventRecord.action == action)
        if resource:
            query = query.filter(AuditEventRecord.resource.ilike(f"%{resource}%"))
        if outcome:
            query = query.filter(AuditEventRecord.outcome == outcome)
        rows = query.order_by(AuditEventRecord.event_ts_utc.desc()).limit(limit).all()
        data = [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in rows
        ]
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.audit.list",
            resource="audit_events",
            outcome="listed",
            detail=f"limit={limit}",
        )
        session.commit()
    return _env(data)


@router.get("/api/access/sso")
def get_sso_profile(request: Request) -> dict:
    from eurogas_nexus.security.oidc import configured_oidc_profile

    _require_admin(request, Permission.IDENTITY_READ)
    return _env(configured_oidc_profile())


def _audit_admin(
    session,
    *,
    actor: str,
    action: str,
    resource: str,
    outcome: str,
    detail: str = "",
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    try:
        from eurogas_nexus.db.repositories.audit import record_audit_event

        record_audit_event(
            session,
            event_type="governance.access",
            principal=actor,
            action=action,
            resource=resource,
            outcome=outcome,
            severity="info",
            detail=detail,
            source_system="access-api",
            now_utc=datetime.now(UTC),
        )
    except Exception:
        return


def _env(data, *, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings or [],
        },
    }


def _require_db() -> None:
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_required",
                "message": "Access administration requires the runtime DB.",
            },
        )


def _session():
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()
