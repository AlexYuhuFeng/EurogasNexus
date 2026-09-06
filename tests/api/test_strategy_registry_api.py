"""API tests for the versioned strategy registry."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base


def _configure_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "strategy-registry.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _definition() -> dict:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    return {
        "definition": {
            "components": [
                {
                    "component_id": "ocm-da",
                    "component_type": "OCM_VS_DAY_AHEAD",
                    "hubs": ["NBP"],
                    "extension_json": {
                        "weight": 1.0,
                        "day_ahead_price_names": ["SAP"],
                        "intraday_price_names": ["ICE_OCM"],
                        "positive_spread_threshold_gbp_mwh": 0.0,
                        "negative_spread_threshold_gbp_mwh": 0.0,
                        "target_bar_minutes": 5,
                        "time_window_start": "05:00",
                        "time_window_end": "05:30",
                    },
                }
            ],
            "parameter_definitions": [],
            "parameter_values": {},
            "risk_controls": {
                "max_ocm_allocation_pct": 80.0,
                "min_day_ahead_allocation_pct": 10.0,
                "require_tso_access": False,
            },
            "economic_assumptions": {},
            "data_requirements": {"hubs": ["NBP"]},
            "evaluation_windows": [],
        },
        "hypothesis": "NBP intraday premium",
        "run_mode": "SHADOW_RUN",
        "resource_contexts": [
            {
                "resource_id": "res-1",
                "resource_name": "Resource 1",
                "available_quantity_mwh_per_day": 100.0,
                "all_in_cost_gbp_mwh": 20.0,
                "required_tso_access": [],
                "company_accessible_tsos": None,
            }
        ],
        "price_observations": [
            {
                "observation_id": "ice-ocm-1",
                "source_system": "ICE",
                "venue": "OCM",
                "hub": "NBP",
                "product": "NBP Within-Day",
                "price_name": "ICE_OCM",
                "price_gbp_mwh": 30.0,
                "observed_at_utc": (now - timedelta(hours=1)).isoformat(),
                "delivery_start_utc": now.isoformat(),
                "delivery_end_utc": (now + timedelta(hours=24)).isoformat(),
                "bar_minutes": 5,
                "source_reference": "ice-ocm:1",
            },
            {
                "observation_id": "sap-da-1",
                "source_system": "SAP",
                "venue": "NBP",
                "hub": "NBP",
                "product": "NBP Day-Ahead",
                "price_name": "SAP",
                "price_gbp_mwh": 25.0,
                "observed_at_utc": (now - timedelta(hours=1)).isoformat(),
                "delivery_start_utc": now.isoformat(),
                "delivery_end_utc": (now + timedelta(hours=24)).isoformat(),
                "bar_minutes": None,
                "source_reference": "sap:nbp:1",
            },
        ],
        "existing_shadow_pnl_gbp": 0.0,
    }


def _create_frozen_version(client: TestClient, strategy_id: str = "api-strategy") -> str:
    created = client.post(
        "/api/strategies",
        json={"strategy_id": strategy_id, "name": "API strategy"},
    )
    assert created.status_code == 200, created.text
    version = client.post(
        f"/api/strategies/{strategy_id}/versions",
        json=_definition(),
    )
    assert version.status_code == 200, version.text
    version_id = version.json()["data"]["strategy_version_id"]
    frozen = client.post(f"/api/strategy-versions/{version_id}/freeze")
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["data"]["status"] == "FROZEN"
    return version_id


def test_registry_requires_configured_runtime_db(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.get("/api/strategies")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_unavailable"


def test_strategy_version_run_roundtrip_reproducible(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)

    strategies = client.get("/api/strategies")
    assert strategies.status_code == 200
    assert strategies.json()["data"][0]["strategy_id"] == "api-strategy"

    versions = client.get("/api/strategies/api-strategy/versions")
    assert versions.status_code == 200
    assert versions.json()["data"][0]["strategy_version_id"] == version_id
    version_payload = versions.json()["data"][0]
    assert "strategy_name" in version_payload["definition_json"]

    run = client.post(
        "/api/strategy-runs",
        json={
            "strategy_version_id": version_id,
            "run_type": "EVALUATION",
            "deterministic_seed": "api-seed",
        },
    )
    assert run.status_code == 200, run.text
    data = run.json()["data"]
    assert data["strategy_version_id"] == version_id
    assert data["run_type"] == "EVALUATION"
    assert data["status"] == "SUCCESS"
    assert data["manifest_hash"].startswith("sha256:")
    assert data["manifest_json"]["strategy_version_content_hash"]
    resource_id = data["manifest_json"]["strategy_definition"]["resource_contexts"][0][
        "resource_id"
    ]
    assert resource_id == "res-1"
    assert data["manifest_json"]["time_boundary"]["data_cutoff_utc"]

    fetched = client.get(f"/api/strategy-runs/{data['run_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["manifest_hash"] == data["manifest_hash"]

    registry_runs = client.get("/api/strategy-runs", params={"strategy_version_id": version_id})
    assert registry_runs.status_code == 200
    assert [row["run_id"] for row in registry_runs.json()["data"]] == [data["run_id"]]


def test_run_type_backtest_requires_explicit_period(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)

    response = client.post(
        "/api/strategy-runs",
        json={"strategy_version_id": version_id, "run_type": "BACKTEST"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "backtest_period_required"


def test_draft_version_cannot_create_run(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    assert client.post(
        "/api/strategies",
        json={"strategy_id": "draft-strategy", "name": "Draft strategy"},
    ).status_code == 200
    version = client.post(
        "/api/strategies/draft-strategy/versions",
        json=_definition(),
    )
    assert version.status_code == 200
    version_id = version.json()["data"]["strategy_version_id"]

    response = client.post(
        "/api/strategy-runs",
        json={"strategy_version_id": version_id, "run_type": "EVALUATION"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "strategy_version_not_frozen"


def test_freeze_is_idempotently_rejected_and_fork_preserves_definition(
    tmp_path, monkeypatch,
) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)

    second_freeze = client.post(f"/api/strategy-versions/{version_id}/freeze")
    assert second_freeze.status_code == 409

    fork = client.post(f"/api/strategy-versions/{version_id}/fork", json={})
    assert fork.status_code == 200
    forked = fork.json()["data"]
    assert forked["status"] == "DRAFT"
    assert forked["parent_version_id"] == version_id
    assert forked["definition_json"] == client.get(
        f"/api/strategy-versions/{version_id}"
    ).json()["data"]["definition_json"]


def test_unknown_version_and_run_are_404(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())

    assert client.get("/api/strategy-versions/missing-version").status_code == 404
    assert client.get("/api/strategy-runs/missing-run").status_code == 404
