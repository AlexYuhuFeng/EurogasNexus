"""P0-2: external LLM provider gate and entitlement fail-closed tests."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.analysis import (
    _export_blocker,
    _filtered_llm_payload,
    _maybe_invoke_provider,
    _snapshot_entitlement_blocker,
)
from eurogas_nexus.core.config import Settings, get_settings
from eurogas_nexus.domain.analysis import AnalysisRequest, AnalysisSnapshot


def test_llm_provider_forced_off_in_release_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    # Explicit override must NOT re-enable the provider in release.
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "true")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_external_provider_enabled is False
    finally:
        get_settings.cache_clear()


def test_llm_provider_forced_off_in_trial_environment(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "trial")
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "true")
    get_settings.cache_clear()
    try:
        assert get_settings().llm_external_provider_enabled is False
    finally:
        get_settings.cache_clear()


def test_llm_provider_on_in_development_by_default(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.delenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().llm_external_provider_enabled is True
    finally:
        get_settings.cache_clear()


def test_llm_provider_can_be_disabled_in_development(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.setenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", "false")
    get_settings.cache_clear()
    try:
        assert get_settings().llm_external_provider_enabled is False
    finally:
        get_settings.cache_clear()


def test_provider_invocation_blocked_by_profile(monkeypatch) -> None:
    from eurogas_nexus.core.config import Settings as CoreSettings

    monkeypatch.setattr(
        "eurogas_nexus.core.config.get_settings",
        lambda: CoreSettings(llm_external_provider_enabled=False),
    )
    request = AnalysisRequest(
        question="Summarize TTF",
        task="DB_INQUIRY",
        invoke_provider=True,
    )
    snapshot = AnalysisSnapshot(
        snapshot_id="s1",
        source="runtime-db-not-configured",
        created_at_utc=datetime.now(UTC),
        ontology={},
    )
    provider_text, status = _maybe_invoke_provider(request, snapshot)
    assert provider_text is None
    assert status == "LLM_PROVIDER_DISABLED_IN_PROFILE"


def test_snapshot_entitlement_blocks_unlicensed_source() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s2",
        source="runtime-postgresql",
        created_at_utc=datetime.now(UTC),
        ontology={},
        market_observations=[
            {
                "market_venue": "ICIS Heren",
                "product": "TTF day-ahead",
                "source_system": "ICIS_Sim",
                "source_reference": "sim:ICIS:TTF:day-ahead:20260701",
            }
        ],
    )
    assert _snapshot_entitlement_blocker(snapshot) == "ICIS_Sim"


def test_snapshot_entitlement_allows_known_families() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s3",
        source="runtime-postgresql",
        created_at_utc=datetime.now(UTC),
        ontology={},
        market_observations=[
            {
                "market_venue": "EEX",
                "product": "TTF day-ahead",
                "source_system": "EEX_Sim",
                "source_reference": "sim:EEX:TTF:day-ahead:20260701",
            },
            {
                "market_venue": "ENTSOG",
                "product": "flow",
                "source_system": "ENTSOG",
                "source_reference": "entsog:flow:20260701",
            },
        ],
    )
    assert _snapshot_entitlement_blocker(snapshot) is None


def test_snapshot_entitlement_passes_when_no_sources() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s4",
        source="runtime-db-not-configured",
        created_at_utc=datetime.now(UTC),
        ontology={},
    )
    assert _snapshot_entitlement_blocker(snapshot) is None


def test_analysis_api_reports_provider_disabled_in_release(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    monkeypatch.delenv("EUROGAS_NEXUS_API_PROFILE", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(Settings(environment="release")))
        response = client.post(
            "/api/analysis/query",
            json={
                "question": "Summarize TTF context",
                "task": "DB_INQUIRY",
                "invoke_provider": True,
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["provider_status"] == "LLM_PROVIDER_DISABLED_IN_PROFILE"
    finally:
        get_settings.cache_clear()


def test_llm_payload_filters_contract_prices_by_default() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s5",
        source="runtime-postgresql",
        created_at_utc=datetime.now(UTC),
        ontology={},
        portfolio_context=[
            {
                "contract_id": "c1",
                "contract_name": "TTF supply",
                "resource_type": "PIPELINE_IMPORT",
                "delivery_point_name": "TTF",
                "delivery_quantity_mwh_per_day": 10_000,
                "contract_price_gbp_mwh": 25.0,
                "tolerance_risk_allowance_gbp_mwh": 0.1,
            }
        ],
    )

    payload = _filtered_llm_payload(snapshot, include_contract_prices=False)

    row = payload["portfolio_context"][0]
    assert "contract_price_gbp_mwh" not in row
    assert "tolerance_risk_allowance_gbp_mwh" not in row
    assert row["contract_id"] == "c1"
    assert row["delivery_quantity_mwh_per_day"] == 10_000


def test_llm_payload_keeps_contract_prices_on_opt_in() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s6",
        source="runtime-postgresql",
        created_at_utc=datetime.now(UTC),
        ontology={},
        portfolio_context=[
            {
                "contract_id": "c1",
                "contract_name": "TTF supply",
                "resource_type": "PIPELINE_IMPORT",
                "delivery_point_name": "TTF",
                "delivery_quantity_mwh_per_day": 10_000,
                "contract_price_gbp_mwh": 25.0,
            }
        ],
    )

    payload = _filtered_llm_payload(snapshot, include_contract_prices=True)

    assert payload["portfolio_context"][0]["contract_price_gbp_mwh"] == 25.0


def test_export_blocker_denies_unknown_scope_sources() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s7",
        source="runtime-postgresql",
        created_at_utc=datetime.now(UTC),
        ontology={},
        market_observations=[
            {
                "market_venue": "ICIS Heren",
                "product": "TTF day-ahead",
                "source_system": "ICIS_Sim",
                "source_reference": "sim:ICIS:TTF:day-ahead:20260701",
            }
        ],
    )
    assert _export_blocker(snapshot) == "ICIS_Sim"


def test_export_blocker_allows_known_families() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s8",
        source="runtime-postgresql",
        created_at_utc=datetime.now(UTC),
        ontology={},
        market_observations=[
            {
                "market_venue": "EEX",
                "product": "TTF day-ahead",
                "source_system": "EEX_Sim",
                "source_reference": "sim:EEX:TTF:day-ahead:20260701",
            }
        ],
    )
    assert _export_blocker(snapshot) is None

def test_export_blocker_passes_empty_snapshot() -> None:
    snapshot = AnalysisSnapshot(
        snapshot_id="s9",
        source="runtime-db-not-configured",
        created_at_utc=datetime.now(UTC),
        ontology={},
    )
    assert _export_blocker(snapshot) is None
