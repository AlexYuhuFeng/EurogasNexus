"""Route-cost adjacent API tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_lng_regas_assessment_api_supports_delivery_mode() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/lng-regas/assess",
        json={
            "contract_id": "lng-api",
            "cargo_id": "cargo-api",
            "terminal_id": "gb-grain",
            "terminal_name": "Isle of Grain",
            "terminal_access_confirmed": True,
            "terminal_access_reference": "operator-input",
            "cargo_size_mwh": 900000,
            "cargo_arrival_window_start_utc": "2026-06-29T00:00:00Z",
            "cargo_arrival_window_end_utc": "2026-07-01T00:00:00Z",
            "regas_slot_start_utc": "2026-06-30T00:00:00Z",
            "regas_slot_end_utc": "2026-07-04T00:00:00Z",
            "terminal_sendout_capacity_mwh_per_day": 300000,
            "terminal_capacity_source_system": "GIE ALSI/operator",
            "delivery_mode": "TERMINAL_TITLE_TRANSFER",
            "pricing_method": "TTF",
            "index_name": "TTF day-ahead",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["physical_entry_delivery_required"] is False
    assert data["estimated_regas_duration_days"] == 3.0


def test_resource_pool_optimization_api_returns_allocations() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json={
            "portfolio_id": "api-pool",
            "resources": [
                {
                    "resource_id": "beach-a",
                    "resource_name": "Beach A",
                    "resource_type": "BEACH_DELIVERY",
                    "delivery_mode": "PHYSICAL_ENTRY_DELIVERY",
                    "location_point_name": "Generic beach terminal",
                    "available_quantity_mwh_per_day": 10000,
                    "contract_cost_gbp_mwh": 25,
                    "delivery_tolerance_pct": 2,
                    "nomination_tolerance_pct": 1,
                    "accessible_tsos": ["Example TSO"],
                }
            ],
            "sale_options": [
                {
                    "option_id": "hub-a",
                    "label": "Hub A sale",
                    "delivery_mode": "VIRTUAL_HUB_SALE",
                    "target_point_name": "Hub A",
                    "sale_price_gbp_mwh": 29,
                    "route_cost_gbp_mwh": 1.4,
                    "capacity_limit_mwh_per_day": 6000,
                    "required_tso_access": ["Example TSO"],
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["allocations"][0]["allocated_quantity_mwh_per_day"] == 6000
