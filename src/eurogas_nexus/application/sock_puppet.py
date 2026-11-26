"""The second person of a four-eyes act is a second person (security review H7).

An administrator could create a second account, or grant one a role, and approve their own
proposals from it. An approver is refused when the requester created the approver's account
or changed its grants within the cooling period (``EUROGAS_NEXUS_DUAL_CONTROL_COOLING_DAYS``,
default 7 days), as the audit trail records it. Used by the dual control of security-relevant
changes (``api/dual_control.py``) and by the maker-checker on limits and marks
(``application/maker_checker.py``).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

COOLING_DAYS_ENV = "EUROGAS_NEXUS_DUAL_CONTROL_COOLING_DAYS"
#: Audit actions that create an account or change its grants: the cooling-period evidence.
GRANT_ACTIONS = (
    "access.user.create",
    "access.user.update",
    "access.user.demo_account",
    "access.user.invite",
    "access.group.member",
    "identity.principal.create",
    "auth.local.account_created",
)


def cooling_days() -> int:
    try:
        return max(0, int(os.environ.get(COOLING_DAYS_ENV) or 7))
    except ValueError:
        return 7


def sock_puppet_refusal(session, approver_ids: set[str], requester_ids: set[str],
                        approver_principal_id: str | None) -> str | None:
    """Why the approver may not approve the requester's change, or ``None``.

    The requester created the approver's account, or changed its grants, within the cooling
    period: an account one person provisions is not a second person.
    """

    if approver_ids & requester_ids:
        return "the requester may not approve their own change"
    if not approver_principal_id:
        return None
    from eurogas_nexus.db.models import AuditEventRecord

    since = datetime.now(UTC) - timedelta(days=cooling_days())
    hit = (
        session.query(AuditEventRecord.event_id)
        .filter(
            AuditEventRecord.resource == f"identity_principal:{approver_principal_id}",
            AuditEventRecord.principal.in_(sorted(requester_ids)),
            AuditEventRecord.action.in_(GRANT_ACTIONS),
            AuditEventRecord.event_ts_utc >= since,
        )
        .first()
    )
    if hit is not None:
        return (
            f"the requester created or changed this approver's access within the last "
            f"{cooling_days()} days"
        )
    return None


