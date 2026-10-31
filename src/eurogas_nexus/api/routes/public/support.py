"""Problem reports to the IT desk, and the notification channels administrators maintain.

A trader who sees a stale price or a failing read presses *Report a problem*: their words,
the client's allowlisted diagnostics (versions, failing reads with correlation ids) and the
server's view at that moment (version, schema, failing and stale sources) land in one
report, and the IT desk is notified on its channels. Reporters see their own reports and
their status; operators see every report and work them.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.api.routes.public.portfolio_common import (
    db_is_configured,
    db_unavailable,
    env,
    identity_id,
    sqlalchemy_error_type,
)

router = APIRouter(tags=["support"])

_P_TO_SEVERITY = {"P1": "critical", "P2": "high", "P3": "medium", "P4": "low"}
_CATEGORIES = ("data", "wrong_figure", "access", "performance", "how_to", "other")
_MAX_CONTEXT_BYTES = 32_000
_OPERATOR_ROLES = {"OPERATOR", "ADMIN"}


def _roles(request: Request) -> set[str]:
    identity = getattr(request.state, "identity", None)
    held = {str(getattr(identity, "role", "") or "").upper()}
    held |= {str(role).upper() for role in (getattr(identity, "roles", ()) or ())}
    return held - {""}


def _require_db() -> None:
    if not db_is_configured():
        raise HTTPException(status_code=503, detail={"code": "runtime_db_not_configured"})


def _server_context(session) -> dict:
    from eurogas_nexus.application.pipeline_health import pipeline_health
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION
    from eurogas_nexus.version import APPLICATION_VERSION

    try:
        health = pipeline_health(session)
    except Exception as exc:  # noqa: BLE001 - a report must not fail because health failed
        health = {"error": type(exc).__name__}
    sources = [
        {
            key: item.get(key)
            for key in ("source_name", "status", "finished_at_utc", "consecutive_failures")
        }
        for item in health.get("sources", [])
        if item.get("consecutive_failures") or str(item.get("status", "")).lower() != "succeeded"
    ][:25]
    return {
        "application_version": APPLICATION_VERSION,
        "schema_revision": DB_SCHEMA_REVISION,
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "sources_not_healthy": sources,
    }


def _report_row(record) -> dict:
    return {
        "report_id": record.report_id,
        "reporter": record.reporter,
        "reporter_role": record.reporter_role,
        "severity": record.severity,
        "category": record.category,
        "summary": record.summary,
        "description": record.description,
        "page": record.page,
        "client_context": record.client_context,
        "server_context": record.server_context,
        "status": record.status,
        "assignee": record.assignee,
        "resolution": record.resolution,
        "created_at_utc": record.created_at_utc.isoformat(),
        "updated_at_utc": record.updated_at_utc.isoformat(),
    }


class SupportReportBody(BaseModel):
    """A problem report: urgency, kind, what went wrong and the client diagnostics."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    severity: str = Field(pattern="^P[1-4]$")
    category: str = Field(pattern="^(" + "|".join(_CATEGORIES) + ")$")
    summary: str = Field(min_length=5, max_length=200)
    description: str = Field(default="", max_length=8000)
    page: str | None = Field(default=None, max_length=200)
    client_context: dict | None = None


@router.post("/api/support/reports")
def post_support_report(body: SupportReportBody, request: Request) -> dict:
    """Send a problem to the IT desk with diagnostics attached (any signed-in user).

    向 IT 支持提交问题：附带客户端诊断包与服务器当时的状态，并通知 IT 渠道。
    """

    from eurogas_nexus.application.notifications import queue_notification

    _require_db()
    if (
        body.client_context is not None
        and len(json.dumps(body.client_context)) > _MAX_CONTEXT_BYTES
    ):
        raise HTTPException(status_code=413, detail={"code": "client_context_too_large"})
    reporter = identity_id(request) or "anonymous"
    roles = sorted(_roles(request)) or ["UNKNOWN"]
    now = datetime.now(UTC)
    report_id = f"SR-{now:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import SupportReportRecord
        from eurogas_nexus.db.repositories.audit import record_audit_event
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            record = SupportReportRecord(
                report_id=report_id,
                reporter=reporter,
                reporter_role=",".join(roles)[:32],
                severity=body.severity,
                category=body.category,
                summary=body.summary,
                description=body.description,
                page=body.page,
                client_context=body.client_context,
                server_context=_server_context(session),
                status="open",
                assignee=None,
                resolution=None,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session.add(record)
            queue_notification(
                session,
                category="support",
                severity=_P_TO_SEVERITY[body.severity],
                title=f"{report_id} {body.severity} {body.summary}",
                body=(
                    f"Reported by {reporter} ({record.reporter_role}) on {body.page or '-'}.\n"
                    f"Category: {body.category}\n\n{body.description}"
                ),
                dedupe_key=f"support:{report_id}",
                now=now,
            )
            record_audit_event(
                session,
                event_type="support.report",
                principal=reporter,
                action="support.report.create",
                resource=f"support_report:{report_id}",
                outcome="created",
                severity="info",
                detail=f"{body.severity} {body.category}",
            )
            session.commit()
            payload = _report_row(record)
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    return env(payload, request, "runtime-postgresql", [])


@router.get("/api/support/reports")
def list_support_reports(
    request: Request, status: str | None = Query(None, pattern="^(open|acknowledged|resolved)$")
) -> dict:
    """Problem reports: operators see all of them, everyone else their own."""

    _require_db()
    everyone = bool(_roles(request) & _OPERATOR_ROLES)
    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import SupportReportRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            query = session.query(SupportReportRecord)
            if not everyone:
                query = query.filter(SupportReportRecord.reporter == (identity_id(request) or ""))
            if status:
                query = query.filter(SupportReportRecord.status == status)
            rows = [
                _report_row(record)
                for record in query.order_by(SupportReportRecord.created_at_utc.desc())
                .limit(500)
                .all()
            ]
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    return env(
        {"rows": rows, "scope": "all" if everyone else "mine"}, request, "runtime-postgresql", []
    )


class SupportReportUpdate(BaseModel):
    """The IT desk's change to a report: status, assignee, resolution note."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: str = Field(pattern="^(open|acknowledged|resolved)$")
    assignee: str | None = Field(default=None, max_length=128)
    resolution: str | None = Field(default=None, max_length=4000)


@router.patch("/api/support/reports/{report_id}")
def patch_support_report(report_id: str, body: SupportReportUpdate, request: Request) -> dict:
    """Acknowledge, assign or resolve a report (IT desk, audited)."""

    _require_db()
    if body.status == "resolved" and not body.resolution:
        raise HTTPException(status_code=422, detail={"code": "resolution_required"})
    actor = identity_id(request) or "api"
    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import SupportReportRecord
        from eurogas_nexus.db.repositories.audit import record_audit_event
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            record = session.get(SupportReportRecord, report_id)
            if record is None:
                raise HTTPException(status_code=404, detail={"code": "report_not_found"})
            record.status = body.status
            record.assignee = body.assignee or record.assignee or actor
            if body.resolution is not None:
                record.resolution = body.resolution
            record.updated_at_utc = datetime.now(UTC)
            record_audit_event(
                session,
                event_type="support.report",
                principal=actor,
                action=f"support.report.{body.status}",
                resource=f"support_report:{report_id}",
                outcome=body.status,
                severity="info",
                detail=(body.resolution or "")[:500],
            )
            session.commit()
            payload = _report_row(record)
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    return env(payload, request, "runtime-postgresql", [])


# -------------------------------------------------------------------- notification channels


def _channel_row(record, last_delivery=None) -> dict:
    return {
        "channel_id": record.channel_id,
        "name": record.name,
        "kind": record.kind,
        "recipients": record.recipients,
        "webhook": record.secret_preview,
        "categories": record.categories or [],
        "min_severity": record.min_severity,
        "enabled": record.enabled,
        "updated_by": record.updated_by,
        "updated_at_utc": record.updated_at_utc.isoformat(),
        "last_delivery": last_delivery,
    }


@router.get("/api/settings/notification-channels")
def list_notification_channels(request: Request) -> dict:
    """Notification channels with their last delivery (administrators)."""

    _require_db()
    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import NotificationChannelRecord, NotificationDeliveryRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = []
            for record in session.query(NotificationChannelRecord).order_by(
                NotificationChannelRecord.name
            ):
                last = (
                    session.query(NotificationDeliveryRecord)
                    .filter(NotificationDeliveryRecord.channel_id == record.channel_id)
                    .order_by(NotificationDeliveryRecord.attempted_at_utc.desc())
                    .first()
                )
                rows.append(
                    _channel_row(
                        record,
                        None
                        if last is None
                        else {
                            "status": last.status,
                            "detail": (last.detail or "").split("|", 1)[-1],
                            "at_utc": last.attempted_at_utc.isoformat(),
                        },
                    )
                )
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    return env({"rows": rows}, request, "runtime-postgresql", [])


class NotificationChannelBody(BaseModel):
    """A notification channel: kind, recipients or webhook, categories, severity floor."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(pattern="^(email|webhook|sms)$")
    recipients: str | None = Field(default=None, max_length=2000)
    webhook_url: str | None = Field(default=None, max_length=1000)
    categories: list[str] = Field(default_factory=list, max_length=10)
    min_severity: str = Field(default="high", pattern="^(info|low|medium|high|critical)$")
    enabled: bool = True


@router.put("/api/settings/notification-channels/{channel_id}")
def put_notification_channel(
    channel_id: str, body: NotificationChannelBody, request: Request
) -> dict:
    """Create or change a channel (administrators, audited). Webhook URLs are encrypted."""

    from eurogas_nexus.application.notifications import CATEGORIES
    from eurogas_nexus.security.credentials import (
        credential_store_configured,
        encrypt_credential_payload,
    )

    _require_db()
    if not channel_id or len(channel_id) > 64:
        raise HTTPException(status_code=422, detail={"code": "channel_id_invalid"})
    unknown = [c for c in body.categories if c not in CATEGORIES]
    if unknown:
        raise HTTPException(status_code=422, detail={"code": "unknown_category", "values": unknown})
    if body.kind in {"email", "sms"} and not (body.recipients or "").strip():
        raise HTTPException(status_code=422, detail={"code": "recipients_required"})
    actor = identity_id(request) or "api"
    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import NotificationChannelRecord
        from eurogas_nexus.db.repositories.audit import record_audit_event
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            record = session.get(NotificationChannelRecord, channel_id)
            created = record is None
            if record is None:
                record = NotificationChannelRecord(channel_id=channel_id)
                session.add(record)
            if body.kind == "webhook" and body.webhook_url:
                if not body.webhook_url.startswith("https://"):
                    raise HTTPException(status_code=422, detail={"code": "webhook_must_be_https"})
                if not credential_store_configured():
                    raise HTTPException(
                        status_code=503, detail={"code": "credential_store_not_configured"}
                    )
                envelope = encrypt_credential_payload({"token": body.webhook_url})
                record.secret_ciphertext = envelope.encrypted_payload
                record.secret_preview = envelope.redacted_preview
            elif body.kind == "webhook" and record.secret_ciphertext is None:
                raise HTTPException(status_code=422, detail={"code": "webhook_url_required"})
            record.name, record.kind = body.name, body.kind
            record.recipients = body.recipients if body.kind != "webhook" else None
            record.categories = body.categories or None
            record.min_severity, record.enabled = body.min_severity, body.enabled
            record.updated_by, record.updated_at_utc = actor, datetime.now(UTC)
            record_audit_event(
                session,
                event_type="settings.notifications",
                principal=actor,
                action="settings.notification_channel.update",
                resource=f"notification_channel:{channel_id}",
                outcome="created" if created else "updated",
                severity="info",
                detail=f"{body.kind} {body.min_severity} {','.join(body.categories)}",
            )
            session.commit()
            payload = _channel_row(record)
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    return env(payload, request, "runtime-postgresql", [])


@router.post("/api/settings/notification-channels/{channel_id}/test")
def test_notification_channel(channel_id: str, request: Request) -> dict:
    """Send a test message now and report what happened (administrators)."""

    from eurogas_nexus.application.notifications import DEFAULT_SENDERS, Message

    _require_db()
    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import NotificationChannelRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            record = session.get(NotificationChannelRecord, channel_id)
            if record is None:
                raise HTTPException(status_code=404, detail={"code": "channel_not_found"})
            try:
                DEFAULT_SENDERS[record.kind](
                    record,
                    Message("support", "info", "Test notification", "Channel test from Settings."),
                )
                result = {"sent": True, "detail": ""}
            except Exception as exc:  # noqa: BLE001 - reported to the administrator
                result = {"sent": False, "detail": f"{type(exc).__name__}: {exc}"[:300]}
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc
    return env(result, request, "runtime-postgresql", [])
