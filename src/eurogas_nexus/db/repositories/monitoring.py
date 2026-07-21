"""Repository operations for normalized monitoring alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import MonitoringAlertRecord
from eurogas_nexus.domain.monitoring import SEVERITY_ORDER, MonitoringCandidate


def upsert_monitoring_alert(
    session: Session,
    candidate: MonitoringCandidate,
    *,
    now_utc: datetime,
) -> MonitoringAlertRecord:
    """Create or update one alert without duplicating a recurring condition."""

    row = (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.fingerprint == candidate.fingerprint)
        .one_or_none()
    )
    if row is None:
        row = MonitoringAlertRecord(
            alert_id=f"alert-{sha256(candidate.fingerprint.encode()).hexdigest()[:32]}",
            fingerprint=candidate.fingerprint,
            category=candidate.category,
            alert_type=candidate.alert_type,
            severity=candidate.severity,
            status="open",
            title_en=candidate.title_en,
            title_zh_cn=candidate.title_zh_cn,
            message_en=candidate.message_en,
            message_zh_cn=candidate.message_zh_cn,
            entity_type=candidate.entity_type,
            entity_id=candidate.entity_id,
            event_time_utc=candidate.event_time_utc,
            detected_at_utc=now_utc,
            updated_at_utc=now_utc,
            acknowledged_at_utc=None,
            resolved_at_utc=None,
            occurrence_count=1,
            evidence_snapshot=candidate.evidence_snapshot,
            source_refs=candidate.source_refs,
            warnings=candidate.warnings,
            llm_provider_id="DEEPSEEK",
            llm_status="pending",
            llm_summary_en=None,
            llm_summary_zh_cn=None,
            llm_last_attempt_at_utc=None,
            simulated=candidate.simulated,
            human_review_required=candidate.human_review_required,
        )
        session.add(row)
        session.flush()
        return row

    previous_event_time = _as_utc(row.event_time_utc)
    next_event_time = _as_utc(candidate.event_time_utc)
    severity_increased = SEVERITY_ORDER.get(candidate.severity, 0) > SEVERITY_ORDER.get(
        row.severity, 0
    )
    condition_returned = row.status == "resolved"
    if next_event_time > previous_event_time:
        row.occurrence_count += 1
        row.event_time_utc = candidate.event_time_utc
    row.category = candidate.category
    row.alert_type = candidate.alert_type
    row.severity = candidate.severity
    row.title_en = candidate.title_en
    row.title_zh_cn = candidate.title_zh_cn
    row.message_en = candidate.message_en
    row.message_zh_cn = candidate.message_zh_cn
    row.entity_type = candidate.entity_type
    row.entity_id = candidate.entity_id
    row.evidence_snapshot = candidate.evidence_snapshot
    row.source_refs = candidate.source_refs
    row.warnings = candidate.warnings
    row.simulated = candidate.simulated
    row.human_review_required = candidate.human_review_required
    row.updated_at_utc = now_utc
    row.resolved_at_utc = None
    if severity_increased or condition_returned:
        row.status = "open"
        row.acknowledged_at_utc = None
        row.llm_status = "pending"
        row.llm_summary_en = None
        row.llm_summary_zh_cn = None
        row.llm_last_attempt_at_utc = None
    session.flush()
    return row


def resolve_absent_monitoring_alerts(
    session: Session,
    active_fingerprints: set[str],
    *,
    now_utc: datetime,
) -> int:
    """Resolve worker-managed conditions that are no longer active."""

    rows = session.query(MonitoringAlertRecord).filter(
        MonitoringAlertRecord.status.in_(("open", "acknowledged"))
    )
    resolved = 0
    for row in rows.all():
        if row.fingerprint in active_fingerprints:
            continue
        row.status = "resolved"
        row.resolved_at_utc = now_utc
        row.updated_at_utc = now_utc
        resolved += 1
    session.flush()
    return resolved


def list_monitoring_alerts(
    session: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 100,
) -> list[dict]:
    query = session.query(MonitoringAlertRecord)
    if status:
        query = query.filter(MonitoringAlertRecord.status == status)
    if category:
        query = query.filter(MonitoringAlertRecord.category == category)
    if severity:
        query = query.filter(MonitoringAlertRecord.severity == severity)
    rows = query.order_by(
        MonitoringAlertRecord.updated_at_utc.desc(),
        MonitoringAlertRecord.detected_at_utc.desc(),
    ).limit(limit)
    return [monitoring_alert_payload(row) for row in rows.all()]


def get_monitoring_alert(session: Session, alert_id: str) -> MonitoringAlertRecord | None:
    return session.get(MonitoringAlertRecord, alert_id)


def acknowledge_monitoring_alert(
    session: Session,
    alert_id: str,
    *,
    now_utc: datetime,
) -> MonitoringAlertRecord | None:
    row = session.get(MonitoringAlertRecord, alert_id)
    if row is None:
        return None
    if row.status == "open":
        row.status = "acknowledged"
        row.acknowledged_at_utc = now_utc
        row.updated_at_utc = now_utc
        session.flush()
    return row


def monitoring_summary(session: Session) -> dict:
    rows = session.query(MonitoringAlertRecord).all()
    open_rows = [row for row in rows if row.status == "open"]
    return {
        "open_count": len(open_rows),
        "acknowledged_count": sum(row.status == "acknowledged" for row in rows),
        "critical_count": sum(row.severity == "critical" for row in open_rows),
        "warning_count": sum(row.severity == "warning" for row in open_rows),
        "info_count": sum(row.severity == "info" for row in open_rows),
        "llm_pending_count": sum(
            row.llm_status not in {"success", "not_requested"}
            for row in open_rows
        ),
        "simulated_count": sum(row.simulated for row in open_rows),
    }


def monitoring_alert_payload(row: MonitoringAlertRecord) -> dict:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in MonitoringAlertRecord.__table__.columns
    }


def _json_value(value):
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
