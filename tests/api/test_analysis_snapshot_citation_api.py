"""Analysis Snapshot citation on the analysis-query and portfolio-report paths.

Architecture V2 Wave 4 scope, extended past the route-cost and backtest paths the
citation was first delivered on. The contract these tests pin is the same one those
paths follow:

- an optional ``analysis_snapshot_id`` is verified against persisted snapshots
  *before* the run does anything else, so an unverifiable citation fails closed
  (503 without a runtime store, 422 for an unknown id);
- the produced result echoes the reference only when one was supplied, so a caller
  that cites nothing keeps its previous payload exactly;
- the citation is durable: it is part of the persisted analysis record, and the
  tracked report run records it as the snapshot the report was computed against.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AnalysisRunRecord, GeneratedReportRecord

PUBLIC_TOKEN = "test-public-api-token"
HEADERS = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}

ANALYSIS_BODY = {
    "question": "Summarize current TTF context",
    "task": "DB_INQUIRY",
    "invoke_provider": False,
}

REPORT_BODY = {
    "title": "Current portfolio report",
    "invoke_provider": False,
}


def _database(tmp_path, monkeypatch) -> str:
    """Point the runtime store at a fresh SQLite database."""

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'analysis-citation.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _snapshot_id(client: TestClient, *, headers: dict[str, str] | None = None) -> str:
    response = client.post("/api/analysis-snapshots", json={}, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]["snapshot_id"]


def _no_database(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)


# ---------------------------------------------------------------------------
# POST /api/analysis/query
# ---------------------------------------------------------------------------


def test_analysis_query_echoes_the_snapshot_it_cited(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())
    snapshot_id = _snapshot_id(client)

    response = client.post(
        "/api/analysis/query",
        json={**ANALYSIS_BODY, "analysis_snapshot_id": snapshot_id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["analysis_snapshot_id"] == snapshot_id
    # The citation is an echo, not a re-computation: the deterministic answer and its own
    # input snapshot are unchanged.
    assert data["provider_status"] == "not_invoked"
    assert data["snapshot_id"]
    assert data["snapshot_id"] != snapshot_id


def test_analysis_query_without_a_citation_keeps_the_previous_payload(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post("/api/analysis/query", json=ANALYSIS_BODY)

    assert response.status_code == 200
    # The additive field is absent rather than null: a caller that cites nothing keeps the
    # payload it had before the citation existed.
    assert "analysis_snapshot_id" not in response.json()["data"]


def test_analysis_query_refuses_an_unknown_snapshot_reference(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/analysis/query",
        json={**ANALYSIS_BODY, "analysis_snapshot_id": "asnap-missing"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "analysis_snapshot_not_found"


def test_analysis_query_cannot_verify_a_reference_without_a_runtime_store(monkeypatch) -> None:
    _no_database(monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/analysis/query",
        json={**ANALYSIS_BODY, "analysis_snapshot_id": "asnap-any"},
    )

    # Fail closed: an unverifiable citation is not accepted, and the run does not happen.
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"


def test_analysis_query_persists_the_citation_with_the_record(tmp_path, monkeypatch) -> None:
    database_url = _database(tmp_path, monkeypatch)
    client = TestClient(create_app())
    snapshot_id = _snapshot_id(client)

    response = client.post(
        "/api/analysis/query",
        json={**ANALYSIS_BODY, "analysis_snapshot_id": snapshot_id},
    )
    assert response.status_code == 200
    analysis_id = response.json()["data"]["analysis_id"]

    # Re-reading the analysis must not lose the reference it cites: the citation travels in
    # the persisted record's own output snapshot, so it needs no schema change to survive.
    with Session(create_engine(database_url, future=True)) as session:
        row = session.scalars(
            select(AnalysisRunRecord).where(AnalysisRunRecord.analysis_id == analysis_id)
        ).one()
    assert row.output_snapshot["analysis_snapshot_id"] == snapshot_id


# ---------------------------------------------------------------------------
# POST /api/reports/portfolio
# ---------------------------------------------------------------------------


def test_portfolio_report_echoes_the_snapshot_it_cited(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())
    snapshot_id = _snapshot_id(client)

    response = client.post(
        "/api/reports/portfolio",
        json={**REPORT_BODY, "analysis_snapshot_id": snapshot_id},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["analysis_snapshot_id"] == snapshot_id
    assert data["task"] == "PORTFOLIO_REPORT"


def test_portfolio_report_without_a_citation_keeps_the_previous_payload(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post("/api/reports/portfolio", json=REPORT_BODY)

    assert response.status_code == 200
    assert "analysis_snapshot_id" not in response.json()["data"]


def test_portfolio_report_refuses_an_unknown_snapshot_reference(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/reports/portfolio",
        json={**REPORT_BODY, "analysis_snapshot_id": "asnap-missing"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "analysis_snapshot_not_found"


def test_portfolio_report_cannot_verify_a_reference_without_a_runtime_store(monkeypatch) -> None:
    _no_database(monkeypatch)
    client = TestClient(create_app())

    response = client.post(
        "/api/reports/portfolio",
        json={**REPORT_BODY, "analysis_snapshot_id": "asnap-any"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "runtime_db_not_configured"


def test_portfolio_report_records_the_citation_on_its_job(tmp_path, monkeypatch) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    snapshot_id = _snapshot_id(client, headers=HEADERS)

    response = client.post(
        "/api/reports/portfolio",
        json={**REPORT_BODY, "analysis_snapshot_id": snapshot_id},
        headers=HEADERS,
    )
    assert response.status_code == 200

    rows = client.get("/api/jobs", params={"kind": "REPORT"}, headers=HEADERS).json()["data"]
    assert len(rows) == 1
    job = rows[0]
    # The tracked run records the reference it was computed against, so the citation is
    # durable in the job model as well as on the report itself.
    assert job["snapshot_id"] == snapshot_id
    assert job["status"] == "SUCCEEDED"


def test_portfolio_report_records_an_empty_reference_when_it_cited_nothing(
    tmp_path, monkeypatch
) -> None:
    _database(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post("/api/reports/portfolio", json=REPORT_BODY, headers=HEADERS)
    assert response.status_code == 200

    rows = client.get("/api/jobs", params={"kind": "REPORT"}, headers=HEADERS).json()["data"]
    assert len(rows) == 1
    # A report that cited nothing records an empty reference rather than a guess.
    assert rows[0]["snapshot_id"] == ""
    assert "analysis_snapshot_id" not in response.json()["data"]


def test_portfolio_report_record_keeps_its_sections_while_the_job_keeps_the_citation(
    tmp_path, monkeypatch
) -> None:
    database_url = _database(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    snapshot_id = _snapshot_id(client, headers=HEADERS)

    response = client.post(
        "/api/reports/portfolio",
        json={**REPORT_BODY, "analysis_snapshot_id": snapshot_id},
        headers=HEADERS,
    )
    assert response.status_code == 200
    report_id = response.json()["data"]["analysis_id"]

    with Session(create_engine(database_url, future=True)) as session:
        row = session.scalars(
            select(GeneratedReportRecord).where(GeneratedReportRecord.report_id == report_id)
        ).one()

    # The stored report keeps what it always kept - its sections and source references - and
    # the citation is durable on the tracked run and on the returned report. The report record
    # itself has no column for a cited reference, which is a stated limit rather than a claim:
    # this test asserts what the record does hold, not that it holds the citation.
    assert [section["section_id"] for section in row.sections]
    assert snapshot_id not in str(row.source_refs)
