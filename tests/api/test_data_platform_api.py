"""Unified Data Platform API tests (Architecture V2 Wave 4, SQLite-backed).

Pins the delivered behaviour of:

- ``GET /api/data-products`` - catalogue declaration, per-principal entitlement
  reporting (restricted is reported, never omitted and never zeroed) and the
  section 3 display rule (no API keys, secret values, scheduler internals or
  retry traces);
- ``POST/GET /api/analysis-snapshots`` - Analysis Snapshot v1 round trip;
- the route-cost recommendation citing the snapshot it was computed against.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FlowObservationRecord,
    FxObservationRecord,
    MarketObservationRecord,
    TsoTariffRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"

#: Operator-posture field names that must never reach a business-facing payload.
FORBIDDEN_KEYS = {
    "api_key",
    "key_hash",
    "bearer",
    "secret",
    "credential_state",
    "credential_status",
    "credential_last_tested_at_utc",
    "redacted_preview",
    "scheduler_enabled",
    "next_run_at_utc",
    "consecutive_failures",
    "circuit_state",
    "last_ingestion_message",
    "error_message",
    "retry_of_run_id",
    "adapter_version",
    "scheduler",
    "raw_payload",
}


@pytest.fixture()
def db_url(tmp_path, monkeypatch: pytest.MonkeyPatch) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'data-platform.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _seed_runtime_rows(database_url: str) -> None:
    """Seed canonical rows so version references are measurable, not empty."""

    now = datetime.now(UTC)
    with Session(create_engine(database_url, future=True)) as session:
        session.add(
            MarketObservationRecord(
                observation_id="mkt-nbp-da-1",
                market_venue="ICE OCM",
                product="NBP Day-Ahead",
                price=33.2,
                unit="EUR/MWh",
                currency="EUR",
                period_start_utc=now,
                period_end_utc=now + timedelta(hours=1),
                observed_at_utc=now,
                source_system="ICE_OCM_Sim",
                source_reference="test:sim",
                source_record_id="sim-1",
                freshness="live",
                quality_score=0.9,
                research_only=True,
                metadata_json={"hub": "NBP", "simulated": True},
            )
        )
        session.add(
            FlowObservationRecord(
                observation_id="flow-1",
                point_id="entsog-itp-1",
                point_name="BBL",
                direction="exit",
                kind="actual",
                flow_mcm_d=12.5,
                period_start_utc=now,
                period_end_utc=now + timedelta(hours=1),
                observed_at_utc=now,
                source_system="ENTSOG",
                source_reference="entsog-operationaldatas",
                source_record_id="op-1",
                freshness="live",
                research_only=True,
                metadata_json={},
            )
        )
        session.add(
            FxObservationRecord(
                observation_id="fx-eurgbp-1",
                pair="EURGBP",
                base_currency="EUR",
                quote_currency="GBP",
                rate=0.84,
                rate_type="reference",
                value_date=now.date().isoformat(),
                observed_at_utc=now,
                source_system="ECB",
                source_reference="ecb-eurofxref-daily",
                source_record_id="2026-01-02-GBP",
                freshness="live",
                research_only=True,
                metadata_json={},
            )
        )
        session.add(
            TsoTariffRecord(
                tariff_id="bbl-forward-annual-firm",
                document_id="bbl-company-tariffs-gas-year-2025-plus",
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                gas_year="2025+",
                point_id="bbl-forward",
                source_point_name="BBL Forward Flow NL to GB",
                direction="EXIT",
                capacity_product="ANNUAL",
                firmness="FIRM",
                tariff_value=1.0,
                currency="EUR",
                unit="EUR/MWh",
                effective_from=now,
                effective_to=None,
                tariff_status="FINAL",
                source_table="tariffs-gas-year-2025-and-beyond",
                source_page=3,
                source_refs=["https://bblcompany.com/tariffs/tariffs-gas-year-2025-and-beyond"],
                manual_review_required=True,
                created_at_utc=now,
            )
        )
        session.commit()


def _bearer(database_url: str, *, name: str, role: str, scopes: list[str]) -> str:
    with Session(create_engine(database_url, future=True)) as session:
        row = create_identity_principal(
            session,
            name=name,
            display_name=name.title(),
            role=role,
            data_scopes=scopes,
        )
        _key, bearer = create_identity_api_key(session, row.principal_id, display_name="dp")
        session.commit()
    return bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def _walk_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys |= _walk_keys(item)
    elif isinstance(value, list | tuple):
        for item in value:
            keys |= _walk_keys(item)
    return keys


# ---------------------------------------------------------------------------
# Data Product catalogue
# ---------------------------------------------------------------------------


def test_catalogue_lists_every_product_with_business_posture(db_url: str) -> None:
    _seed_runtime_rows(db_url)
    client = TestClient(create_app())

    response = client.get("/api/data-products")
    assert response.status_code == 200
    body = response.json()
    data = body["data"]
    assert data["catalogue_version"] == "data-products.v1"
    assert data["runtime_available"] is True

    products = {entry["product_id"]: entry for entry in data["products"]}
    assert "nbp-day-ahead-market-context" in products
    assert "weather-context" in products

    nbp = products["nbp-day-ahead-market-context"]
    assert nbp["time_basis"]["basis"] == "gas_day"
    assert nbp["time_basis"]["gas_day_calendar"] == "EU-CAM-UTC-2025"
    assert nbp["availability"]["state"] == "simulated_only"
    assert nbp["entitlement"]["status"] == "allowed"
    assert nbp["provenance"]["row_count"] == 1
    assert nbp["provenance"]["confidence"] == "LOW"
    assert "SIMULATED_SUBSTITUTE_ONLY" in nbp["provenance"]["quality_flags"]

    flow = products["european-physical-flow"]
    assert flow["availability"]["state"] == "available"
    assert flow["provenance"]["confidence"] == "HIGH"
    assert flow["provenance"]["freshness"]["status"] == "FRESH"

    weather = products["weather-context"]
    assert weather["availability"]["state"] == "declared_only"
    assert weather["provenance"]["freshness"]["status"] == "MISSING"
    assert weather["provenance"]["confidence"] == "UNKNOWN"
    assert "NO_SOURCE_IMPLEMENTATION" in weather["provenance"]["quality_flags"]


def test_catalogue_exposes_no_operator_internals(db_url: str) -> None:
    _seed_runtime_rows(db_url)
    client = TestClient(create_app())

    payload = client.get("/api/data-products").json()
    serialized = json.dumps(payload)
    assert "nexus_" not in serialized
    leaked = _walk_keys(payload) & FORBIDDEN_KEYS
    assert leaked == set(), f"operator internals leaked: {sorted(leaked)}"


def test_restricted_product_is_reported_not_omitted_or_zeroed(db_url: str) -> None:
    _seed_runtime_rows(db_url)
    analyst = _bearer(db_url, name="dp-analyst", role="ANALYST", scopes=["ENTSOG"])
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/data-products", headers=_headers(analyst))
    assert response.status_code == 200
    data = response.json()["data"]
    products = {entry["product_id"]: entry for entry in data["products"]}

    # The licensed market products are still listed, marked restricted, and carry
    # no provenance block at all - not an empty one and not a zero.
    nbp = products["nbp-day-ahead-market-context"]
    assert nbp["restricted"] is True
    assert nbp["entitlement"]["status"] == "restricted"
    assert nbp["entitlement"]["reason"] == "entitlement_restricted"
    assert nbp["entitlement"]["restricted_family_count"] == 4
    assert nbp["entitlement"]["granted_family_count"] == 0
    assert nbp["provenance"] is None

    summary = data["entitlement_summary"]
    assert summary["restricted_products"] >= 1
    assert summary["total_products"] == len(data["products"])

    # Public-baseline products are unaffected for the same principal.
    assert products["european-physical-flow"]["entitlement"]["status"] == "allowed"
    assert products["european-physical-flow"]["provenance"] is not None


def test_legacy_service_principal_keeps_the_previous_reach(db_url: str) -> None:
    _seed_runtime_rows(db_url)
    client = TestClient(create_app(Settings(api_profile="release")))

    data = client.get("/api/data-products", headers=_headers()).json()["data"]
    assert data["entitlement_summary"]["restricted_products"] == 0


def test_catalogue_without_a_runtime_database_is_honest(db_url: str, monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    client = TestClient(create_app())

    body = client.get("/api/data-products").json()
    assert body["data"]["runtime_available"] is False
    entry = body["data"]["products"][0]
    assert entry["provenance"]["freshness"]["status"] in {"MISSING", "NOT_EXPECTED"}
    assert "RUNTIME_DATABASE_NOT_CONFIGURED" in entry["provenance"]["quality_flags"]
    assert "Runtime DB is not configured" in " ".join(body["meta"]["warnings"])


# ---------------------------------------------------------------------------
# Analysis Snapshot v1
# ---------------------------------------------------------------------------


def test_snapshot_round_trip_records_versions_and_absences(db_url: str) -> None:
    _seed_runtime_rows(db_url)
    client = TestClient(create_app())

    created = client.post(
        "/api/analysis-snapshots",
        json={
            "as_of_utc": "2026-01-02T10:00:00+00:00",
            "active_context": {"workspace": "market", "hub": "NBP", "gas_day": "2026-01-02"},
            "manual_assumptions": {"storage_fill_source": "operator estimate"},
        },
    )
    assert created.status_code == 200
    payload = created.json()["data"]
    snapshot_id = payload["snapshot_id"]
    assert snapshot_id.startswith("asnap-")
    assert payload["schema_version"] == "analysis-snapshot.v1"
    assert payload["gas_day"] == "2026-01-02"
    assert payload["gas_day_calendar"] == "EU-CAM-UTC-2025"
    assert payload["content_hash"] and len(payload["content_hash"]) == 64

    states = {item["field"]: item for item in payload["field_availability"]}
    assert states["market_data_versions"]["state"] == "available"
    assert states["network_capacity_version"]["state"] == "unavailable"
    assert states["network_capacity_version"]["unavailable_reason"] == "NO_RUNTIME_ROWS"
    assert states["weather_demand_assumptions"]["state"] == "unavailable"
    assert (
        states["weather_demand_assumptions"]["unavailable_reason"]
        == "WEATHER_SOURCE_NOT_CONFIGURED"
    )
    assert states["manual_assumptions"]["state"] == "available"
    assert states["entitlement_context"]["state"] == "available"

    assert payload["market_data_versions"]["measured_row_count"] == 1
    assert payload["tariff_fx"]["measured_row_count"] == 2
    assert payload["manual_assumptions"] == {"storage_fill_source": "operator estimate"}
    assert payload["active_context"]["hub"] == "NBP"
    assert "WEATHER_DEMAND_ASSUMPTIONS_UNAVAILABLE" in payload["warnings"]

    fetched = client.get(f"/api/analysis-snapshots/{snapshot_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["content_hash"] == payload["content_hash"]

    listed = client.get("/api/analysis-snapshots")
    assert listed.status_code == 200
    assert [row["snapshot_id"] for row in listed.json()["data"]] == [snapshot_id]

    by_gas_day = client.get("/api/analysis-snapshots", params={"gas_day": "2025-01-01"})
    assert by_gas_day.json()["data"] == []


def test_snapshot_is_reproducible_from_its_own_payload(db_url: str) -> None:
    """The published content_hash can be recomputed by an independent reader."""

    from eurogas_nexus.domain.data_platform.snapshots import descriptor_content_hash

    _seed_runtime_rows(db_url)
    client = TestClient(create_app())
    payload = client.post("/api/analysis-snapshots", json={}).json()["data"]

    body = {key: value for key, value in payload.items() if key != "content_hash"}
    assert descriptor_content_hash(body) == payload["content_hash"]


def test_snapshot_records_the_entitlement_context_of_its_creator(db_url: str) -> None:
    _seed_runtime_rows(db_url)
    analyst = _bearer(db_url, name="dp-snapshot-analyst", role="ANALYST", scopes=["ENTSOG"])
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post("/api/analysis-snapshots", json={}, headers=_headers(analyst))
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["created_by"] == "dp-snapshot-analyst"
    context = payload["entitlement_context"]
    assert context["role"] == "ANALYST"
    assert context["restricted_product_count"] >= 1
    assert "ENTSOG" in context["entitled_source_families"]
    assert "CREATOR_ENTITLEMENT_LIMITED" in payload["warnings"]
    # Restricted family names are counted, never listed.
    assert not any(
        family in json.dumps(context) for family in ("EEX", "Trayport", "ICIS", "Kpler")
    )


def test_snapshot_requires_a_viewer_or_higher_and_a_database(db_url: str, monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    client = TestClient(create_app())

    response = client.post("/api/analysis-snapshots", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"


def test_snapshot_refuses_context_keys_the_backend_cannot_express(db_url: str) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/analysis-snapshots",
        json={"active_context": {"decision_case": "case-1"}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "active_context_key_unsupported"
    assert detail["unsupported_keys"] == ["decision_case"]


def test_unknown_snapshot_reference_is_a_404(db_url: str) -> None:
    client = TestClient(create_app())

    response = client.get("/api/analysis-snapshots/asnap-does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "analysis_snapshot_not_found"


def test_snapshot_write_is_governed_in_the_release_profile(db_url: str) -> None:
    viewer = _bearer(db_url, name="dp-viewer", role="VIEWER", scopes=["ENTSOG"])
    client = TestClient(create_app(Settings(api_profile="release")))

    denied = client.post("/api/analysis-snapshots", json={}, headers=_headers(viewer))
    assert denied.status_code == 403
    assert denied.json()["detail"]["error"] == "identity_role_forbidden"

    # Reading the descriptor stays at the READ floor for the same identity.
    assert client.get("/api/analysis-snapshots", headers=_headers(viewer)).status_code == 200


# ---------------------------------------------------------------------------
# Reproducibility reference on a produced result
# ---------------------------------------------------------------------------


def _recommendation_body(**extra: object) -> dict:
    return {
        "request_id": "wave4-snapshot-citation",
        "source_point_id": "TTF",
        "target_point_id": "NBP",
        "required_quantity_mwh_per_day": 100,
        "gas_year": "2025+",
        "capacity_product": "ANNUAL",
        "firmness": "FIRM",
        "candidates": [
            {
                "route_id": "local-sale",
                "route_name": "TTF local sale",
                "destination_market": "TTF",
                "sale_price": 34,
                "price_currency": "EUR",
                "price_unit": "EUR/MWh",
                "capacity_status": "NOT_REQUIRED",
            }
        ],
        **extra,
    }


def test_route_recommendation_echoes_the_snapshot_it_was_computed_against(
    db_url: str,
) -> None:
    _seed_runtime_rows(db_url)
    client = TestClient(create_app())
    snapshot_id = client.post("/api/analysis-snapshots", json={}).json()["data"]["snapshot_id"]

    response = client.post(
        "/api/route-cost/recommend",
        json=_recommendation_body(analysis_snapshot_id=snapshot_id),
    )
    assert response.status_code == 200
    assert response.json()["data"]["analysis_snapshot_id"] == snapshot_id


def test_route_recommendation_still_works_without_a_snapshot_reference(db_url: str) -> None:
    client = TestClient(create_app())

    response = client.post("/api/route-cost/recommend", json=_recommendation_body())
    assert response.status_code == 200
    assert response.json()["data"]["analysis_snapshot_id"] is None


def test_route_recommendation_refuses_an_unknown_snapshot_reference(db_url: str) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/recommend",
        json=_recommendation_body(analysis_snapshot_id="asnap-missing"),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "analysis_snapshot_not_found"
