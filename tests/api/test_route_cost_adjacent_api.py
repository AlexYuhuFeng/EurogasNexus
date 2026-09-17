"""Route-cost adjacent API tests."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base

PUBLIC_TOKEN = "test-public-api-token"
HEADERS = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}

#: The resource-pool optimisation scenario used by the citation and tracking
#: tests below (the same shape as the delivered allocation test).
OPTIMIZATION_SCENARIO = {
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
}


def _database(tmp_path, monkeypatch) -> str:
    """Point the runtime store at a fresh SQLite database (no runtime store otherwise)."""

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'route-cost-jobs.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


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
    # 4,000 MWh/d of the 10,000 MWh/d resource remain unallocated, so the
    # status must be PARTIAL — SUCCESS would be dishonest.
    assert data["status"] == "PARTIAL"
    assert "PORTFOLIO_VOLUME_UNALLOCATED" in data["warnings"]
    assert data["allocations"][0]["allocated_quantity_mwh_per_day"] == 6000
    # No reproducibility reference was cited, so the additive field is absent:
    # a caller that cites nothing keeps the previous payload exactly.
    assert "analysis_snapshot_id" not in data


# ---------------------------------------------------------------------------
# Analysis Snapshot citation on the resource-pool optimisation run (Wave 4 scope)
# ---------------------------------------------------------------------------


def test_resource_pool_optimization_echoes_the_snapshot_it_was_computed_against(
    tmp_path, monkeypatch
) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())
    snapshot_id = client.post("/api/analysis-snapshots", json={}).json()["data"]["snapshot_id"]

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json={**OPTIMIZATION_SCENARIO, "analysis_snapshot_id": snapshot_id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["analysis_snapshot_id"] == snapshot_id
    # The citation is an echo, not a re-computation: the allocation is unchanged.
    assert data["status"] == "PARTIAL"
    assert data["allocations"][0]["allocated_quantity_mwh_per_day"] == 6000


def test_resource_pool_optimization_refuses_an_unknown_snapshot_reference(
    tmp_path, monkeypatch
) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json={**OPTIMIZATION_SCENARIO, "analysis_snapshot_id": "asnap-missing"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "analysis_snapshot_not_found"


def test_resource_pool_optimization_cannot_verify_a_reference_without_a_runtime_db(
    monkeypatch,
) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json={**OPTIMIZATION_SCENARIO, "analysis_snapshot_id": "asnap-any"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"


# ---------------------------------------------------------------------------
# Unified job tracking on the resource-pool optimisation run (Wave 8 scope)
# ---------------------------------------------------------------------------


def test_resource_pool_optimization_run_is_tracked_in_jobs(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json=OPTIMIZATION_SCENARIO,
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PARTIAL"

    listed = client.get("/api/jobs", params={"kind": "OPTIMISATION"}, headers=HEADERS)
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1
    job = rows[0]
    assert job["status"] == "SUCCEEDED"
    assert job["principal"] == "public-api"
    assert job["scope_refs"] == ["PORTFOLIO:api-pool"]
    # A pure computation persists no artefact: no output reference is invented.
    assert job["output_refs"] == []
    assert job["provenance"] == ["route-cost-resource-pool"]
    assert job["input_hash"]
    assert job["correlation_id"]


def test_resource_pool_optimization_job_commits_the_snapshot_it_cited(
    tmp_path, monkeypatch
) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    snapshot_id = (
        client.post("/api/analysis-snapshots", json={}, headers=HEADERS)
        .json()["data"]["snapshot_id"]
    )

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json={**OPTIMIZATION_SCENARIO, "analysis_snapshot_id": snapshot_id},
        headers=HEADERS,
    )
    assert response.status_code == 200

    rows = client.get("/api/jobs", params={"kind": "OPTIMISATION"}, headers=HEADERS).json()["data"]
    assert len(rows) == 1
    assert rows[0]["snapshot_id"] == snapshot_id


def test_resource_pool_optimization_runs_untracked_without_a_runtime_db(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.post(
        "/api/route-cost/resource-pool/optimize",
        json=OPTIMIZATION_SCENARIO,
    )

    # Tracking is skipped rather than refusing work the deployment can still run.
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PARTIAL"
    assert "analysis_snapshot_id" not in response.json()["data"]
