"""Governed LLM-ready analysis API tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_business_ontology_endpoint_exposes_guardrails() -> None:
    client = TestClient(create_app())

    response = client.get("/api/analysis/ontology")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "StrategyRun" in data["entities"]
    assert "LLM providers are not source of truth" in data["guardrails"]


def test_analysis_query_uses_snapshot_without_invoking_provider() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/analysis/query",
        json={
            "question": "Summarize current TTF context",
            "task": "DB_INQUIRY",
            "invoke_provider": False,
            "selected_terms": ["TTF"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert body["data"]["provider_id"] == "DEEPSEEK"
    assert body["data"]["provider_status"] == "not_invoked"
    assert body["data"]["research_only"] is True
    assert body["data"]["human_review_required"] is True
    assert "LLM_PROVIDER_NOT_INVOKED" in body["data"]["warnings"]
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["data"]["warnings"]


def test_portfolio_report_returns_required_sections() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/reports/portfolio",
        json={
            "title": "Current portfolio report",
            "selected_resources": ["operator-ttf-bbl-portfolio"],
            "invoke_provider": False,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert response.json()["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert data["task"] == "PORTFOLIO_REPORT"
    assert {section["section_id"] for section in data["sections"]} >= {
        "portfolio",
        "market",
        "strategy",
    }


def test_glossary_context_returns_ttf_operational_context() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/glossary/TTF/context",
        params={
            "lang": "en",
            "duration_start_utc": "2026-05-31T00:00:00Z",
            "duration_end_utc": "2026-06-02T00:00:00Z",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["context_type"] == "hub"
    assert "Dutch virtual gas hub" in data["description"]
    assert data["requested_duration"]["duration_start_utc"].startswith("2026-05-31")
    assert data["capacity"] is None
    assert data["capacity_usage"] is None
    assert data["related_prices"] == []
    assert data["live_market_marks"] == []
    assert data["related_contracts"] == []
    assert "RUNTIME_DB_CONTEXT_NOT_AVAILABLE" in data["warnings"]
    assert "PRICE_CONTEXT_MISSING" in data["warnings"]
    assert {section["section_id"] for section in data["context_sections"]} >= {
        "overview",
        "capacity",
        "prices",
        "routes",
        "contracts",
        "data_quality",
    }


def test_glossary_context_returns_licensed_price_context_warning() -> None:
    client = TestClient(create_app())

    response = client.get("/api/glossary/ICIS%20Heren/context", params={"lang": "zh-CN"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["context_type"] == "price_assessment"
    assert "授权" in data["description"]
    assert "ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA" in data["warnings"]
    assert data["related_prices"] == []
    assert "PRICE_CONTEXT_MISSING" in data["warnings"]
    assert any(section["section_id"] == "prices" for section in data["context_sections"])
