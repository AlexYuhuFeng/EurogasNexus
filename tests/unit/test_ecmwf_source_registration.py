"""RFC 0003 registration checks for the public ECMWF Open Data source."""

from eurogas_nexus.api.routes.public.sources import SOURCE_ID_BY_NAME
from eurogas_nexus.domain.ingestion.source_registry import registered_sources

ECMWF_SOURCE_ID = "src-ecmwf-open-data"
ECMWF_SOURCE_SYSTEM = "ECMWF_OPEN_DATA"


def _source_for_system(source_system: str) -> dict:
    matches = [
        source
        for source in registered_sources()
        if source["source_system"] == source_system
    ]
    assert len(matches) == 1, f"expected one {source_system} source, got {len(matches)}"
    return matches[0]


def test_ecmwf_open_data_is_distinct_registered_public_source() -> None:
    sources = registered_sources()
    assert len(sources) == 27
    assert len({source["source_id"] for source in sources}) == len(sources)
    assert len({source["source_system"] for source in sources}) == len(sources)

    source = _source_for_system(ECMWF_SOURCE_SYSTEM)

    assert source["source_id"] == ECMWF_SOURCE_ID
    assert source["category"] == "weather"
    assert source["datasets"] == ["ifs_0p25_oper_2t_forecasts"]
    assert source["freshness_expectation_minutes"] == 720
    assert source["entitlement_scope"] == "public"
    assert source["credential_requirements"] == []
    assert source["credential_provider_id"] is None
    assert source["credential_state"] == "not_required"
    assert source["export_restrictions"] == []
    assert "ECMWF" in source["description"]
    assert "public" in source["description"]
    assert "CC BY 4.0" in source["description"]
    assert "attribution" in source["description"]


def test_ecmwf_open_data_registration_does_not_activate_the_source() -> None:
    source = _source_for_system(ECMWF_SOURCE_SYSTEM)

    assert source["status"] == "registered"
    assert source["connectivity_status"] == "registered"
    assert source["operational_status"] == "registered"
    assert source["workflow_ready"] is False
    assert source["certification_stage"] == "unverified"
    assert source["certification_allows_live"] is False
    assert source["last_success_at_utc"] is None


def test_ecmwf_open_data_has_exact_source_alias_mapping() -> None:
    assert SOURCE_ID_BY_NAME["ECMWF_OPEN_DATA"] == ECMWF_SOURCE_ID


def test_existing_licensed_weather_source_is_unchanged() -> None:
    source = _source_for_system("Weather")

    assert source["source_id"] == "src-weather"
    assert source["category"] == "weather"
    assert source["datasets"] == ["temperature", "hdd", "cdd", "forecast"]
    assert source["entitlement_scope"] == "licensed"
    assert source["credential_requirements"] == ["api_key"]
    assert source["credential_provider_id"] == "Weather"
    assert source["export_restrictions"] == ["license-controlled"]
    assert source["freshness_expectation_minutes"] == 180
