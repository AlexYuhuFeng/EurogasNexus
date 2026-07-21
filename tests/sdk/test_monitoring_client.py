"""SDK monitoring client tests."""

from __future__ import annotations

import httpx

from eurogas_nexus.sdk.monitoring import (
    MonitoringAnalysis,
    MonitoringSummary,
    analyze_monitoring_alert,
    fetch_monitoring_summary,
)


def test_monitoring_summary_uses_stable_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, timeout: int) -> httpx.Response:
        captured.update(url=url, timeout=timeout)
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "data": {
                    "open_count": 2,
                    "acknowledged_count": 1,
                    "critical_count": 0,
                    "warning_count": 2,
                    "info_count": 0,
                    "llm_pending_count": 1,
                    "simulated_count": 2,
                }
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    result = fetch_monitoring_summary("http://testserver")

    assert captured == {
        "url": "http://testserver/api/monitoring/summary",
        "timeout": 10,
    }
    assert isinstance(result, MonitoringSummary)
    assert result.open_count == 2


def test_monitoring_analysis_posts_question_to_backend(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(url: str, json: dict, timeout: int) -> httpx.Response:
        captured.update(url=url, json=json, timeout=timeout)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "data": {
                    "analysis_id": "analysis-1",
                    "alert_id": "alert-1",
                    "provider_id": "DEEPSEEK",
                    "provider_status": "success",
                    "answer": "Review the evidence.",
                    "model": "deepseek-v4-flash",
                    "language": "en",
                    "source_refs": ["runtime-postgresql"],
                    "warnings": [],
                    "human_review_required": True,
                }
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = analyze_monitoring_alert(
        "http://testserver",
        "alert-1",
        question="What changed?",
    )

    assert captured["url"] == "http://testserver/api/monitoring/alerts/alert-1/analysis"
    assert captured["json"] == {
        "question": "What changed?",
        "language": "en",
        "model": "deepseek-v4-flash",
    }
    assert captured["timeout"] == 60
    assert isinstance(result, MonitoringAnalysis)
    assert result.provider_status == "success"
