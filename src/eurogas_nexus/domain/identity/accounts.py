"""What Admin -> Users shows about a person: how they sign in and the one state.

Pure functions over the principal and its local credential (no database access), shared by
the identity repository (the users list) and the local-account service.
"""

from __future__ import annotations

from datetime import UTC, datetime

INVITED_STATUS = "INVITED"


def _now(now_utc: datetime | None) -> datetime:
    value = now_utc or datetime.now(UTC)
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def account_kind(row, credential) -> str:
    """``local`` (password), ``sso`` (company sign-in), ``service`` or ``key`` (API key only)."""

    if credential is not None:
        return "local"
    if row.principal_type == "SERVICE":
        return "service"
    if (row.identity_source or "LOCAL").upper() != "LOCAL" or row.status == INVITED_STATUS:
        return "sso"
    return "key"


def account_state(
    row,
    credential,
    *,
    now_utc: datetime | None = None,
) -> str:
    """What Admin -> Users shows: ACTIVE, INVITED, DISABLED, LOCKED or PENDING."""

    now = _now(now_utc)
    if row.status in {"DISABLED", "LOCKED", "PENDING", INVITED_STATUS}:
        return row.status
    if credential is not None:
        locked_until = _aware(credential.locked_until_utc)
        if locked_until is not None and locked_until > now:
            return "LOCKED"
        if credential.must_change_password and row.last_login_at_utc is None:
            return INVITED_STATUS
    return "ACTIVE" if row.status == "ACTIVE" else row.status


def credential_payload(
    credential, *, now_utc: datetime | None = None
) -> dict | None:
    """Safe facts about a local password (never the hash, salt or token)."""

    if credential is None:
        return None
    now = _now(now_utc)
    locked_until = _aware(credential.locked_until_utc)
    expires = _aware(credential.temporary_expires_at_utc)
    return {
        "must_change_password": bool(credential.must_change_password),
        "temporary_password_expires_at_utc": expires.isoformat() if expires else None,
        "temporary_password_expired": bool(
            credential.must_change_password and expires is not None and expires <= now
        ),
        "locked_until_utc": (
            locked_until.isoformat() if locked_until and locked_until > now else None
        ),
        "failed_attempts": int(credential.failed_attempts or 0),
        "password_set_at_utc": _aware(credential.password_set_at_utc).isoformat(),
        "demo_account": bool(credential.is_demo),
    }


