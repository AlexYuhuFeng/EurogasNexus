"""Local accounts and SSO pre-provisioning (Admin -> Users).

Two ways a person exists in the product:

* **Company SSO** (unchanged), plus *pre-provisioning*: an administrator adds the person
  before their first SSO sign-in (e-mail and/or subject, roles, job functions, scopes). The
  principal waits as ``INVITED`` and is linked and activated by that first sign-in.
* **Local accounts** for firms without SSO (``EUROGAS_NEXUS_LOCAL_ACCOUNTS``: ``auto`` -
  the default - turns them on only when no SSO is configured; ``on``/``off`` force it). An
  administrator creates the account and receives a one-time temporary password, shown once;
  the person must choose their own password at first sign-in.

Security rules enforced here (and only here, so every caller - API, CLI, demo start-up -
gets the same ones): the password policy and scrypt storage of ``security/passwords.py``;
a uniform refusal for every failed sign-in; per-account back-off (5 failures lock the
account for 15 minutes, doubling for each further 5, at most 24 hours) and a per-address
throttle; session revocation on a password change, reset or disable; the last active
administrator can be neither disabled, locked, demoted nor deleted; a principal with audit
history is never deleted (disable it instead); every administrative act is audited with
who, whom and what - never a password or token.

A job function or work mode never grants anything here: roles are the only grant.

Demo test accounts (``EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS``) use the same code path. They are
marked ``is_demo``, skip the forced change, may carry a password shorter than the policy,
and sign in only while the server runs the demo profile in a development/test environment;
the setting is refused anywhere else (:func:`assert_demo_accounts_allowed`).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.identity import (
    IdentityApiKeyRecord,
    IdentityExternalIdRecord,
    IdentityLocalCredentialRecord,
    IdentityPrincipalRecord,
    UserSessionRecord,
)
from eurogas_nexus.domain.identity.accounts import (  # noqa: F401 - re-exported
    INVITED_STATUS,
    account_kind,
    account_state,
    credential_payload,
)
from eurogas_nexus.security import passwords
from eurogas_nexus.security.local_accounts_policy import (  # noqa: F401 - re-exported
    DEMO_ENVIRONMENTS,
    DEMO_TEST_ACCOUNTS_ENV,
    LOCAL_ACCOUNTS_ENV,
    assert_demo_accounts_allowed,
    demo_profile_active,
    local_accounts_enabled,
    local_accounts_setting,
)

#: A temporary password lets its holder choose a password for this long.
TEMPORARY_PASSWORD_TTL = timedelta(hours=72)
#: The password-change step after a temporary-password sign-in.
CHANGE_TOKEN_TTL = timedelta(minutes=10)
#: Per-account back-off: this many consecutive failures lock the account ...
MAX_FAILED_ATTEMPTS = 5
#: ... for this long, doubling for each further block of failures, capped.
BASE_LOCKOUT = timedelta(minutes=15)
MAX_LOCKOUT = timedelta(hours=24)
#: Per-address throttle: failed sign-ins from one address within the window.
MAX_ADDRESS_FAILURES = 20
ADDRESS_WINDOW_SECONDS = 15 * 60
#: Demo test accounts may be shorter than the policy, never shorter than this.
DEMO_MIN_PASSWORD_LENGTH = 8

UNIFORM_FAILURE_MESSAGE = (
    "User name or password is incorrect, or the account is temporarily locked after "
    "repeated attempts. Ask your administrator if this continues."
)


class LocalAccountError(Exception):
    """A refused account operation: stable ``code``, HTTP ``status_code``, safe message."""

    def __init__(self, code: str, status_code: int, message: str, **extra: object) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message
        self.extra = extra


# --- reads ------------------------------------------------------------------------------


def _now(now_utc: datetime | None) -> datetime:
    value = now_utc or datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def credential_for(session: Session, principal_id: str) -> IdentityLocalCredentialRecord | None:
    return session.get(IdentityLocalCredentialRecord, principal_id)


def _is_active_admin(row: IdentityPrincipalRecord) -> bool:
    roles = {str(r).upper() for r in (row.roles or [row.role])}
    return row.principal_type == "USER" and row.status == "ACTIVE" and "ADMIN" in roles


def active_administrator_ids(session: Session) -> set[str]:
    rows = (
        session.query(IdentityPrincipalRecord)
        .filter(IdentityPrincipalRecord.status == "ACTIVE")
        .all()
    )
    return {row.principal_id for row in rows if _is_active_admin(row)}


def ensure_not_last_administrator(session: Session, row: IdentityPrincipalRecord) -> None:
    """Refuse an act that would leave no active administrator.

    Called before disabling, locking, demoting or deleting ``row``: when ``row`` is an
    active administrator and no other one exists, the product would have nobody left who
    can administer it.
    """

    if not _is_active_admin(row):
        return
    if active_administrator_ids(session) - {row.principal_id}:
        return
    raise LocalAccountError(
        "last_administrator",
        409,
        "This is the last active administrator. Make someone else an administrator first.",
    )


# --- audit ------------------------------------------------------------------------------


def _audit(
    session: Session,
    *,
    actor: str,
    action: str,
    resource: str,
    outcome: str,
    detail: str = "",
    severity: str = "info",
    event_type: str = "governance.access",
    source_system: str = "access-api",
    now_utc: datetime | None = None,
) -> None:
    from eurogas_nexus.application.audit_service import governed_actions
    from eurogas_nexus.db.repositories import audit as audit_repository

    # GOV-1 (P5): an account change is a governed write; its audit row is part of it and the
    # change fails without it. Sign-in events keep the plain in-transaction record.
    record = (
        audit_repository.record_governed_audit
        if action in governed_actions()
        else audit_repository.record_audit_event
    )
    record(
        session,
        event_type=event_type,
        principal=actor[:128],
        action=action,
        resource=resource,
        outcome=outcome,
        severity=severity,
        detail=detail,
        source_system=source_system,
        now_utc=_now(now_utc),
    )


# --- administration ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccountGrants:
    """What an administrator grants a new person (roles) and declares about them."""

    roles: tuple[str, ...] = ("VIEWER",)
    data_scopes: tuple[str, ...] = ()
    job_functions: tuple[str, ...] = ()
    office: str | None = None
    groups: tuple[str, ...] = field(default=())


def _normalized_roles(roles: tuple[str, ...] | list[str]) -> list[str]:
    from eurogas_nexus.security.identity import role_value

    normalized: list[str] = []
    for value in roles or ():
        try:
            role = role_value(str(value)).value
        except Exception as exc:  # noqa: BLE001 - reported as one validation error
            raise LocalAccountError("role_invalid", 422, f"Unknown role {value!r}.") from exc
        if role not in normalized:
            normalized.append(role)
    return normalized or ["VIEWER"]


def _apply_grants(
    session: Session, row: IdentityPrincipalRecord, grants: AccountGrants
) -> None:
    from eurogas_nexus.security.capabilities import parse_job_functions
    from eurogas_nexus.security.identity import primary_role

    roles = _normalized_roles(grants.roles)
    row.roles = roles
    row.role = primary_role(roles)
    row.data_scopes = sorted(
        {str(scope).strip().upper() for scope in grants.data_scopes if str(scope).strip()}
    )
    try:
        functions = parse_job_functions(list(grants.job_functions))
    except ValueError as exc:
        raise LocalAccountError("unknown_job_function", 422, str(exc)) from exc
    row.job_functions = [item.value for item in functions] or None
    row.office = (grants.office or "").strip().upper()[:16] or None
    if grants.groups:
        from eurogas_nexus.db.models.identity_groups import (
            IdentityGroupMemberRecord,
            IdentityGroupRecord,
        )

        for group_id in grants.groups:
            group = session.get(IdentityGroupRecord, group_id)
            if group is None or group.status != "ACTIVE":
                raise LocalAccountError("group_not_found", 422, f"Unknown group {group_id!r}.")
            if session.get(IdentityGroupMemberRecord, (group_id, row.principal_id)) is None:
                session.add(
                    IdentityGroupMemberRecord(group_id=group_id, principal_id=row.principal_id)
                )


def _new_principal(
    session: Session,
    *,
    name: str,
    display_name: str,
    email: str | None,
    identity_source: str,
    status: str,
    now: datetime,
) -> IdentityPrincipalRecord:
    from eurogas_nexus.domain.identity.principal import (
        PrincipalValidationError,
        normalize_principal,
    )

    try:
        normalized = normalize_principal(name)
    except PrincipalValidationError as exc:
        raise LocalAccountError("username_invalid", 422, str(exc)) from exc
    taken = (
        session.query(IdentityPrincipalRecord)
        .filter(func.lower(IdentityPrincipalRecord.name) == normalized.lower())
        .first()
    )
    if taken is not None:
        raise LocalAccountError(
            "username_taken", 409, f"The user name {normalized!r} is already in use."
        )
    row = IdentityPrincipalRecord(
        principal_id=f"principal-{uuid4().hex[:12]}",
        principal_type="USER",
        name=normalized,
        display_name=(display_name or "").strip()[:128] or normalized,
        role="VIEWER",
        roles=["VIEWER"],
        email=(email or "").strip()[:254] or None,
        identity_source=identity_source,
        status=status,
        data_scopes=[],
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(row)
    session.flush()
    return row


def _store_password(
    credential: IdentityLocalCredentialRecord,
    password: str,
    *,
    must_change: bool,
    now: datetime,
) -> None:
    stored = passwords.hash_password(password)
    credential.kdf = stored.kdf
    credential.kdf_params = dict(stored.params)
    credential.salt_b64 = stored.salt_b64
    credential.password_hash_b64 = stored.digest_b64
    credential.must_change_password = must_change
    credential.temporary_expires_at_utc = now + TEMPORARY_PASSWORD_TTL if must_change else None
    credential.password_set_at_utc = now
    credential.failed_attempts = 0
    credential.locked_until_utc = None
    credential.change_token_hash = None
    credential.change_token_expires_at_utc = None
    credential.updated_at_utc = now


def _stored(credential: IdentityLocalCredentialRecord) -> passwords.PasswordHash:
    return passwords.PasswordHash(
        kdf=credential.kdf,
        params={k: int(v) for k, v in dict(credential.kdf_params or {}).items()},
        salt_b64=credential.salt_b64,
        digest_b64=credential.password_hash_b64,
    )


def _grant_summary(row: IdentityPrincipalRecord) -> str:
    return (
        f"roles={sorted(row.roles or [row.role])}; scopes={sorted(row.data_scopes or [])}; "
        f"job_functions={sorted(row.job_functions or [])}; office={row.office}"
    )


def create_local_account(
    session: Session,
    *,
    username: str,
    display_name: str,
    email: str | None,
    grants: AccountGrants,
    actor: str,
    now_utc: datetime | None = None,
) -> tuple[IdentityPrincipalRecord, str]:
    """Create a local account and return it with its one-time temporary password.

    The temporary password is returned exactly once; only its scrypt derivation is stored.
    """

    if not local_accounts_enabled():
        raise LocalAccountError(
            "local_accounts_disabled",
            409,
            "Local accounts are turned off for this deployment (company SSO is configured).",
        )
    now = _now(now_utc)
    row = _new_principal(
        session,
        name=username,
        display_name=display_name,
        email=email,
        identity_source="LOCAL",
        status="ACTIVE",
        now=now,
    )
    _apply_grants(session, row, grants)
    secret = passwords.generate_one_time_secret()
    credential = IdentityLocalCredentialRecord(
        principal_id=row.principal_id,
        is_demo=False,
        created_by=actor,
        created_at_utc=now,
    )
    _store_password(credential, secret, must_change=True, now=now)
    session.add(credential)
    session.flush()
    _audit(
        session,
        actor=actor,
        action="access.user.create",
        resource=f"identity_principal:{row.principal_id}",
        outcome="created",
        detail=f"kind=local; name={row.name}; {_grant_summary(row)}",
        now_utc=now,
    )
    return row, secret


def invite_sso_user(
    session: Session,
    *,
    email: str | None,
    subject: str | None,
    display_name: str,
    grants: AccountGrants,
    actor: str,
    now_utc: datetime | None = None,
) -> IdentityPrincipalRecord:
    """Pre-provision a company-SSO user; they are linked and activated at first sign-in.

    Matching at first sign-in: the configured issuer's subject when one is given here,
    otherwise the e-mail address (case-insensitive) the identity provider asserts.
    """

    from eurogas_nexus.security.oidc import oidc_configured

    if not oidc_configured():
        raise LocalAccountError(
            "sso_not_configured", 409, "Company SSO is not configured for this deployment."
        )
    mail = (email or "").strip().lower() or None
    sub = (subject or "").strip() or None
    if not mail and not sub:
        raise LocalAccountError(
            "invite_identifier_missing", 422, "Give the person's e-mail address or SSO subject."
        )
    if mail and ("@" not in mail or len(mail) > 254):
        raise LocalAccountError("email_invalid", 422, "The e-mail address is not valid.")
    now = _now(now_utc)
    if mail:
        clash = (
            session.query(IdentityPrincipalRecord)
            .filter(func.lower(IdentityPrincipalRecord.email) == mail)
            .first()
        )
        if clash is not None:
            raise LocalAccountError(
                "email_taken", 409, "Someone with this e-mail address already exists."
            )
    base = (mail or f"sso-{sub}").split("@")[0]
    import re

    name = re.sub(r"[^A-Za-z0-9._@-]+", "-", f"sso-{base}" if mail else base).strip("-")[:56]
    candidate = name or "sso-user"
    suffix = 1
    while (
        session.query(IdentityPrincipalRecord)
        .filter(func.lower(IdentityPrincipalRecord.name) == candidate.lower())
        .first()
        is not None
    ):
        suffix += 1
        candidate = f"{name}-{suffix}"
    row = _new_principal(
        session,
        name=candidate,
        display_name=display_name or (mail or sub or candidate),
        email=mail,
        identity_source="OIDC",
        status=INVITED_STATUS,
        now=now,
    )
    _apply_grants(session, row, grants)
    if sub:
        from eurogas_nexus.db.repositories.security import (
            create_external_identity,
            find_external_identity,
        )
        from eurogas_nexus.security.oidc import _issuer  # noqa: PLC2701 - configured issuer

        if find_external_identity(session, _issuer(), sub) is not None:
            raise LocalAccountError(
                "subject_taken", 409, "This SSO subject is already linked to someone."
            )
        create_external_identity(
            session,
            principal_id=row.principal_id,
            issuer=_issuer(),
            subject=sub,
            provider_id="oidc",
            email=mail,
            display_name=row.display_name,
            now_utc=now,
        )
    session.flush()
    _audit(
        session,
        actor=actor,
        action="access.user.invite",
        resource=f"identity_principal:{row.principal_id}",
        outcome="created",
        detail=(
            f"kind=sso; match={'subject' if sub else 'email'}; {_grant_summary(row)}"
        ),
        now_utc=now,
    )
    return row


def claim_sso_invite(
    session: Session, identity, *, now_utc: datetime | None = None
) -> IdentityPrincipalRecord | None:
    """Link a first SSO sign-in to the person an administrator pre-provisioned.

    Matches an ``INVITED`` principal by the asserted e-mail (case-insensitive) when the
    token does not say the address is unverified. Returns the activated principal, or
    ``None`` when nobody was invited under that address.
    """

    email = (getattr(identity, "email", None) or "").strip().lower()
    if not email or getattr(identity, "email_verified", None) is False:
        return None
    row = (
        session.query(IdentityPrincipalRecord)
        .filter(
            IdentityPrincipalRecord.status == INVITED_STATUS,
            func.lower(IdentityPrincipalRecord.email) == email,
        )
        .order_by(IdentityPrincipalRecord.created_at_utc)
        .first()
    )
    if row is None:
        return None
    # An invite pinned to a subject is matched by that subject only.
    pinned = (
        session.query(IdentityExternalIdRecord)
        .filter(IdentityExternalIdRecord.principal_id == row.principal_id)
        .first()
    )
    if pinned is not None:
        return None
    from eurogas_nexus.db.repositories.security import create_external_identity

    now = _now(now_utc)
    create_external_identity(
        session,
        principal_id=row.principal_id,
        issuer=identity.issuer,
        subject=identity.subject,
        provider_id="oidc",
        email=email,
        display_name=getattr(identity, "name", "") or row.display_name,
        now_utc=now,
    )
    activate_invite(session, row, now_utc=now)
    return row


def activate_invite(
    session: Session, row: IdentityPrincipalRecord, *, now_utc: datetime | None = None
) -> None:
    """An invited SSO user signed in for the first time: they become ACTIVE (audited)."""

    if row.status != INVITED_STATUS:
        return
    now = _now(now_utc)
    row.status = "ACTIVE"
    row.updated_at_utc = now
    _audit(
        session,
        actor=row.principal_id,
        action="access.user.invite_accepted",
        resource=f"identity_principal:{row.principal_id}",
        outcome="activated",
        detail="first company sign-in",
        event_type="governance.auth",
        source_system="oidc-auth",
        now_utc=now,
    )
    session.flush()


def reset_password(
    session: Session,
    principal_id: str,
    *,
    actor: str,
    now_utc: datetime | None = None,
) -> str:
    """Issue a new one-time temporary password; every session of the person ends."""

    from eurogas_nexus.db.repositories.security import revoke_principal_sessions

    row = session.get(IdentityPrincipalRecord, principal_id)
    if row is None:
        raise LocalAccountError("user_not_found", 404, "No such user.")
    credential = credential_for(session, principal_id)
    if credential is None:
        raise LocalAccountError(
            "not_a_local_account",
            409,
            "This person signs in with company SSO; their password is managed there.",
        )
    now = _now(now_utc)
    secret = passwords.generate_one_time_secret()
    _store_password(credential, secret, must_change=True, now=now)
    revoked = revoke_principal_sessions(session, principal_id, now_utc=now)
    row.updated_at_utc = now
    session.flush()
    _audit(
        session,
        actor=actor,
        action="access.user.password_reset",
        resource=f"identity_principal:{principal_id}",
        outcome="reset",
        detail=f"one-time password issued; sessions_ended={revoked}",
        now_utc=now,
    )
    return secret


def delete_user(session: Session, principal_id: str, *, actor: str) -> None:
    """Delete a person who has never acted; anyone with audit history is disabled instead."""

    from eurogas_nexus.db.models import AuditEventRecord
    from eurogas_nexus.db.models.identity_groups import IdentityGroupMemberRecord

    row = session.get(IdentityPrincipalRecord, principal_id)
    if row is None:
        raise LocalAccountError("user_not_found", 404, "No such user.")
    if principal_id == actor:
        raise LocalAccountError("cannot_delete_self", 409, "You cannot delete your own account.")
    ensure_not_last_administrator(session, row)
    acted = (
        session.query(AuditEventRecord.event_id)
        .filter(AuditEventRecord.principal == principal_id)
        .first()
    )
    keys = (
        session.query(IdentityApiKeyRecord.key_id)
        .filter(IdentityApiKeyRecord.principal_id == principal_id)
        .first()
    )
    sessions = (
        session.query(UserSessionRecord.session_id)
        .filter(UserSessionRecord.principal_id == principal_id)
        .first()
    )
    if acted is not None or keys is not None or sessions is not None or row.last_login_at_utc:
        raise LocalAccountError(
            "user_has_history",
            409,
            "This person has signed in or acted, so the record is kept for the audit trail. "
            "Disable the account instead.",
        )
    credential = credential_for(session, principal_id)
    if credential is not None:
        session.delete(credential)
    session.query(IdentityExternalIdRecord).filter(
        IdentityExternalIdRecord.principal_id == principal_id
    ).delete(synchronize_session=False)
    session.query(IdentityGroupMemberRecord).filter(
        IdentityGroupMemberRecord.principal_id == principal_id
    ).delete(synchronize_session=False)
    session.flush()
    name = row.name
    session.delete(row)
    try:
        session.flush()
    except Exception as exc:  # noqa: BLE001 - a record elsewhere still names this person
        raise LocalAccountError(
            "user_has_history",
            409,
            "Records elsewhere refer to this person. Disable the account instead.",
        ) from exc
    _audit(
        session,
        actor=actor,
        action="access.user.delete",
        resource=f"identity_principal:{principal_id}",
        outcome="deleted",
        detail=f"name={name}",
    )


# --- sign-in ----------------------------------------------------------------------------

_ADDRESS_FAILURES: dict[str, tuple[float, int]] = {}
_ADDRESS_LOCK = threading.Lock()


def _address_key(address: str) -> str:
    import hashlib

    return "la:" + hashlib.sha256(address.encode("utf-8")).hexdigest()[:32]


def _address_blocked(address: str) -> bool:
    """Whether the address has failed too often (counted across every API process when the
    shared cache is configured; this process's own count when it is not or is unreachable)."""

    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    cache = shared_cache()
    if cache.shared:
        try:
            held = cache.get(_address_key(address))
            return held is not None and int(held) >= MAX_ADDRESS_FAILURES
        except SharedCacheUnavailable:
            pass
    now = time.monotonic()
    with _ADDRESS_LOCK:
        started, count = _ADDRESS_FAILURES.get(address, (now, 0))
        if now - started >= ADDRESS_WINDOW_SECONDS:
            _ADDRESS_FAILURES.pop(address, None)
            return False
        return count >= MAX_ADDRESS_FAILURES


def _record_address_failure(address: str) -> None:
    from eurogas_nexus.core.shared_cache import SharedCacheUnavailable, shared_cache

    cache = shared_cache()
    if cache.shared:
        try:
            cache.incr(_address_key(address), ttl_seconds=ADDRESS_WINDOW_SECONDS)
        except SharedCacheUnavailable:
            pass
    # This process counts too: it is what applies while the shared cache is unreachable.
    now = time.monotonic()
    with _ADDRESS_LOCK:
        started, count = _ADDRESS_FAILURES.get(address, (now, 0))
        if now - started >= ADDRESS_WINDOW_SECONDS:
            started, count = now, 0
        _ADDRESS_FAILURES[address] = (started, count + 1)


def reset_address_throttle() -> None:
    """Forget every per-address failure (tests)."""

    with _ADDRESS_LOCK:
        _ADDRESS_FAILURES.clear()


def lockout_duration(failed_attempts: int) -> timedelta | None:
    """Back-off after ``failed_attempts`` consecutive failures (None: not locked)."""

    if failed_attempts < MAX_FAILED_ATTEMPTS or failed_attempts % MAX_FAILED_ATTEMPTS:
        return None
    blocks = min(failed_attempts // MAX_FAILED_ATTEMPTS, 12)
    return min(BASE_LOCKOUT * (2 ** (blocks - 1)), MAX_LOCKOUT)


@dataclass(frozen=True, slots=True)
class SignInOutcome:
    """A verified sign-in: either a session, or the password-change step first."""

    principal: IdentityPrincipalRecord
    session_token: str | None = None
    change_token: str | None = None
    #: The code step of a sign-in with a second factor (security review H6).
    mfa_token: str | None = None
    #: The session opened is for enrolling a second factor only (the policy requires one).
    mfa_enrolment_required: bool = False


def _find_local(
    session: Session, username: str
) -> tuple[IdentityPrincipalRecord | None, IdentityLocalCredentialRecord | None]:
    name = (username or "").strip()
    if not name or len(name) > 254:
        return None, None
    rows = (
        session.query(IdentityPrincipalRecord, IdentityLocalCredentialRecord)
        .join(
            IdentityLocalCredentialRecord,
            IdentityLocalCredentialRecord.principal_id == IdentityPrincipalRecord.principal_id,
        )
        .filter(
            (func.lower(IdentityPrincipalRecord.name) == name.lower())
            | (func.lower(IdentityPrincipalRecord.email) == name.lower())
        )
        .all()
    )
    exact = [pair for pair in rows if pair[0].name == name]
    chosen = exact or rows
    if len(chosen) != 1:
        return None, None
    return chosen[0][0], chosen[0][1]


def _uniform_failure() -> LocalAccountError:
    return LocalAccountError("invalid_credentials", 401, UNIFORM_FAILURE_MESSAGE)


def _deny(
    session: Session,
    *,
    address: str,
    reason: str,
    principal_id: str | None,
    now: datetime,
) -> None:
    _record_address_failure(address)
    _audit(
        session,
        actor=principal_id or "anonymous",
        action="auth.local.denied",
        resource=f"identity_principal:{principal_id}" if principal_id else "local_sign_in",
        outcome="denied",
        severity="warning",
        detail=f"reason={reason}",
        event_type="governance.auth",
        source_system="local-auth",
        now_utc=now,
    )


def sign_in(
    session: Session,
    *,
    username: str,
    password: str,
    source_address: str,
    client_type: str = "local_password",
    now_utc: datetime | None = None,
) -> SignInOutcome:
    """Verify a user name and password; the caller commits the session afterwards.

    Every refusal raises the same ``invalid_credentials`` error (and takes about the same
    time), except two that only someone who knew the password can reach: an expired
    temporary password, and the per-address throttle (HTTP 429, which names no account).
    The audit trail records the true reason.
    """

    if not local_accounts_enabled():
        raise LocalAccountError(
            "local_accounts_disabled", 404, "Local sign-in is not offered by this deployment."
        )
    now = _now(now_utc)
    address = source_address or "unknown"
    if _address_blocked(address):
        _audit(
            session,
            actor="anonymous",
            action="auth.local.throttled",
            resource="local_sign_in",
            outcome="denied",
            severity="warning",
            detail="reason=address_throttled",
            event_type="governance.auth",
            source_system="local-auth",
            now_utc=now,
        )
        raise LocalAccountError(
            "rate_limited", 429, "Too many failed sign-ins from this address. Try again later."
        )
    row, credential = _find_local(session, username)
    if row is None or credential is None:
        passwords.burn_verification_time(password)
        _deny(session, address=address, reason="unknown_user", principal_id=None, now=now)
        raise _uniform_failure()
    if credential.is_demo and not demo_profile_active():
        passwords.burn_verification_time(password)
        _deny(
            session, address=address, reason="demo_account_outside_demo",
            principal_id=row.principal_id, now=now,
        )
        raise _uniform_failure()
    locked_until = _aware(credential.locked_until_utc)
    if locked_until is not None and locked_until > now:
        passwords.burn_verification_time(password)
        _deny(session, address=address, reason="locked", principal_id=row.principal_id, now=now)
        raise _uniform_failure()
    stored = _stored(credential)
    if not passwords.verify_password(password, stored):
        credential.failed_attempts = int(credential.failed_attempts or 0) + 1
        credential.last_failed_at_utc = now
        lock = lockout_duration(credential.failed_attempts)
        if lock is not None:
            credential.locked_until_utc = now + lock
        credential.updated_at_utc = now
        _deny(
            session, address=address, reason="bad_password",
            principal_id=row.principal_id, now=now,
        )
        if lock is not None:
            _audit(
                session,
                actor=row.principal_id,
                action="auth.local.locked",
                resource=f"identity_principal:{row.principal_id}",
                outcome="locked",
                severity="warning",
                detail=(
                    f"failed_attempts={credential.failed_attempts}; "
                    f"locked_minutes={int(lock.total_seconds() // 60)}"
                ),
                event_type="governance.auth",
                source_system="local-auth",
                now_utc=now,
            )
        raise _uniform_failure()
    if row.status != "ACTIVE":
        _deny(
            session, address=address, reason=f"status_{row.status.lower()}",
            principal_id=row.principal_id, now=now,
        )
        raise _uniform_failure()
    expires = _aware(credential.temporary_expires_at_utc)
    if credential.must_change_password and expires is not None and expires <= now:
        _deny(
            session, address=address, reason="temporary_password_expired",
            principal_id=row.principal_id, now=now,
        )
        raise LocalAccountError(
            "temporary_password_expired",
            401,
            "This temporary password has expired. Ask your administrator for a new one.",
        )
    credential.failed_attempts = 0
    credential.locked_until_utc = None
    credential.updated_at_utc = now
    if passwords.needs_rehash(stored) and not credential.must_change_password:
        upgraded = passwords.hash_password(password)
        credential.kdf = upgraded.kdf
        credential.kdf_params = dict(upgraded.params)
        credential.salt_b64 = upgraded.salt_b64
        credential.password_hash_b64 = upgraded.digest_b64
    if credential.must_change_password and not credential.is_demo:
        token = passwords.generate_token()
        credential.change_token_hash = passwords.hash_token(token)
        credential.change_token_expires_at_utc = now + CHANGE_TOKEN_TTL
        _audit(
            session,
            actor=row.principal_id,
            action="auth.local.password_change_required",
            resource=f"identity_principal:{row.principal_id}",
            outcome="pending",
            detail="temporary password accepted; a new password is required",
            event_type="governance.auth",
            source_system="local-auth",
            now_utc=now,
        )
        session.flush()
        return SignInOutcome(principal=row, change_token=token)
    return _session_or_second_factor(session, row, client_type, now, "login")


def _session_or_second_factor(
    session: Session, row: IdentityPrincipalRecord, client_type: str, now: datetime, how: str
) -> SignInOutcome:
    """After the password: a session, the code step, or an enrolment-only session (H6)."""

    from eurogas_nexus.application import mfa

    if mfa.enrolled(session, row.principal_id):
        token = mfa.start_challenge(session, row, client_type, now=now)
        _audit(
            session,
            actor=row.principal_id,
            action="auth.local.mfa_required",
            resource=f"identity_principal:{row.principal_id}",
            outcome="pending",
            detail=f"step={how}; password accepted, second factor pending",
            event_type="governance.auth",
            source_system="local-auth",
            now_utc=now,
        )
        return SignInOutcome(principal=row, mfa_token=token)
    if mfa.required_for(row) and not getattr(_credential_of(session, row), "is_demo", False):
        return SignInOutcome(
            principal=row,
            session_token=_open_session(session, row, mfa.ENROLMENT_SESSION, now, how),
            mfa_enrolment_required=True,
        )
    return SignInOutcome(
        principal=row, session_token=_open_session(session, row, client_type, now, how)
    )


def _credential_of(session: Session, row: IdentityPrincipalRecord):
    return credential_for(session, row.principal_id)


def complete_mfa_sign_in(
    session: Session,
    *,
    mfa_token: str,
    code: str | None,
    recovery_code: str | None,
    now_utc: datetime | None = None,
) -> SignInOutcome:
    """The code step of a sign-in; opens the session (security review H6)."""

    from eurogas_nexus.application import mfa

    now = _now(now_utc)
    try:
        row, client_type = mfa.complete_challenge(
            session, mfa_token, code=code, recovery_code=recovery_code, now=now
        )
    except mfa.MfaError as exc:
        raise LocalAccountError(exc.code, exc.status_code, exc.message) from exc
    return SignInOutcome(
        principal=row, session_token=_open_session(session, row, client_type, now, "mfa")
    )


def _open_session(
    session: Session,
    row: IdentityPrincipalRecord,
    client_type: str,
    now: datetime,
    how: str,
) -> str:
    from eurogas_nexus.application.enterprise_auth import create_principal_session

    result = create_principal_session(
        session, principal=row, client_type=client_type, now_utc=now
    )
    row.last_login_at_utc = now
    row.updated_at_utc = now
    _audit(
        session,
        actor=row.principal_id,
        action="auth.local.login",
        resource=f"identity_principal:{row.principal_id}",
        outcome="success",
        detail=f"method=local_password; step={how}",
        event_type="governance.auth",
        source_system="local-auth",
        now_utc=now,
    )
    session.flush()
    return result.session_token


def _set_new_password(
    session: Session,
    row: IdentityPrincipalRecord,
    credential: IdentityLocalCredentialRecord,
    new_password: str,
    *,
    now: datetime,
) -> int:
    from eurogas_nexus.db.repositories.security import revoke_principal_sessions

    try:
        passwords.check_password_policy(new_password, username=row.name)
    except passwords.PasswordPolicyError as exc:
        raise LocalAccountError(exc.code, 422, exc.message) from exc
    if passwords.verify_password(new_password, _stored(credential)):
        raise LocalAccountError(
            "password_reused", 422, "Choose a password different from the current one."
        )
    _store_password(credential, new_password, must_change=False, now=now)
    return revoke_principal_sessions(session, row.principal_id, now_utc=now)


def complete_password_change(
    session: Session,
    *,
    change_token: str,
    new_password: str,
    client_type: str = "local_password",
    now_utc: datetime | None = None,
) -> SignInOutcome:
    """The forced change after a temporary-password sign-in; opens the first session."""

    now = _now(now_utc)
    token_hash = passwords.hash_token(change_token or "")
    credential = (
        session.query(IdentityLocalCredentialRecord)
        .filter(IdentityLocalCredentialRecord.change_token_hash == token_hash)
        .one_or_none()
    )
    expires = _aware(credential.change_token_expires_at_utc) if credential else None
    if credential is None or expires is None or expires <= now:
        raise LocalAccountError(
            "change_token_invalid",
            401,
            "This step has expired. Sign in again with your temporary password.",
        )
    row = session.get(IdentityPrincipalRecord, credential.principal_id)
    if row is None or row.status != "ACTIVE":
        raise LocalAccountError("change_token_invalid", 401, "Sign in again.")
    revoked = _set_new_password(session, row, credential, new_password, now=now)
    _audit(
        session,
        actor=row.principal_id,
        action="auth.local.password_changed",
        resource=f"identity_principal:{row.principal_id}",
        outcome="changed",
        detail=f"step=first_sign_in; sessions_ended={revoked}",
        event_type="governance.auth",
        source_system="local-auth",
        now_utc=now,
    )
    return _session_or_second_factor(session, row, client_type, now, "after_password_change")


def change_own_password(
    session: Session,
    *,
    principal_id: str,
    current_password: str,
    new_password: str,
    source_address: str,
    client_type: str = "local_password",
    now_utc: datetime | None = None,
) -> SignInOutcome:
    """A signed-in person changes their own password; every other session ends."""

    now = _now(now_utc)
    row = session.get(IdentityPrincipalRecord, principal_id)
    credential = credential_for(session, principal_id) if row else None
    if row is None or credential is None:
        raise LocalAccountError(
            "not_a_local_account",
            409,
            "You sign in with company SSO; change your password there.",
        )
    if not passwords.verify_password(current_password, _stored(credential)):
        credential.failed_attempts = int(credential.failed_attempts or 0) + 1
        credential.last_failed_at_utc = now
        lock = lockout_duration(credential.failed_attempts)
        if lock is not None:
            credential.locked_until_utc = now + lock
        _deny(
            session, address=source_address or "unknown", reason="bad_current_password",
            principal_id=principal_id, now=now,
        )
        raise LocalAccountError(
            "current_password_incorrect", 403, "The current password is not correct."
        )
    revoked = _set_new_password(session, row, credential, new_password, now=now)
    _audit(
        session,
        actor=principal_id,
        action="auth.local.password_changed",
        resource=f"identity_principal:{principal_id}",
        outcome="changed",
        detail=f"step=self_service; sessions_ended={revoked}",
        event_type="governance.auth",
        source_system="local-auth",
        now_utc=now,
    )
    return SignInOutcome(
        principal=row,
        session_token=_open_session(session, row, client_type, now, "after_password_change"),
    )


# --- demo test accounts -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DemoAccountSpec:
    """One configured demo test account (never a customer account)."""

    username: str
    password: str
    template: str
    allow_admin: bool = False


#: Demo test account -> the existing demo tester whose roles and job functions it copies.
DEFAULT_DEMO_TEMPLATES: dict[str, str] = {
    "test_trader": "demo.trader",
    "test_nl_trader": "demo.nl.trader",
    "test_analyst": "demo.analyst",
    "test_risk": "demo.risk",
    "test_manager": "demo.manager",
    "test_finance": "demo.finance",
    "test_compliance": "demo.compliance",
    "test_ops": "demo.ops",
    "test_admin": "demo.admin",
}


def parse_demo_accounts(value: str) -> list[DemoAccountSpec]:
    """Parse ``EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS``.

    Two forms:

    * CSV: ``name:password[:admin]`` entries separated by commas, e.g.
      ``test_trader:12345678,test_admin:12345678:admin``;
    * JSON: a list of ``{"username", "password", "as"?, "allow_admin"?}`` objects.

    ``as`` names the demo tester to copy (``demo.trader`` ...); it defaults from the name
    (:data:`DEFAULT_DEMO_TEMPLATES`). An account whose template holds the ADMIN role must
    say so explicitly (``:admin`` / ``"allow_admin": true``).

    Raises:
        ValueError: naming every malformed entry (no password is ever echoed).
    """

    text = (value or "").strip()
    if not text:
        return []
    entries: list[dict] = []
    if text.startswith("["):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{DEMO_TEST_ACCOUNTS_ENV} is not valid JSON") from exc
        if not isinstance(loaded, list):
            raise ValueError(f"{DEMO_TEST_ACCOUNTS_ENV} JSON must be a list of objects")
        for item in loaded:
            if not isinstance(item, dict):
                raise ValueError(f"{DEMO_TEST_ACCOUNTS_ENV} JSON entries must be objects")
            entries.append(
                {
                    "username": str(item.get("username") or "").strip(),
                    "password": str(item.get("password") or ""),
                    "template": str(item.get("as") or "").strip(),
                    "allow_admin": item.get("allow_admin") is True,
                }
            )
    else:
        for raw in text.split(","):
            part = raw.strip()
            if not part:
                continue
            name, _, rest = part.partition(":")
            password, _, flag = rest.partition(":")
            entries.append(
                {
                    "username": name.strip(),
                    "password": password,
                    "template": "",
                    "allow_admin": flag.strip().lower() == "admin",
                }
            )
    problems: list[str] = []
    specs: list[DemoAccountSpec] = []
    seen: set[str] = set()
    for entry in entries:
        name = entry["username"]
        template = entry["template"] or DEFAULT_DEMO_TEMPLATES.get(name, "")
        if not name:
            problems.append("an entry has no user name")
            continue
        if name in seen:
            problems.append(f"{name}: listed twice")
            continue
        seen.add(name)
        if len(entry["password"]) < DEMO_MIN_PASSWORD_LENGTH:
            problems.append(
                f"{name}: password missing or shorter than {DEMO_MIN_PASSWORD_LENGTH} characters"
            )
        if not template:
            problems.append(f"{name}: unknown account; give the demo tester to copy with 'as'")
        specs.append(
            DemoAccountSpec(
                username=name,
                password=entry["password"],
                template=template,
                allow_admin=entry["allow_admin"],
            )
        )
    if problems:
        raise ValueError(f"{DEMO_TEST_ACCOUNTS_ENV}: " + "; ".join(problems))
    return specs


def ensure_demo_account(
    session: Session,
    spec: DemoAccountSpec,
    *,
    display_name: str,
    grants: AccountGrants,
    reapply: bool,
    now_utc: datetime | None = None,
) -> str:
    """Create or refresh one demo test account; returns created/updated/kept.

    Refused unless the demo profile is active. The password may be shorter than the
    policy (the owner's convenience on a public demo); the account is marked demo, needs
    no change at first sign-in and never signs in outside a demo server.
    """

    if not demo_profile_active():
        raise LocalAccountError(
            "demo_accounts_refused",
            409,
            "Demo test accounts exist only on the demo server (demo profile).",
        )
    if "ADMIN" in {r.upper() for r in grants.roles} and not spec.allow_admin:
        raise LocalAccountError(
            "demo_admin_not_named",
            422,
            f"{spec.username} would hold the ADMIN role; mark it explicitly with ':admin'.",
        )
    now = _now(now_utc)
    row = (
        session.query(IdentityPrincipalRecord)
        .filter(IdentityPrincipalRecord.name == spec.username)
        .one_or_none()
    )
    outcome = "kept"
    if row is None:
        row = _new_principal(
            session,
            name=spec.username,
            display_name=display_name,
            email=None,
            identity_source="LOCAL",
            status="ACTIVE",
            now=now,
        )
        outcome = "created"
    credential = credential_for(session, row.principal_id)
    if credential is None:
        if outcome != "created":
            raise LocalAccountError(
                "demo_name_taken",
                409,
                f"{spec.username} already exists and is not a demo test account.",
            )
        credential = IdentityLocalCredentialRecord(
            principal_id=row.principal_id, created_by="demo-start", created_at_utc=now
        )
        session.add(credential)
    elif not credential.is_demo and outcome != "created":
        raise LocalAccountError(
            "demo_name_taken",
            409,
            f"{spec.username} already exists and is not a demo test account.",
        )
    if outcome == "created" or reapply:
        _apply_grants(session, row, grants)
        row.display_name = display_name
        row.status = "ACTIVE"
        row.updated_at_utc = now
        if outcome != "created":
            outcome = "updated"
    else:
        # Data scopes follow the code on every start, so a narrowed grant (book isolation,
        # security review H1) reaches an existing demo account without a reset.
        wanted = sorted(
            {str(scope).strip().upper() for scope in grants.data_scopes if str(scope).strip()}
        )
        if sorted(row.data_scopes or []) != wanted:
            row.data_scopes = wanted
            row.updated_at_utc = now
            outcome = "updated"
    if outcome == "created" or not passwords.verify_password(spec.password, _stored(credential)):
        # Demo only: no policy check (the setting may carry a short shared password).
        _store_password(credential, spec.password, must_change=False, now=now)
        if outcome == "kept":
            outcome = "updated"
    else:
        # Every demo start lifts a lock (anyone can lock a public test name).
        credential.failed_attempts = 0
        credential.locked_until_utc = None
    credential.is_demo = True
    credential.updated_at_utc = now
    session.flush()
    if outcome != "kept":
        _audit(
            session,
            actor="demo-start",
            action="access.user.demo_account",
            resource=f"identity_principal:{row.principal_id}",
            outcome=outcome,
            detail=f"name={row.name}; template={spec.template}; {_grant_summary(row)}",
            source_system="demo-start",
            now_utc=now,
        )
    return outcome


def disable_unlisted_demo_accounts(
    session: Session, listed: set[str], *, now_utc: datetime | None = None
) -> list[str]:
    """Disable demo test accounts that the setting no longer lists (sessions end)."""

    from eurogas_nexus.db.repositories.security import revoke_principal_sessions

    now = _now(now_utc)
    disabled: list[str] = []
    rows = (
        session.query(IdentityPrincipalRecord, IdentityLocalCredentialRecord)
        .join(
            IdentityLocalCredentialRecord,
            IdentityLocalCredentialRecord.principal_id == IdentityPrincipalRecord.principal_id,
        )
        .filter(IdentityLocalCredentialRecord.is_demo.is_(True))
        .all()
    )
    for row, _credential in rows:
        if row.name in listed or row.status != "ACTIVE":
            continue
        row.status = "DISABLED"
        row.updated_at_utc = now
        revoke_principal_sessions(session, row.principal_id, now_utc=now)
        disabled.append(row.name)
        _audit(
            session,
            actor="demo-start",
            action="access.user.demo_account",
            resource=f"identity_principal:{row.principal_id}",
            outcome="disabled",
            detail=f"name={row.name}; no longer listed",
            source_system="demo-start",
            now_utc=now,
        )
    session.flush()
    return disabled
