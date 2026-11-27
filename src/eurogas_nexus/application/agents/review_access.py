"""Object ACL checks for review capability handlers."""

from __future__ import annotations

from fastapi import HTTPException

from eurogas_nexus.domain.agents.contracts import CapabilityFailureCode, CapabilityResult


def guard_review_capability(session, arguments, context, definition):
    """Check that a named caller may read every review target the call names.

    The caller must be an active named identity (the same refusal the strategy guard this
    replaced applied before any target check), so an unnamed caller is refused rather than
    answered with the decisions visible to nobody in particular.

    Args:
        session: Open database session.
        arguments: Capability arguments (``entity_type`` and ``entity_id``).
        context: Agent invocation context carrying the principal id.
        definition: Capability definition used for the blocked result.

    Returns:
        A blocked :class:`CapabilityResult` when a target is not readable, else None.
    """

    from eurogas_nexus.db.repositories.identity_access import require_named_principal
    from eurogas_nexus.db.repositories.review import can_read_review_target

    try:
        principal_id = require_named_principal(session, getattr(context, "principal_id", None))
        if arguments.get("entity_type") and arguments.get("entity_id"):
            if not can_read_review_target(
                session,
                arguments["entity_type"],
                arguments["entity_id"],
                principal_id,
            ):
                raise HTTPException(404)
    except HTTPException:
        return CapabilityResult.blocked(
            capability=definition.capability_id,
            capability_version=definition.capability_version,
            code=CapabilityFailureCode.ENTITY_NOT_FOUND,
            detail="Review target not found or not accessible",
        )
    return None
