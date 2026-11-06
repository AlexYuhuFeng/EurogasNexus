"""Real authenticated HTTP + persisted Job/functional-run integration."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import functional_runs
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from tests.api.test_nwe_balance_scenario import scenario


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'functional.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    clients = {}
    with Session(engine) as session:
        for name in ("alice", "bob"):
            owner = create_identity_principal(
                session, name=name, display_name=name, role="ANALYST", data_scopes=["*"]
            )
            _, bearer = create_identity_api_key(session, owner.principal_id, scopes=["*"])
            clients[name] = TestClient(
                create_app(Settings(api_profile="release")),
                headers={
                    "X-Eurogas-Api-Key": "test-public-api-token",
                    "X-Eurogas-Identity": bearer,
                },
            )
        session.commit()
    yield clients, sessionmaker(engine), engine
    for client in clients.values():
        client.close()
    engine.dispose()


def submit(client, key="one", inputs=None):
    return client.post(
        "/api/functional-runs",
        json={"kind": "NWE_BALANCE", "inputs": inputs or scenario(), "idempotency_key": key},
    )


def test_persisted_run_idempotency_ownership_and_exact_replay(desk):
    clients, _, _ = desk
    alice, bob = clients["alice"], clients["bob"]
    response = submit(alice)
    assert response.status_code == 202, response.text
    run = response.json()["data"]
    path = f"/api/functional-runs/{run['run_id']}"
    completed = alice.get(path).json()["data"]
    assert completed["status"] == "SUCCEEDED", completed
    assert completed["result"]["data"]["status"] == "WEATHER_COMPLETE"
    assert bob.get(path).status_code == 404
    assert submit(alice).json()["data"]["run_id"] == run["run_id"]
    changed = scenario()
    changed["inventory_twh"] = 200
    assert submit(alice, inputs=changed).status_code == 409
    replay = alice.post(path + "/replay", json={"idempotency_key": "replay"})
    assert replay.status_code == 202, replay.text
    replay_path = f"/api/functional-runs/{replay.json()['data']['run_id']}"
    replay_result = alice.get(replay_path).json()["data"]
    assert replay_result["result"] == completed["result"]
    compared = alice.post(path + "/compare", json={"other_run_id": replay_result["run_id"]})
    assert compared.json()["data"]["same_result"]
    assert compared.json()["data"]["same_inputs"]


def test_cancel_queued_job_prevents_computation_and_recovery_survives_restart(desk, monkeypatch):
    clients, factory, _ = desk
    execute = functional_runs.execute
    monkeypatch.setattr(functional_runs, "execute", lambda *args: None)
    run = submit(clients["alice"]).json()["data"]
    cancelled = clients["alice"].post(f"/api/jobs/{run['job_id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    monkeypatch.setattr(functional_runs, "execute", execute)
    execute(factory, run["run_id"])
    result = clients["alice"].get(f"/api/functional-runs/{run['run_id']}").json()["data"]
    assert result["status"] == "CANCELLED" and result["result"] is None
    monkeypatch.setattr(functional_runs, "execute", lambda *args: None)
    queued = submit(clients["alice"], key="recovered").json()["data"]
    monkeypatch.setattr(functional_runs, "execute", execute)
    assert functional_runs.run_pending(factory) == 1
    result = clients["alice"].get(f"/api/functional-runs/{queued['run_id']}").json()["data"]
    assert result["status"] == "SUCCEEDED"


def test_invalid_inner_input_returns_422_and_no_job(desk):
    clients, _, _ = desk
    assert submit(clients["alice"], inputs={"bad": "field"}).status_code == 422


def test_validation_freeze_prediction_and_shadow_evaluation(desk):
    from tests.unit.test_functional_analysis_contracts import validation

    clients, _, _ = desk
    client = clients["alice"]
    body = {"kind": "WEATHER_VALIDATION", "inputs": validation(), "idempotency_key": "validation"}
    response = client.post("/api/functional-runs", json=body)
    assert response.status_code == 202, response.text
    run_id = response.json()["data"]["run_id"]
    registered = client.post("/api/functional-models", json={"other_run_id": run_id})
    assert registered.status_code == 200, registered.text
    model = registered.json()["data"]
    assert model["status"] == "SHADOW"
    assert clients["bob"].get(f"/api/functional-models/{model['model_id']}").status_code == 404
    route = f"/api/functional-models/{model['model_id']}"
    prediction = client.post(
        route + "/predict",
        json={
            "idempotency_key": "forecast",
            "prediction_origin": "2026-04-15T06:00:00Z",
            "feature_policy_hash": "a" * 64,
            "features": [
                {
                    "day": "2026-04-16",
                    "hdd": 10,
                    "available_at": "2026-04-15T05:00:00Z",
                    "source_reference": "fixture:forecast",
                }
            ],
        },
    )
    assert prediction.status_code == 202, prediction.text
    prediction_id = prediction.json()["data"]["run_id"]
    computed = client.get(f"/api/functional-runs/{prediction_id}").json()["data"]
    assert computed["status"] == "SUCCEEDED", computed
    assert computed["result"]["points"][0]["call_gwh"] == pytest.approx(2700)
    actual = {
        "day": "2026-04-16",
        "norway_gwh": 1000,
        "lng_gwh": 400,
        "storage_net_withdrawal_gwh": 1400,
        "available_at": "2026-04-17T06:00:00Z",
        "source_reference": "fixture:actual",
    }
    evaluation = client.post(
        route + "/evaluate",
        json={
            "idempotency_key": "evaluate",
            "prediction_run_id": prediction_id,
            "actuals": [actual],
            "evaluation_as_of": "2026-04-18T00:00:00Z",
            "maximum_mae_gwh": 50,
        },
    )
    assert evaluation.status_code == 202, evaluation.text
    measured = client.get(f"/api/functional-runs/{evaluation.json()['data']['run_id']}").json()[
        "data"
    ]
    assert measured["result"]["mae_gwh"] == pytest.approx(100)
    assert measured["result"]["drifted"] is True
    # Analyst can inspect/shadow, but cannot perform reviewer adoption.
    assert (
        client.patch(
            route, json={"status": "RESEARCH_APPROVED", "note": "reviewed evidence"}
        ).status_code
        == 403
    )


def test_dependency_revisions_mark_stale_without_rewriting_input_snapshot(desk):
    clients, _, _ = desk
    client = clients["alice"]
    response = client.post(
        "/api/functional-runs",
        json={
            "kind": "NWE_BALANCE",
            "inputs": scenario(),
            "idempotency_key": "versions",
            "version_refs": {"contract:123": "v1"},
        },
    )
    assert response.status_code == 202, response.text
    path = f"/api/functional-runs/{response.json()['data']['run_id']}"
    before = client.get(path).json()["data"]
    changed = client.post(
        "/api/functional-runs/reconcile", json={"changes": {"contract:123": "v2"}}
    )
    assert changed.status_code == 200, changed.text
    after = client.get(path).json()["data"]
    assert after["stale_dependencies"] == ["contract:123"]
    assert before["manifest"] == after["manifest"]
    assert before["result"] == after["result"]
    foreign = clients["bob"].post(
        "/api/functional-runs/reconcile", json={"changes": {"contract:123": "v3"}}
    )
    assert foreign.json()["data"]["recompute_required"] == []


def test_worker_failure_is_persisted_and_does_not_claim_success(desk, monkeypatch):
    clients, _, _ = desk

    def failure(*args):
        raise TimeoutError("deadline")

    monkeypatch.setattr(functional_runs, "compute", failure)
    response = submit(clients["alice"])
    path = f"/api/functional-runs/{response.json()['data']['run_id']}"
    result = clients["alice"].get(path).json()["data"]
    assert result["status"] == "FAILED"
    assert result["error_code"] == "FUNCTIONAL_TIMEOUT"
    assert result["result"] is None


def test_reviewed_region_profile_uses_certified_stored_weather(desk, monkeypatch):
    from sqlalchemy import select

    from eurogas_nexus.db.models.identity import IdentityPrincipalRecord
    from tests.api.test_balance_persisted_weather import payload as stored_payload
    from tests.api.test_weather_degree_days_api import (
        EARLY_RECEIPT,
        FUTURE_EXPIRY,
        _certification,
        _seed_full_day,
    )

    clients, factory, _ = desk
    client = clients["alice"]
    body = stored_payload()
    window = body["persisted_weather"][0]
    configuration = {k: v for k, v in window.items() if k not in {"gas_days", "prediction_origin"}}
    created = client.post(
        "/api/functional-runs",
        json={"kind": "WEATHER_PROFILE", "inputs": configuration, "idempotency_key": "region"},
    )
    assert created.status_code == 202, created.text
    frozen = client.post(
        "/api/functional-models", json={"other_run_id": created.json()["data"]["run_id"]}
    )
    assert frozen.status_code == 200, frozen.text
    model = frozen.json()["data"]
    body["weather_profile_id"] = model["model_id"]
    assert client.post("/api/market/nwe-balance", json=body).status_code == 409
    with factory() as session:
        owner = session.scalar(
            select(IdentityPrincipalRecord).where(IdentityPrincipalRecord.name == "alice")
        )
        owner.roles = ["ANALYST", "REVIEWER"]
        _seed_full_day(
            session,
            monkeypatch,
            temperature_c=4,
            receipt=EARLY_RECEIPT,
            suffix=b"-reviewed-profile",
        )
        session.add(_certification(expires_at_utc=FUTURE_EXPIRY))
        session.commit()
    reviewed = client.patch(
        f"/api/functional-models/{model['model_id']}",
        json={"status": "RESEARCH_APPROVED", "note": "Reviewed NWE regional weighting method"},
    )
    assert reviewed.status_code == 200, reviewed.text
    response = client.post("/api/market/nwe-balance", json=body)
    assert response.status_code == 200, response.text
    assert (
        response.json()["data"]["weather_evidence"][0]["region_profile_version"]
        == model["version_hash"]
    )
    body["persisted_weather"][0]["heating_base_c"] = 12
    assert client.post("/api/market/nwe-balance", json=body).status_code == 422


def test_idempotent_runtime_retry_reuses_the_original_data_resolution(desk, monkeypatch):
    from eurogas_nexus.api import balance_weather
    from eurogas_nexus.application.nwe_balance_scenario import NweBalanceScenarioRequest

    clients, _, _ = desk
    original = scenario()
    calls = []

    def resolve(payload, request):
        calls.append(payload)
        return NweBalanceScenarioRequest.model_validate(original), [], ["first-resolution"]

    monkeypatch.setattr(balance_weather, "compose_balance_weather", resolve)
    inputs = {
        "use_runtime_history": True,
        "prediction_origin": original["prediction_origin"],
        "start": original["start"],
        "days": original["days"],
    }
    first = submit(clients["alice"], inputs=inputs)
    second = submit(clients["alice"], inputs=inputs)
    assert first.status_code == second.status_code == 202
    assert first.json()["data"]["run_id"] == second.json()["data"]["run_id"]
    assert len(calls) == 1
    assert second.json()["data"]["manifest"]["evidence_warnings"] == ["first-resolution"]
