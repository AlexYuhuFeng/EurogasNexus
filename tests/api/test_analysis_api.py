"""Governed LLM-ready analysis API tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_business_ontology_endpoint_exposes_guardrails() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/analysis/ontology")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "StrategyRun" in data["entities"]
    assert "LLM providers are not source of truth" in data["guardrails"]


def test_analysis_query_uses_snapshot_without_invoking_provider() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/analysis/query",
        json={
            "question": "Summarize current Easington context",
            "task": "DB_INQUIRY",
            "invoke_provider": False,
            "selected_terms": ["Easington Entry Point"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["provider_id"] == "DEEPSEEK"
    assert body["data"]["provider_status"] == "not_invoked"
    assert body["data"]["research_only"] is True
    assert body["data"]["human_review_required"] is True
    assert "LLM_PROVIDER_NOT_INVOKED" in body["data"]["warnings"]


def test_portfolio_report_returns_required_sections() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/reports/portfolio",
        json={
            "title": "Current portfolio report",
            "selected_resources": ["demo-easington-contract"],
            "invoke_provider": False,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task"] == "PORTFOLIO_REPORT"
    assert {section["section_id"] for section in data["sections"]} >= {
        "portfolio",
        "market",
        "strategy",
    }


def test_glossary_context_returns_easington_operational_context() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/glossary/Easington%20Entry%20Point/context")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["context_type"] == "entry_point"
    assert "National Gas NTS" in data["description"]
    assert data["capacity"] is not None
    assert data["capacity_usage"] is not None
    assert data["related_prices"]
