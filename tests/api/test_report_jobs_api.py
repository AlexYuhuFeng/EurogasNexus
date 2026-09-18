"""Report run registration tests (Architecture V2 Wave 8, report path).

``POST /api/reports/portfolio`` persists its report best-effort inside the request, which
is why the path was left out of the unified job model: a job that cites an artefact the
store does not hold is worse than no job at all. Now that persistence reports whether it
really stored the report, the run registers into the job model with an honest artefact
list, and a configured store that refuses the write says so in the response instead of
failing silently.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import GeneratedReportRecord, JobRecord

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _configure_store(tmp_path, monkeypatch) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'report-jobs.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _report_body() -> dict:
    return {
        "title": "Current portfolio report",
        "invoke_provider": False,
        "duration_start_utc": datetime(2026, 9, 16, 4, 0, tzinfo=UTC).isoformat(),
        "duration_end_utc": datetime(2026, 9, 17, 4, 0, tzinfo=UTC).isoformat(),
    }


def test_a_stored_report_registers_a_job_that_cites_it(tmp_path, monkeypatch) -> None:
    database_url = _configure_store(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post("/api/reports/portfolio", json=_report_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert "REPORT_NOT_PERSISTED" not in data["warnings"]

    with Session(create_engine(database_url, future=True)) as session:
        reports = session.execute(select(GeneratedReportRecord)).scalars().all()
        jobs = session.execute(select(JobRecord)).scalars().all()

    assert [report.report_id for report in reports] == [data["analysis_id"]]
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "REPORT"
    assert job.status == "SUCCEEDED"
    # The artefact reference is the report that really exists, under its stored id.
    assert list(job.output_refs_json) == [f"generated_report:{data['analysis_id']}"]
    assert job.input_hash
    assert "portfolio-report" in list(job.provenance_json)


def test_a_refused_write_is_reported_and_cites_no_artefact(tmp_path, monkeypatch) -> None:
    database_url = _configure_store(tmp_path, monkeypatch)

    # A configured store that refuses the write: the run still succeeds, the response says
    # the report was not stored, and the job records no artefact it cannot back up.
    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.analysis._persist_report_if_db",
        lambda *_args, **_kwargs: (False, True),
    )
    client = TestClient(create_app())

    response = client.post("/api/reports/portfolio", json=_report_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert "REPORT_NOT_PERSISTED" in data["warnings"]

    with Session(create_engine(database_url, future=True)) as session:
        assert session.execute(select(GeneratedReportRecord)).scalars().all() == []
        jobs = session.execute(select(JobRecord)).scalars().all()

    assert len(jobs) == 1
    assert jobs[0].status == "SUCCEEDED"
    assert list(jobs[0].output_refs_json) == []


def test_a_deployment_without_a_store_reports_the_posture_not_a_failure(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())

    response = client.post("/api/reports/portfolio", json=_report_body())

    assert response.status_code == 200
    data = response.json()["data"]
    # No store configured is a declared posture (the envelope reports
    # runtime-db-not-configured), not a failed write, and no job is invented for it.
    assert "REPORT_NOT_PERSISTED" not in data["warnings"]
    assert response.json()["meta"]["source_references"] == ["runtime-db-not-configured"]
