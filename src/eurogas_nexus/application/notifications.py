"""Tell people when something needs them: email, chat webhook or SMS, through an outbox.

Anything worth telling someone about is written once to ``notification_outbox`` with a
dedupe key (a monitoring alert, a problem report to the IT desk, a tariff deadline), so the
same event never notifies twice. The worker dispatches each outbox row to every enabled
channel whose categories and minimum severity match, records one delivery per channel and
retries a failed delivery up to :data:`MAX_ATTEMPTS` times, at least
:data:`RETRY_AFTER` apart. Nothing is sent from a request thread.

Channels (Settings → Notifications, administrators):

``email``   the firm's own SMTP relay (``EUROGAS_NEXUS_SMTP_*``); recipients listed on the
            channel. No third-party mail service is used.
``webhook`` a Microsoft Teams or Slack incoming webhook; the URL is a secret, stored
            encrypted with the credential-store key and never returned in clear.
``sms``     the firm's own SMS gateway (``EUROGAS_NEXUS_SMS_GATEWAY_URL``, optional bearer
            token), which receives ``{"to": ..., "text": ...}`` per number. Kept for what
            cannot wait: P1 problems and high-severity alerts by default.
"""

from __future__ import annotations

import os
import smtplib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
CATEGORIES = ("alert", "support", "limits", "tariff", "source")
KINDS = ("email", "webhook", "sms")
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=5)
SMS_MAX_CHARS = 300

SMTP_HOST_ENV = "EUROGAS_NEXUS_SMTP_HOST"
SMTP_PORT_ENV = "EUROGAS_NEXUS_SMTP_PORT"
SMTP_USERNAME_ENV = "EUROGAS_NEXUS_SMTP_USERNAME"
SMTP_PASSWORD_ENV = "EUROGAS_NEXUS_SMTP_PASSWORD"
SMTP_FROM_ENV = "EUROGAS_NEXUS_SMTP_FROM"
SMTP_STARTTLS_ENV = "EUROGAS_NEXUS_SMTP_STARTTLS"
SMS_GATEWAY_URL_ENV = "EUROGAS_NEXUS_SMS_GATEWAY_URL"
SMS_GATEWAY_TOKEN_ENV = "EUROGAS_NEXUS_SMS_GATEWAY_TOKEN"


@dataclass(frozen=True)
class Message:
    category: str
    severity: str
    title: str
    body: str


Sender = Callable[[object, Message], None]


def severity_rank(value: str) -> int:
    return SEVERITY_ORDER.get((value or "").casefold(), 0)


def queue_notification(
    session, *, category: str, severity: str, title: str, body: str, dedupe_key: str, now: datetime
) -> bool:
    """Write one outbox row unless the same event is already there; True when written."""

    from eurogas_nexus.db.models import NotificationOutboxRecord

    if (
        session.query(NotificationOutboxRecord.notification_id)
        .filter(NotificationOutboxRecord.dedupe_key == dedupe_key[:200])
        .first()
    ):
        return False
    session.add(
        NotificationOutboxRecord(
            notification_id=uuid.uuid4().hex,
            category=category,
            severity=severity.casefold(),
            title=title[:256],
            body=body[:8000],
            dedupe_key=dedupe_key[:200],
            created_at_utc=now,
            dispatched_at_utc=None,
        )
    )
    return True


def mirror_monitoring_alerts(session, *, now: datetime) -> int:
    """Queue every open monitoring alert once (keyed by alert id)."""

    from eurogas_nexus.db.models import MonitoringAlertRecord

    queued = 0
    for alert in (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
        .filter(MonitoringAlertRecord.acknowledged_at_utc.is_(None))
        .all()
    ):
        queued += queue_notification(
            session,
            category="alert",
            severity=alert.severity,
            title=alert.title_en,
            body=alert.message_en,
            dedupe_key=f"alert:{alert.alert_id}",
            now=now,
        )
    return queued


# ------------------------------------------------------------------------------- senders


def _recipients(channel) -> list[str]:
    return [item.strip() for item in (channel.recipients or "").split(",") if item.strip()]


def send_email(channel, message: Message, environ=None) -> None:
    env = os.environ if environ is None else environ
    host = env.get(SMTP_HOST_ENV, "").strip()
    sender = env.get(SMTP_FROM_ENV, "").strip()
    if not host or not sender:
        raise RuntimeError("SMTP relay not configured (EUROGAS_NEXUS_SMTP_HOST and _FROM)")
    email = EmailMessage()
    email["From"] = sender
    email["To"] = ", ".join(_recipients(channel))
    email["Subject"] = f"[Eurogas Nexus] {message.severity.upper()}: {message.title}"
    email.set_content(f"{message.body}\n\n-- Eurogas Nexus ({message.category})")
    port = int(env.get(SMTP_PORT_ENV, "587") or 587)
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if env.get(SMTP_STARTTLS_ENV, "true").strip().casefold() not in {"0", "false", "no"}:
            smtp.starttls()
        username = env.get(SMTP_USERNAME_ENV, "").strip()
        if username:
            smtp.login(username, env.get(SMTP_PASSWORD_ENV, ""))
        smtp.send_message(email)


def send_webhook(channel, message: Message) -> None:
    import httpx

    from eurogas_nexus.security.credentials import decrypt_credential_payload

    if not channel.secret_ciphertext:
        raise RuntimeError("webhook URL missing")
    url = decrypt_credential_payload(channel.secret_ciphertext).get("token", "")
    # Teams and Slack incoming webhooks both accept a plain {"text": ...} body.
    text = f"**{message.severity.upper()} · {message.title}**\n\n{message.body}"
    response = httpx.post(url, json={"text": text}, timeout=15)
    response.raise_for_status()


def send_sms(channel, message: Message, environ=None) -> None:
    import httpx

    env = os.environ if environ is None else environ
    url = env.get(SMS_GATEWAY_URL_ENV, "").strip()
    if not url:
        raise RuntimeError("SMS gateway not configured (EUROGAS_NEXUS_SMS_GATEWAY_URL)")
    token = env.get(SMS_GATEWAY_TOKEN_ENV, "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    text = f"Eurogas Nexus {message.severity.upper()}: {message.title}"[:SMS_MAX_CHARS]
    for number in _recipients(channel):
        response = httpx.post(url, json={"to": number, "text": text}, headers=headers, timeout=15)
        response.raise_for_status()


DEFAULT_SENDERS: dict[str, Sender] = {
    "email": send_email,
    "webhook": send_webhook,
    "sms": send_sms,
}


def channel_matches(channel, message: Message) -> bool:
    if not channel.enabled:
        return False
    categories = channel.categories or []
    if categories and message.category not in categories:
        return False
    return severity_rank(message.severity) >= severity_rank(channel.min_severity)


def dispatch(session, *, now: datetime, senders: dict[str, Sender] | None = None) -> dict:
    """Send due outbox rows to matching channels; returns counts by outcome."""

    from eurogas_nexus.db.models import (
        NotificationChannelRecord,
        NotificationDeliveryRecord,
        NotificationOutboxRecord,
    )

    senders = senders or DEFAULT_SENDERS
    channels = session.query(NotificationChannelRecord).all()
    counts = {"sent": 0, "failed": 0, "skipped": 0}
    pending = (
        session.query(NotificationOutboxRecord)
        .filter(NotificationOutboxRecord.dispatched_at_utc.is_(None))
        .order_by(NotificationOutboxRecord.created_at_utc)
        .limit(200)
        .all()
    )
    for row in pending:
        message = Message(row.category, row.severity, row.title, row.body)
        settled = True
        for channel in channels:
            if not channel_matches(channel, message):
                continue
            delivery = session.get(
                NotificationDeliveryRecord, (row.notification_id, channel.channel_id)
            )
            if delivery is not None and delivery.status == "sent":
                continue
            attempts = int((delivery.detail or "0|").split("|", 1)[0] or 0) if delivery else 0
            if delivery is not None and (
                attempts >= MAX_ATTEMPTS or _aware(delivery.attempted_at_utc) > now - RETRY_AFTER
            ):
                settled = settled and attempts >= MAX_ATTEMPTS
                continue
            try:
                senders[channel.kind](channel, message)
                status, detail = "sent", f"{attempts + 1}|"
                counts["sent"] += 1
            except Exception as exc:  # noqa: BLE001 - one channel's failure is recorded, not raised
                status, detail = "failed", f"{attempts + 1}|{type(exc).__name__}: {exc}"[:500]
                counts["failed"] += 1
                if attempts + 1 < MAX_ATTEMPTS:
                    settled = False
            if delivery is None:
                delivery = NotificationDeliveryRecord(
                    notification_id=row.notification_id, channel_id=channel.channel_id
                )
                session.add(delivery)
            delivery.status, delivery.detail, delivery.attempted_at_utc = status, detail, now
        if settled:
            row.dispatched_at_utc = now
    session.flush()
    return counts


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
