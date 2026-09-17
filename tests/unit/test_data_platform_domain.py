"""Unified Data Platform domain unit tests (Architecture V2 Wave 4).

Pure domain behaviour: per-principal entitlement evaluation is fail-closed and
uses the repository's single derived-result policy; the descriptor hash is a
stable reproducibility reference; and the descriptor payload exposes declared
availability instead of a missing key.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.domain.data_platform.products import (
    DataProduct,
    DataProductAvailability,
    ServedSurface,
    SurfaceKind,
    TimeBasis,
    data_products,
    evaluate_product_entitlement,
    product_by_id,
)
from eurogas_nexus.domain.data_platform.snapshots import (
    AvailabilityState,
    DescriptorFieldState,
    SnapshotDescriptor,
    descriptor_content_hash,
    descriptor_payload,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal


def _principal(*, role: str = "ANALYST", scopes: tuple[str, ...] = ()) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p-1",
        name="unit-principal",
        principal_type="USER",
        role=role,
        status="ACTIVE",
        data_scopes=scopes,
        roles=(role,),
    )


def _product(**overrides: object) -> DataProduct:
    base: dict[str, object] = {
        "product_id": "unit-product",
        "business_name": "Unit Product",
        "description": "unit",
        "domain": "market",
        "source_families": ("EEX",),
        "simulated_families": (),
        "entitlement_families": ("EEX", "Trayport"),
        "time_basis": TimeBasis.GAS_DAY,
        "gas_day_calendar": "EU-CAM-UTC-2025",
        "freshness_expectation_minutes": 60,
        "availability": DataProductAvailability.AVAILABLE,
        "availability_note": "unit",
        "served_by": (ServedSurface(SurfaceKind.ENDPOINT, "/api/market/observations", "unit"),),
        "provenance_tables": ("market_observations",),
    }
    base.update(overrides)
    return DataProduct(**base)  # type: ignore[arg-type]


def test_public_baseline_products_need_no_commercial_grant() -> None:
    product = _product(entitlement_families=())
    verdict = evaluate_product_entitlement(_principal(scopes=()), product)
    assert verdict.allowed is True
    assert verdict.restricted_family_count == 0
    assert verdict.reason == "no_commercial_family_required"


def test_one_missing_family_restricts_the_whole_product() -> None:
    verdict = evaluate_product_entitlement(_principal(scopes=("EEX",)), _product())
    assert verdict.allowed is False
    assert verdict.required_family_count == 2
    assert verdict.granted_family_count == 1
    assert verdict.restricted_family_count == 1
    assert verdict.reason == "entitlement_restricted"


def test_a_wildcard_scope_grants_every_declared_family() -> None:
    verdict = evaluate_product_entitlement(_principal(scopes=("*",)), _product())
    assert verdict.allowed is True
    assert verdict.granted_family_count == 2


def test_a_family_without_an_explicit_grant_fails_closed() -> None:
    """Unknown families are refused unless the principal holds an explicit scope.

    This is the documented ``principal_allows_source_family`` contract: the
    baseline set plus an explicit ``*``/family grant, and nothing else. An
    unrelated scope must never be read as an entitlement.
    """

    product = _product(entitlement_families=("TotallyUnknownVendor",))
    assert evaluate_product_entitlement(_principal(scopes=()), product).allowed is False
    assert (
        evaluate_product_entitlement(_principal(scopes=("ENTSOG",)), product).allowed is False
    )
    assert (
        evaluate_product_entitlement(
            _principal(scopes=("TotallyUnknownVendor",)), product
        ).allowed
        is True
    )


def test_legacy_service_principal_keeps_the_single_trust_domain_view() -> None:
    legacy = AuthenticatedPrincipal(
        principal_id="service:public-api",
        name="public-api",
        principal_type="SERVICE",
        role="OPERATOR",
        status="ACTIVE",
        data_scopes=("*",),
        roles=("OPERATOR",),
        auth_method="legacy_public_token",
    )
    for product in data_products():
        assert evaluate_product_entitlement(legacy, product).allowed is True


def test_product_lookup_is_exact() -> None:
    assert product_by_id("no-such-product") is None
    assert product_by_id("european-physical-flow") is not None


def test_catalogue_declares_at_least_one_honest_gap() -> None:
    states = {product.availability for product in data_products()}
    assert DataProductAvailability.DECLARED_ONLY in states
    assert DataProductAvailability.NOT_IMPLEMENTED in states


def _descriptor(**overrides: object) -> SnapshotDescriptor:
    base: dict[str, object] = {
        "snapshot_id": "asnap-unit",
        "schema_version": "analysis-snapshot.v1",
        "as_of_utc": datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
        "gas_day": "2026-01-02",
        "gas_day_calendar": "EU-CAM-UTC-2025",
        "time_basis": "gas_day",
        "created_at_utc": datetime(2026, 1, 2, 10, 1, tzinfo=UTC),
        "created_by": "unit",
        "field_states": (
            DescriptorFieldState(
                field="weather_demand_assumptions",
                state=AvailabilityState.UNAVAILABLE,
                detail="no producer",
                unavailable_reason="WEATHER_SOURCE_NOT_CONFIGURED",
            ),
        ),
    }
    base.update(overrides)
    return SnapshotDescriptor(**base)  # type: ignore[arg-type]


def test_descriptor_hash_is_stable_and_content_sensitive() -> None:
    first = _descriptor()
    again = _descriptor()
    assert first.content_hash == again.content_hash

    changed = _descriptor(manual_assumptions={"a": 1})
    assert changed.content_hash != first.content_hash


def test_descriptor_hash_ignores_its_own_carried_value() -> None:
    payload = descriptor_payload(_descriptor())
    assert descriptor_content_hash(payload) == descriptor_content_hash(
        {**payload, "content_hash": "deadbeef"}
    )


def test_descriptor_payload_declares_absence_instead_of_omitting_keys() -> None:
    payload = descriptor_payload(_descriptor())
    for field in (
        "market_data_versions",
        "network_capacity_version",
        "portfolio_version",
        "contract_resource_versions",
        "tariff_fx",
        "weather_demand_assumptions",
        "manual_assumptions",
        "model_calculation_versions",
        "entitlement_context",
    ):
        assert field in payload, field
        assert payload[field] == {}
    assert payload["field_availability"][0]["unavailable_reason"] == (
        "WEATHER_SOURCE_NOT_CONFIGURED"
    )
    descriptor = _descriptor()
    assert descriptor.state_for("weather_demand_assumptions") is not None
    assert descriptor.state_for("not_a_field") is None
