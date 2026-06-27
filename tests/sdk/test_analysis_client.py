"""SDK analysis client tests."""

import httpx

from eurogas_nexus.sdk.analysis import (
    AnalysisResult,
    ask_analysis,
    fetch_business_ontology,
    generate_portfolio_report,
)


def test_analysis_sdk_targets_backend_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"data": _analysis_payload()},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = ask_analysis("http://testserver", question="What is Easington?")

    assert captured["url"] == "http://testserver/api/analysis/query"
    assert captured["json"]["question"] == "What is Easington?"
    assert isinstance(result, AnalysisResult)


def test_report_sdk_targets_backend_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"data": _analysis_payload()},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = generate_portfolio_report("http://testserver", title="Portfolio")

    assert captured["url"] == "http://testserver/api/reports/portfolio"
    assert result.research_only is True


def test_ontology_sdk_targets_backend_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, timeout: int) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={"data": {"entities": ["StrategyRun"], "guardrails": []}},
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = fetch_business_ontology("http://testserver")

    assert captured["url"] == "http://testserver/api/analysis/ontology"
    assert result["entities"] == ["StrategyRun"]


def _analysis_payload() -> dict:
    return {
        "analysis_id": "analysis-test",
        "task": "DB_INQUIRY",
        "provider_id": "DEEPSEEK",
        "provider_status": "not_invoked",
        "answer_en": "answer",
        "answer_zh_cn": "鍥炵瓟",
        "citations": ["snapshot"],
        "sections": [],
        "missing_inputs": [],
        "warnings": ["LLM_PROVIDER_NOT_INVOKED"],
        "snapshot_id": "snapshot-test",
        "created_at_utc": "2026-06-01T00:00:00Z",
        "research_only": True,
        "human_review_required": True,
    }
