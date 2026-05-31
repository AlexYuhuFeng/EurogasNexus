"""UK Easington contract option API tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_easington_contract_options_api_returns_option_pnl() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/route-cost/uk/easington/options", json={
        "contract_id": "api-easington-demo",
        "gas_year": "2025/26",
        "delivery_quantity_mwh_per_day": 10000,
        "contract_price_gbp_mwh": 25,
        "nbp_sale_price_gbp_mwh": 28,
        "physical_exit_sale_price_gbp_mwh": 28.5,
        "physical_exit_point_name": "Bacton GDN (EA)",
        "delivery_tolerance_pct": 2,
        "nomination_tolerance_pct": 1,
        "tolerance_risk_allowance_gbp_mwh": 0.1,
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["contract_id"] == "api-easington-demo"
    assert data["research_only"] is True
    assert {option["option_id"] for option in data["options"]} == {
        "nbp_virtual_sale",
        "physical_exit_delivery",
    }
    assert data["options"][0]["source_refs"]


def test_easington_live_pnl_api_returns_decision_support_signal() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/route-cost/uk/easington/live-pnl", json={
        "contract": {
            "contract_id": "api-live-easington",
            "gas_year": "2025/26",
            "delivery_quantity_mwh_per_day": 10000,
            "contract_price_gbp_mwh": 25,
            "nbp_sale_price_gbp_mwh": 28,
            "physical_exit_sale_price_gbp_mwh": 28.5,
            "physical_exit_point_name": "Bacton GDN (EA)",
            "delivery_tolerance_pct": 2,
            "nomination_tolerance_pct": 1,
            "tolerance_risk_allowance_gbp_mwh": 0.1,
        },
        "marks": [
            {
                "venue": "ICE OCM",
                "hub": "NBP",
                "product": "Within-day",
                "bid_gbp_mwh": 28.2,
                "ask_gbp_mwh": 28.4,
                "last_gbp_mwh": 28.3,
                "mark_time_utc": "2026-05-31T08:30:00Z",
                "source_system": "operator-entered-live-mark",
            }
        ],
    })

    assert response.status_code == 200
    data = response.json()["data"]
    live_by_option = {item["option_id"]: item for item in data["live_marks"]}
    assert live_by_option["nbp_virtual_sale"]["signal"]["suggestion_type"] == "DECISION_SUPPORT"
    assert live_by_option["nbp_virtual_sale"]["live_net_pnl_gbp_per_day"] == 18861.0


def test_lng_regas_assessment_api_supports_delivery_mode() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/route-cost/lng-regas/assess", json={
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
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["physical_entry_delivery_required"] is False
    assert data["estimated_regas_duration_days"] == 3.0


def test_resource_pool_optimization_api_returns_allocations() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/route-cost/resource-pool/optimize", json={
        "portfolio_id": "api-pool",
        "resources": [
            {
                "resource_id": "beach-a",
                "resource_name": "Beach A",
                "resource_type": "BEACH_DELIVERY",
                "delivery_mode": "PHYSICAL_ENTRY_DELIVERY",
                "location_point_name": "Easington Beach Terminal",
                "available_quantity_mwh_per_day": 10000,
                "contract_cost_gbp_mwh": 25,
                "delivery_tolerance_pct": 2,
                "nomination_tolerance_pct": 1,
                "accessible_tsos": ["National Gas NTS"],
            }
        ],
        "sale_options": [
            {
                "option_id": "nbp",
                "label": "NBP sale",
                "delivery_mode": "VIRTUAL_HUB_SALE",
                "target_point_name": "NBP",
                "sale_price_gbp_mwh": 29,
                "route_cost_gbp_mwh": 1.4,
                "capacity_limit_mwh_per_day": 6000,
                "required_tso_access": ["National Gas NTS"],
            }
        ],
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["allocations"][0]["allocated_quantity_mwh_per_day"] == 6000
