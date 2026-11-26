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
    # A critical limit breach nobody has acknowledged keeps its severity when the figure
    # improves (say a limit raised to 92 %): the change is shown, the breach is not forgotten
    # until someone acknowledges it (QA-R-01).
    held = needs_acknowledgement(row) and not severity_increased and not condition_returned
    if next_event_time > previous_event_time:
        row.occurrence_count += 1
        row.event_time_utc = candidate.event_time_utc
    row.category = candidate.category
    row.alert_type = candidate.alert_type
    row.severity = row.severity if held else candidate.severity
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


#: How a held breach says its condition cleared (a warning line, so every client shows it).
CLEARED_PREFIX = "Condition cleared at"


def needs_acknowledgement(row: MonitoringAlertRecord) -> bool:
    """A critical limit alert for human review that nobody has acknowledged yet."""

    return (
        row.category == "limits"
        and row.severity == "critical"
        and bool(row.human_review_required)
        and row.status == "open"
    )


def _cleared_notes(warnings: list[str] | None) -> list[str]:
    return [line for line in (warnings or []) if str(line).startswith(CLEARED_PREFIX)]


def resolve_absent_monitoring_alerts(
    session: Session,
    active_fingerprints: set[str],
    *,
    now_utc: datetime,
) -> int:
    """Resolve worker-managed conditions that are no longer active.

    A critical limit breach that nobody acknowledged stays open when its condition clears (a
    limit raised, a deal unlinked): it says when it cleared and waits for a person to
    acknowledge it, and the next scan after that closes it (QA-R-01).
    """

    rows = session.query(MonitoringAlertRecord).filter(
        MonitoringAlertRecord.status.in_(("open", "acknowledged"))
    )
    resolved = 0
    resolved_ids: list[str] = []
    for row in rows.all():
        if row.fingerprint in active_fingerprints:
            continue
        if needs_acknowledgement(row):
            if not _cleared_notes(row.warnings):
                when = _as_utc(now_utc).strftime("%Y-%m-%d %H:%M UTC")
                row.warnings = [
                    *(row.warnings or []),
                    f"{CLEARED_PREFIX} {when}; acknowledge to close.",
                ]
                row.updated_at_utc = now_utc
            continue
        row.status = "resolved"
        row.resolved_at_utc = now_utc
        row.updated_at_utc = now_utc
        resolved_ids.append(row.alert_id)
        resolved += 1
    if resolved_ids:
        _drop_reader_marks(session, resolved_ids)
    session.flush()
    return resolved


def list_monitoring_alerts(
    session: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    limit: int = 100,
    visible=None,
) -> list[dict]:
    """List monitoring alerts with optional filters, newest first.

    列出监控告警（可按状态/分类/级别过滤，按更新时间倒序）。

    Args:
        session: DB session.
        status: Status filter, or None.
        category: Category filter, or None.
        severity: Severity filter, or None.
        limit: Max rows.
        visible: Optional predicate over rows; rows it rejects are left out.

    Returns:
        List of alert payload dicts.
    """

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
    )
    if visible is None:
        return [monitoring_alert_payload(row) for row in rows.limit(limit).all()]
    return [monitoring_alert_payload(row) for row in rows.all() if visible(row)][:limit]


def get_monitoring_alert(session: Session, alert_id: str) -> MonitoringAlertRecord | None:
    """Fetch one alert by id (None when absent)."""

    return session.get(MonitoringAlertRecord, alert_id)


def acknowledge_monitoring_alert(
    session: Session,
    alert_id: str,
    *,
    now_utc: datetime,
) -> tuple[MonitoringAlertRecord, bool] | None:
    """Acknowledge an open alert, at most once, and report whether it transitioned.

    确认一条 open 状态的告警；非 open 状态（含已确认、已恢复）保持不变。

    The transition is a single conditional UPDATE (``status = 'open'``), so the database,
    not a read-then-write in the process, decides who wins: concurrent acknowledgements
    race on the row and exactly one moves it, which is what keeps one actor, one timestamp
    and one success audit per acknowledgement. A repeat or no-op acknowledgement changes
    nothing, so the original acknowledger and time are preserved; a resolved alert is never
    reopened or acknowledged.

    Args:
        session: DB session.
        alert_id: Alert id.
        now_utc: Acknowledge time.

    Returns:
        ``(record, transitioned)`` where ``transitioned`` is True only when this call moved
        the alert from open to acknowledged; None when no alert has that id.
    """

    transitioned = (
        session.query(MonitoringAlertRecord)
        .filter(
            MonitoringAlertRecord.alert_id == alert_id,
            MonitoringAlertRecord.status == "open",
        )
        .update(
            {
                MonitoringAlertRecord.status: "acknowledged",
                MonitoringAlertRecord.acknowledged_at_utc: now_utc,
                MonitoringAlertRecord.updated_at_utc: now_utc,
            },
            synchronize_session=False,
        )
    )
    # The conditional UPDATE bypasses the identity map, so reload before serializing.
    session.expire_all()
    row = session.get(MonitoringAlertRecord, alert_id)
    if row is None:
        return None
    return row, transitioned == 1


def monitoring_summary(session: Session, visible=None) -> dict:
    """Aggregate alert counts by status/severity/LLM state.

    汇总告警统计：按状态/级别/LLM 待处理/模拟数据计数。

    Args:
        session: DB session.

    Returns:
        Dict of aggregate counters.
    """

    rows = [
        row
        for row in session.query(MonitoringAlertRecord).all()
        if visible is None or visible(row)
    ]
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
    """Serialize an alert row to its API payload (datetimes -> ISO).

    Args:
        row: The alert record.

    Returns:
        Dict with every table column, datetimes normalized to UTC ISO.
    """

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


#: The personal marks a person can put on alerts in their own alert centre.
READER_ACTIONS = ("read", "dismiss", "restore")


def apply_reader_action(
    session: Session,
    principal_id: str,
    alerts: list[MonitoringAlertRecord],
    action: str,
    *,
    now_utc: datetime,
) -> int:
    """Mark alerts read, dismissed or restored for one person and return how many changed.

    The mark records the alert's severity as it stands now: an alert that escalates
    afterwards, or clears and comes back, counts as new again for that person. Dismissing also marks
    the alert read. Restoring clears the dismissal only; the alert stays read.
    """

    from eurogas_nexus.db.models import MonitoringAlertReaderStateRecord

    if action not in READER_ACTIONS:
        raise ValueError(f"unknown reader action {action!r}")
    changed = 0
    for alert in alerts:
        row = session.get(MonitoringAlertReaderStateRecord, (principal_id, alert.alert_id))
        if row is None:
            if action == "restore":
                continue
            row = MonitoringAlertReaderStateRecord(
                principal_id=principal_id, alert_id=alert.alert_id
            )
            session.add(row)
        if action in {"read", "dismiss"}:
            row.read_at_utc = now_utc
            row.read_event_time_utc = alert.event_time_utc
            row.read_severity = alert.severity
        if action == "dismiss":
            row.dismissed_at_utc = now_utc
            row.dismissed_event_time_utc = alert.event_time_utc
            row.dismissed_severity = alert.severity
        if action == "restore":
            row.dismissed_at_utc = None
            row.dismissed_event_time_utc = None
            row.dismissed_severity = None
        changed += 1
    session.flush()
    return changed


def reader_state(
    session: Session,
    principal_id: str,
    alerts: list[MonitoringAlertRecord],
) -> dict[str, dict]:
    """One person's current marks on the given alerts, keyed by alert id.

    An alert is ``read`` when the person read it and it has not escalated since, and
    ``dismissed`` on the same terms for a dismissal. Alerts with neither mark are left out.
    """

    from eurogas_nexus.db.models import MonitoringAlertReaderStateRecord

    if not alerts:
        return {}
    by_id = {alert.alert_id: alert for alert in alerts}
    rows = (
        session.query(MonitoringAlertReaderStateRecord)
        .filter(
            MonitoringAlertReaderStateRecord.principal_id == principal_id,
            MonitoringAlertReaderStateRecord.alert_id.in_(list(by_id)),
        )
        .all()
    )
    state: dict[str, dict] = {}
    for row in rows:
        alert = by_id[row.alert_id]
        read = row.read_at_utc is not None and _still_current(
            alert, row.read_event_time_utc, row.read_severity
        )
        dismissed = row.dismissed_at_utc is not None and _still_current(
            alert, row.dismissed_event_time_utc, row.dismissed_severity
        )
        if read or dismissed:
            state[row.alert_id] = {
                "read": read,
                "dismissed": dismissed,
                "read_at_utc": row.read_at_utc.isoformat() if read and row.read_at_utc else None,
                "dismissed_at_utc": (
                    row.dismissed_at_utc.isoformat() if dismissed and row.dismissed_at_utc else None
                ),
            }
    return state


def _drop_reader_marks(session: Session, alert_ids: list[str]) -> None:
    """Forget every reader's marks on resolved alerts, so a return reads as new."""

    from eurogas_nexus.db.models import MonitoringAlertReaderStateRecord

    session.query(MonitoringAlertReaderStateRecord).filter(
        MonitoringAlertReaderStateRecord.alert_id.in_(alert_ids)
    ).delete(synchronize_session=False)


def _still_current(
    alert: MonitoringAlertRecord,
    marked_event_time: datetime | None,
    marked_severity: str | None,
) -> bool:
    """True while the alert has not escalated since the mark."""

    # The event time is not compared: for a level alert (a credit line at 86%) it moves on
    # every revaluation without anything new for the reader. A condition that clears and comes
    # back starts fresh because resolving an alert drops every reader's marks on it.
    del marked_event_time
    return SEVERITY_ORDER.get(alert.severity, 0) <= SEVERITY_ORDER.get(marked_severity or "", 0)
