"""SDK client for persisted monitoring alerts and DeepSeek interaction."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import api_url


class MonitoringAlert(BaseModel):
    """One persisted monitoring alert with optional LLM analysis context.

    Attributes:
        alert_id: Unique identifier of the alert.
        fingerprint: Deduplication fingerprint of the underlying event.
        category: Category of the alert.
        alert_type: Type of the alert within its category.
        severity: Severity level (e.g., critical, warning, info).
        status: Lifecycle status (e.g., open, acknowledged, resolved).
        title_en: Alert title in English.
        title_zh_cn: Alert title in Simplified Chinese.
        message_en: Alert message in English.
        message_zh_cn: Alert message in Simplified Chinese.
        entity_type: Type of the entity the alert refers to.
        entity_id: Identifier of the entity the alert refers to.
        event_time_utc: Time of the triggering event (ISO 8601).
        detected_at_utc: Time the alert was detected (ISO 8601).
        updated_at_utc: Time the alert was last updated (ISO 8601).
        acknowledged_at_utc: Acknowledgement time; None when not acknowledged.
        resolved_at_utc: Resolution time; None when not resolved.
        occurrence_count: How many times the alert has been observed.
        evidence_snapshot: Snapshot of evidence captured with the alert.
        source_refs: References to the underlying source records.
        warnings: Non-blocking warnings about the alert.
        llm_provider_id: Provider used for the LLM summary; may be empty.
        llm_status: Status of the LLM summary generation.
        llm_summary_en: LLM summary in English; None when not generated.
        llm_summary_zh_cn: LLM summary in Simplified Chinese; None when not
            generated.
        llm_last_attempt_at_utc: Time of the last LLM attempt; None when none.
        simulated: Whether the alert comes from a simulation.
        human_review_required: Whether the alert needs human review.
    """

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
    """Aggregate counters over the persisted alert set.

    Attributes:
        open_count: Number of open alerts.
        acknowledged_count: Number of acknowledged alerts.
        critical_count: Number of critical alerts.
        warning_count: Number of warning alerts.
        info_count: Number of informational alerts.
        llm_pending_count: Alerts still waiting for an LLM summary.
        simulated_count: Alerts originating from simulations.
    """

    open_count: int
    acknowledged_count: int
    critical_count: int
    warning_count: int
    info_count: int
    llm_pending_count: int
    simulated_count: int


class MonitoringAnalysis(BaseModel):
    """One LLM-generated analysis answer for a monitoring alert.

    Attributes:
        analysis_id: Unique identifier of the analysis; None when not assigned.
        alert_id: Identifier of the alert being analyzed.
        provider_id: Identifier of the provider that answered.
        provider_status: Provider-side status of the answer.
        answer: The analysis answer text; None when generation failed.
        model: Model that produced the answer.
        language: Language of the answer (``en`` or ``zh-CN``).
        source_refs: References used by the analysis.
        warnings: Non-blocking warnings about the analysis.
        human_review_required: Whether the answer needs human review.
    """

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
    """Fetch persisted monitoring alerts, optionally filtered.

    Args:
        base_url: Operator-provided server root URL.
        status: Only return alerts in this status (e.g., open, resolved).
        category: Only return alerts in this category.
        severity: Only return alerts at this severity.
        limit: Maximum number of alerts to return.

    Returns:
        List of validated monitoring alerts.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    response = _http.get(
        api_url(base_url, "monitoring/alerts"),
        # 只剔除未提供的过滤项（is not None 而非真值判断）：limit 等带默认值
        # 的参数始终显式下发，避免客户端与服务端默认分页行为不一致。
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
    """Fetch aggregate counters over the persisted alert set.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        Summary counters (open, acknowledged, critical, and LLM-pending).

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    response = _http.get(api_url(base_url, "monitoring/summary"), timeout=10)
    response.raise_for_status()
    return MonitoringSummary.model_validate(response.json()["data"])


def acknowledge_monitoring_alert(base_url: str, alert_id: str) -> MonitoringAlert:
    """Acknowledge one monitoring alert by id.

    Args:
        base_url: Operator-provided server root URL.
        alert_id: Identifier of the alert to acknowledge.

    Returns:
        The updated alert with its acknowledgement timestamps.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    response = _http.post(
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
    """Ask the configured analysis provider to explain one monitoring alert.

    Args:
        base_url: Operator-provided server root URL.
        alert_id: Identifier of the alert to analyze.
        question: Free-form question about the alert.
        language: Language for the answer (``en`` or ``zh-CN``).

    Returns:
        The validated analysis answer for the alert.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    response = _http.post(
        api_url(base_url, f"monitoring/alerts/{alert_id}/analysis"),
        json={
            "question": question,
            "language": language,
            # 固定分析模型：告警解释需要跨请求可比、可审计，不能跟随
            # 服务端默认模型变动而漂移。
            "model": "deepseek-v4-flash",
        },
        # LLM 分析是慢路径（最长 60s），与普通告警查询的 10s 超时区分开。
        timeout=60,
    )
    response.raise_for_status()
    return MonitoringAnalysis.model_validate(response.json()["data"])
