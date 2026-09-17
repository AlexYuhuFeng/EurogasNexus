"""Who is recorded as the actor of a governance act (Architecture V2).

A review decision, a decision-record transition and a review-pack confirmation are
governance acts: the platform stores who made them and writes an audit event under that
name. The actor is therefore the **authenticated identity**, never a request-body field - a
caller that can type a name can attribute a decision to somebody who never made it, and the
audit trail would repeat the claim as if the platform had verified it.

W0-03 C13 records the finding this rule closes: the review-decision path took its actor from
the body and used it as the audit event's principal, while the Decision Case path already
resolved the actor from the identity. Two paths, two answers to "who decided" - so the rule
now has one home and both paths call it.

Where no identity exists - the private-network compatibility posture, which authenticates a
deployment token rather than a person - the deployment's own public-API principal is
recorded, because that is who actually acted. Recording a caller-supplied name there would
be the same claim-by-typing the rule exists to prevent.
"""

from __future__ import annotations

from fastapi import Request

from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    legacy_public_token_principal,
)


def acting_actor(request: Request) -> AuthenticatedPrincipal:
    """The principal a governance act is recorded against.

    Args:
        request: Incoming request, whose ``state.identity`` the authentication
            dependency attaches when a real identity was verified.

    Returns:
        The authenticated principal, or the deployment's public-API principal when
        the request carried no verified identity. Never a value from the request body.
    """

    identity = getattr(request.state, "identity", None)
    if isinstance(identity, AuthenticatedPrincipal):
        return identity
    return legacy_public_token_principal()
