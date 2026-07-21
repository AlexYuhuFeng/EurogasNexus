"""Deterministic runtime monitoring and optional DeepSeek enrichment."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    IngestionRunRecord,
    IntradayOpportunityRecord,
    MonitoringAlertRecord,
    StrategyAlertRecord,
)
from eurogas_nexus.db.repositories.monitoring import (
    resolve_absent_monitoring_alerts,
    upsert_monitoring_alert,
)
from eurogas_nexus.domain.monitoring import MonitoringCandidate
from eurogas_nexus.llm import DEEPSEEK_DEFAULT_MODEL, DeepSeekCallResult, invoke_deepseek
from eurogas_nexus.security.provider_keys import load_provider_api_key

ProviderCall = Callable[..., DeepSeekCallResult]
ApiKeyLoader = Callable[[str], str | None]


def scan_monitoring_conditions(
    session: Session,
    *,
    now_utc: datetime | None = None,
    enrich_with_llm: bool = True,
    max_llm_enrichments: int = 3,
    api_key_loader: ApiKeyLoader | None = None,
    provider_call: ProviderCall | None = None,
) -> dict[str, int]:
    """Persist current conditions and enrich only new or escalated alerts."""

    now = _as_utc(now_utc or datetime.now(UTC))
    candidates = [
        *_opportunity_candidates(session, now),
        *_strategy_candidates(session),
        *_source_failure_candidates(session),
    ]
    active_fingerprints = {candidate.fingerprint for candidate in candidates}
    rows = [
        upsert_monitoring_alert(session, candidate, now_utc=now)
        for candidate in candidates
    ]
    resolved_count = resolve_absent_monitoring_alerts(
        session,
        active_fingerprints,
        now_utc=now,
    )
    session.commit()

    enriched_count = 0
    if enrich_with_llm and max_llm_enrichments > 0:
        enriched_count = _enrich_pending_alerts(
            session,
            rows,
            now_utc=now,
            limit=max_llm_enrichments,
            api_key_loader=api_key_loader or load_provider_api_key,
            provider_call=provider_call or invoke_deepseek,
        )

    return {
        "active_count": len(candidates),
        "resolved_count": resolved_count,
        "llm_enriched_count": enriched_count,
    }


def enrich_monitoring_alert(
    session: Session,
    alert: MonitoringAlertRecord,
    *,
    now_utc: datetime | None = None,
    api_key_loader: ApiKeyLoader | None = None,
    provider_call: ProviderCall | None = None,
) -> DeepSeekCallResult:
    """Request a live DeepSeek explanation for one persisted alert."""

    now = _as_utc(now_utc or datetime.now(UTC))
    key_loader = api_key_loader or load_provider_api_key
    call = provider_call or invoke_deepseek
    api_key = key_loader("DEEPSEEK") or key_loader("LLM")
    alert.llm_provider_id = "DEEPSEEK"
    alert.llm_last_attempt_at_utc = now
    if not api_key:
        result = DeepSeekCallResult(
            status="missing_credential",
            error_code="credential_missing",
        )
        alert.llm_status = result.status
        session.commit()
        return result

    result = call(
        api_key=api_key,
        messages=_alert_enrichment_messages(alert),
        model=DEEPSEEK_DEFAULT_MODEL,
        temperature=0.1,
        max_tokens=900,
    )
    alert.llm_status = result.status
    if result.status == "success" and result.content:
        summary_en, summary_zh_cn = _parse_bilingual_summary(result.content)
        alert.llm_summary_en = summary_en
        alert.llm_summary_zh_cn = summary_zh_cn
    else:
        warning = f"deepseek_enrichment:{result.error_code or result.status}"
        alert.warnings = list(dict.fromkeys([*(alert.warnings or []), warning]))
    session.commit()
    return result


def _opportunity_candidates(
    session: Session,
    now_utc: datetime,
) -> list[MonitoringCandidate]:
    rows = (
        session.query(IntradayOpportunityRecord)
        .filter(IntradayOpportunityRecord.valid_until_utc >= now_utc)
        .order_by(IntradayOpportunityRecord.detected_at_utc.desc())
        .limit(500)
        .all()
    )
    latest: dict[str, IntradayOpportunityRecord] = {}
    for row in rows:
        fingerprint = _opportunity_fingerprint(row)
        latest.setdefault(fingerprint, row)

    candidates: list[MonitoringCandidate] = []
    for fingerprint, row in latest.items():
        if row.status not in {"ACTIONABLE_REVIEW", "BLOCKED"}:
            continue
        actionable = row.status == "ACTIONABLE_REVIEW"
        severity = "warning" if actionable else "info"
        margin = _format_amount(row.net_margin, row.comparison_currency, row.comparison_unit)
        route = f"{row.buy_hub} -> {row.sell_hub} via {row.route_name}"
        title_en = (
            "Intraday spread requires review"
            if actionable
            else "Route opportunity is blocked"
        )
        title_zh_cn = "日内价差机会待复核" if actionable else "路径机会当前受阻"
        message_en = (
            f"{route}; net margin {margin}."
            if actionable
            else f"{route}; required inputs or access are incomplete."
        )
        message_zh_cn = (
            f"{route}；净边际为 {margin}。"
            if actionable
            else f"{route}；必要输入、容量或准入条件不完整。"
        )
        candidates.append(
            MonitoringCandidate(
                fingerprint=fingerprint,
                category="market_opportunity",
                alert_type=row.opportunity_type.lower(),
                severity=severity,
                title_en=title_en,
                title_zh_cn=title_zh_cn,
                message_en=message_en,
                message_zh_cn=message_zh_cn,
                entity_type="intraday_opportunity",
                entity_id=row.opportunity_id,
                event_time_utc=row.detected_at_utc,
                evidence_snapshot=_opportunity_evidence(row),
                source_refs=list(row.source_refs or []),
                warnings=list(row.warnings or []),
                simulated=bool(row.simulated),
                human_review_required=True,
            )
        )
    return candidates


def _strategy_candidates(session: Session) -> list[MonitoringCandidate]:
    rows = (
        session.query(StrategyAlertRecord)
        .filter(StrategyAlertRecord.acknowledged.is_(False))
        .order_by(StrategyAlertRecord.created_at_utc.desc())
        .limit(200)
        .all()
    )
    return [
        MonitoringCandidate(
            fingerprint=f"strategy:{row.alert_id}",
            category="strategy",
            alert_type=row.alert_type,
            severity=_normalize_severity(row.severity),
            title_en="Strategy monitor alert",
            title_zh_cn="策略监控告警",
            message_en=row.message_en,
            message_zh_cn=row.message_zh_cn,
            entity_type="strategy_run",
            entity_id=row.run_id,
            event_time_utc=row.created_at_utc,
            evidence_snapshot={
                "strategy_alert_id": row.alert_id,
                "run_id": row.run_id,
                "alert_type": row.alert_type,
                "severity": row.severity,
            },
            source_refs=[f"strategy-run:{row.run_id}"],
            human_review_required=True,
        )
        for row in rows
    ]


def _source_failure_candidates(session: Session) -> list[MonitoringCandidate]:
    rows = (
        session.query(IngestionRunRecord)
        .order_by(IngestionRunRecord.started_at_utc.desc())
        .limit(500)
        .all()
    )
    runs_by_source: dict[str, list[IngestionRunRecord]] = defaultdict(list)
    for row in rows:
        runs_by_source[row.source_name].append(row)

    candidates: list[MonitoringCandidate] = []
    for source_name, source_rows in runs_by_source.items():
        latest = source_rows[0]
        if latest.status != "failed":
            continue
        consecutive_failures = 0
        for row in source_rows:
            if row.status != "failed":
                break
            consecutive_failures += 1
        severity = "critical" if consecutive_failures >= 3 else "warning"
        candidates.append(
            MonitoringCandidate(
                fingerprint=f"source_failure:{source_name.lower()}",
                category="data_source",
                alert_type="ingestion_failed",
                severity=severity,
                title_en=f"{source_name} ingestion failed",
                title_zh_cn=f"{source_name} 数据更新失败",
                message_en=(
                    f"The latest {source_name} ingestion failed; "
                    f"{consecutive_failures} consecutive failure(s)."
                ),
                message_zh_cn=(
                    f"最近一次 {source_name} 数据更新失败；"
                    f"已连续失败 {consecutive_failures} 次。"
                ),
                entity_type="data_source",
                entity_id=source_name,
                event_time_utc=latest.started_at_utc,
                evidence_snapshot={
                    "run_id": latest.run_id,
                    "source_name": source_name,
                    "status": latest.status,
                    "started_at_utc": _as_utc(latest.started_at_utc).isoformat(),
                    "finished_at_utc": (
                        _as_utc(latest.finished_at_utc).isoformat()
                        if latest.finished_at_utc
                        else None
                    ),
                    "consecutive_failures": consecutive_failures,
                    "notes": latest.notes,
                },
                source_refs=[f"ingestion-run:{latest.run_id}"],
                warnings=[latest.notes] if latest.notes else [],
                human_review_required=True,
            )
        )
    return candidates


def _enrich_pending_alerts(
    session: Session,
    rows: list[MonitoringAlertRecord],
    *,
    now_utc: datetime,
    limit: int,
    api_key_loader: ApiKeyLoader,
    provider_call: ProviderCall,
) -> int:
    retry_before = now_utc - timedelta(minutes=5)
    eligible = [
        row
        for row in rows
        if row.status == "open"
        and row.llm_status != "success"
        and (
            row.llm_last_attempt_at_utc is None
            or _as_utc(row.llm_last_attempt_at_utc) <= retry_before
        )
    ]
    enriched = 0
    for row in sorted(
        eligible,
        key=lambda item: (item.severity != "critical", item.detected_at_utc),
    )[:limit]:
        result = enrich_monitoring_alert(
            session,
            row,
            now_utc=now_utc,
            api_key_loader=api_key_loader,
            provider_call=provider_call,
        )
        if result.status == "success":
            enriched += 1
    return enriched


def _alert_enrichment_messages(alert: MonitoringAlertRecord) -> list[dict[str, str]]:
    snapshot = {
        "category": alert.category,
        "type": alert.alert_type,
        "severity": alert.severity,
        "title_en": alert.title_en,
        "message_en": alert.message_en,
        "evidence": alert.evidence_snapshot,
        "source_references": alert.source_refs,
        "warnings": alert.warnings,
        "simulated": alert.simulated,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the governed analysis layer of Eurogas Nexus. Explain the "
                "provided deterministic European gas-market alert. Do not claim that "
                "orders were or should automatically be executed. Distinguish facts, "
                "assumptions, simulated inputs, and missing evidence. Return JSON only "
                "with string fields summary_en and summary_zh_cn. Each summary must be "
                "concise, operationally useful, and require human review."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(snapshot, ensure_ascii=False, default=str),
        },
    ]


def _parse_bilingual_summary(content: str) -> tuple[str, str]:
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].lstrip()
    try:
        payload: dict[str, Any] = json.loads(candidate)
        summary_en = str(payload.get("summary_en") or "").strip()
        summary_zh_cn = str(payload.get("summary_zh_cn") or "").strip()
        if summary_en and summary_zh_cn:
            return summary_en, summary_zh_cn
    except (TypeError, ValueError):
        pass
    return content.strip(), content.strip()


def _opportunity_fingerprint(row: IntradayOpportunityRecord) -> str:
    return ":".join(
        (
            "opportunity",
            row.opportunity_type.lower(),
            row.route_id.lower(),
            row.product.lower(),
            row.buy_hub.lower(),
            row.sell_hub.lower(),
        )
    )


def _opportunity_evidence(row: IntradayOpportunityRecord) -> dict[str, Any]:
    return {
        "opportunity_id": row.opportunity_id,
        "status": row.status,
        "route_id": row.route_id,
        "route_name": row.route_name,
        "buy_venue": row.buy_venue,
        "sell_venue": row.sell_venue,
        "buy_hub": row.buy_hub,
        "sell_hub": row.sell_hub,
        "product": row.product,
        "buy_ask": row.buy_ask,
        "sell_bid": row.sell_bid,
        "gross_spread": row.gross_spread,
        "route_cost": row.route_cost,
        "trading_cost": row.trading_cost,
        "risk_buffer": row.risk_buffer,
        "net_margin": row.net_margin,
        "max_quantity_mwh": row.max_quantity_mwh,
        "indicative_net_value": row.indicative_net_value,
        "comparison_currency": row.comparison_currency,
        "comparison_unit": row.comparison_unit,
        "quote_age_seconds": row.quote_age_seconds,
        "confidence_score": row.confidence_score,
        "assumptions": row.assumptions,
        "missing_inputs": row.missing_inputs,
        "valid_until_utc": _as_utc(row.valid_until_utc).isoformat(),
    }


def _normalize_severity(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"critical", "error", "high"}:
        return "critical"
    if normalized in {"warning", "warn", "medium"}:
        return "warning"
    return "info"


def _format_amount(value: float | None, currency: str, unit: str) -> str:
    if value is None:
        return "unavailable"
    return f"{currency} {value:.4f}/{unit}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
