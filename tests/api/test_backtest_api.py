"""API tests for the temporally safe professional backtest path."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MarketObservationRecord,
    StrategyDataSnapshotRecord,
    StrategyRunRecord,
)

PUBLIC_TOKEN = "test-public-api-token"
HEADERS = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}


def _configure_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "backtest-api.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    with Session(engine) as session:
        owner = create_identity_principal(
            session,
            name="registry-owner",
            display_name="Registry Owner",
            role="ANALYST",
            data_scopes=["*"],
        )
        _, bearer = create_identity_api_key(session, owner.principal_id, scopes=["*"])
        session.commit()
    original_init = TestClient.__init__

    def owner_client(self, app, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("X-Eurogas-Api-Key", "test-public-api-token")
        headers.setdefault("X-Eurogas-Identity", bearer)
        original_init(self, app, *args, headers=headers, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", owner_client)
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
                    # CR-04 engine/2 needs a complete frozen per-leg target
                    # mapping. Rolling current-gas-day targets are declared here
                    # so the seeded gas-day windows below match exactly.
                    "evidence_targets": [
                        {
                            "leg_id": "day_ahead",
                            "price_names": ["SAP"],
                            "role": "DELIVERY_PRICE",
                            "hub": "NBP",
                            "tenor": "day-ahead",
                            "price_basis": "MID",
                            "target_basis": "GAS_DAY",
                            "calendar_id": "EU-CAM-UTC-2025",
                            "gas_day_offset": 0,
                        },
                        {
                            "leg_id": "intraday",
                            "price_names": ["ICE_OCM"],
                            "role": "DELIVERY_PRICE",
                            "hub": "NBP",
                            "tenor": "within-day",
                            "price_basis": "MID",
                            "target_basis": "GAS_DAY",
                            "calendar_id": "EU-CAM-UTC-2025",
                            "gas_day_offset": 0,
                        },
                    ],
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
            # EU-CAM-UTC-2025 gas day in July (BST): 04:00Z to 04:00Z.
            delivery_start = datetime(2026, 7, 1 + day, 4, 0, tzinfo=UTC)
            delivery_end = datetime(2026, 7, 2 + day, 4, 0, tzinfo=UTC)
            observed = datetime(2026, 7, 1 + day, 4, 30, tzinfo=UTC)
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
                        period_start_utc=delivery_start,
                        period_end_utc=delivery_end,
                        observed_at_utc=observed,
                        source_system=source,
                        source_reference=f"bt:{observation_id}:{day}",
                        freshness="simulated_live",
                        quality_score=0.6,
                        research_only=True,
                        metadata_json={
                            "hub": "NBP",
                            "tenor": tenor,
                            # Explicit CR-04 evidence metadata: the target-aware
                            # selector never infers a role or basis.
                            "evidence_role": "DELIVERY_PRICE",
                            "price_basis": "MID",
                            "price_timing": (
                                "instant" if observation_id == "ice" else "daily_assessment"
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


def test_create_backtest_run_and_retrieve_events_series_attribution(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    run = client.post("/api/strategy-runs", json=_backtest_payload(version_id))
    assert run.status_code == 200, run.text
    data = run.json()["data"]
    assert data["run_type"] == "BACKTEST"
    # CR-04 engine/2: a declared frozen version now runs the target-aware
    # selector. The seeded gas-day windows are the same admissible evidence the
    # legacy name-only selector used, so the financial expectations below are
    # unchanged; only the engine identity and the evidence provenance move.
    assert data["backtest_engine_version"] == "backtest-engine/2"
    assert data["status"] == "COMPLETED_WITH_WARNINGS"
    assert data["manifest_json"]["parameters"] == {}
    assert data["backtest_metrics"]["evaluation_count"] == 2
    assert data["backtest_metrics"]["candidate_decision_count"] == 2
    # Reviewer-readable delta versus engine/1 (see result.md): the legacy name-only
    # selector averaged every same-name row available at T, so decision 2 averaged
    # SAP {25, 26} -> 25.5 and ICE {30, 31} -> 30.5 (gross 1850). Engine/2 admits
    # exactly the one row per leg whose half-open interval equals the resolved
    # target, so decision 2 values SAP 26.0 / ICE 31.0 (gross 1900, +50).
    assert data["backtest_metrics"]["gross_indicative_pnl_gbp"] == 1900.0
    assert data["backtest_metrics"]["modeled_costs_gbp"] == 100.0
    assert data["backtest_metrics"]["net_indicative_pnl_gbp"] == 1800.0
    assert data["manifest_json"]["evidence"]["evidence_selection"]["rules_version"] == (
        "target-evidence-selection/v1"
    )
    assert len(data["manifest_json"]["evidence"]["evidence_selection"]["target_declarations"]) == 2
    run_id = data["run_id"]

    events = client.get(f"/api/strategy-runs/{run_id}/events")
    assert events.status_code == 200
    assert [row["decision_sequence"] for row in events.json()["data"]] == [1, 2]
    assert events.json()["data"][0]["outcome"] == "COMPLETED_WITH_WARNINGS"
    # The resolved target and per-leg selection reason survive the round trip
    # through the existing event JSON (no migration).
    trace = events.json()["data"][0]["evidence_selection_trace"]
    assert {item["price_name"] for item in trace} == {"SAP", "ICE_OCM"}
    assert all(item["outcome"] == "MATCHED" for item in trace)
    assert trace[0]["resolved_start_utc"] == "2026-07-01T04:00:00Z"

    series = client.get(f"/api/strategy-runs/{run_id}/series")
    assert series.status_code == 200
    assert len(series.json()["data"]) == 2
    assert series.json()["data"][1]["cumulative_net_indicative_pnl_gbp"] == 1800.0

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
    events = client.get(f"/api/strategy-runs/{run.json()['data']['run_id']}/events")
    assert events.json()["data"][0]["day_ahead_average_gbp_mwh"] == 25.0


def test_draft_version_cannot_backtest(tmp_path, monkeypatch) -> None:
    _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/strategies",
            json={"strategy_id": "draft-bt", "name": "Draft BT"},
        ).status_code
        == 200
    )
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
    # The experiment-grouped entry point runs the same engine/2 path.
    assert run.json()["data"]["backtest_engine_version"] == "backtest-engine/2"
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


# ---------------------------------------------------------------------------
# Analysis Snapshot citation on the strategy backtest run (Wave 4 scope)
# ---------------------------------------------------------------------------


def test_backtest_run_echoes_the_snapshot_it_was_computed_against(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)
    snapshot_id = client.post("/api/analysis-snapshots", json={}).json()["data"]["snapshot_id"]

    run = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(version_id, analysis_snapshot_id=snapshot_id),
    )

    assert run.status_code == 200, run.text
    data = run.json()["data"]
    assert data["analysis_snapshot_id"] == snapshot_id
    # The citation is an echo, not a second computation: the run is unchanged.
    assert data["backtest_metrics"]["evaluation_count"] == 2
    # Engine/2 one-row-per-leg selection at decision 2 (delta documented above).
    assert data["backtest_metrics"]["net_indicative_pnl_gbp"] == 1800.0


def test_backtest_run_refuses_an_unknown_snapshot_reference(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    refused = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(version_id, analysis_snapshot_id="asnap-missing"),
    )

    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "analysis_snapshot_not_found"
    # Verified before the run: no run row and no job were created.
    jobs = TestClient(create_app(Settings(api_profile="release"))).get(
        "/api/jobs", params={"kind": "BACKTEST"}, headers=HEADERS
    )
    assert jobs.json()["data"] == []


# ---------------------------------------------------------------------------
# Unified job tracking on the strategy backtest run (Wave 8 scope)
# ---------------------------------------------------------------------------


def test_backtest_run_is_tracked_as_a_job_with_its_persisted_run(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    run = client.post("/api/strategy-runs", json=_backtest_payload(version_id))
    assert run.status_code == 200, run.text
    data = run.json()["data"]
    # No reproducibility reference was cited: the additive field is absent, so
    # the previous payload is byte-identical for that caller.
    assert "analysis_snapshot_id" not in data

    jobs = TestClient(create_app(Settings(api_profile="release"))).get(
        "/api/jobs", params={"kind": "BACKTEST"}, headers=HEADERS
    )
    assert jobs.status_code == 200
    rows = jobs.json()["data"]
    assert len(rows) == 1
    assert rows[0]["status"] == "SUCCEEDED"
    # The artefact is the persisted run the endpoint returned.
    assert rows[0]["output_refs"] == [f"strategy_run:{data['run_id']}"]
    assert rows[0]["scope_refs"] == [f"STRATEGY_VERSION:{version_id}"]
    assert rows[0]["provenance"] == ["strategy-registry"]
    assert rows[0]["input_hash"]


def test_backtest_run_job_commits_the_snapshot_it_cited(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)
    snapshot_id = client.post("/api/analysis-snapshots", json={}).json()["data"]["snapshot_id"]

    run = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(version_id, analysis_snapshot_id=snapshot_id),
    )
    assert run.status_code == 200, run.text

    jobs = TestClient(create_app(Settings(api_profile="release"))).get(
        "/api/jobs", params={"kind": "BACKTEST"}, headers=HEADERS
    )
    rows = jobs.json()["data"]
    assert len(rows) == 1
    assert rows[0]["snapshot_id"] == snapshot_id
    assert rows[0]["output_refs"] == [f"strategy_run:{run.json()['data']['run_id']}"]


def test_backtest_run_refuses_a_period_that_has_not_occurred(tmp_path, monkeypatch) -> None:
    # BACKTEST_ENGINE_SPEC section 1 promises a historical evaluation. A window
    # ending after the request instant is not historical, and the run must be
    # refused before any evidence snapshot or run row is written.
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    now = datetime.now(UTC).replace(microsecond=0)
    refused = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(
            version_id,
            evaluation_period_start_utc=(now - timedelta(days=1)).isoformat(),
            evaluation_period_end_utc=(now + timedelta(days=30)).isoformat(),
        ),
    )

    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "backtest_request_invalid"
    assert "after the request time" in detail["message"]

    # No run row, evidence snapshot or tracked job survives the refusal.
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        assert session.query(StrategyRunRecord).count() == 0
        assert session.query(StrategyDataSnapshotRecord).count() == 0

    jobs = TestClient(create_app(Settings(api_profile="release"))).get(
        "/api/jobs", params={"kind": "BACKTEST"}, headers=HEADERS
    )
    assert jobs.status_code == 200
    assert jobs.json()["data"] == []
