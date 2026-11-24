"""Enterprise Access & Identity administration endpoints.

Administration routes additionally require ADMIN (or the documented
operator compatibility for audit export via internal profile). The self-service
group picker exposes only the authenticated principal's own group names. Fine-grained
checks are enforced in the handler; the coarse route permission enforces the
ADMIN role floor.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.governance.audit import GovernedAuditError
from eurogas_nexus.security.authorization import (
    Permission,
    authorize,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from eurogas_nexus.security.rate_limit import require_admin_rate_limit

router = APIRouter(tags=["access"], dependencies=[Depends(require_admin_rate_limit)])

#: Refusal code for a caller that would change its own roles or data scopes.
ENTITLEMENT_SELF_GRANT_FORBIDDEN = "entitlement_self_grant_forbidden"


class AccessUpdateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED|LOCKED)$")
    roles: list[str] | None = None
    data_scopes: list[str] | None = None
    email: str | None = Field(default=None, max_length=254)
    # Composition only (never a grant): what the person does and where they sit.
    job_functions: list[str] | None = Field(default=None, max_length=10)
    office: str | None = Field(default=None, max_length=16, pattern="^[A-Za-z]{0,16}$")


class UserCreateRequest(BaseModel):
    """Add a person: a company-SSO invite or a local account (as the deployment allows)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: str = Field(pattern="^(local|sso)$")
    #: Local accounts: the sign-in name (letters, digits, . _ @ -).
    username: str | None = Field(default=None, max_length=64)
    display_name: str = Field(default="", max_length=128)
    email: str | None = Field(default=None, max_length=254)
    #: SSO invites: the provider's subject, when known (otherwise the e-mail matches).
    subject: str | None = Field(default=None, max_length=256)
    roles: list[str] = Field(default_factory=lambda: ["VIEWER"], max_length=8)
    data_scopes: list[str] = Field(default_factory=list, max_length=64)
    job_functions: list[str] = Field(default_factory=list, max_length=10)
    office: str | None = Field(default=None, max_length=16, pattern="^[A-Za-z]{0,16}$")
    groups: list[str] = Field(default_factory=list, max_length=32)


class LicenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    vendor: str = Field(min_length=1, max_length=64)
    source_family: str = Field(min_length=1, max_length=32, pattern="^[A-Za-z0-9_]+$")
    licence_type: str = Field(pattern="^(ENTERPRISE|SITE|NAMED_USER)$")
    licensed_use: str = Field(pattern="^(DISPLAY|NON_DISPLAY|DISPLAY_AND_NON_DISPLAY)$")
    valid_from: date
    valid_to: date | None = None
    offices: list[str] = Field(default_factory=list, max_length=32)
    seats: int | None = Field(default=None, ge=1, le=100_000)
    contract_reference: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=2000)


class ApiKeyCreateRequest(BaseModel):
    principal_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(default="default", min_length=1, max_length=128)
    expires_at_utc: datetime | None = None
    scopes: list[str] = Field(default_factory=list)


class OwnApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    display_name: str = Field(default="personal", min_length=1, max_length=128)
    expires_at_utc: datetime | None = None
    scopes: list[str] = Field(default_factory=list, max_length=32)


#: A personal key lives this long unless asked for less, and never longer than the maximum.
OWN_KEY_DEFAULT_DAYS = 90
OWN_KEY_MAX_DAYS = 365
#: How a person must be signed in to issue a key for themselves: interactively, so a stolen
#: key cannot mint a successor that outlives its revocation.
INTERACTIVE_AUTH_METHODS = frozenset({"session", "oidc_access_token", "gateway_header"})


class GroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)


class GroupUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")


def _group_payload(row) -> dict:
    return {"group_id": row.group_id, "name": row.name, "status": row.status}


@router.get("/api/me/groups")
def own_groups(request: Request) -> dict:
    from eurogas_nexus.db.models.strategy_access import (
        IdentityGroupMemberRecord,
        IdentityGroupRecord,
    )
    from eurogas_nexus.db.repositories.strategy_access import require_named_principal

    principal = getattr(request.state, "identity", None)
    _require_db()
    with _session() as session:
        principal_id = require_named_principal(session, getattr(principal, "principal_id", None))
        rows = (
            session.query(IdentityGroupRecord)
            .join(
                IdentityGroupMemberRecord,
                IdentityGroupMemberRecord.group_id == IdentityGroupRecord.group_id,
            )
            .filter(
                IdentityGroupMemberRecord.principal_id == principal_id,
                IdentityGroupRecord.status == "ACTIVE",
            )
            .order_by(IdentityGroupRecord.name, IdentityGroupRecord.group_id)
            .all()
        )
        return _env([{"group_id": row.group_id, "name": row.name} for row in rows])


def _own_key_principal(request: Request, *, issuing: bool) -> AuthenticatedPrincipal:
    principal = getattr(request.state, "identity", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"code": "authentication_required"})
    if principal.principal_type != "USER":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "personal_keys_are_for_people",
                "message": "A service principal's keys are issued by an administrator.",
            },
        )
    if issuing and principal.auth_method not in INTERACTIVE_AUTH_METHODS:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "interactive_sign_in_required",
                "message": "Sign in to the product to create a key; a key cannot create a key.",
            },
        )
    return principal


@router.get("/api/me/api-keys")
def own_api_keys(request: Request) -> dict:
    """The caller's own API keys (never the secret, which is shown once at creation).

    调用者自己的 API 密钥列表（不含密钥本身，密钥仅在创建时显示一次）。
    """

    from eurogas_nexus.db.models import IdentityApiKeyRecord
    from eurogas_nexus.db.repositories import identity as identity_repository

    principal = _own_key_principal(request, issuing=False)
    _require_db()
    with _session() as session:
        rows = (
            session.query(IdentityApiKeyRecord)
            .filter(IdentityApiKeyRecord.principal_id == principal.principal_id)
            .order_by(IdentityApiKeyRecord.created_at_utc.desc())
            .all()
        )
        return _env([identity_repository._key_payload(row) for row in rows])


@router.post("/api/me/api-keys")
def create_own_api_key(body: OwnApiKeyCreateRequest, request: Request) -> dict:
    """Create a personal API key for the signed-in person, for the SDK or a script.

    为当前登录用户创建个人 API 密钥（用于 SDK 或脚本）；密钥仅显示一次。

    The key acts as the person and never beyond them: its scopes must be ones the person
    holds, it expires (90 days by default, at most 365), and only an interactive sign-in
    may create one. The secret is returned exactly once; the creation is audited.
    """

    from eurogas_nexus.db.repositories import identity as identity_repository

    principal = _own_key_principal(request, issuing=True)
    _require_db()
    now = datetime.now(UTC)
    expires = body.expires_at_utc or now + timedelta(days=OWN_KEY_DEFAULT_DAYS)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= now or expires > now + timedelta(days=OWN_KEY_MAX_DAYS):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "key_expiry_out_of_range",
                "message": f"A personal key expires within {OWN_KEY_MAX_DAYS} days.",
            },
        )
    held = {str(scope).upper() for scope in principal.data_scopes}
    asked = [str(scope).strip().upper() for scope in body.scopes if str(scope).strip()]
    not_held = sorted(scope for scope in asked if "*" not in held and scope not in held)
    if not_held:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "scope_not_held",
                "message": "A key cannot reach data its owner cannot: " + ", ".join(not_held),
            },
        )
    with _session() as session:
        key, bearer = identity_repository.create_identity_api_key(
            session,
            principal.principal_id,
            display_name=body.display_name,
            expires_at_utc=expires,
            scopes=asked or list(principal.data_scopes),
            created_by=principal.principal_id,
        )
        _audit_admin(
            session,
            actor=principal.principal_id,
            action="me.api_key.create",
            resource=f"identity_api_key:{key.key_id}",
            outcome="created",
            detail=f"expires_at_utc={expires.isoformat()}",
        )
        payload = identity_repository._key_payload(key)
        session.commit()
    return _env(
        {"key": payload, "api_key": bearer, "warning": "Copy the key now; it is shown once."}
    )


@router.post("/api/me/api-keys/{key_id}/revoke")
def revoke_own_api_key(key_id: str, request: Request) -> dict:
    """Revoke one of the caller's own API keys; any way of signing in may revoke.

    撤销调用者自己的一个 API 密钥。
    """

    from eurogas_nexus.db.models import IdentityApiKeyRecord

    principal = _own_key_principal(request, issuing=False)
    _require_db()
    with _session() as session:
        key = session.get(IdentityApiKeyRecord, key_id)
        if key is None or key.principal_id != principal.principal_id:
            raise HTTPException(status_code=404, detail={"code": "api_key_not_found"})
        if key.revoked_at_utc is None:
            key.revoked_at_utc = datetime.now(UTC)
        _audit_admin(
            session,
            actor=principal.principal_id,
            action="me.api_key.revoke",
            resource=f"identity_api_key:{key_id}",
            outcome="revoked",
        )
        session.commit()
    return _env({"key_id": key_id, "revoked": True})


@router.get("/api/access/groups")
def list_groups(request: Request) -> dict:
    from eurogas_nexus.db.models.strategy_access import IdentityGroupRecord

    _require_admin(request, Permission.IDENTITY_READ)
    _require_db()
    with _session() as session:
        return _env(
            [
                _group_payload(row)
                for row in session.query(
                    IdentityGroupRecord,
                )
                .order_by(IdentityGroupRecord.name, IdentityGroupRecord.group_id)
                .all()
            ]
        )


@router.post("/api/access/groups")
def create_group(body: GroupCreateRequest, request: Request) -> dict:
    from sqlalchemy.exc import IntegrityError

    from eurogas_nexus.db.models.strategy_access import IdentityGroupRecord

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    with _session() as session:
        row = IdentityGroupRecord(group_id=f"group-{uuid4().hex}", name=body.name, status="ACTIVE")
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"error": "group_name_conflict"}) from exc
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.group.create",
            resource=f"identity_group:{row.group_id}",
            outcome="created",
        )
        session.commit()
        return _env(_group_payload(row))


@router.patch("/api/access/groups/{group_id}")
def update_group(group_id: str, body: GroupUpdateRequest, request: Request) -> dict:
    from sqlalchemy.exc import IntegrityError

    from eurogas_nexus.db.models.strategy_access import IdentityGroupRecord

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    with _session() as session:
        row = session.get(IdentityGroupRecord, group_id)
        if row is None:
            raise HTTPException(status_code=404, detail={"error": "group_not_found"})
        if body.name is not None:
            row.name = body.name
        if body.status is not None:
            row.status = body.status
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise HTTPException(status_code=409, detail={"error": "group_name_conflict"}) from exc
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.group.update",
            resource=f"identity_group:{group_id}",
            outcome="updated",
        )
        session.commit()
        return _env(_group_payload(row))


@router.put("/api/access/groups/{group_id}/members/{principal_id}")
def add_group_member(group_id: str, principal_id: str, request: Request) -> dict:
    return _change_group_member(group_id, principal_id, request, add=True)


@router.delete("/api/access/groups/{group_id}/members/{principal_id}")
def remove_group_member(group_id: str, principal_id: str, request: Request) -> dict:
    return _change_group_member(group_id, principal_id, request, add=False)


def _change_group_member(group_id: str, principal_id: str, request: Request, *, add: bool) -> dict:
    from eurogas_nexus.db.models import IdentityPrincipalRecord
    from eurogas_nexus.db.models.strategy_access import (
        IdentityGroupMemberRecord,
        IdentityGroupRecord,
    )

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    with _session() as session:
        group = session.get(IdentityGroupRecord, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail={"error": "group_not_found"})
        if session.get(IdentityPrincipalRecord, principal_id) is None:
            raise HTTPException(status_code=404, detail={"error": "user_not_found"})
        row = session.get(IdentityGroupMemberRecord, (group_id, principal_id))
        # Membership grants read access to private commercial strategies. Like
        # role/scope grants, an administrator cannot grant this to themselves.
        if add and row is None and principal_id == admin.principal_id:
            _audit_admin(
                session,
                actor=admin.principal_id,
                action="access.group.member.add",
                resource=f"identity_group:{group_id}",
                outcome="denied",
            )
            session.commit()
            raise HTTPException(status_code=403, detail={"error": ENTITLEMENT_SELF_GRANT_FORBIDDEN})
        if add and group.status != "ACTIVE":
            raise HTTPException(status_code=409, detail={"error": "group_disabled"})
        if add and row is None:
            session.add(IdentityGroupMemberRecord(group_id=group_id, principal_id=principal_id))
        elif not add and row is not None:
            session.delete(row)
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.group.member.add" if add else "access.group.member.remove",
            resource=f"identity_group:{group_id}/member:{principal_id}",
            outcome="added" if add else "removed",
        )
        session.commit()
        return _env({"group_id": group_id, "principal_id": principal_id, "member": add})


def _changes_own_grants(
    *,
    admin: AuthenticatedPrincipal,
    principal_id: str,
    row,
    body: AccessUpdateRequest,
) -> bool:
    """Whether this request would change the caller's own roles or data scopes.

    Only a *change* is refused: a request that repeats the current grants is a no-op and
    stays allowed, so an administration form that submits unchanged fields keeps working,
    while an escalation - or a self-demotion - has to be made by a second administrator.
    """

    if principal_id != admin.principal_id:
        return False
    if body.roles is None and body.data_scopes is None:
        return False
    current_roles = sorted(str(item) for item in (row.roles or [row.role]))
    current_scopes = sorted(str(item) for item in (row.data_scopes or []))
    requested_roles = (
        sorted(str(item) for item in body.roles) if body.roles is not None else current_roles
    )
    requested_scopes = (
        sorted(str(item) for item in body.data_scopes)
        if body.data_scopes is not None
        else current_scopes
    )
    return requested_roles != current_roles or requested_scopes != current_scopes


def _change_summary(before: dict, after: dict) -> str:
    """What an update changed (who and whom are the event's actor and resource)."""

    fields = ("status", "roles", "data_scopes", "job_functions", "office", "email")
    changed = [
        f"{name}: {before.get(name)} -> {after.get(name)}"
        for name in fields
        if before.get(name) != after.get(name)
    ]
    return "; ".join(changed)[:900]


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
    envelope = _env([_with_segregation_warning(row) for row in rows])
    envelope["meta"]["account_options"] = _account_options()
    return envelope


def _with_segregation_warning(user: dict) -> dict:
    """The user with ``segregation_warning`` (QA-R-03): the conflict, or ``None``. Additive.

    ANALYST with REVIEWER is granted, never refused, and answered with the warning: the
    server refuses that person's risk writes (``security/segregation.py``).
    """

    from eurogas_nexus.security.segregation import grant_conflict

    return {**user, "segregation_warning": grant_conflict(user.get("roles") or [user.get("role")])}


def _account_options() -> dict:
    """How people may be added on this deployment (drives Admin -> Users -> Add user)."""

    from eurogas_nexus.application.local_accounts import (
        TEMPORARY_PASSWORD_TTL,
        local_accounts_enabled,
        local_accounts_setting,
    )
    from eurogas_nexus.security.oidc import oidc_configured

    return {
        "local_accounts": local_accounts_enabled(),
        "local_accounts_setting": local_accounts_setting(),
        "sso_invites": oidc_configured(),
        "temporary_password_hours": int(TEMPORARY_PASSWORD_TTL.total_seconds() // 3600),
    }


def _account_error(exc) -> HTTPException:
    detail = {"error": exc.code, "code": exc.code, "message": exc.message}
    return HTTPException(status_code=exc.status_code, detail=detail)


@router.post("/api/access/users")
def create_user(body: UserCreateRequest, request: Request) -> dict:
    """Add a person (ADMIN). A local account answers its one-time password exactly once.

    ``kind=local``: user name, display name, optional e-mail and grants; the response
    carries ``one_time_password`` (never stored in clear, never shown again) that the
    person uses once to choose their own password. ``kind=sso``: a pre-provisioned company
    user, ``INVITED`` until their first SSO sign-in links and activates them.
    """

    from eurogas_nexus.application import local_accounts
    from eurogas_nexus.db.repositories import identity as identity_repository

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    grants = local_accounts.AccountGrants(
        roles=tuple(body.roles),
        data_scopes=tuple(body.data_scopes),
        job_functions=tuple(body.job_functions),
        office=body.office,
        groups=tuple(body.groups),
    )
    with _session() as session:
        if body.data_scopes:
            _require_licences(
                session,
                principal_id="",
                current=[],
                requested=body.data_scopes,
                office=(body.office or "").strip().upper() or None,
                admin=admin,
                before={},
            )
        try:
            if body.kind == "local":
                if not body.username:
                    raise local_accounts.LocalAccountError(
                        "username_required", 422, "Give the person a user name."
                    )
                row, secret = local_accounts.create_local_account(
                    session,
                    username=body.username,
                    display_name=body.display_name,
                    email=body.email,
                    grants=grants,
                    actor=admin.principal_id,
                )
            else:
                row = local_accounts.invite_sso_user(
                    session,
                    email=body.email,
                    subject=body.subject,
                    display_name=body.display_name,
                    grants=grants,
                    actor=admin.principal_id,
                )
                secret = None
        except local_accounts.LocalAccountError as exc:
            session.rollback()
            raise _account_error(exc) from exc
        payload = identity_repository.identity_principal_payload(session, row.principal_id)
        session.commit()
    data: dict = {"user": _with_segregation_warning(payload)}
    if secret is not None:
        data["one_time_password"] = secret
        data["warning"] = (
            "Give this temporary password to the person; it is shown once. They choose "
            "their own password when they first sign in."
        )
    return _env(data)


@router.post("/api/access/users/{principal_id}/reset-password")
def reset_user_password(principal_id: str, request: Request) -> dict:
    """Issue a new one-time password for a local account (ADMIN); their sessions end."""

    from eurogas_nexus.application import local_accounts
    from eurogas_nexus.db.repositories import identity as identity_repository

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    with _session() as session:
        try:
            secret = local_accounts.reset_password(
                session, principal_id, actor=admin.principal_id
            )
        except local_accounts.LocalAccountError as exc:
            session.rollback()
            raise _account_error(exc) from exc
        payload = identity_repository.identity_principal_payload(session, principal_id)
        session.commit()
    return _env(
        {
            "user": payload,
            "one_time_password": secret,
            "warning": "Shown once. Every session of this person has ended.",
        }
    )


@router.delete("/api/access/users/{principal_id}")
def delete_user(principal_id: str, request: Request) -> dict:
    """Delete a person who never signed in or acted (ADMIN); otherwise 409 - disable instead."""

    from eurogas_nexus.application import local_accounts

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    with _session() as session:
        try:
            local_accounts.delete_user(session, principal_id, actor=admin.principal_id)
        except local_accounts.LocalAccountError as exc:
            session.rollback()
            raise _account_error(exc) from exc
        session.commit()
    return _env({"principal_id": principal_id, "deleted": True})


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
        if _changes_own_grants(admin=admin, principal_id=principal_id, row=row, body=body):
            # Architecture V2 finding C6b: entitlement is granted, not assumed, and a grant
            # the grantee makes to itself is not a grant. The refusal is audited as a denial
            # - and committed - so an attempt is visible even though nothing changed.
            _audit_admin(
                session,
                actor=admin.principal_id,
                action="access.user.update",
                resource=f"identity_principal:{principal_id}",
                outcome="denied",
                detail=(
                    "self grant refused: roles and data scopes are changed by another administrator"
                ),
                before=before,
            )
            session.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "error": ENTITLEMENT_SELF_GRANT_FORBIDDEN,
                    "message": (
                        "Roles and data scopes are granted by someone else: this identity "
                        "cannot change its own grants. Ask a second administrator to make "
                        "the change."
                    ),
                    "principal_id": principal_id,
                    "research_only": True,
                    "human_review_required": True,
                },
            )
        if body.data_scopes is not None:
            office = (
                (body.office.strip().upper() or None) if body.office is not None else row.office
            )
            _require_licences(
                session,
                principal_id=principal_id,
                current=row.data_scopes or [],
                requested=body.data_scopes,
                office=office,
                admin=admin,
                before=before,
            )
        from eurogas_nexus.application import local_accounts

        demoted = body.roles is not None and "ADMIN" not in {
            str(role).strip().upper() for role in body.roles
        }
        if (body.status in {"DISABLED", "LOCKED"} and row.status == "ACTIVE") or demoted:
            try:
                local_accounts.ensure_not_last_administrator(session, row)
            except local_accounts.LocalAccountError as exc:
                _audit_admin(
                    session,
                    actor=admin.principal_id,
                    action="access.user.update",
                    resource=f"identity_principal:{principal_id}",
                    outcome="denied",
                    detail="last active administrator",
                )
                session.commit()
                raise _account_error(exc) from exc
        if body.status == "ACTIVE":
            credential = local_accounts.credential_for(session, principal_id)
            if credential is not None:
                # Enabling a locked-out local account also lifts its back-off.
                credential.failed_attempts = 0
                credential.locked_until_utc = None
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
        if body.job_functions is not None:
            from eurogas_nexus.security.capabilities import parse_job_functions

            try:
                functions = parse_job_functions(body.job_functions)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "unknown_job_function", "message": str(exc)},
                ) from exc
            row.job_functions = [item.value for item in functions] or None
        if body.office is not None:
            row.office = body.office.strip().upper() or None
        row.updated_at_utc = datetime.now(UTC)
        after = principal_payload(session, row)
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.user.update",
            resource=f"identity_principal:{principal_id}",
            outcome="updated",
            detail=_change_summary(before, after),
            before=before,
            after=after,
        )
        listed = identity_repository.identity_principal_payload(session, principal_id) or {}
        session.commit()
        return _env(_with_segregation_warning({**after, **listed}))


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
    from eurogas_nexus.domain.ingestion.source_registry import registered_sources
    from eurogas_nexus.security.identity import PUBLIC_BASELINE_SOURCE_FAMILIES

    licensed = {
        str(row["source_system"]).upper()
        for row in registered_sources()
        if row["credential_requirements"] and not str(row["source_system"]).endswith("_Sim")
    }
    licensed |= {"TRAYPORT", "WMR", "BFIX"}
    return _env(
        {
            "public_baseline": sorted(PUBLIC_BASELINE_SOURCE_FAMILIES),
            "commercial": sorted(licensed - {f.upper() for f in PUBLIC_BASELINE_SOURCE_FAMILIES}),
            "wildcard": "*",
        }
    )


def _licence_payload(row, holders: list[dict]) -> dict:
    return {
        "licence_id": row.licence_id,
        "vendor": row.vendor,
        "source_family": row.source_family,
        "licence_type": row.licence_type,
        "licensed_use": row.licensed_use,
        "valid_from": row.valid_from.isoformat(),
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "offices": list(row.offices or []),
        "seats": row.seats,
        "contract_reference": row.contract_reference,
        "notes": row.notes,
        "active": row.valid_from <= date.today()
        and (row.valid_to is None or date.today() <= row.valid_to),
        "holders": holders,
        "seats_used": len(holders) if row.licence_type == "NAMED_USER" else None,
        "updated_by": row.updated_by,
        "updated_at_utc": row.updated_at_utc.isoformat(),
    }


def _licences(session):
    from eurogas_nexus.db.models import MarketDataLicenceRecord
    from eurogas_nexus.domain.market_data.licences import Licence, LicenceType, LicensedUse

    rows = session.query(MarketDataLicenceRecord).all()
    return rows, [
        Licence(
            licence_id=row.licence_id,
            vendor=row.vendor,
            source_family=row.source_family,
            licence_type=LicenceType(row.licence_type),
            use=LicensedUse(row.licensed_use),
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            offices=tuple(row.offices or ()),
            seats=row.seats,
            contract_reference=row.contract_reference,
        )
        for row in rows
    ]


def _holders_by_family(session, *, exclude: str | None = None) -> dict[str, list[dict]]:
    from eurogas_nexus.db.models import IdentityPrincipalRecord

    holders: dict[str, list[dict]] = {}
    for person in session.query(IdentityPrincipalRecord).all():
        if person.principal_id == exclude or person.status != "ACTIVE":
            continue
        for scope in person.data_scopes or []:
            holders.setdefault(str(scope).upper(), []).append(
                {
                    "principal_id": person.principal_id,
                    "display_name": person.display_name,
                    "office": person.office,
                }
            )
    return holders


def _require_licences(
    session,
    *,
    principal_id: str,
    current: list[str],
    requested: list[str],
    office: str | None,
    admin: AuthenticatedPrincipal,
    before: dict,
) -> None:
    """Refuse (audited) a newly granted licensed family the licence register does not cover."""

    from eurogas_nexus.domain.market_data.licences import grant_problems
    from eurogas_nexus.security.identity import PUBLIC_BASELINE_SOURCE_FAMILIES

    added = {s.strip().upper() for s in requested} - {str(s).upper() for s in current}
    if not added:
        return
    _rows, licences = _licences(session)
    holders = {
        family: len(people)
        for family, people in _holders_by_family(session, exclude=principal_id).items()
    }
    problems = grant_problems(
        families=added,
        office=office,
        licences=licences,
        holders=holders,
        public_families=PUBLIC_BASELINE_SOURCE_FAMILIES,
        today=date.today(),
    )
    if not problems:
        return
    _audit_admin(
        session,
        actor=admin.principal_id,
        action="access.user.update",
        resource=f"identity_principal:{principal_id}",
        outcome="denied",
        detail="unlicensed data scope: "
        + "; ".join(f"{k}: {v}" for k, v in sorted(problems.items())),
        before=before,
    )
    session.commit()
    raise HTTPException(
        status_code=409,
        detail={
            "error": "data_scope_not_licensed",
            "message": "Grant licensed data scopes only against a licence in the register.",
            "families": problems,
        },
    )


@router.get("/api/access/market-data-licences")
def list_market_data_licences(request: Request) -> dict:
    """The licence register with each licence's current holders (vendor usage report)."""

    admin = _require_admin(request, Permission.IDENTITY_READ)
    _require_db()
    with _session() as session:
        rows, _ = _licences(session)
        holders = _holders_by_family(session)
        payload = [
            _licence_payload(row, holders.get(row.source_family.upper(), []))
            for row in sorted(rows, key=lambda r: (r.source_family, r.licence_id))
        ]
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.licences.list",
            resource="market_data_licences",
            outcome="listed",
        )
        session.commit()
    return _env(payload)


@router.put("/api/access/market-data-licences/{licence_id}")
def put_market_data_licence(licence_id: str, body: LicenceRequest, request: Request) -> dict:
    """Record or amend one licence. End a licence by setting ``valid_to``; rows are kept."""

    from eurogas_nexus.db.models import MarketDataLicenceRecord
    from eurogas_nexus.domain.market_data.licences import (
        Licence,
        LicenceType,
        LicensedUse,
        validate_licence,
    )

    admin = _require_admin(request, Permission.IDENTITY_MANAGE)
    _require_db()
    if not licence_id or len(licence_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "licence_id_invalid"})
    offices = sorted({o.strip().upper() for o in body.offices if o.strip()})
    problems = validate_licence(
        Licence(
            licence_id=licence_id,
            vendor=body.vendor,
            source_family=body.source_family,
            licence_type=LicenceType(body.licence_type),
            use=LicensedUse(body.licensed_use),
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            offices=tuple(offices),
            seats=body.seats,
        )
    )
    if problems:
        raise HTTPException(
            status_code=422, detail={"code": "licence_invalid", "problems": problems}
        )
    with _session() as session:
        row = session.get(MarketDataLicenceRecord, licence_id)
        before = None
        if row is None:
            row = MarketDataLicenceRecord(licence_id=licence_id)
            session.add(row)
        else:
            before = _licence_payload(row, [])
        row.vendor = body.vendor
        row.source_family = body.source_family.upper()
        row.licence_type = body.licence_type
        row.licensed_use = body.licensed_use
        row.valid_from = body.valid_from
        row.valid_to = body.valid_to
        row.offices = offices or None
        row.seats = body.seats
        row.contract_reference = body.contract_reference
        row.notes = body.notes
        row.updated_by = admin.principal_id
        row.updated_at_utc = datetime.now(UTC)
        session.flush()
        after = _licence_payload(row, [])
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.licence.update",
            resource=f"market_data_licence:{licence_id}",
            outcome="updated" if before else "created",
            before=before,
            after=after,
        )
        session.commit()
    return _env(after)


@router.get("/api/access/api-keys")
def list_api_keys(request: Request) -> dict:
    from eurogas_nexus.db.repositories import identity as identity_repository

    admin = _require_admin(request, Permission.API_KEYS_MANAGE)
    _require_db()

    with _session() as session:
        rows = identity_repository.list_identity_principals(session)
        keys = [key for row in rows for key in row.get("keys", [])]
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
            target = identity_repository.get_identity_principal(session, body.principal_id)
            # A key acts as its principal. An administrator issues keys for service
            # principals; a person issues their own, so nobody can act as someone else.
            if (
                target is not None
                and target.principal_type == "USER"
                and target.principal_id != admin.principal_id
            ):
                _audit_admin(
                    session,
                    actor=admin.principal_id,
                    action="access.api_key.create",
                    resource=f"identity_principal:{body.principal_id}",
                    outcome="denied",
                    detail="personal_key_self_service",
                )
                session.commit()
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "personal_key_self_service",
                        "message": (
                            "A person creates their own API key in Settings; an administrator "
                            "creates keys for service principals only."
                        ),
                    },
                )
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
    except HTTPException:
        raise
    except GovernedAuditError:
        raise  # 503 audit_unavailable: the key was not created
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
    start_utc: str | None = Query(default=None, max_length=40),
    end_utc: str | None = Query(default=None, max_length=40),
    cursor: str | None = Query(default=None, max_length=1024),
) -> dict:
    """Audit events, newest first, walkable past any page size (#59).

    The first page is anchored to a high-water mark (``end_utc``, else the request time), so
    events written while an investigator pages - including the audit of this read - never
    shift the walk. Order is (timestamp, event id) descending, stable under tied timestamps.
    ``meta.continuation.cursor`` continues the walk; it is bound to the filters and refused
    with any other set. ``audit.read`` is checked on every page.
    """

    from eurogas_nexus.application.audit_paging import (
        AuditCursorError,
        AuditFilters,
        decode_cursor,
        encode_cursor,
        parse_window_bound,
    )

    admin = _require_admin(request, Permission.AUDIT_READ)
    _require_db()
    filters = AuditFilters(
        actor=actor or "",
        action=action or "",
        resource=resource or "",
        outcome=outcome or "",
        start_utc=start_utc or "",
        end_utc=end_utc or "",
    )
    try:
        start = parse_window_bound(start_utc, "start_utc")
        end = parse_window_bound(end_utc, "end_utc")
        position = decode_cursor(cursor, filters) if cursor else None
    except AuditCursorError as exc:
        raise HTTPException(
            status_code=400, detail={"error_code": exc.code, "message": str(exc)}
        ) from exc
    anchor = position.anchor if position else (end or datetime.now(UTC))
    with _session() as session:
        from sqlalchemy import and_, or_

        from eurogas_nexus.db.models import AuditEventRecord

        query = session.query(AuditEventRecord).filter(AuditEventRecord.event_ts_utc <= anchor)
        if start:
            query = query.filter(AuditEventRecord.event_ts_utc >= start)
        if actor:
            query = query.filter(AuditEventRecord.principal == actor)
        if action:
            query = query.filter(AuditEventRecord.action == action)
        if resource:
            query = query.filter(AuditEventRecord.resource.ilike(f"%{resource}%"))
        if outcome:
            query = query.filter(AuditEventRecord.outcome == outcome)
        if position:
            query = query.filter(
                or_(
                    AuditEventRecord.event_ts_utc < position.last_ts,
                    and_(
                        AuditEventRecord.event_ts_utc == position.last_ts,
                        AuditEventRecord.event_id < position.last_id,
                    ),
                )
            )
        rows = (
            query.order_by(AuditEventRecord.event_ts_utc.desc(), AuditEventRecord.event_id.desc())
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        data = [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in rows
        ]
        next_cursor = (
            encode_cursor(
                anchor=anchor,
                last_ts=rows[-1].event_ts_utc,
                last_id=rows[-1].event_id,
                filters=filters,
            )
            if has_more and rows
            else None
        )
        _audit_admin(
            session,
            actor=admin.principal_id,
            action="access.audit.list",
            resource="audit_events",
            outcome="listed",
            detail=f"limit={limit}" + (" continuation" if position else ""),
        )
        session.commit()
    envelope = _env(data)
    envelope["meta"]["continuation"] = {
        "anchor_utc": _iso_utc(anchor),
        "has_more": has_more,
        "cursor": next_cursor,
    }
    return envelope


def _iso_utc(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


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
    """Audit an administration act in the caller's transaction.

    GOV-1 (P5): a change (a user, role, group, licence or key) is a governed write, so its
    audit row is written with it and the change fails when the row cannot be written. A list
    read or a refused change (outcome ``denied``) changed nothing and stays best-effort.
    """

    from eurogas_nexus.application.audit_service import governed_actions
    from eurogas_nexus.db.repositories import audit as audit_repository

    fields = {
        "event_type": "governance.access",
        "principal": actor,
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "severity": "info",
        "detail": detail,
        "source_system": "access-api",
        "now_utc": datetime.now(UTC),
        # Stored as JSON: dates and decimals in a payload are kept as their text.
        "before_summary": json.loads(json.dumps(before, default=str)) if before else None,
        "after_summary": json.loads(json.dumps(after, default=str)) if after else None,
    }
    if action in governed_actions() and outcome != "denied":
        audit_repository.record_governed_audit(session, **fields)
        return
    try:
        # In a savepoint, so a failed row leaves the read's own transaction untouched.
        with session.begin_nested():
            audit_repository.record_audit_event(session, **fields)
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
