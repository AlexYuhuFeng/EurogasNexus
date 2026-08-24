"""API tests for R34 storage and nomination assessment workflows."""

from __future__ import annotations

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def _client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="development")))


def test_storage_dispatch_endpoint_returns_assessment() -> None:
    response = _client().post(
        "/api/optimization/storage-dispatch",
        json={
            "facility": {
                "initial_inventory_mwh": 100,
                "minimum_inventory_mwh": 0,
                "maximum_inventory_mwh": 200,
                "maximum_injection_mwh": 50,
                "maximum_withdrawal_mwh": 50,
                "terminal_inventory_mwh": 100,
            },
            "periods": [
                {"period_id": "p1", "market_price_gbp_mwh": 10},
                {"period_id": "p2", "market_price_gbp_mwh": 30},
            ],
            "inventory_step_mwh": 50,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "optimal"
    assert payload["data"]["terminal_inventory_mwh"] == 100
    assert len(payload["data"]["decisions"]) == 2
    assert payload["meta"]["human_review_required"] is True
    assert payload["meta"]["research_only"] is True


def test_nomination_window_endpoint_returns_assessment_only() -> None:
    response = _client().post(
        "/api/optimization/nomination-window",
        json={
            "initial_quantity_mwh": 100,
            "windows": [
                {
                    "window_id": "within-day",
                    "opens_at": "00:00",
                    "closes_at": "06:00",
                    "maximum_change_mwh": 10,
                }
            ],
            "instructions": [
                {
                    "submitted_at": "2026-01-01T01:00:00+00:00",
                    "requested_quantity_mwh": 115,
                },
                {
                    "submitted_at": "2026-01-01T12:00:00+00:00",
                    "requested_quantity_mwh": 90,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["status"] == "feasible"
    assert payload["data"]["final_quantity_mwh"] == 110
    assert payload["data"]["decisions"][1]["accepted"] is False
    assert payload["data"]["decisions"][1]["reason"] == "OUTSIDE_NOMINATION_WINDOW"
    assert payload["meta"]["human_review_required"] is True


def test_storage_and_nomination_reject_runtime_decision() -> None:
    client = _client()
    storage = client.post(
        "/api/optimization/storage-dispatch",
        json={
            "decision_context": "RUNTIME_DECISION",
            "facility": {
                "initial_inventory_mwh": 10,
                "minimum_inventory_mwh": 0,
                "maximum_inventory_mwh": 20,
                "maximum_injection_mwh": 5,
                "maximum_withdrawal_mwh": 5,
            },
            "periods": [{"period_id": "p1", "market_price_gbp_mwh": 20}],
        },
    )
    nomination = client.post(
        "/api/optimization/nomination-window",
        json={"decision_context": "RUNTIME_DECISION", "initial_quantity_mwh": 0},
    )

    assert storage.status_code == 422
    assert storage.json()["detail"]["code"] == "runtime_decision_client_input_forbidden"
    assert nomination.status_code == 422
    assert nomination.json()["detail"]["code"] == "runtime_decision_window_master_required"
