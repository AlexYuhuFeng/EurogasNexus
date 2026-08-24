"""Row-level entitlement scope annotation tests (Gate 1)."""

from eurogas_nexus.governance.entitlement import (
    EntitlementScope,
    entitlement_scope_for_source,
)


def test_known_family_is_internal_research() -> None:
    assert (
        entitlement_scope_for_source("ENTSOG") == EntitlementScope.INTERNAL_RESEARCH.value
    )
    assert (
        entitlement_scope_for_source("ECB") == EntitlementScope.INTERNAL_RESEARCH.value
    )
    assert (
        entitlement_scope_for_source("operator-input")
        == EntitlementScope.INTERNAL_RESEARCH.value
    )


def test_simulated_sources_use_their_licensed_family() -> None:
    assert (
        entitlement_scope_for_source("EEX_Sim") == EntitlementScope.INTERNAL_RESEARCH.value
    )
    assert (
        entitlement_scope_for_source("ICE_OCM_Sim")
        == EntitlementScope.INTERNAL_RESEARCH.value
    )


def test_unknown_family_fails_closed() -> None:
    assert entitlement_scope_for_source("ICIS_Sim") == EntitlementScope.UNKNOWN.value
    assert entitlement_scope_for_source("SomeVendor") == EntitlementScope.UNKNOWN.value
    assert entitlement_scope_for_source("") == EntitlementScope.UNKNOWN.value


def test_market_rows_carry_entitlement_scope() -> None:
    from types import SimpleNamespace

    from eurogas_nexus.api.routes.public.market import _market_row

    row = _market_row(
        SimpleNamespace(
            observation_id="o1",
            market_venue="EEX",
            product="TTF day-ahead",
            price=31.0,
            unit="EUR/MWh",
            currency="EUR",
            period_start_utc=__import__("datetime").datetime(2026, 1, 1),
            period_end_utc=__import__("datetime").datetime(2026, 1, 2),
            observed_at_utc=__import__("datetime").datetime(2026, 1, 1),
            source_system="EEX_Sim",
            source_reference="sim:EEX",
            source_record_id="r1",
            freshness="live",
            quality_score=0.9,
            research_only=False,
            metadata_json={},
        )
    )
    assert row["entitlement_scope"] == EntitlementScope.INTERNAL_RESEARCH.value
