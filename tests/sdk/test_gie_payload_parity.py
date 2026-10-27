"""Regression: real GIE-shaped API payloads must reach the typed SDK intact.

The test drives the actual FastAPI routes with synthetic AGSI/ALSI rows, keeps
the exact JSON the TestClient receives, and then replays that JSON through the
SDK's public HTTP boundary with ``httpx.MockTransport``. The SDK fixtures are
therefore API responses, not hand-written dictionaries shaped like the models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from eurogas_nexus_sdk.lng import fetch_lng_observations, fetch_lng_terminals
from eurogas_nexus_sdk.storage import fetch_storage_observations, fetch_storage_sites
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import lng as lng_routes
from eurogas_nexus.api.routes.public import storage as storage_routes
from eurogas_nexus.db.models import LngObservationRecord, StorageObservationRecord

BASE_URL = "https://nexus.example"
TOKEN = "test-public-api-token"
OBSERVED_AT = "2026-10-27T06:00:00+00:00"
PERIOD_START = "2026-10-26T05:00:00+00:00"
PERIOD_END = "2026-10-27T05:00:00+00:00"


def _storage_record(
    *,
    observation_id: str,
    facility_id: str,
    facility_name: str,
    country: str,
    inventory_twh: float | None,
    working_capacity_twh: float | None,
    fill_pct: float | None,
    injection_twh_d: float | None,
    withdrawal_twh_d: float | None,
) -> StorageObservationRecord:
    return StorageObservationRecord(
        observation_id=observation_id,
        source_dataset="AGSI",
        facility_id=facility_id,
        facility_name=facility_name,
        country=country,
        inventory_twh=inventory_twh,
        working_capacity_twh=working_capacity_twh,
        fill_pct=fill_pct,
        injection_twh_d=injection_twh_d,
        withdrawal_twh_d=withdrawal_twh_d,
        period_start_utc=datetime(2026, 10, 26, 5, tzinfo=UTC),
        period_end_utc=datetime(2026, 10, 27, 5, tzinfo=UTC),
        observed_at_utc=datetime(2026, 10, 27, 6, tzinfo=UTC),
        source_system="GIE",
        source_reference="gie-agsi-api",
        source_record_id=f"{facility_id}-2026-10-26",
        freshness="live",
        research_only=True,
    )


def _lng_record(
    *,
    observation_id: str,
    terminal_id: str,
    terminal_name: str,
    country: str,
    inventory_twh: float | None,
    send_out_twh_d: float | None,
    dtmi_twh: float | None,
) -> LngObservationRecord:
    return LngObservationRecord(
        observation_id=observation_id,
        source_dataset="ALSI",
        terminal_id=terminal_id,
        terminal_name=terminal_name,
        country=country,
        inventory_twh=inventory_twh,
        send_out_twh_d=send_out_twh_d,
        dtmi_twh=dtmi_twh,
        period_start_utc=datetime(2026, 10, 26, 5, tzinfo=UTC),
        period_end_utc=datetime(2026, 10, 27, 5, tzinfo=UTC),
        observed_at_utc=datetime(2026, 10, 27, 6, tzinfo=UTC),
        source_system="GIE",
        source_reference="gie-alsi-api",
        source_record_id=f"{terminal_id}-2026-10-26",
        freshness="live",
        research_only=True,
    )


@pytest.fixture()
def gie_api_payloads(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    """Return the exact JSON four actual GIE read routes emit for synthetic rows."""

    storage_rows = [
        _storage_record(
            observation_id="gie-agsi-NL-AGS1-2026-10-26",
            facility_id="NL-AGS1",
            facility_name="Synthetic AGSI North",
            country="NL",
            inventory_twh=1.5,
            working_capacity_twh=3.0,
            fill_pct=50.0,
            injection_twh_d=0.02,
            withdrawal_twh_d=0.01,
        ),
        _storage_record(
            observation_id="gie-agsi-DE-AGS2-2026-10-26",
            facility_id="DE-AGS2",
            facility_name="Synthetic AGSI South",
            country="DE",
            inventory_twh=None,
            working_capacity_twh=None,
            fill_pct=None,
            injection_twh_d=None,
            withdrawal_twh_d=None,
        ),
    ]
    lng_rows = [
        _lng_record(
            observation_id="gie-alsi-NL-ALS1-2026-10-26",
            terminal_id="NL-ALS1",
            terminal_name="Synthetic ALSI Terminal",
            country="NL",
            inventory_twh=0.75,
            send_out_twh_d=0.03,
            dtmi_twh=0.02,
        ),
        _lng_record(
            observation_id="gie-alsi-BE-ALS2-2026-10-26",
            terminal_id="BE-ALS2",
            terminal_name="Synthetic ALSI Terminal Two",
            country="BE",
            inventory_twh=None,
            send_out_twh_d=None,
            dtmi_twh=None,
        ),
    ]
    monkeypatch.setattr(
        storage_routes,
        "_db_storage_observations",
        lambda: [storage_routes._storage_row(row) for row in storage_rows],
    )
    monkeypatch.setattr(
        lng_routes,
        "_db_lng_observations",
        lambda: [lng_routes._lng_row(row) for row in lng_rows],
    )
    # tests/sdk/conftest.py clears ambient tokens. Configure the shared
    # deployment token explicitly so both the TestClient and the SDK calls
    # below authenticate with a real credential.
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", TOKEN)
    client = TestClient(create_app(), headers={"X-Eurogas-Api-Key": TOKEN})
    payloads: dict[str, dict[str, Any]] = {}
    for path in (
        "/api/storage/sites",
        "/api/storage/observations",
        "/api/lng/terminals",
        "/api/lng/observations",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        payloads[path] = response.json()

    # Confirm the captured body is the current API contract, not a model-shaped
    # fixture. Missing geo/mcm/observation_type keys are the point of the change.
    storage_site = payloads["/api/storage/sites"]["data"][0]
    assert "working_capacity_twh" in storage_site
    assert "lat" not in storage_site
    assert "working_capacity_mcm" not in storage_site
    storage_observation = payloads["/api/storage/observations"]["data"][0]
    assert "facility_id" in storage_observation
    assert "observation_type" not in storage_observation
    assert "volume_mcm" not in storage_observation
    lng_terminal = payloads["/api/lng/terminals"]["data"][0]
    assert "inventory_twh" in lng_terminal
    assert "lat" not in lng_terminal
    assert "capacity_mcm_d" not in lng_terminal
    lng_observation = payloads["/api/lng/observations"]["data"][0]
    assert "terminal_name" in lng_observation
    assert "observation_type" not in lng_observation
    assert "value_mcm" not in lng_observation
    return payloads


def _install_sdk_mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    payloads: dict[str, dict[str, Any]],
) -> list[httpx.Request]:
    """Route SDK HTTP GETs through MockTransport and return the seen requests."""

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payloads[request.url.path], request=request)

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(transport=transport) as client:
            return client.get(url, **kwargs)

    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", TOKEN)
    monkeypatch.setattr(httpx, "get", fake_get)
    return seen


def test_actual_storage_payloads_deserialize_into_typed_sdk(
    gie_api_payloads: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _install_sdk_mock_transport(monkeypatch, gie_api_payloads)

    sites = fetch_storage_sites(BASE_URL)
    observations = fetch_storage_observations(BASE_URL)

    assert [request.url.path for request in seen] == [
        "/api/storage/sites",
        "/api/storage/observations",
    ]
    assert all(request.headers["authorization"] == f"Bearer {TOKEN}" for request in seen)

    site = sites[0]
    assert site.site_id == "NL-AGS1"
    assert site.name == "Synthetic AGSI North"
    assert site.country == "NL"
    assert site.working_capacity_twh == 3.0
    assert site.fill_pct == 50.0
    assert site.observed_at_utc == OBSERVED_AT
    assert site.source_system == "GIE"
    assert site.status == "observed"
    # Unknown geography and non-published mcm capacity stay None.
    assert site.lat is None
    assert site.lon is None
    assert site.working_capacity_mcm is None
    assert sites[1].working_capacity_twh is None
    assert sites[1].fill_pct is None

    observation = observations[0]
    assert observation.facility_id == "NL-AGS1"
    assert observation.facility_name == "Synthetic AGSI North"
    assert observation.site_id == "NL-AGS1"
    assert observation.site_name == "Synthetic AGSI North"
    assert observation.country == "NL"
    assert observation.source_dataset == "AGSI"
    assert observation.inventory_twh == 1.5
    assert observation.working_capacity_twh == 3.0
    assert observation.fill_pct == 50.0
    assert observation.injection_twh_d == 0.02
    assert observation.withdrawal_twh_d == 0.01
    assert observation.period_start_utc == PERIOD_START
    assert observation.period_end_utc == PERIOD_END
    assert observation.observed_at_utc == OBSERVED_AT
    assert observation.source_system == "GIE"
    assert observation.source_reference == "gie-agsi-api"
    assert observation.freshness == "live"
    assert observation.research_only is True
    # The actual API has no observation kind or mcm volume; neither is invented.
    assert observation.observation_type is None
    assert observation.volume_mcm is None

    missing = observations[1]
    assert missing.inventory_twh is None
    assert missing.working_capacity_twh is None
    assert missing.fill_pct is None
    assert missing.injection_twh_d is None
    assert missing.withdrawal_twh_d is None


def test_actual_lng_payloads_deserialize_into_typed_sdk(
    gie_api_payloads: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _install_sdk_mock_transport(monkeypatch, gie_api_payloads)

    terminals = fetch_lng_terminals(BASE_URL)
    observations = fetch_lng_observations(BASE_URL)

    assert [request.url.path for request in seen] == [
        "/api/lng/terminals",
        "/api/lng/observations",
    ]
    assert all(request.headers["authorization"] == f"Bearer {TOKEN}" for request in seen)

    terminal = terminals[0]
    assert terminal.terminal_id == "NL-ALS1"
    assert terminal.name == "Synthetic ALSI Terminal"
    assert terminal.country == "NL"
    assert terminal.inventory_twh == 0.75
    assert terminal.send_out_twh_d == 0.03
    assert terminal.dtmi_twh == 0.02
    assert terminal.observed_at_utc == OBSERVED_AT
    assert terminal.source_system == "GIE"
    assert terminal.status == "observed"
    # Unknown geography and non-published mcm capacity stay None.
    assert terminal.lat is None
    assert terminal.lon is None
    assert terminal.capacity_mcm_d is None
    assert terminal.storage_capacity_mcm is None
    assert terminals[1].inventory_twh is None
    assert terminals[1].send_out_twh_d is None
    assert terminals[1].dtmi_twh is None

    observation = observations[0]
    assert observation.terminal_id == "NL-ALS1"
    assert observation.terminal_name == "Synthetic ALSI Terminal"
    assert observation.country == "NL"
    assert observation.source_dataset == "ALSI"
    assert observation.inventory_twh == 0.75
    assert observation.send_out_twh_d == 0.03
    assert observation.dtmi_twh == 0.02
    assert observation.period_start_utc == PERIOD_START
    assert observation.period_end_utc == PERIOD_END
    assert observation.observed_at_utc == OBSERVED_AT
    assert observation.source_system == "GIE"
    assert observation.source_reference == "gie-alsi-api"
    assert observation.freshness == "live"
    assert observation.research_only is True
    # The actual API has no observation kind or mcm value; neither is invented.
    assert observation.observation_type is None
    assert observation.value_mcm is None

    missing = observations[1]
    assert missing.inventory_twh is None
    assert missing.send_out_twh_d is None
    assert missing.dtmi_twh is None
