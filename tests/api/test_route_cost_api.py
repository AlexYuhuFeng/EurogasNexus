"""European route-cost API tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import route_cost as route_cost_routes
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)


def test_get_tso_tariffs_returns_empty_when_runtime_db_is_not_configured() -> None:
    client = TestClient(create_app())

    response = client.get("/api/route-cost/tso-tariffs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["scope"] == "EUROPEAN_TSO_TARIFFS"
    assert payload["data"]["tariffs"] == []
    assert payload["meta"]["source_references"] == ["runtime-db-not-configured"]


def test_get_tso_tariffs_can_filter_bbl_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        route_cost_routes,
        "_load_tariffs",
        lambda: (published_european_corridor_tariffs(), "runtime-postgresql", []),
    )
    client = TestClient(create_app())

    response = client.get(
        "/api/route-cost/tso-tariffs",
        params={"tso": "BBL Company", "market_area": "BBL"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scope"] == "EUROPEAN_TSO_TARIFFS"
    assert {tariff["source_point_name"] for tariff in data["tariffs"]} == {
        "BBL Forward Flow NL to GB",
        "BBL Reverse Flow GB to NL",
    }


def test_calculate_requires_explicit_tso_tariff_legs() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/calculate",
        json={
            "scenario_id": "api-no-legs",
            "source_resource_type": "PIPELINE_IMPORT",
            "start_point_id": "TTF",
            "target_hub_or_point_id": "NBP",
            "business_model": "CROSS_BORDER_TRANSFER",
            "delivery_mode": "BORDER_TRANSFER",
            "gas_year": "2025+",
            "capacity_product": "ANNUAL",
            "firmness": "FIRM",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "BLOCKED"
    assert data["missing_inputs"] == ["ROUTE_TARIFF_LEGS_REQUIRED"]


def test_calculate_accepts_explicit_european_tso_tariff_legs(monkeypatch) -> None:
    monkeypatch.setattr(
        route_cost_routes,
        "_load_tariffs",
        lambda: (published_european_corridor_tariffs(), "runtime-postgresql", []),
    )
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/calculate",
        json={
            "scenario_id": "api-bbl-european-multileg",
            "source_resource_type": "PIPELINE_IMPORT",
            "start_point_id": "TTF",
            "target_hub_or_point_id": "NBP",
            "business_model": "CROSS_BORDER_TRANSFER",
            "delivery_mode": "BORDER_TRANSFER",
            "gas_year": "2025+",
            "capacity_product": "ANNUAL",
            "firmness": "FIRM",
            "required_tso_access": ["BBL Company"],
            "company_accessible_tsos": ["BBL Company"],
            "tariff_legs": [
                {
                    "leg_id": "bbl-forward",
                    "country": "NL",
                    "tso": "BBL Company",
                    "market_area": "BBL",
                    "point_name": "BBL Forward Flow NL to GB",
                    "direction": "EXIT",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["total_cost"] == 1.0
    assert data["currency"] == "EUR"


def test_recommend_route_allocation_selects_local_sale_when_reroute_is_worse(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        route_cost_routes,
        "_load_tariffs",
        lambda: (published_european_corridor_tariffs(), "runtime-postgresql", []),
    )
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/recommend",
        json={
            "request_id": "api-netback-allocation",
            "source_point_id": "TTF",
            "target_point_id": "NBP",
            "required_quantity_mwh_per_day": 100,
            "gas_year": "2025+",
            "capacity_product": "ANNUAL",
            "firmness": "FIRM",
            "company_accessible_tsos": ["BBL Company"],
            "candidates": [
                {
                    "route_id": "cheap-nbp-route",
                    "route_name": "TTF -> BBL -> NBP",
                    "destination_market": "NBP",
                    "sale_price": 35,
                    "price_currency": "EUR",
                    "price_unit": "EUR/MWh",
                    "required_tso_access": ["BBL Company"],
                    "available_capacity_mwh_per_day": 20,
                    "tariff_legs": [
                        {
                            "leg_id": "bbl-forward",
                            "country": "NL",
                            "tso": "BBL Company",
                            "market_area": "BBL",
                            "point_name": "BBL Forward Flow NL to GB",
                            "direction": "EXIT",
                        }
                    ],
                },
                {
                    "route_id": "expensive-reroute",
                    "route_name": "TTF -> expensive NBP reroute",
                    "destination_market": "NBP",
                    "sale_price": 35,
                    "price_currency": "EUR",
                    "price_unit": "EUR/MWh",
                    "available_capacity_mwh_per_day": 100,
                    "manual_cost": 8,
                    "cost_currency": "EUR",
                    "cost_unit": "EUR/MWh",
                },
                {
                    "route_id": "local-ttf-sale",
                    "route_name": "Sell locally at TTF",
                    "destination_market": "TTF",
                    "sale_price": 31,
                    "price_currency": "EUR",
                    "price_unit": "EUR/MWh",
                    "available_capacity_mwh_per_day": 100,
                    "manual_cost": 0,
                    "cost_currency": "EUR",
                    "cost_unit": "EUR/MWh",
                },
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert [(item["route_id"], item["allocated_mwh_per_day"]) for item in data["allocations"]] == [
        ("cheap-nbp-route", 20.0),
        ("local-ttf-sale", 80.0),
    ]
