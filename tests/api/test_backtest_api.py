"""API tests for the temporally safe professional backtest path."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord


def _configure_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "backtest-api.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _definition_body() -> dict:
    return {
        "hypothesis": "NBP intraday premium",
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
        "run_mode": "BACKTEST",
        "resource_contexts": [
            {
                "resource_id": "res-1",
                "resource_name": "Resource",
                "available_quantity_mwh_per_day": 100.0,
                "all_in_cost_gbp_mwh": 20.0,
                "required_tso_access": [],
            }
        ],
        "price_observations": [],
        "existing_shadow_pnl_gbp": 0.0,
    }


def _create_frozen_version(client: TestClient) -> str:
    created = client.post(
        "/api/strategies",
        json={"strategy_id": "bt-api-strategy", "name": "BT API strategy"},
    )
    assert created.status_code == 200, created.text
    version = client.post(
        "/api/strategies/bt-api-strategy/versions",
        json=_definition_body(),
    )
    assert version.status_code == 200, version.text
    version_id = version.json()["data"]["strategy_version_id"]
    frozen = client.post(f"/api/strategy-versions/{version_id}/freeze")
    assert frozen.status_code == 200, frozen.text
    return version_id


def _seed_observations(tmp_path, monkeypatch, database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        for day in range(2):
            observed = datetime(2026, 7, 1, 4, 30, tzinfo=UTC) + timedelta(
                days=day
            )
            for observation_id, source, venue, price, tenor in [
                ("ice", "ICE_OCM_Sim", "ICE OCM", 30.0 + day, "within-day"),
                ("sap", "SAP_Sim", "SAP", 25.0 + day, "day-ahead"),
            ]:
                session.add(
                    MarketObservationRecord(
                        observation_id=f"bt-{observation_id}-{day}",
                        market_venue=venue,
                        product=f"NBP {tenor}",
                        price=price,
                        unit="GBP/MWh",
                        currency="GBP",
                        period_start_utc=observed,
                        period_end_utc=observed + timedelta(hours=24),
                        observed_at_utc=observed,
                        source_system=source,
                        source_reference=f"bt:{observation_id}:{day}",
                        freshness="simulated_live",
                        quality_score=0.6,
                        research_only=True,
                        metadata_json={
                            "hub": "NBP",
                            "tenor": tenor,
                            "price_timing": (
                                "instant"
                                if observation_id == "ice"
                                else "daily_assessment"
                            ),
                            "simulated": True,
                        },
                    )
                )
        session.commit()


def _backtest_payload(version_id: str, **overrides) -> dict:
    payload = {
        "strategy_version_id": version_id,
        "run_type": "BACKTEST",
        "evaluation_period_start_utc": "2026-07-01T00:00:00Z",
        "evaluation_period_end_utc": "2026-07-03T00:00:00Z",
        "economic_assumptions": {
            "missing_data_policy": "FAIL",
            "cost_components": [
                {
                    "code": "TRANSACTION_COST",
                    "treatment": "MODELED_COST",
                    "amount_gbp_mwh": 0.5,
                    "source_refs": ["assumption:tx"],
                }
            ],
        },
    }
    payload.update(overrides)
    return payload


def test_create_backtest_run_and_retrieve_events_series_attribution(
    tmp_path, monkeypatch
) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    run = client.post("/api/strategy-runs", json=_backtest_payload(version_id))
    assert run.status_code == 200, run.text
    data = run.json()["data"]
    assert data["run_type"] == "BACKTEST"
    assert data["backtest_engine_version"] == "backtest-engine/1"
    assert data["status"] == "COMPLETED_WITH_WARNINGS"
    assert data["manifest_json"]["parameters"] == {}
    assert data["backtest_metrics"]["evaluation_count"] == 2
    assert data["backtest_metrics"]["candidate_decision_count"] == 2
    assert data["backtest_metrics"]["gross_indicative_pnl_gbp"] == 1850.0
    assert data["backtest_metrics"]["modeled_costs_gbp"] == 100.0
    assert data["backtest_metrics"]["net_indicative_pnl_gbp"] == 1750.0
    run_id = data["run_id"]

    events = client.get(f"/api/strategy-runs/{run_id}/events")
    assert events.status_code == 200
    assert [row["decision_sequence"] for row in events.json()["data"]] == [1, 2]
    assert events.json()["data"][0]["outcome"] == "COMPLETED_WITH_WARNINGS"

    series = client.get(f"/api/strategy-runs/{run_id}/series")
    assert series.status_code == 200
    assert len(series.json()["data"]) == 2
    assert series.json()["data"][1]["cumulative_net_indicative_pnl_gbp"] == 1750.0

    attribution = client.get(f"/api/strategy-runs/{run_id}/attribution")
    assert attribution.status_code == 200
    dimensions = {row["dimension"] for row in attribution.json()["data"]}
    assert {"market_bucket", "cost_component"} <= dimensions


def test_future_observation_is_not_used(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)
    # Add a future-dated row inside the DB; the engine must ignore it for day 1.
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        session.add(
            MarketObservationRecord(
                observation_id="bt-future-sap",
                market_venue="SAP",
                product="NBP day-ahead",
                price=999.0,
                unit="GBP/MWh",
                currency="GBP",
                period_start_utc=datetime(2026, 7, 3, tzinfo=UTC),
                period_end_utc=datetime(2026, 7, 4, tzinfo=UTC),
                observed_at_utc=datetime(2026, 7, 2, 23, 0, tzinfo=UTC),
                source_system="SAP_Sim",
                source_reference="bt:future:sap",
                freshness="simulated_live",
                quality_score=0.6,
                research_only=True,
                metadata_json={"hub": "NBP", "tenor": "day-ahead"},
            )
        )
        session.commit()

    run = client.post("/api/strategy-runs", json=_backtest_payload(version_id))
    assert run.status_code == 200
    events = client.get(
        f"/api/strategy-runs/{run.json()['data']['run_id']}/events"
    )
    assert events.json()["data"][0]["day_ahead_average_gbp_mwh"] == 25.0


def test_draft_version_cannot_backtest(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    assert client.post(
        "/api/strategies",
        json={"strategy_id": "draft-bt", "name": "Draft BT"},
    ).status_code == 200
    version = client.post(
        "/api/strategies/draft-bt/versions",
        json=_definition_body(),
    )
    version_id = version.json()["data"]["strategy_version_id"]

    response = client.post("/api/strategy-runs", json=_backtest_payload(version_id))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "strategy_version_not_frozen"


def test_invalid_period_and_parameter_overrides_rejected(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)

    invalid_period = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(
            version_id,
            evaluation_period_start_utc="2026-07-03T00:00:00Z",
            evaluation_period_end_utc="2026-07-01T00:00:00Z",
        ),
    )
    assert invalid_period.status_code == 422
    assert invalid_period.json()["detail"]["code"] == "backtest_request_invalid"

    overrides = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(version_id, parameter_values={"weight": 2.0}),
    )
    assert overrides.status_code == 422
    assert overrides.json()["detail"]["code"] == "backtest_request_invalid"


def test_experiment_create_get_and_run_link(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    experiment = client.post(
        "/api/backtest-experiments",
        json={
            "strategy_id": "bt-api-strategy",
            "base_strategy_version_id": version_id,
            "name": "Single run proof",
            "hypothesis": "intraday premium persists",
            "evaluation_period_start_utc": "2026-07-01T00:00:00Z",
            "evaluation_period_end_utc": "2026-07-03T00:00:00Z",
        },
    )
    assert experiment.status_code == 200, experiment.text
    experiment_id = experiment.json()["data"]["experiment_id"]

    run = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(version_id, experiment_id=experiment_id),
    )
    assert run.status_code == 200, run.text
    run_id = run.json()["data"]["run_id"]

    fetched = client.get(f"/api/backtest-experiments/{experiment_id}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["run_ids"] == [run_id]


def test_unknown_backtest_run_events_are_404(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())

    assert client.get("/api/strategy-runs/missing/events").status_code == 404
    assert client.get("/api/strategy-runs/missing/series").status_code == 404


def test_legacy_evaluation_path_still_works(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)

    evaluation = client.post(
        "/api/strategy-runs",
        json={"strategy_version_id": version_id, "run_type": "EVALUATION"},
    )

    assert evaluation.status_code == 200
    assert evaluation.json()["data"]["run_type"] == "EVALUATION"
