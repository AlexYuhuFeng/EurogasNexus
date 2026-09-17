"""Product error taxonomy tests (Architecture V2 Wave 8, taxonomy layer).

The taxonomy exists so a failure answers what happened, what it affects, the
likely cause and how to recover, through a stable code - and so an internal cause
can never leak to a business user.
"""

from __future__ import annotations

import pytest

from eurogas_nexus.domain.operations.error_taxonomy import (
    ERROR_CATALOGUE,
    UNKNOWN_ERROR_CODE,
    ErrorFamily,
    ErrorSeverity,
    Recoverability,
    catalogue_by_family,
    error_definition,
    error_family,
    error_payload,
    family_for_operational_category,
)
from eurogas_nexus.domain.operations.errors import OperationalErrorCategory


def test_every_catalogued_code_is_complete_and_typed() -> None:
    assert ERROR_CATALOGUE
    for code, definition in ERROR_CATALOGUE.items():
        assert definition.code == code
        assert isinstance(definition.family, ErrorFamily)
        assert isinstance(definition.severity, ErrorSeverity)
        assert isinstance(definition.recoverability, Recoverability)
        assert definition.message_key == f"errors.{code}.message"
        assert definition.action_key == f"errors.{code}.action"


def test_the_catalogue_covers_the_codes_the_api_already_returns() -> None:
    # These are the codes that exist in the repository today; the taxonomy must
    # explain them rather than leaving them unclassified.
    for code in [
        "unauthenticated",
        "invalid_credentials",
        "session_invalid",
        "identity_not_provisioned",
        "identity_role_forbidden",
        "permission_denied",
        "permission_not_declared",
        "entitlement_denied",
        "entitlement_unavailable",
        "export_denied",
        "runtime_db_unavailable",
        "runtime_db_required",
        "dataset_spec_invalid",
        "dataset_build_invalid",
        "dev_login_disabled",
        "oidc_not_configured",
        "principal_missing",
        "identity_store_unavailable",
    ]:
        definition = error_definition(code)
        assert definition.code == code, code
        assert definition.family is not ErrorFamily.SYSTEM, code


def test_v2_named_failure_modes_are_catalogued() -> None:
    assert error_family("DATA_STALE") is ErrorFamily.DATA
    assert error_family("DATA_MISSING") is ErrorFamily.DATA
    assert error_family("PORTFOLIO_INCOMPLETE") is ErrorFamily.DATA
    assert error_family("SNAPSHOT_EXPIRED") is ErrorFamily.DATA
    assert error_family("ROUTE_INFEASIBLE") is ErrorFamily.CALCULATION
    assert error_family("OPTIMIZATION_INFEASIBLE") is ErrorFamily.CALCULATION
    assert error_family("PROVIDER_UNAVAILABLE") is ErrorFamily.DEPENDENCY
    assert error_family("AGENT_BUDGET_EXCEEDED") is ErrorFamily.AGENT
    assert error_family("commercial_access_not_granted") is ErrorFamily.ENTITLEMENT


def test_an_unknown_code_fails_closed_to_system() -> None:
    definition = error_definition("something_new")

    assert definition.code == UNKNOWN_ERROR_CODE
    assert definition.family is ErrorFamily.SYSTEM
    assert definition.recoverability is Recoverability.UNKNOWN
    assert error_family("") is ErrorFamily.SYSTEM


def test_an_uncatalogued_code_keeps_its_name_and_gains_an_inferred_family() -> None:
    """The API raises dozens of specific codes; the envelope still classifies them."""

    cases = {
        "runtime_db_not_configured": ErrorFamily.CONFIGURATION,
        "analysis_snapshot_not_found": ErrorFamily.VALIDATION,
        "gas_day_invalid": ErrorFamily.VALIDATION,
        "case_not_decidable": ErrorFamily.VALIDATION,
        "manual_assumptions_too_many": ErrorFamily.VALIDATION,
        "optimization_input_invalid": ErrorFamily.VALIDATION,
        "registry_unavailable": ErrorFamily.DEPENDENCY,
        "artifact_store_unavailable": ErrorFamily.DEPENDENCY,
        "export_denied_entitlement": ErrorFamily.ENTITLEMENT,
        "capability_not_registered": ErrorFamily.AGENT,
    }
    assert not (set(cases) & set(ERROR_CATALOGUE)), "these cases are meant to be uncatalogued"
    for code, family in cases.items():
        definition = error_definition(code)
        assert definition.code == code, code
        assert definition.family is family, code
        # An uncatalogued code takes family-level keys, so a client always has text.
        assert definition.message_key == f"errors.family.{family.value}.title", code
        assert definition.action_key == f"errors.family.{family.value}.action", code

    # Catalogued codes keep their own keys and family.
    assert error_family("credential_store_not_configured") is ErrorFamily.CONFIGURATION
    assert error_family("llm_provider_denied") is ErrorFamily.ENTITLEMENT
    assert (
        error_definition("credential_store_not_configured").message_key
        == "errors.credential_store_not_configured.message"
    )

    payload = error_payload("analysis_snapshot_not_found", correlation_id="c-2")
    assert payload["error"] == "analysis_snapshot_not_found"
    assert payload["family"] == "VALIDATION"
    assert payload["message_key"] == "errors.family.VALIDATION.title"


def test_the_payload_carries_the_v2_fields_and_the_correlation_id() -> None:
    payload = error_payload("entitlement_denied", correlation_id="corr-9")

    assert payload["error"] == "entitlement_denied"
    assert payload["family"] == "ENTITLEMENT"
    assert payload["severity"] == "error"
    assert payload["recoverability"] == "permanent"
    assert payload["message_key"] == "errors.entitlement_denied.message"
    assert payload["action_key"] == "errors.entitlement_denied.action"
    assert payload["correlation_id"] == "corr-9"
    assert "detail" not in payload


def test_operator_detail_never_reaches_a_business_user() -> None:
    business = error_payload("runtime_db_unavailable", operator_detail="dsn=postgresql://secret")
    assert "operator_detail" not in business

    operator = error_payload(
        "runtime_db_unavailable", operator_detail="dsn=postgresql://secret", operator=True
    )
    assert operator["operator_detail"] == "dsn=postgresql://secret"

    # Even on an operator surface, an informational code carries no detail.
    informational = error_payload("JOB_CANCELLED", operator_detail="stack", operator=True)
    assert "operator_detail" not in informational


def test_a_safe_message_override_is_allowed_and_keeps_the_keys() -> None:
    payload = error_payload("DATA_STALE", message="Last verified 12 minutes ago.", correlation_id="c1")

    assert payload["message"] == "Last verified 12 minutes ago."
    assert payload["message_key"] == "errors.DATA_STALE.message"
    assert payload["severity"] == "warning"
    assert payload["recoverability"] == "retry"


def test_the_infrastructure_taxonomy_bridges_onto_the_product_families() -> None:
    assert family_for_operational_category(OperationalErrorCategory.ENTITLEMENT) is ErrorFamily.ENTITLEMENT
    assert family_for_operational_category(OperationalErrorCategory.SOLVER) is ErrorFamily.CALCULATION
    assert family_for_operational_category(OperationalErrorCategory.DATABASE) is ErrorFamily.DEPENDENCY
    assert family_for_operational_category(OperationalErrorCategory.JOB) is ErrorFamily.JOB
    assert family_for_operational_category(OperationalErrorCategory.INTERNAL) is ErrorFamily.SYSTEM

    for category in OperationalErrorCategory:
        assert isinstance(family_for_operational_category(category), ErrorFamily)


def test_catalogue_grouping_is_complete_and_stable() -> None:
    grouped = catalogue_by_family()

    set(grouped) == set(ErrorFamily)
    flattened = [code for codes in grouped.values() for code in codes]
    assert sorted(flattened) == sorted(ERROR_CATALOGUE)
    assert len(flattened) == len(set(flattened)) == len(ERROR_CATALOGUE)
