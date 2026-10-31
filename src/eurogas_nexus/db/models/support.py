"""Problem reports to the IT desk, and the notification outbox, channels and deliveries."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class SupportReportRecord(Base):
    """A user's problem report: their words, the client's diagnostics and server context."""

    __tablename__ = "support_reports"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reporter: Mapped[str] = mapped_column(String(128), nullable=False)
    reporter_role: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(4), nullable=False)  # P1..P4
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    page: Mapped[str | None] = mapped_column(String(200), nullable=True)
    #: The client's allowlisted diagnostics bundle (versions, failing reads, correlation ids).
    client_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: What the server knew at that moment: version, schema, failing and stale sources.
    server_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # open, acknowledged, resolved
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationChannelRecord(Base):
    """Where notifications go: an email list, a chat webhook or an SMS list."""

    __tablename__ = "notification_channels"

    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # email, webhook, sms
    #: Email addresses or phone numbers (comma-separated); empty for a webhook.
    recipients: Mapped[str | None] = mapped_column(Text(), nullable=True)
    #: Webhook URL encrypted with the credential store key; never returned in clear.
    secret_ciphertext: Mapped[str | None] = mapped_column(Text(), nullable=True)
    secret_preview: Mapped[str | None] = mapped_column(String(64), nullable=True)
    categories: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    min_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationOutboxRecord(Base):
    """One thing worth telling someone about, written once and dispatched by the worker."""

    __tablename__ = "notification_outbox"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_notification_outbox_dedupe"),)

    notification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispatched_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NotificationDeliveryRecord(Base):
    """The result of sending one notification to one channel."""

    __tablename__ = "notification_deliveries"

    notification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # sent, failed, skipped
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempted_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
