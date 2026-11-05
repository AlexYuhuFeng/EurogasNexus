"""Weather scenarios exercise the public API and the real regional balance engine."""

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app

START = date(2026, 11, 8)


def scenario():
    origin = datetime(2026, 11, 7, 23, tzinfo=UTC).isoformat()
    history, weather = [], []
    for back in range(60, 0, -1):
        day = START - timedelta(days=back)
        hdd = 5 + back % 10
        call = 1500 + 120 * hdd - (200 if day.weekday() >= 5 else 0)
        evidence = dict(day=day.isoformat(), available_at=origin, source_reference=f"input:{day}")
        history.append(
            dict(**evidence, norway_gwh=1000, lng_gwh=400, storage_net_withdrawal_gwh=call - 1400)
        )
        weather.append(dict(**evidence, hdd=hdd))
    return dict(
        prediction_origin=origin,
        start=START.isoformat(),
        days=2,
        history=history,
        inventory_twh=100,
        working_capacity_twh=120,
        weather=dict(
            region="NWE",
            feature_policy_hash="a" * 64,
            heating_base_c=15.5,
            gas_day_calendar="EU-CAM-UTC-2025",
            history=weather,
            forecast=[
                dict(
                    day=(START + timedelta(days=i)).isoformat(),
                    hdd=20,
                    available_at=origin,
                    source_reference="forecast:run-1",
                )
                for i in range(2)
            ],
        ),
    )


@pytest.fixture
def client():
    return TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"})


def post(client, payload):
    return client.post("/api/market/nwe-balance", json=payload)


def test_weather_changes_supply_call_and_storage_against_identical_baseline(client):
    response = post(client, scenario())
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "WEATHER_COMPLETE"
    assert data["forecast"][0]["call_gwh"] == pytest.approx(3700)
    assert data["model"]["slope_per_hdd"] == pytest.approx(120)
    assert data["comparison"][0]["call_delta_gwh"] > 0
    assert data["comparison"][0]["call_delta_gwh"] == pytest.approx(
        data["comparison"][0]["storage_delta_gwh"]
    )
    assert data["persisted"] is False
    assert response.json()["meta"]["validation_basis"] == "SCENARIO_IN_SAMPLE_FIT"


def test_partial_weather_and_no_weather_have_explicit_status(client):
    payload = scenario()
    payload["weather"]["forecast"].pop()
    data = post(client, payload).json()["data"]
    assert data["status"] == "WEATHER_PARTIAL"
    assert data["forecast"][1]["methods"]["call"] != "weather_regression"
    payload["weather"] = None
    data = post(client, payload).json()["data"]
    assert data["status"] == "BASELINE_ONLY"
    assert all(row["call_delta_gwh"] == 0 for row in data["comparison"])


def test_input_hash_and_replay_detect_changed_inputs(client):
    payload = scenario()
    first = post(client, payload).json()["data"]
    payload["history"].reverse()
    payload["weather"]["history"].reverse()
    second = post(client, payload).json()["data"]
    assert first["input_hash"] == second["input_hash"]
    replay = post(client, first["inputs"]).json()["data"]
    assert replay == first
    payload["weather"]["forecast"][0]["hdd"] = 21
    assert post(client, payload).json()["data"]["input_hash"] != first["input_hash"]


@pytest.mark.parametrize("invalid", ["late", "duplicate", "horizon", "gap", "nan", "calendar"])
def test_invalid_or_future_evidence_is_rejected(client, invalid):
    payload = deepcopy(scenario())
    if invalid == "late":
        payload["weather"]["forecast"][0]["available_at"] = "2026-11-09T00:00:00Z"
    elif invalid == "duplicate":
        payload["weather"]["forecast"].append(payload["weather"]["forecast"][0])
    elif invalid == "horizon":
        payload["weather"]["forecast"][0]["day"] = "2026-12-01"
    elif invalid == "gap":
        payload["history"].pop(10)
    elif invalid == "nan":
        payload["weather"]["history"][0]["hdd"] = "NaN"
    else:
        payload["weather"]["gas_day_calendar"] = "invented"
    assert post(client, payload).status_code == 422


def test_singular_hdd_training_returns_honest_baseline(client):
    payload = scenario()
    for row in payload["weather"]["history"]:
        row["hdd"] = 10
    response = post(client, payload)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "BASELINE_ONLY"
    assert any("HDD_MODEL_NOT_FITTED" in warning for warning in response.json()["meta"]["warnings"])


def test_sdk_submits_to_same_backend_and_preserves_evidence(client, monkeypatch):
    from eurogas_nexus_sdk import _http
    from eurogas_nexus_sdk.fundamentals import calculate_nwe_balance_scenario

    def send(url, *, json, timeout):
        assert url == "https://example.test/api/market/nwe-balance"
        assert timeout == 30.0
        return post(client, json)

    monkeypatch.setattr(_http, "post", send)
    result = calculate_nwe_balance_scenario("https://example.test", scenario())
    assert result.data["status"] == "WEATHER_COMPLETE"
    assert "forecast:run-1" in result.meta.source_references


def test_scenario_compute_has_governed_permission_without_changing_get():
    from eurogas_nexus.security.permissions import Permission, permission_for_path

    assert permission_for_path("/api/market/nwe-balance", "POST") == Permission.GOVERNED
    assert permission_for_path("/api/market/nwe-balance", "GET") == Permission.READ
