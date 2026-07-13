"""API tests for phase-two optimization routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def _client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="development")))


def test_route_optimization_endpoint() -> None:
    response = _client().post(
        "/api/optimization/route",
        json={
            "source": "A",
            "target": "C",
            "required_capacity_mwh": 50,
            "accessible_tsos": ["TSO-1", "TSO-2"],
            "edges": [
                {
                    "edge_id": "direct",
                    "source": "A",
                    "target": "C",
                    "tariff_gbp_mwh": 4,
                    "available_capacity_mwh": 100,
                    "tso": "TSO-1",
                },
                {
                    "edge_id": "ab",
                    "source": "A",
                    "target": "B",
                    "tariff_gbp_mwh": 1,
                    "available_capacity_mwh": 100,
                    "tso": "TSO-1",
                },
                {
                    "edge_id": "bc",
                    "source": "B",
                    "target": "C",
                    "tariff_gbp_mwh": 1.5,
                    "available_capacity_mwh": 80,
                    "tso": "TSO-2",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "optimal"
    assert payload["edge_ids"] == ["ab", "bc"]
    assert payload["human_review_required"] is True


def test_resource_pool_optimization_endpoint() -> None:
    response = _client().post(
        "/api/optimization/resource-pool",
        json={
            "resources": [
                {
                    "resource_id": "supply",
                    "available_mwh": 100,
                    "unit_cost_gbp_mwh": 20,
                    "minimum_take_mwh": 20,
                }
            ],
            "sale_options": [
                {
                    "option_id": "nbp",
                    "destination_node": "NBP",
                    "sale_price_gbp_mwh": 35,
                    "capacity_mwh": 80,
                    "variable_cost_gbp_mwh": 2,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "optimal"
    assert payload["objective_value_gbp"] == 1040
    assert payload["unsold_volume_mwh"] == 20


def test_capacity_optimization_endpoint() -> None:
    response = _client().post(
        "/api/optimization/capacity",
        json={
            "required_capacity_mwh": 90,
            "expected_throughput_mwh": 20,
            "products": [
                {"product_id": "small", "capacity_mwh": 40, "fixed_cost_gbp": 100},
                {"product_id": "medium", "capacity_mwh": 70, "fixed_cost_gbp": 180},
                {
                    "product_id": "monthly",
                    "capacity_mwh": 30,
                    "fixed_cost_gbp": 40,
                    "variable_cost_gbp_mwh": 1,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_product_ids"] == ["medium", "monthly"]
    assert payload["total_cost_gbp"] == 240


def test_contract_optimization_endpoint() -> None:
    response = _client().post(
        "/api/optimization/contracts",
        json={
            "market_price_gbp_mwh": 30,
            "demand_limit_mwh": 40,
            "resources": [
                {
                    "resource_id": "contract",
                    "available_mwh": 100,
                    "unit_cost_gbp_mwh": 20,
                    "minimum_take_mwh": 10,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "optimal"
    assert payload["dispatches"][0]["quantity_mwh"] == 40
    assert payload["objective_value_gbp"] == 400
