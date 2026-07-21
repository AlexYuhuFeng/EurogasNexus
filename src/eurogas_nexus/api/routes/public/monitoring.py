"""Unified monitoring alert and live DeepSeek interaction routes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from eurogas_nexus.llm import invoke_deepseek
from eurogas_nexus.security.provider_keys import load_provider_api_key

router = APIRouter(tags=["monitoring"])


class AlertAnalysisRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    language: Literal["en", "zh-CN"] = "en"
    model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"


@router.get("/api/monitoring/alerts")
def get_alerts(
    status: Literal["open", "acknowledged", "resolved"] | None = None,
    category: str | None = Query(default=None, max_length=64),
    severity: Literal["info", "warning", "critical"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    from eurogas_nexus.db.repositories.monitoring import list_monitoring_alerts

    with _session() as session:
        data = list_monitoring_alerts(
            session,
            status=status,
            category=category,
            severity=severity,
            limit=limit,
        )
    return _env(data)


@router.get("/api/monitoring/summary")
def get_alert_summary() -> dict:
    from eurogas_nexus.db.repositories.monitoring import monitoring_summary

    with _session() as session:
        data = monitoring_summary(session)
    return _env(data)


@router.post("/api/monitoring/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str) -> dict:
    from eurogas_nexus.db.repositories.monitoring import (
        acknowledge_monitoring_alert,
        monitoring_alert_payload,
    )

    with _session() as session:
        row = acknowledge_monitoring_alert(
            session,
            alert_id,
            now_utc=datetime.now(UTC),
        )
        if row is None:
            raise _not_found(alert_id)
        session.commit()
        data = monitoring_alert_payload(row)
    return _env(data)


@router.post("/api/monitoring/alerts/{alert_id}/analysis")
def analyze_alert(alert_id: str, payload: AlertAnalysisRequest) -> dict:
    """Ask live DeepSeek about one alert without exposing the API credential."""

    from eurogas_nexus.db.repositories.monitoring import (
        get_monitoring_alert,
        monitoring_alert_payload,
    )

    with _session() as session:
        row = get_monitoring_alert(session, alert_id)
        if row is None:
            raise _not_found(alert_id)
        alert_snapshot = monitoring_alert_payload(row)

    api_key = load_provider_api_key("DEEPSEEK") or load_provider_api_key("LLM")
    if not api_key:
        data = {
            "analysis_id": None,
            "alert_id": alert_id,
            "provider_id": "DEEPSEEK",
            "provider_status": "missing_credential",
            "answer": None,
            "model": payload.model,
            "language": payload.language,
            "source_refs": alert_snapshot["source_refs"],
            "warnings": ["DeepSeek credential is not configured or is disabled."],
            "human_review_required": True,
        }
        return _env(data, warnings=data["warnings"])

    result = invoke_deepseek(
        api_key=api_key,
        messages=_analysis_messages(alert_snapshot, payload),
        model=payload.model,
        temperature=0.15,
        max_tokens=1600,
    )
    analysis_id = f"monitoring-analysis-{uuid4().hex}"
    warnings = list(alert_snapshot.get("warnings") or [])
    if result.status != "success":
        warnings.append(f"deepseek:{result.error_code or result.status}")
    data = {
        "analysis_id": analysis_id,
        "alert_id": alert_id,
        "provider_id": "DEEPSEEK",
        "provider_status": result.status,
        "answer": result.content,
        "model": payload.model,
        "language": payload.language,
        "source_refs": alert_snapshot["source_refs"],
        "warnings": list(dict.fromkeys(warnings)),
        "human_review_required": True,
    }
    _persist_analysis_run(
        analysis_id=analysis_id,
        request=payload,
        alert_snapshot=alert_snapshot,
        result=data,
    )
    return _env(data, warnings=data["warnings"])


def _analysis_messages(
    alert_snapshot: dict,
    request: AlertAnalysisRequest,
) -> list[dict[str, str]]:
    language_instruction = (
        "Respond in Simplified Chinese."
        if request.language == "zh-CN"
        else "Respond in English."
    )
    return [
        {
            "role": "system",
            "content": (
                "You are the governed live analysis layer of Eurogas Nexus. Use only "
                "the supplied PostgreSQL alert snapshot and its cited evidence. "
                "Clearly separate observed facts, simulated inputs, assumptions, and "
                "missing data. Provide decision support and concrete checks, but never "
                "claim to execute a trade, nomination, booking, or approval. "
                f"{language_instruction} Human review is mandatory."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": request.question,
                    "alert": alert_snapshot,
                },
                ensure_ascii=False,
                default=str,
            ),
        },
    ]


def _persist_analysis_run(
    *,
    analysis_id: str,
    request: AlertAnalysisRequest,
    alert_snapshot: dict,
    result: dict,
) -> None:
    try:
        from eurogas_nexus.db.models import AnalysisRunRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            session.add(
                AnalysisRunRecord(
                    analysis_id=analysis_id,
                    task="MONITORING_ALERT_ANALYSIS",
                    provider_id="DEEPSEEK",
                    provider_status=result["provider_status"],
                    prompt_snapshot={
                        "question": request.question,
                        "language": request.language,
                        "model": request.model,
                    },
                    input_snapshot=alert_snapshot,
                    output_snapshot=result,
                    source_refs=list(result["source_refs"]),
                    warnings=list(result["warnings"]),
                    created_at_utc=datetime.now(UTC),
                    research_only=False,
                    human_review_required=True,
                )
            )
            session.commit()
    except Exception:
        return


def _session():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_database_not_configured",
                "message": "Runtime PostgreSQL is required for monitoring alerts.",
            },
        )
    return get_session_factory()()


def _not_found(alert_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "monitoring_alert_not_found",
            "message": f"Monitoring alert {alert_id} was not found.",
        },
    )


def _env(data: object, *, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": False,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
