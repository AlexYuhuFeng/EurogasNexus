"""Feasibility and allocation API tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_post_feasibility_200(client: TestClient) -> None:
    r = client.post("/api/research/feasibility", json={
        "route_name": "TTF-NCG", "from_node_id": "n1", "to_node_id": "n2",
        "capacity_available_mcm_d": 100.0, "required_capacity_mcm_d": 50.0,
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["status"] == "feasible"


def test_post_feasibility_infeasible(client: TestClient) -> None:
    r = client.post("/api/research/feasibility", json={
        "route_name": "Test", "from_node_id": "n1", "to_node_id": "n2",
        "capacity_available_mcm_d": 10.0, "required_capacity_mcm_d": 100.0,
    })
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "infeasible"


def test_post_allocation_200(client: TestClient) -> None:
    r = client.post("/api/research/allocation", json={
        "scenario_name": "Winter Base", "total_demand_boe_d": 5000000.0,
        "candidates": [
            {"candidate_id": "c1", "route_name": "TTF-NCG",
             "capacity_available_boe_d": 3000000, "cost_eur_mwh": 40.5, "rank": 1},
            {"candidate_id": "c2", "route_name": "Emden-NCG",
             "capacity_available_boe_d": 3000000, "cost_eur_mwh": 41.2, "rank": 2},
        ],
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total_allocated_boe_d"] == 5000000.0


def test_post_allocation_with_unallocated(client: TestClient) -> None:
    r = client.post("/api/research/allocation", json={
        "scenario_name": "Test", "total_demand_boe_d": 5000000.0,
        "candidates": [
            {"candidate_id": "c1", "route_name": "R1",
             "capacity_available_boe_d": 1000000, "cost_eur_mwh": 40.0, "rank": 1},
        ],
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["unallocated_boe_d"] == 4000000.0


def test_feasibility_metadata(client: TestClient) -> None:
    r = client.post("/api/research/feasibility", json={
        "route_name": "T", "from_node_id": "a", "to_node_id": "b",
    })
    assert r.json()["meta"]["research_only"] is True
