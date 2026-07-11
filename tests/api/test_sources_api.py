"""Source registry and ingestion API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_list_sources_returns_200(client: TestClient) -> None:
    response = client.get("/api/sources")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 13


def test_list_sources_includes_all_families(client: TestClient) -> None:
    response = client.get("/api/sources")
    systems = {s["source_system"] for s in response.json()["data"]}
    assert {
        "Argus",
        "DEEPSEEK",
        "ECB",
        "EEX",
        "ENTSOG",
        "GIE",
        "ICE_OCM",
        "ICIS",
        "Kpler",
        "BBL",
        "IUK",
        "GTS",
        "NaTran",
        "GermanTSO",
        "FluxysBelgium",
        "CNMCEnagas",
        "NationalGasNTS",
        "Platts",
        "Trayport",
        "Weather",
    }.issubset(systems)


def test_sources_are_grouped_for_source_center(client: TestClient) -> None:
    response = client.get("/api/sources")
    data = response.json()["data"]
    by_category = {}
    for source in data:
        by_category.setdefault(source["category"], set()).add(source["source_system"])

    assert {"Platts", "ICIS", "EEX", "ICE_OCM", "Trayport", "Kpler", "Argus"}.issubset(
        by_category["price"]
    )
    assert by_category["fx"] == {"ECB"}
    assert {"ENTSOG", "GIE"}.issubset(by_category["infrastructure"])
    assert {
        "NationalGasNTS",
        "BBL",
        "IUK",
        "GTS",
        "NaTran",
        "GermanTSO",
        "FluxysBelgium",
        "CNMCEnagas",
    }.issubset(by_category["tariff"])
    assert "Weather" in by_category["weather"]
    assert "DEEPSEEK" in by_category["ai"]


def test_sources_include_simulated_market_price_feeds_when_runtime_rows_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {
            "EEX_Sim": 18,
            "ICE_OCM_Sim": 2,
            "Trayport_Sim": 12,
            "ICIS_Sim": 6,
        },
    )
    monkeypatch.setattr(
        sources_routes,
        "_latest_ingestion_status_by_source",
        lambda: {
            "src-eex-sim": {
                "latest": {
                    "status": "succeeded",
                    "started_at_utc": "2026-07-01T10:15:00+00:00",
                    "finished_at_utc": "2026-07-01T10:15:00+00:00",
                    "source_reference": "records=18; source=EEX_Sim",
                },
                "last_success_at_utc": "2026-07-01T10:15:00+00:00",
            }
        },
    )
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    sources = {item["source_system"]: item for item in response.json()["data"]}
    assert sources["EEX_Sim"]["category"] == "price"
    assert sources["EEX_Sim"]["credential_requirements"] == []
    assert sources["EEX_Sim"]["live_record_count"] == 18
    assert sources["EEX_Sim"]["connectivity_status"] == "active"
    assert "live_records_available" in sources["EEX_Sim"]["diagnostics"]
    assert sources["ICE_OCM_Sim"]["live_record_count"] == 2
    assert sources["Trayport_Sim"]["live_record_count"] == 12
    assert sources["ICIS_Sim"]["live_record_count"] == 6


def test_licensed_price_sources_show_active_preview_substitute_when_subscription_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {
            "EEX_Sim": 18,
            "ICE_OCM_Sim": 2,
            "Trayport_Sim": 12,
            "ICIS_Sim": 6,
        },
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    sources = {item["source_system"]: item for item in response.json()["data"]}
    assert sources["EEX"]["connectivity_status"] == "needs_credential"
    assert sources["EEX"]["preview_substitute_source_system"] == "EEX_Sim"
    assert sources["EEX"]["preview_substitute_status"] == "active"
    assert sources["EEX"]["preview_substitute_record_count"] == 18
    assert sources["EEX"]["operational_status"] == "active_simulated"
    assert sources["EEX"]["workflow_ready"] is True
    assert sources["EEX"]["effective_source_system"] == "EEX_Sim"
    assert sources["EEX"]["effective_record_count"] == 18
    assert "preview_substitute_active" in sources["EEX"]["diagnostics"]
    assert sources["ICE_OCM"]["preview_substitute_source_system"] == "ICE_OCM_Sim"
    assert sources["ICE_OCM"]["preview_substitute_status"] == "active"
    assert sources["Trayport"]["preview_substitute_source_system"] == "Trayport_Sim"
    assert sources["Trayport"]["operational_status"] == "active_simulated"
    assert sources["Trayport"]["workflow_ready"] is True
    assert sources["ICIS"]["preview_substitute_source_system"] == "ICIS_Sim"
    assert sources["ICIS"]["preview_substitute_status"] == "active"
    assert sources["Platts"]["preview_substitute_source_system"] is None


def test_sources_response_meta_includes_category_posture_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {
            "EEX_Sim": 18,
            "ICE_OCM_Sim": 2,
            "ICIS_Sim": 6,
            "ENTSOG": 140,
            "GIE": 12,
            "NationalGasNTS": 1315,
        },
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})

    response = TestClient(create_app()).get("/api/sources")

    assert response.status_code == 200
    summary = response.json()["meta"]["source_posture_summary"]
    assert summary["totals"]["registered_sources"] >= 20
    assert summary["totals"]["active_sources"] >= 5
    assert summary["totals"]["workflow_ready_sources"] >= 8
    assert summary["totals"]["preview_substitutes_active"] == 3
    assert summary["totals"]["runtime_records"] == 1493

    categories = {item["category"]: item for item in summary["categories"]}
    assert categories["price"]["preview_substitutes_active"] == 3
    assert categories["price"]["workflow_ready_sources"] >= 6
    assert categories["price"]["missing_credentials"] >= 5
    assert categories["price"]["next_action"] == "configure_live_credentials"
    assert categories["infrastructure"]["active_sources"] == 1
    assert categories["infrastructure"]["missing_credentials"] == 1
    assert categories["infrastructure"]["runtime_records"] == 152
    assert categories["tariff"]["runtime_records"] == 1315


def test_source_records_include_diagnostics_and_credential_state(client: TestClient) -> None:
    response = client.get("/api/sources")
    source = next(item for item in response.json()["data"] if item["source_system"] == "ICIS")

    assert source["category"] == "price"
    assert source["category_label"] == "Prices"
    assert source["credential_state"] == "missing"
    assert source["connectivity_status"] == "needs_credential"
    assert source["operational_status"] == "needs_credential"
    assert source["workflow_ready"] is False
    assert source["effective_source_system"] == "ICIS"
    assert source["status"] == source["connectivity_status"]
    assert source["last_success_at_utc"] is None
    assert source["last_failure_at_utc"] is None
    assert source["diagnostics"] == ["credential_missing"]


def test_get_source_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/sources/src-entsog")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "ENTSOG"
    assert response.json()["data"]["credential_requirements"] == []


def test_gie_source_declares_operator_key_requirement(client: TestClient) -> None:
    response = client.get("/api/sources/src-gie")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "GIE"
    assert response.json()["data"]["credential_requirements"] == ["api_key"]
    assert response.json()["data"]["category"] == "infrastructure"


def test_national_gas_nts_source_uses_runtime_tariff_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {"NationalGasNTS": 1315},
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})

    response = TestClient(create_app()).get("/api/sources")
    assert response.status_code == 200

    source = next(
        item for item in response.json()["data"] if item["source_system"] == "NationalGasNTS"
    )
    assert source["live_record_count"] == 1315
    assert source["connectivity_status"] == "active"
    assert source["diagnostics"] == ["live_records_available"]


def test_interconnector_sources_use_runtime_tariff_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from eurogas_nexus.api.routes.public import sources as sources_routes

    monkeypatch.setattr(sources_routes, "_db_is_configured", lambda: True)
    monkeypatch.setattr(
        sources_routes,
        "_runtime_source_counts",
        lambda: {"BBL": 2, "IUK": 4},
    )
    monkeypatch.setattr(sources_routes, "_latest_ingestion_status_by_source", lambda: {})
    monkeypatch.setattr(sources_routes, "_credential_status_by_provider", lambda: {})

    response = TestClient(create_app()).get("/api/sources")
    assert response.status_code == 200

    sources = {item["source_system"]: item for item in response.json()["data"]}
    assert sources["BBL"]["connectivity_status"] == "active"
    assert sources["BBL"]["live_record_count"] == 2
    assert sources["IUK"]["connectivity_status"] == "active"
    assert sources["IUK"]["live_record_count"] == 4


def test_get_source_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/sources/nonexistent")
    assert response.status_code == 404


def test_list_ingestion_runs_returns_200(client: TestClient) -> None:
    response = client.get("/api/ingestion-runs")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["source-registry"]


def test_list_ingestion_runs_filter_by_source(client: TestClient) -> None:
    response = client.get("/api/ingestion-runs?source_id=src-ecb")
    assert response.status_code == 200

    runs = response.json()["data"]
    assert all(r["source_id"] == "src-ecb" for r in runs)


def test_ingestion_run_notes_parse_records_key_value() -> None:
    from eurogas_nexus.api.routes.public.sources import _records_from_notes

    assert _records_from_notes("records=18; source=EEX_Sim") == 18


def test_response_metadata(client: TestClient) -> None:
    response = client.get("/api/sources")
    meta = response.json()["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
