"""Neutral identity checks shared by routes, jobs and capability handlers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import IdentityPrincipalRecord


def require_named_principal(session: Session, principal_id: str | None) -> str:
    """Return an active named principal id or refuse.

    Args:
        session: Open database session.
        principal_id: Claimed principal id.

    Returns:
        The active principal id.

    Raises:
        HTTPException: 403 when the principal is missing or not active.
    """

    principal = session.get(IdentityPrincipalRecord, principal_id) if principal_id else None
    if principal is None or principal.status != "ACTIVE":
        raise HTTPException(
            status_code=403, detail={
                "code": "named_principal_required",
                "message": "A named active identity is required to own this record",
            }
        )
    return principal.principal_id
