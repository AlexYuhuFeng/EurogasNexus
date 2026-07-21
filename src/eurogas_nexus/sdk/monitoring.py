"""SDK client for persisted monitoring alerts and DeepSeek interaction."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from eurogas_nexus.sdk._transport import api_url


class MonitoringAlert(BaseModel):
    alert_id: str
    fingerprint: str
    category: str
    alert_type: str
    severity: str
    status: str
    title_en: str
    title_zh_cn: str
    message_en: str
    message_zh_cn: str
    entity_type: str
    entity_id: str
    event_time_utc: str
    detected_at_utc: str
    updated_at_utc: str
    acknowledged_at_utc: str | None = None
    resolved_at_utc: str | None = None
    occurrence_count: int
    evidence_snapshot: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    llm_provider_id: str
    llm_status: str
    llm_summary_en: str | None = None
    llm_summary_zh_cn: str | None = None
    llm_last_attempt_at_utc: str | None = None
    simulated: bool
    human_review_required: bool


class MonitoringSummary(BaseModel):
    open_count: int
    acknowledged_count: int
    critical_count: int
    warning_count: int
    info_count: int
    llm_pending_count: int
    simulated_count: int


class MonitoringAnalysis(BaseModel):
    analysis_id: str | None = None
    alert_id: str
    provider_id: str
    provider_status: str
    answer: str | None = None
    model: str
    language: str
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool


def fetch_monitoring_alerts(
    base_url: str,
    *,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[MonitoringAlert]:
    response = httpx.get(
        api_url(base_url, "monitoring/alerts"),
        params={
            key: value
            for key, value in {
                "status": status,
                "category": category,
                "severity": severity,
                "limit": limit,
            }.items()
            if value is not None
        },
        timeout=10,
    )
    response.raise_for_status()
    return [MonitoringAlert.model_validate(row) for row in response.json()["data"]]


def fetch_monitoring_summary(base_url: str) -> MonitoringSummary:
    response = httpx.get(api_url(base_url, "monitoring/summary"), timeout=10)
    response.raise_for_status()
    return MonitoringSummary.model_validate(response.json()["data"])


def acknowledge_monitoring_alert(base_url: str, alert_id: str) -> MonitoringAlert:
    response = httpx.post(
        api_url(base_url, f"monitoring/alerts/{alert_id}/acknowledge"),
        json={},
        timeout=10,
    )
    response.raise_for_status()
    return MonitoringAlert.model_validate(response.json()["data"])


def analyze_monitoring_alert(
    base_url: str,
    alert_id: str,
    *,
    question: str,
    language: Literal["en", "zh-CN"] = "en",
) -> MonitoringAnalysis:
    response = httpx.post(
        api_url(base_url, f"monitoring/alerts/{alert_id}/analysis"),
        json={
            "question": question,
            "language": language,
            "model": "deepseek-v4-flash",
        },
        timeout=60,
    )
    response.raise_for_status()
    return MonitoringAnalysis.model_validate(response.json()["data"])
