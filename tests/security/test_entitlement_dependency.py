"""Entitlement dependency contract tests (architecture conflict register C7).

``api/dependencies/entitlement.py`` is deliberately not mounted on any route today: the
enforced control on the governed read routes is the per-family, per-row filter, and this
dependency is a coarser route-level gate that would refuse a partially entitled
principal the whole route. That decision is recorded in the module docstring, and these
tests make sure the dependency is a *decided* piece of code rather than dead code: if it
is ever mounted, its refusals are already known to be fail-closed.

The tests call the dependency directly (it is an async function, so they run under
``asyncio``), which is exactly how FastAPI would call it with a declared family.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from eurogas_nexus.api.dependencies.entitlement import require_entitlement
from eurogas_nexus.security.identity import AuthenticatedPrincipal, Role


class _State:
    def __init__(self, identity: AuthenticatedPrincipal | None) -> None:
        self.identity = identity


class _Request:
    def __init__(self, identity: AuthenticatedPrincipal | None) -> None:
        self.state = _State(identity)


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="entitlement-subject",
        name="Entitlement Subject",
        principal_type="USER",
        role=Role.ANALYST.value,
        status="ACTIVE",
        data_scopes=scopes,
        roles=(Role.ANALYST.value,),
    )


def _call(request: _Request, source_system: str) -> None:
    asyncio.run(require_entitlement(request, source_system))  # type: ignore[arg-type]


def test_no_declared_family_is_a_documented_no_op() -> None:
    """A route that declares no governed family is not evaluated."""

    _call(_Request(_principal()), "")


def test_a_baseline_family_is_available_to_an_active_principal() -> None:
    """Public baseline families need no explicit grant; commercial ones do."""

    _call(_Request(_principal("GIE")), "ENTSOG")
    _call(_Request(_principal()), "GIE")


def test_an_unentitled_principal_is_refused_with_the_audit_reason() -> None:
    """A commercial family the principal has no data-scope grant for fails closed."""

    with pytest.raises(HTTPException) as denied:
        _call(_Request(_principal("GIE")), "EEX")

    assert denied.value.status_code == 403
    detail = denied.value.detail
    assert detail["error"] == "entitlement_denied"
    assert detail["source_system"] == "EEX"
    assert "no data-scope grant" in detail["reason"]
    # The refusal keeps the decision-support markers the other gates report.
    assert detail["research_only"] is True
    assert detail["human_review_required"] is True

    # The same principal with the grant passes, so the refusal is about the grant and
    # not about the family being unreviewed.
    _call(_Request(_principal("EEX")), "EEX")


def test_an_unknown_family_is_refused_even_for_an_unrestricted_principal() -> None:
    """An unreviewed source is never granted, however broad the principal's scopes."""

    with pytest.raises(HTTPException) as denied:
        _call(_Request(_principal("*")), "SOME_UNREVIEWED_VENDOR")

    assert denied.value.status_code == 403
    assert denied.value.detail["error"] == "entitlement_denied"
    assert "not in the known-entitled set" in denied.value.detail["reason"]


def test_an_unavailable_governance_module_refuses_rather_than_grants(monkeypatch) -> None:
    """An entitlement state that cannot be evaluated is a denial, never a pass."""

    import eurogas_nexus.governance.entitlement as governance

    def _explode(*_args, **_kwargs):
        raise RuntimeError("governance registry unavailable")

    monkeypatch.setattr(governance, "entitlement_check", _explode)

    with pytest.raises(HTTPException) as denied:
        _call(_Request(_principal("ENTSOG")), "ENTSOG")

    assert denied.value.status_code == 403
    detail = denied.value.detail
    assert detail["error"] == "entitlement_unavailable"
    assert detail["error_class"] == "RuntimeError"


def test_the_decision_to_leave_it_unwired_is_recorded_in_the_module() -> None:
    """The C7 decision travels with the code, so it cannot be lost silently."""

    import eurogas_nexus.api.dependencies.entitlement as dependency

    docstring = dependency.__doc__ or ""
    assert "C7" in docstring
    assert "deliberately" in docstring
    assert "row-level" in docstring
    assert "07_DATA_GOVERNANCE_AND_RESEARCH.md" in docstring
    assert "test_entitlement_dependency.py" in docstring
