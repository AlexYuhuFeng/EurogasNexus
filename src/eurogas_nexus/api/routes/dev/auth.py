"""Development-only credential login (mounted only by the dev route profile).

The development route profile is the only profile that registers this router,
so ``POST /api/dev/auth/login`` does not exist in the internal or release
profiles. Credentials come from ``EUROGAS_NEXUS_DEV_LOGIN_USERNAME`` /
``EUROGAS_NEXUS_DEV_LOGIN_PASSWORD``; no value is defaulted in source, and an
unconfigured deployment answers 503 ``dev_login_disabled``.

A successful login resolves an EXISTING local identity principal by username or
email and requires ``status == "ACTIVE"``. Nothing is invented here: no
principal is created, and no role or data scope is granted by this endpoint.
The session issued on success is the same backend session as the OIDC flow
(shared ``create_principal_session`` + ``eurogas_session`` cookie contract).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from eurogas_nexus.api.routes.public.auth import _session_cookie
from eurogas_nexus.core.config import resolve_dev_login_credentials_from_env
from eurogas_nexus.security.rate_limit import require_auth_rate_limit

router = APIRouter(tags=["dev-auth"])

SESSION_MAX_AGE_SECONDS = 12 * 3600


class DevLoginRequest(BaseModel):
    """Development credential login body with bounded field lengths."""

    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


@router.post("/auth/login")
def dev_login(
    body: DevLoginRequest,
    request: Request,
    _rate: None = Depends(require_auth_rate_limit),
) -> JSONResponse:
    """Authenticate a development operator and start a backend session.

    Responses: 503 ``dev_login_disabled`` when the environment credential pair
    is unset; 401 ``invalid_credentials`` when either field does not match
    (constant-time compare); 403 ``identity_not_provisioned`` when no ACTIVE
    local principal carries that username/email; 200 with the shared
    ``eurogas_session`` cookie on success.
    """

    credentials = resolve_dev_login_credentials_from_env()
    if credentials is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "dev_login_disabled",
                "message": (
                    "Development credential login is not configured; set "
                    "EUROGAS_NEXUS_DEV_LOGIN_USERNAME and "
                    "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD."
                ),
            },
        )
    expected_username, expected_password = credentials
    if not _credentials_match(
        body.username,
        body.password,
        expected_username,
        expected_password,
    ):
        _audit(
            action="auth.dev_login.denied",
            principal="anonymous",
            outcome="denied",
            severity="warning",
            detail="reason=invalid_credentials",
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_credentials",
                "message": "Username or password is incorrect.",
            },
        )

    _require_db()
    from eurogas_nexus.application.enterprise_auth import (
        create_principal_session,
        principal_payload,
    )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            principal = _resolve_active_principal(session, body.username)
            if principal is None:
                result = None
                payload = None
            else:
                result = create_principal_session(
                    session,
                    principal=principal,
                    client_type="dev_credential",
                )
                payload = principal_payload(session, principal)
                session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc

    if result is None or payload is None:
        _audit(
            action="auth.dev_login.denied",
            principal=body.username[:64],
            outcome="denied",
            severity="warning",
            detail="reason=identity_not_provisioned",
        )
        raise HTTPException(
            status_code=403,
            detail={
                "error": "identity_not_provisioned",
                "message": (
                    "No active local identity principal matches this username; "
                    "an administrator must provision it."
                ),
            },
        )

    _audit(
        action="auth.dev_login.success",
        principal=result.principal_id,
        outcome="success",
        severity="info",
        detail="method=dev_credential",
    )
    response = JSONResponse(
        {
            "data": {
                "authenticated": True,
                "principal_id": payload["principal_id"],
                "display_name": payload["display_name"],
                "role": payload["role"],
                "permissions": payload["permissions"],
            },
            "meta": {"research_only": False, "human_review_required": False},
        }
    )
    # Same cookie contract as the OIDC callback (HttpOnly/SameSite=Lax/Path=/).
    response.headers["Set-Cookie"] = _session_cookie(
        result.session_token,
        request=request,
        max_age_seconds=SESSION_MAX_AGE_SECONDS,
    )
    return response


def _credentials_match(
    username: str,
    password: str,
    expected_username: str,
    expected_password: str,
) -> bool:
    """Constant-time compare of both credential fields.

    Both comparisons always run, so a wrong username cannot be distinguished
    from a wrong password by response timing.
    """

    username_matches = hmac.compare_digest(
        username.encode("utf-8"),
        expected_username.encode("utf-8"),
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )
    return username_matches and password_matches


def _resolve_active_principal(session, username: str):
    """Resolve an existing ACTIVE principal by principal name or email."""

    from sqlalchemy import func

    from eurogas_nexus.db.models import IdentityPrincipalRecord

    normalized = username.strip()
    if not normalized:
        return None
    row = (
        session.query(IdentityPrincipalRecord)
        .filter(IdentityPrincipalRecord.name == normalized)
        .one_or_none()
    )
    if row is None:
        row = (
            session.query(IdentityPrincipalRecord)
            .filter(func.lower(IdentityPrincipalRecord.email) == normalized.lower())
            .order_by(IdentityPrincipalRecord.principal_id)
            .first()
        )
    if row is None or row.status != "ACTIVE":
        return None
    return row


def _audit(
    *,
    action: str,
    principal: str,
    outcome: str,
    severity: str,
    detail: str,
) -> None:
    """Best-effort audit of a development login attempt (never raises)."""

    try:
        from eurogas_nexus.application.audit_service import record_audit_event

        record_audit_event(
            event_type="governance.auth",
            action=action,
            resource="dev_credential_login",
            principal=principal,
            outcome=outcome,
            severity=severity,
            detail=detail,
            source_system="dev-auth",
        )
    except Exception:
        return


def _require_db() -> None:
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "runtime_db_required",
                "message": "Development credential login requires the runtime DB.",
            },
        )


def _session():
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "runtime_db_unavailable",
            "message": "Runtime DB is unavailable for authentication.",
            "error_class": exc.__class__.__name__,
        },
    )
