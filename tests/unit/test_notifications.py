"""Notification outbox: dedupe, channel matching, delivery, retry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.notifications import (
    MAX_ATTEMPTS,
    Message,
    dispatch,
    queue_notification,
    send_email,
    send_sms,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    NotificationChannelRecord,
    NotificationDeliveryRecord,
    NotificationOutboxRecord,
)

NOW = datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def _session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'n.sqlite'}", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _channel(cid, kind="email", categories=None, min_severity="high", enabled=True):
    return NotificationChannelRecord(
        channel_id=cid,
        name=cid,
        kind=kind,
        recipients="it@example.com",
        secret_ciphertext=None,
        secret_preview=None,
        categories=categories,
        min_severity=min_severity,
        enabled=enabled,
        updated_by="t",
        updated_at_utc=NOW,
    )


def test_outbox_dedupes_and_dispatch_matches_category_and_severity(tmp_path):
    session = _session(tmp_path)
    session.add_all(
        [
            _channel("it", categories=["support"], min_severity="medium"),
            _channel("desk", categories=["alert"], min_severity="high"),
            _channel("off", enabled=False, min_severity="info"),
        ]
    )
    assert queue_notification(
        session,
        category="support",
        severity="high",
        title="SR-1",
        body="b",
        dedupe_key="support:SR-1",
        now=NOW,
    )
    assert not queue_notification(
        session,
        category="support",
        severity="high",
        title="SR-1",
        body="b",
        dedupe_key="support:SR-1",
        now=NOW,
    )
    queue_notification(
        session,
        category="alert",
        severity="medium",
        title="stale",
        body="b",
        dedupe_key="alert:1",
        now=NOW,
    )
    sent: list[tuple[str, str]] = []
    counts = dispatch(
        session, now=NOW, senders={"email": lambda ch, m: sent.append((ch.channel_id, m.title))}
    )
    assert sent == [("it", "SR-1")]  # the medium alert is below the desk channel's floor
    assert counts["sent"] == 1
    assert all(r.dispatched_at_utc for r in session.query(NotificationOutboxRecord))


def test_a_failed_delivery_is_retried_then_given_up(tmp_path):
    session = _session(tmp_path)
    session.add(_channel("it", min_severity="info"))
    queue_notification(
        session,
        category="support",
        severity="critical",
        title="down",
        body="b",
        dedupe_key="support:SR-2",
        now=NOW,
    )

    def boom(channel, message):
        raise ConnectionError("relay refused")

    moment = NOW
    for attempt in range(1, MAX_ATTEMPTS + 1):
        counts = dispatch(session, now=moment, senders={"email": boom})
        assert counts["failed"] == 1
        delivery = session.query(NotificationDeliveryRecord).one()
        assert delivery.detail.startswith(f"{attempt}|ConnectionError")
        # Too soon: no new attempt.
        assert dispatch(session, now=moment + timedelta(minutes=1), senders={"email": boom}) == {
            "sent": 0,
            "failed": 0,
            "skipped": 0,
        }
        moment += timedelta(minutes=6)
    row = session.query(NotificationOutboxRecord).one()
    assert row.dispatched_at_utc is not None  # given up after the last attempt


def test_senders_refuse_without_configuration():
    channel = _channel("it")
    message = Message("support", "high", "t", "b")
    for sender in (send_email, send_sms):
        try:
            sender(channel, message, environ={})
        except RuntimeError as exc:
            assert "not configured" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected a refusal")
