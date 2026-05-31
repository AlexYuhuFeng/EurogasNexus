"""UK route-cost API tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_get_uk_easington_tariffs() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/route-cost/uk/tariffs/easington")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scope"] == "UK_NATIONAL_GAS_NTS_ONLY"
    assert len(data["tariffs"]) == 5
    assert data["tariffs"][0]["source_point_name"] == "Easington Beach Terminal"


def test_get_uk_nts_tariffs_can_filter_any_loaded_point() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/v1/route-cost/uk/tariffs",
        params={"point_name": "Bacton GDN (EA)", "direction": "EXIT"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scope"] == "UK_NATIONAL_GAS_NTS_ONLY"
    assert {row["direction"] for row in data["tariffs"]} == {"EXIT"}
    assert {row["source_point_name"] for row in data["tariffs"]} == {"Bacton GDN (EA)"}


def test_calculate_uk_easington_virtual_nbp_sale() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/route-cost/calculate", json={
        "scenario_id": "api-uk-easington-nbp",
        "source_resource_type": "BEACH_DELIVERY",
        "start_point_id": "Easington Beach Terminal",
        "target_hub_or_point_id": "NBP",
        "business_model": "VIRTUAL_HUB_SALE",
        "gas_year": "2025/26",
        "capacity_product": "DAILY",
        "firmness": "FIRM",
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["total_cost"] == 0.1086
    assert data["unit"] == "p/kWh/day"
    assert data["research_only"] is True


def test_calculate_unknown_uk_nts_tariff_rows_returns_partial() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/route-cost/calculate", json={
        "scenario_id": "api-uk-unknown-nts-points",
        "source_resource_type": "PIPELINE_IMPORT",
        "start_point_id": "Unknown UK NTS Entry",
        "target_hub_or_point_id": "Unknown UK NTS Exit",
        "business_model": "CROSS_BORDER_TRANSFER",
        "gas_year": "2025/26",
        "capacity_product": "DAILY",
        "firmness": "FIRM",
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "BLOCKED"
    assert "ENTRY_TARIFF_MISSING" in data["missing_inputs"]
    assert "EXIT_TARIFF_MISSING" in data["missing_inputs"]
