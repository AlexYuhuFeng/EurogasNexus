"""Second factor for local accounts: enrolment, sign-in verification, recovery, reset (H6).

* **Enrol**: a signed-in person asks for a secret (shown once as an ``otpauth://`` URI and in
  text), then confirms it with a code from their app; the confirmation answers ten recovery
  codes, once.
* **Sign in**: after the password, a person with a confirmed factor receives a single-use,
  five-minute ``mfa_token`` instead of a session, and the session opens when they send a code
  (or a recovery code) with it. Five wrong codes end the token.
* **Policy** (``EUROGAS_NEXUS_MFA_REQUIRED``): ``all``, ``privileged`` (every role above VIEWER
  and SCHEDULER, the default in trial and release) or ``off`` (the default in development and
  test). A person the policy covers who has not enrolled signs in to an enrolment-only
  session: every route but enrolment, ``/api/me`` and sign-out answers 403
  ``mfa_enrolment_required`` until they enrol.
* **Reset**: an administrator removes a person's factor under dual control (H7); audited,
  and every session of the person ends.

The secret is encrypted with the deployment key (rotatable, ``security/credentials.py``).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from eurogas_nexus.security import totp

MFA_REQUIRED_ENV = "EUROGAS_NEXUS_MFA_REQUIRED"
CHALLENGE_TTL = timedelta(minutes=5)
MAX_CODE_ATTEMPTS = 5
#: Session client type of an enrolment-only session (``api/dependencies/identity.py``).
ENROLMENT_SESSION = "mfa_enrolment"
UNPRIVILEGED_ROLES = frozenset({"VIEWER", "SCHEDULER"})


class MfaError(Exception):
    def __init__(self, code: str, status: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status
        self.message = message


def policy() -> str:
    raw = (os.environ.get(MFA_REQUIRED_ENV) or "").strip().lower()
    if raw in {"all", "privileged", "off"}:
        return raw
    from eurogas_nexus.core.config import runtime_environment

    environment = runtime_environment()
    return "privileged" if environment in {"trial", "release"} else "off"


def required_for(row) -> bool:
    mode = policy()
    if mode == "all":
        return True
    if mode == "off":
        return False
    roles = {str(role).upper() for role in (row.roles or [row.role])}
    return bool(roles - UNPRIVILEGED_ROLES)


def _now(now: datetime | None) -> datetime:
    value = now or datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _record(session: Session, principal_id: str):
    from eurogas_nexus.db.models import IdentityMfaRecord

    return session.get(IdentityMfaRecord, principal_id)


def enrolled(session: Session, principal_id: str) -> bool:
    row = _record(session, principal_id)
    return row is not None and row.confirmed_at_utc is not None


def status(session: Session, row) -> dict:
    record = _record(session, row.principal_id)
    return {
        "enrolled": record is not None and record.confirmed_at_utc is not None,
        "required": required_for(row),
        "policy": policy(),
        "recovery_codes_left": len(record.recovery_code_hashes or [])
        if record is not None and record.confirmed_at_utc is not None
        else 0,
    }


def _audit(session, *, actor: str, action: str, principal_id: str, outcome: str,
           detail: str = "", severity: str = "info") -> None:
    from eurogas_nexus.db.repositories.audit import record_governed_audit

    record_governed_audit(
        session,
        event_type="governance.auth",
        principal=actor[:64],
        action=action,
        resource=f"identity_principal:{principal_id}",
        outcome=outcome,
        severity=severity,
        detail=detail,
        source_system="local-auth",
    )


def begin_enrolment(session: Session, row, *, now: datetime | None = None) -> dict:
    """A new, unconfirmed secret for ``row`` (replaces an unconfirmed one)."""

    from eurogas_nexus.db.models import IdentityMfaRecord
    from eurogas_nexus.security.credentials import encrypt_text

    current = _record(session, row.principal_id)
    if current is not None and current.confirmed_at_utc is not None:
        raise MfaError("mfa_already_enrolled", 409,
                       "A second factor is already set up; ask an administrator to reset it.")
    moment = _now(now)
    secret = totp.new_secret()
    try:
        encrypted = encrypt_text(secret)
    except ValueError as exc:
        raise MfaError("mfa_key_not_configured", 503,
                       "The deployment key (EUROGAS_NEXUS_SECRET_KEY) is not set.") from exc
    if current is None:
        current = IdentityMfaRecord(principal_id=row.principal_id, created_at_utc=moment,
                                    secret_encrypted=encrypted, updated_at_utc=moment,
                                    failed_attempts=0)
        session.add(current)
    current.secret_encrypted = encrypted
    current.confirmed_at_utc = None
    current.last_step = None
    current.recovery_code_hashes = None
    current.updated_at_utc = moment
    session.flush()
    return {
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, row.name),
        "digits": totp.DIGITS,
        "period_seconds": totp.STEP_SECONDS,
    }


def confirm_enrolment(session: Session, row, code: str, *, now: datetime | None = None) -> dict:
    from eurogas_nexus.security.credentials import decrypt_text

    record = _record(session, row.principal_id)
    if record is None or record.confirmed_at_utc is not None:
        raise MfaError("mfa_not_enrolling", 409, "Start setting up the second factor first.")
    step = totp.verify(decrypt_text(record.secret_encrypted), code,
                       now=_now(now).timestamp())
    if step is None:
        raise MfaError("mfa_code_invalid", 401, "That code is not right. Try the current one.")
    codes = totp.new_recovery_codes()
    moment = _now(now)
    record.confirmed_at_utc = moment
    record.last_step = step
    record.recovery_code_hashes = [totp.hash_recovery_code(code) for code in codes]
    record.updated_at_utc = moment
    _audit(session, actor=row.principal_id, action="auth.mfa.enrolled",
           principal_id=row.principal_id, outcome="enrolled")
    # An enrolment-only session becomes a full one once the factor is set up.
    from eurogas_nexus.db.models import UserSessionRecord

    session.query(UserSessionRecord).filter(
        UserSessionRecord.principal_id == row.principal_id,
        UserSessionRecord.client_type == ENROLMENT_SESSION,
        UserSessionRecord.revoked_at_utc.is_(None),
    ).update({"client_type": "local_password"}, synchronize_session=False)
    session.flush()
    return {"enrolled": True, "recovery_codes": codes}


def start_challenge(session: Session, row, client_type: str, *,
                    now: datetime | None = None) -> str:
    """The single-use token between the password step and the code step."""

    from eurogas_nexus.security import passwords

    record = _record(session, row.principal_id)
    token = passwords.generate_token()
    record.challenge_hash = passwords.hash_token(token)
    record.challenge_expires_at_utc = _now(now) + CHALLENGE_TTL
    record.challenge_client_type = client_type[:32]
    record.failed_attempts = 0
    session.flush()
    return token


def complete_challenge(session: Session, token: str, *, code: str | None,
                       recovery_code: str | None, now: datetime | None = None):
    """Verify the code for ``token``; returns ``(principal row, client type)``."""

    from eurogas_nexus.db.models import IdentityMfaRecord, IdentityPrincipalRecord
    from eurogas_nexus.security import passwords
    from eurogas_nexus.security.credentials import decrypt_text

    moment = _now(now)
    record = (
        session.query(IdentityMfaRecord)
        .filter(IdentityMfaRecord.challenge_hash == passwords.hash_token(token or ""))
        .one_or_none()
    )
    expires = record.challenge_expires_at_utc if record is not None else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if record is None or expires is None or expires <= moment:
        raise MfaError("mfa_challenge_invalid", 401, "This step has expired. Sign in again.")
    row = session.get(IdentityPrincipalRecord, record.principal_id)
    if row is None or row.status != "ACTIVE":
        raise MfaError("mfa_challenge_invalid", 401, "Sign in again.")
    used = None
    if recovery_code:
        digest = totp.hash_recovery_code(recovery_code)
        hashes = list(record.recovery_code_hashes or [])
        if digest in hashes:
            hashes.remove(digest)
            record.recovery_code_hashes = hashes
            used = "recovery_code"
    elif code:
        step = totp.verify(decrypt_text(record.secret_encrypted), code,
                           last_step=record.last_step, now=moment.timestamp())
        if step is not None:
            record.last_step = step
            used = "totp"
    if used is None:
        record.failed_attempts = int(record.failed_attempts or 0) + 1
        if record.failed_attempts >= MAX_CODE_ATTEMPTS:
            record.challenge_hash = None
        _audit(session, actor=row.principal_id, action="auth.mfa.denied",
               principal_id=row.principal_id, outcome="denied", severity="warning",
               detail=f"attempts={record.failed_attempts}")
        session.flush()
        raise MfaError("mfa_code_invalid", 401, "That code is not right.")
    client_type = record.challenge_client_type or "local_password"
    record.challenge_hash = None
    record.challenge_expires_at_utc = None
    record.failed_attempts = 0
    record.updated_at_utc = moment
    _audit(session, actor=row.principal_id, action="auth.mfa.verified",
           principal_id=row.principal_id, outcome="success", detail=f"method={used}",
           severity="warning" if used == "recovery_code" else "info")
    session.flush()
    return row, client_type


def reset(session: Session, principal_id: str, *, actor: str) -> bool:
    """Remove a person's second factor (an administrator's act under dual control)."""

    from eurogas_nexus.db.repositories.security import revoke_principal_sessions

    record = _record(session, principal_id)
    if record is None:
        return False
    session.delete(record)
    ended = revoke_principal_sessions(session, principal_id)
    _audit(session, actor=actor, action="auth.mfa.reset", principal_id=principal_id,
           outcome="reset", severity="warning", detail=f"sessions_ended={ended}")
    session.flush()
    return True
