"""Segregation of duties for the risk function.

Limits, credit lines, mandates, hedge bands and opportunity thresholds are maintained by the
risk function. Holding REVIEWER is necessary but not enough: a principal who also holds a
front-office role (ANALYST: traders, originators, analysts) would set the limits their own
deals are measured against. Roles are ranked (ANALYST outranks REVIEWER), so rank alone can
never be the test.

This is the control every desk audit asks for first (persona review P-01, P-02, standard
B7/F4). There is no override: a combined account (such as the all-roles demo tester) does
risk work by signing in as a risk identity.
"""

from __future__ import annotations

from typing import Any

#: Roles that originate or trade deals and so may not maintain the limits on them.
FRONT_OFFICE_ROLES = frozenset({"ANALYST"})
RISK_FUNCTION_ROLE = "REVIEWER"


def held_roles(identity: Any) -> frozenset[str]:
    """Every role the identity holds, upper-cased (primary role and the roles list)."""

    held = {str(getattr(identity, "role", "") or "").upper()}
    held |= {str(role).upper() for role in (getattr(identity, "roles", ()) or ())}
    held.discard("")
    return frozenset(held)


def risk_function_refusal(identity: Any, *, what: str) -> dict[str, str] | None:
    """Why ``identity`` may not maintain ``what`` for the risk function, or ``None``.

    Returns the 403 detail: ``risk_function_required`` without REVIEWER, or
    ``segregation_of_duties`` when a front-office role is held as well.
    """

    held = held_roles(identity)
    if RISK_FUNCTION_ROLE not in held:
        return {
            "code": "risk_function_required",
            "message": f"{what} are maintained by risk (REVIEWER role).",
        }
    front = sorted(held & FRONT_OFFICE_ROLES)
    if front:
        return {
            "code": "segregation_of_duties",
            "message": (
                f"{what} are maintained by risk, independent of the front office; this "
                f"identity also holds {', '.join(front)}. Sign in with a risk identity."
            ),
        }
    return None


def names_of(identity: Any) -> frozenset[str]:
    """The identity's id, name and display name, case-folded, for "is this me?" checks."""

    values = (
        getattr(identity, "principal_id", None),
        getattr(identity, "name", None),
        getattr(identity, "display_name", None),
    )
    return frozenset(str(value).strip().casefold() for value in values if value)


def grant_conflict(roles: Any) -> dict[str, Any] | None:
    """The segregation-of-duties warning for a grant of ``roles``, or ``None`` (QA-R-03).

    An administrator may grant a front-office role and the risk role together (a combined
    test account, a small desk); the grant is not refused. It is answered with this warning,
    because the server refuses that person's risk writes (:func:`risk_function_refusal`):
    they could set the limits their own deals are measured against.
    """

    held = frozenset(str(role).strip().upper() for role in (roles or ()) if role)
    front = sorted(held & FRONT_OFFICE_ROLES)
    if not front or RISK_FUNCTION_ROLE not in held:
        return None
    return {
        "code": "segregation_of_duties",
        "roles": [*front, RISK_FUNCTION_ROLE],
        "message": (
            f"{' and '.join(front)} with {RISK_FUNCTION_ROLE}: this person trades or originates "
            "and holds the risk role. Their limit, mandate, hedge-band and threshold changes "
            "are refused (segregation of duties); give risk work to a separate risk identity."
        ),
    }
