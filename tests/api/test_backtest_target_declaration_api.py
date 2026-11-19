"""HTTP mapping of the CR-04 target-declaration refusal and engine/2 enablement.

Both backtest entry points (the single run and the experiment-grouped run)
reach exactly one application service. An undeclared frozen version is refused
with a structured 422 carrying the stable ``target_delivery_not_declared`` code
and writes nothing; a completely declared version runs engine/2 and persists
engine/2 provenance. The client renders the stable ``code``, so this test pins
that mapping.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.models import StrategyDataSnapshotRecord, StrategyRunRecord
from tests.api.test_backtest_api import (
    HEADERS,
    _backtest_payload,
    _configure_db,
    _definition_body,
    _seed_observations,
)


def _create_undeclared_frozen_version(client: TestClient) -> str:
    """A frozen version that declares no evidence target (the refusal fixture)."""

    created = client.post(
        "/api/strategies",
        json={"strategy_id": "bt-api-strategy", "name": "BT API strategy"},
    )
    assert created.status_code == 200, created.text
    body = _definition_body()
    body["definition"]["components"][0].pop("evidence_targets", None)
    version = client.post("/api/strategies/bt-api-strategy/versions", json=body)
    assert version.status_code == 200, version.text
    version_id = version.json()["data"]["strategy_version_id"]
    frozen = client.post(f"/api/strategy-versions/{version_id}/freeze")
    assert frozen.status_code == 200, frozen.text
    return version_id


def _client(tmp_path, monkeypatch) -> tuple[TestClient, str, str]:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_undeclared_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)
    return client, version_id, database_url


def _create_frozen_version_with_body(client: TestClient, body: dict) -> str:
    created = client.post(
        "/api/strategies",
        json={"strategy_id": "bt-api-strategy", "name": "BT API strategy"},
    )
    assert created.status_code == 200, created.text
    version = client.post("/api/strategies/bt-api-strategy/versions", json=body)
    assert version.status_code == 200, version.text
    version_id = version.json()["data"]["strategy_version_id"]
    frozen = client.post(f"/api/strategy-versions/{version_id}/freeze")
    assert frozen.status_code == 200, frozen.text
    return version_id


def _assert_no_run_or_snapshot(database_url: str) -> None:
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        assert session.query(StrategyRunRecord).count() == 0
        assert session.query(StrategyDataSnapshotRecord).count() == 0


def test_an_undeclared_backtest_is_a_structured_422(tmp_path, monkeypatch) -> None:
    client, version_id, database_url = _client(tmp_path, monkeypatch)

    refused = client.post("/api/strategy-runs", json=_backtest_payload(version_id))

    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "target_delivery_not_declared"
    assert "fork" in detail["message"].lower()
    _assert_no_run_or_snapshot(database_url)

    jobs = TestClient(create_app(Settings(api_profile="release"))).get(
        "/api/jobs", params={"kind": "BACKTEST"}, headers=HEADERS
    )
    assert jobs.status_code == 200
    assert jobs.json()["data"] == []


def test_an_experiment_grouped_run_maps_the_same_code(tmp_path, monkeypatch) -> None:
    client, version_id, _ = _client(tmp_path, monkeypatch)
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

    refused = client.post(
        "/api/strategy-runs",
        json=_backtest_payload(version_id, experiment_id=experiment_id),
    )

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "target_delivery_not_declared"


def test_the_future_window_code_is_unchanged_by_the_new_guard(tmp_path, monkeypatch) -> None:
    client, version_id, database_url = _client(tmp_path, monkeypatch)
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
    _assert_no_run_or_snapshot(database_url)


def test_legacy_evaluation_is_not_guarded(tmp_path, monkeypatch) -> None:
    # CR-04 refuses new *historical* runs only. The existing EVALUATION/scenario
    # path keeps its current behaviour.
    client, version_id, _ = _client(tmp_path, monkeypatch)

    evaluation = client.post(
        "/api/strategy-runs",
        json={"strategy_version_id": version_id, "run_type": "EVALUATION"},
    )

    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["data"]["run_type"] == "EVALUATION"


def test_a_declared_version_runs_engine2_through_the_same_endpoint(
    tmp_path, monkeypatch
) -> None:
    from tests.api.test_backtest_api import _create_frozen_version

    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    version_id = _create_frozen_version(client)
    _seed_observations(tmp_path, monkeypatch, database_url)

    run = client.post("/api/strategy-runs", json=_backtest_payload(version_id))

    assert run.status_code == 200, run.text
    data = run.json()["data"]
    assert data["backtest_engine_version"] == "backtest-engine/2"
    assert data["backtest_metrics"]["events_reusing_admitted_price_refs"] == 0
    assert data["backtest_metrics"]["events_with_simulated_evidence"] == 2
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        assert session.query(StrategyRunRecord).count() == 1
        assert session.query(StrategyDataSnapshotRecord).count() == 1


def test_a_multi_component_definition_is_a_structured_422(tmp_path, monkeypatch) -> None:
    # Bounded first engine/2 supports exactly one OCM_VS_DAY_AHEAD component; a
    # second one could cross-pollinate price names with different hubs/targets.
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    body = _definition_body()
    second = copy.deepcopy(body["definition"]["components"][0])
    second["component_id"] = "ocm-da-2"
    body["definition"]["components"].append(second)
    version_id = _create_frozen_version_with_body(client, body)
    _seed_observations(tmp_path, monkeypatch, database_url)

    refused = client.post("/api/strategy-runs", json=_backtest_payload(version_id))

    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "target_component_scope_unsupported"
    assert "OCM_VS_DAY_AHEAD" in detail["message"]
    _assert_no_run_or_snapshot(database_url)


def test_a_name_in_two_leg_roles_is_a_structured_422(tmp_path, monkeypatch) -> None:
    database_url = _configure_db(tmp_path, monkeypatch)
    client = TestClient(create_app())
    body = _definition_body()
    component = body["definition"]["components"][0]
    # Case-insensitively the same name as both the day-ahead and intraday leg.
    component["extension_json"]["intraday_price_names"] = ["sap"]
    version_id = _create_frozen_version_with_body(client, body)
    _seed_observations(tmp_path, monkeypatch, database_url)

    refused = client.post("/api/strategy-runs", json=_backtest_payload(version_id))

    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "target_evidence_mapping_ambiguous"
    assert "SAP" in detail["message"]
    _assert_no_run_or_snapshot(database_url)
