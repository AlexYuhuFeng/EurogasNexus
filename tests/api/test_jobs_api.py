"""Unified Job API tests (Architecture V2 Wave 8).

The job surface must be honest: it lists what the deployment actually ran, records
artefacts and stable failure codes, and refuses to cancel a job that has already
finished.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.jobs import job_input_hash, track_job
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base

PUBLIC_TOKEN = "test-public-api-token"
HEADERS = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}


def _db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "jobs.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def test_a_tracked_job_records_its_outcome_and_outputs(tmp_path, monkeypatch) -> None:
    database_url = _db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)

    with Session(engine) as session:
        with track_job(
            session,
            kind="DATASET_BUILD",
            principal="analyst.one",
            inputs={"dataset_spec_id": "spec-1"},
            correlation_id="corr-9",
        ) as job:
            job.add_output("dataset_snapshot:ds-1")
            job.add_output("dataset_snapshot:ds-1")
        session.commit()
        job_id = job.job_id

    client = TestClient(create_app(Settings(api_profile="release")))

    one = client.get(f"/api/jobs/{job_id}", headers=HEADERS)
    assert one.status_code == 200
    payload = one.json()["data"]
    assert payload["status"] == "SUCCEEDED"
    assert payload["kind"] == "DATASET_BUILD"
    assert payload["principal"] == "analyst.one"
    assert payload["output_refs"] == ["dataset_snapshot:ds-1"]
    assert payload["input_hash"] == job_input_hash({"dataset_spec_id": "spec-1"})
    assert payload["correlation_id"] == "corr-9"
    assert payload["duration_seconds"] >= 0
    assert payload["error_code"] == ""

    listed = client.get("/api/jobs", headers=HEADERS)
    assert listed.status_code == 200
    assert [row["job_id"] for row in listed.json()["data"]] == [job_id]

    filtered = client.get("/api/jobs", params={"kind": "BACKTEST"}, headers=HEADERS)
    assert filtered.json()["data"] == []


def test_a_failed_tracked_job_keeps_the_stable_code_and_reraises(tmp_path, monkeypatch) -> None:
    database_url = _db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)

    class Boom(RuntimeError):
        code = "runtime_db_unavailable"

    with Session(engine) as session:
        try:
            with track_job(session, kind="OPTIMISATION", principal="analyst.one"):
                raise Boom("the store is down")
        except Boom:
            session.commit()
        else:  # pragma: no cover - the tracker must never swallow the failure
            raise AssertionError("the original exception must propagate")

    client = TestClient(create_app(Settings(api_profile="release")))
    rows = client.get("/api/jobs", params={"kind": "OPTIMISATION"}, headers=HEADERS).json()["data"]
    assert len(rows) == 1
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["error_code"] == "runtime_db_unavailable"
    assert rows[0]["error_message"] == "Boom"
    assert rows[0]["cancellable"] is False


def test_cancellation_is_refused_for_a_finished_job(tmp_path, monkeypatch) -> None:
    database_url = _db(tmp_path, monkeypatch)
    engine = create_engine(database_url, future=True)

    with Session(engine) as session:
        with track_job(session, kind="REPORT", principal="analyst.one") as job:
            job.add_output("generated_report:r-1")
        session.commit()

        from eurogas_nexus.db.repositories.jobs import create_job, start_job

        running = create_job(session, kind="BACKTEST", principal="analyst.one")
        start_job(session, str(running["job_id"]))
        session.commit()
        finished_id = job.job_id
        running_id = str(running["job_id"])

    client = TestClient(create_app(Settings(api_profile="release")))

    refused = client.post(f"/api/jobs/{finished_id}/cancel", headers=HEADERS)
    assert refused.status_code == 409
    assert refused.json()["detail"]["error"] == "job_already_finished"

    cancelled = client.post(f"/api/jobs/{running_id}/cancel", headers=HEADERS)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    missing = client.post("/api/jobs/job-does-not-exist/cancel", headers=HEADERS)
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "unknown_job"

    unknown = client.get("/api/jobs/job-does-not-exist", headers=HEADERS)
    assert unknown.status_code == 404


def test_the_job_surface_requires_authentication(tmp_path, monkeypatch) -> None:
    _db(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))

    assert client.get("/api/jobs").status_code == 401
