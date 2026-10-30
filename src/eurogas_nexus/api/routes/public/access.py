"""Enterprise Access & Identity administration endpoints.

Administration routes additionally require ADMIN (or the documented
operator compatibility for audit export via internal profile). The self-service
group picker exposes only the authenticated principal's own group names. Fine-grained
checks are enforced in the handler; the coarse route permission enforces the
ADMIN role floor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

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
