"""The analysis and report selection refusal contract.

`POST /api/analysis/query` and `POST /api/reports/portfolio` accept six selection or
filter fields that the pipeline never reads. Accepting them would return a run over the
whole entitled snapshot while the caller believed their selection had been applied, so
both routes refuse a non-empty selection with `422 analysis_selection_not_supported`
naming every offending field - before the snapshot is loaded, before the run is tracked
and before any provider call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app

ANALYSIS_FIELDS = (
    "selected_terms",
    "selected_assets",
    "selected_contracts",
    "include_sections",
)

REPORT_FIELDS = (
    "portfolio_id",
    "selected_resources",
    "selected_contracts",
    "selected_strategies",
)


def _analysis_body(**overrides) -> dict:
    body = {"question": "Summarize current TTF context", "task": "DB_INQUIRY"}
    body.update(overrides)
    return body


def _report_body(**overrides) -> dict:
    body = {"title": "Current portfolio report"}
    body.update(overrides)
    return body


@pytest.mark.parametrize("field", ANALYSIS_FIELDS)
def test_analysis_query_refuses_an_unsupported_selection(field: str) -> None:
    client = TestClient(create_app())

    response = client.post("/api/analysis/query", json=_analysis_body(**{field: ["TTF"]}))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "analysis_selection_not_supported"
    assert detail["fields"] == [field]
    assert detail["resource"] == "analysis_query"
    # The refusal states its own posture rather than borrowing a status code's meaning.
    assert detail["research_only"] is True
    assert detail["human_review_required"] is True
    assert "question" in detail["message"]


@pytest.mark.parametrize("field", REPORT_FIELDS)
def test_portfolio_report_refuses_an_unsupported_selection(field: str) -> None:
    client = TestClient(create_app())

    # `portfolio_id` is a scalar field, the other three are lists: the refusal answers the
    # selection, not the shape, so each is supplied in the type the model declares.
    supplied = "PF-1" if field == "portfolio_id" else ["PF-1"]
    response = client.post("/api/reports/portfolio", json=_report_body(**{field: supplied}))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "analysis_selection_not_supported"
    assert detail["fields"] == [field]
    assert detail["resource"] == "portfolio_report"


def test_the_refusal_names_every_offending_field_at_once() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/analysis/query",
        json=_analysis_body(
            selected_terms=["TTF"],
            selected_assets=[],
            selected_contracts=["C-1", "C-2"],
            include_sections=["market"],
        ),
    )

    assert response.status_code == 422
    # Empty selections are not offences: only the fields the caller really filled in are
    # named, in request order, so the repair is a single edit.
    assert response.json()["detail"]["fields"] == [
        "selected_terms",
        "selected_contracts",
        "include_sections",
    ]


def test_an_empty_selection_changes_nothing() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/analysis/query",
        json=_analysis_body(
            selected_terms=[],
            selected_assets=[],
            selected_contracts=[],
            include_sections=[],
        ),
    )

    assert response.status_code == 200
    assert response.json()["data"]["task"] == "DB_INQUIRY"


def test_the_report_route_still_runs_without_any_selection() -> None:
    client = TestClient(create_app())

    response = client.post("/api/reports/portfolio", json=_report_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task"] == "PORTFOLIO_REPORT"
    assert {section["section_id"] for section in data["sections"]} >= {
        "portfolio",
        "market",
        "strategy",
    }


def test_a_refused_selection_is_refused_before_the_run_exists(tmp_path, monkeypatch) -> None:
    """Nothing is loaded, tracked or persisted for a request that is refused."""

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import GeneratedReportRecord, JobRecord

    database_url = f"sqlite+pysqlite:///{(tmp_path / 'selection-refusal.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(database_url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    client = TestClient(create_app())
    response = client.post(
        "/api/reports/portfolio",
        json=_report_body(selected_resources=["operator-ttf-bbl-portfolio"]),
    )

    assert response.status_code == 422
    with Session(create_engine(database_url, future=True)) as session:
        assert session.execute(select(JobRecord)).scalars().all() == []
        assert session.execute(select(GeneratedReportRecord)).scalars().all() == []


def test_a_refused_selection_is_refused_before_the_provider_is_called() -> None:
    """A refused selection never buys an external request."""

    called: list[dict] = []

    def _record_call(**kwargs):  # pragma: no cover - only reached on regression
        called.append(kwargs)
        raise AssertionError("a refused selection must not reach the provider")

    import eurogas_nexus.api.routes.public.analysis as analysis_routes

    original = analysis_routes.invoke_deepseek
    analysis_routes.invoke_deepseek = _record_call
    try:
        client = TestClient(create_app())
        response = client.post(
            "/api/analysis/query",
            json=_analysis_body(invoke_provider=True, selected_assets=["RES-1"]),
        )
    finally:
        analysis_routes.invoke_deepseek = original

    assert response.status_code == 422
    assert called == []
