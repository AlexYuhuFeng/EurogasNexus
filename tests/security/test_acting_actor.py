"""Who is recorded as the actor of a job, run or operational action.

Found while implementing owner decision D1 (architecture conflict C5): the compatibility
principal's ``principal_id`` is ``service:public-api``, and the actor validator rejects a colon.
Every route that turned an attached identity into a job's ``principal`` therefore failed - in the
release profile too, where that principal has always been attached for a deployment-token caller.
Installing the identity layer in the development profile is what surfaced it, but the defect was
not confined to development.

The rule now has one home (`acting_actor_name`), the same way the C13 actor rule does: an actor is
taken from the identity only when the identity was **authenticated**, and a caller the deployment
serves without a credential is recorded under the fallback the routes used before. The actor is
never a value from the request body.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from eurogas_nexus.api.dependencies.acting_actor import (
    IDENTITY_AUTHENTICATED_FLAG,
    acting_actor,
    acting_actor_name,
)
from eurogas_nexus.domain.identity.principal import (
    PrincipalValidationError,
    normalize_principal,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal


def _request(**state: object) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(**state))


def _principal(principal_id: str, name: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=principal_id,
        name=name,
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=("ENTSOG",),
        roles=("ANALYST",),
        auth_method="identity_key",
    )


def test_the_compatibility_principal_id_is_not_a_valid_actor() -> None:
    """The defect this helper closes, stated as an assertion rather than a comment."""

    with pytest.raises(PrincipalValidationError):
        normalize_principal(legacy_public_token_principal().principal_id)
    # Its name is a valid principal, which is why the platform records that for its own caller.
    assert normalize_principal(legacy_public_token_principal().name) == "public-api"


def test_an_authenticated_caller_is_recorded_by_their_own_principal() -> None:
    request = _request(
        identity=_principal("principal-analyst", "analyst"),
        **{IDENTITY_AUTHENTICATED_FLAG: True},
    )

    assert acting_actor_name(request) == "principal-analyst"
    # A valid actor, so the job row can actually be written.
    assert normalize_principal(acting_actor_name(request)) == "principal-analyst"
    assert acting_actor(request).principal_id == "principal-analyst"


def test_an_unauthenticated_caller_is_never_recorded_as_the_compatibility_principal_id() -> None:
    compatibility = legacy_public_token_principal()
    request = _request(identity=compatibility, **{IDENTITY_AUTHENTICATED_FLAG: False})

    actor = acting_actor_name(request)
    assert actor == "operator"
    # The value the old helpers returned here - ``service:public-api`` - cannot be stored at all.
    assert actor != compatibility.principal_id
    assert normalize_principal(actor) == "operator"


def test_no_identity_at_all_falls_back_to_the_pre_decision_actor() -> None:
    assert acting_actor_name(_request()) == "operator"
    assert acting_actor_name(_request(), fallback="scheduler") == "scheduler"
    # A foreign object on `state.identity` is not an identity.
    assert acting_actor_name(_request(identity="not-a-principal")) == "operator"


def test_the_job_tracking_routes_share_one_actor_rule() -> None:
    """Three routes used to derive the actor by hand, and all three got it wrong the same way."""

    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    routes = root / "src" / "eurogas_nexus" / "api" / "routes" / "public"
    for name in ("shadow.py", "strategy_registry.py", "source_operations.py"):
        source = (routes / name).read_text(encoding="utf-8")
        assert "acting_actor_name(request)" in source, name
        assert "str(identity.principal_id)" not in source, name
