"""Stale feeds and the market event outbox raise monitoring alerts (M6).

- an enabled source whose last success is older than its stale threshold raises one alert
  (the same alert on every scan, not one per scan) and it resolves when the source is fresh;
- a source never yet successful alerts only after it has been enabled past that threshold;
- a dead letter raises an alert naming the consumer and the event; replaying it resolves it;
- a delivery left waiting past fifteen minutes raises an alert; draining resolves it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MarketEventDeliveryRecord,
    MonitoringAlertRecord,
    SourceRuntimeStateRecord,
)
from eurogas_nexus.db.repositories.dataops import ensure_source_runtime_state
from eurogas_nexus.domain.dataops.contracts import FreshnessState
from eurogas_nexus.domain.dataops.freshness import FreshnessEvidence, evaluate_source_freshness
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.domain.market_events import MarketEvent

NOW = datetime(2026, 11, 17, 11, 0, tzinfo=UTC)  # a Tuesday: exchange calendars are open


@pytest.fixture()
def session(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'alerts.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with Session(engine) as session:
        yield session


def _scan(session, at):
    return scan_monitoring_conditions(session, now_utc=at, enrich_with_llm=False)


def _open(session, alert_type):
    return (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.alert_type == alert_type)
        .filter(MonitoringAlertRecord.resolved_at_utc.is_(None))
        .all()
    )


def _scheduled_source():
    """A source definition that, at NOW, expects updates: a month-old success is stale."""

    for definition in source_definitions():
        long_ago = evaluate_source_freshness(
            definition, FreshnessEvidence(last_success_at_utc=NOW - timedelta(days=30)), now_utc=NOW
        )
        just_now = evaluate_source_freshness(
            definition, FreshnessEvidence(last_success_at_utc=NOW), now_utc=NOW
        )
        if long_ago.state is FreshnessState.STALE and just_now.state is FreshnessState.FRESH:
            return definition
    raise AssertionError("no scheduled source with a stale threshold")


def _enabled(session, definition, *, last_success, activated):
    state = ensure_source_runtime_state(session, definition, now_utc=activated)
    state.enabled = True
    state.activated_at_utc = activated
    state.last_success_at_utc = last_success
    session.commit()
    return state


def test_a_stale_source_raises_one_alert_until_it_is_fresh(session) -> None:
    definition = _scheduled_source()
    state = _enabled(
        session,
        definition,
        last_success=NOW - timedelta(days=30),
        activated=NOW - timedelta(days=60),
    )
    _scan(session, NOW)
    (alert,) = _open(session, "source_stale")
    assert alert.entity_id == definition.source_id
    assert alert.evidence_snapshot["freshness_state"] == "STALE"
    # The stored state still says whatever its last run left; the scan judges by time.
    _scan(session, NOW + timedelta(minutes=5))
    (again,) = _open(session, "source_stale")
    assert again.alert_id == alert.alert_id
    assert (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.alert_type == "source_stale")
        .count()
        == 1
    )

    state.last_success_at_utc = NOW + timedelta(minutes=9)
    session.commit()
    _scan(session, NOW + timedelta(minutes=10))
    assert _open(session, "source_stale") == []


def test_a_source_never_successful_alerts_only_after_its_stale_threshold(session) -> None:
    definition = _scheduled_source()
    threshold = timedelta(minutes=definition.freshness_policy.stale_after_minutes)
    state = _enabled(session, definition, last_success=None, activated=NOW - timedelta(minutes=1))
    _scan(session, NOW)
    assert _open(session, "source_stale") == []
    state.activated_at_utc = NOW - threshold - timedelta(minutes=1)
    session.commit()
    _scan(session, NOW)
    (alert,) = _open(session, "source_stale")
    assert alert.evidence_snapshot["freshness_state"] == "MISSING"


def test_a_disabled_source_raises_nothing(session) -> None:
    definition = _scheduled_source()
    state = _enabled(
        session,
        definition,
        last_success=NOW - timedelta(days=30),
        activated=NOW - timedelta(days=60),
    )
    state.enabled = False
    session.commit()
    _scan(session, NOW)
    assert _open(session, "source_stale") == []
    assert session.get(SourceRuntimeStateRecord, definition.source_id) is not None


def _publish(session, *, ingested):
    published = outbox.publish(
        session,
        MarketEvent(
            source_id="src-test",
            event_type="price.updated",
            subject_key="hub:TTF:2026-11-18",
            dependency_keys=("hub:TTF:2026-11-18",),
            ingested_at_utc=ingested,
            payload={"price": "31.25"},
        ),
    )
    session.commit()
    return published


def test_a_dead_letter_names_the_consumer_and_the_event_until_replayed(session) -> None:
    published = _publish(session, ingested=NOW)
    delivery = session.query(MarketEventDeliveryRecord).one()
    delivery.status, delivery.attempts, delivery.last_error = outbox.DEAD, 5, "evaluator raised"
    session.commit()

    _scan(session, NOW + timedelta(minutes=1))
    (alert,) = _open(session, "market_event_dead_letter")
    assert alert.entity_id == "opportunities" and alert.severity == "critical"
    assert published.event_id in alert.message_en and "hub:TTF:2026-11-18" in alert.message_en
    assert _open(session, "market_event_lag") == []  # a dead letter waits on no worker

    outbox.replay(session, "opportunities", since_utc=NOW - timedelta(hours=1))
    session.commit()
    _scan(session, NOW + timedelta(minutes=2))
    assert _open(session, "market_event_dead_letter") == []


def test_deliveries_left_waiting_raise_a_lag_alert_until_drained(session) -> None:
    _publish(session, ingested=NOW)
    _scan(session, NOW + timedelta(minutes=10))
    assert _open(session, "market_event_lag") == []  # within fifteen minutes

    _scan(session, NOW + timedelta(minutes=20))
    (alert,) = _open(session, "market_event_lag")
    assert alert.severity == "warning" and alert.entity_id == "opportunities"
    _scan(session, NOW + timedelta(minutes=90))
    (alert,) = _open(session, "market_event_lag")
    assert alert.severity == "critical"

    outbox.process(session, "opportunities", now_utc=NOW + timedelta(minutes=91))
    session.commit()
    _scan(session, NOW + timedelta(minutes=92))
    assert _open(session, "market_event_lag") == []
