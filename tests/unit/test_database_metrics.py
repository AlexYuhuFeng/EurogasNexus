"""Scrape-time database metrics: freshness by the clock, heartbeat age, jobs, feed, outbox."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.dataops_observability import database_metric_text
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    DataOperationsHeartbeatRecord,
    SourceRuntimeStateRecord,
)
from eurogas_nexus.db.models.jobs import JobRecord
from eurogas_nexus.db.models.market_events import MarketEventDeliveryRecord, MarketEventRecord
from eurogas_nexus.db.models.market_intelligence import MarketQuoteRecord

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def _samples(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            name, value = line.rsplit(" ", 1)
            out[name] = value
    return out


def _state(source_id: str, **overrides) -> SourceRuntimeStateRecord:
    values = dict(
        source_id=source_id,
        provider="ECB",
        dataset="fx",
        source_class="PUBLIC",
        enabled=True,
        circuit_state="HEALTHY",
        consecutive_failures=0,
        consecutive_successes=1,
        freshness_state="FRESH",
        last_quality_result="PASSED",
        quality_warning_count=0,
        quality_error_count=0,
        last_quality_issue_count=0,
        entitlement_state="UNKNOWN",
        certification_state="NOT_REQUIRED",
        adapter_version="v1",
        schedule_json={},
        freshness_policy_json={
            "normal_max_age_minutes": 60,
            "late_after_minutes": 120,
            "stale_after_minutes": 240,
        },
        retry_policy_json={},
        rate_limit_policy_json={},
        circuit_policy_json={},
        calendar="TARGET",
        updated_at_utc=NOW,
        research_only=True,
    )
    values.update(overrides)
    return SourceRuntimeStateRecord(**values)


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_freshness_is_aged_by_the_clock_not_frozen_in_the_state_row() -> None:
    with _session() as session:
        # The row says 60 s old and FRESH; the last success was five hours ago, and no
        # scheduler has scanned since (it died). The metric must say five hours.
        session.add(
            _state(
                "src-ecb",
                last_success_at_utc=NOW - timedelta(hours=5),
                source_age_seconds=60,
            )
        )
        session.add(_state("src-off", enabled=False, last_success_at_utc=NOW))
        session.commit()
        samples = _samples(database_metric_text(session, now_utc=NOW))
    assert samples['eurogas_source_freshness_seconds{source_id="src-ecb"}'] == "18000"
    assert samples['eurogas_source_stale_after_seconds{source_id="src-ecb"}'] == "14400"
    assert samples['eurogas_source_enabled{source_id="src-off"}'] == "0"
    # A disabled source has no age: it is not expected to be fresh.
    assert 'eurogas_source_freshness_seconds{source_id="src-off"}' not in samples


def test_heartbeat_age_and_scheduled_sources() -> None:
    with _session() as session:
        session.add(
            DataOperationsHeartbeatRecord(
                heartbeat_id="primary",
                last_heartbeat_at_utc=NOW - timedelta(seconds=45),
                last_scan_at_utc=NOW - timedelta(seconds=90),
                sources_scheduled=10,
            )
        )
        session.commit()
        samples = _samples(database_metric_text(session, now_utc=NOW))
    assert samples['eurogas_scheduler_heartbeat_age_seconds{scheduler="dataops"}'] == "45"
    assert samples['eurogas_scheduler_heartbeat_age_seconds{scheduler="shadow"}'] == "+Inf"
    assert samples['eurogas_scheduler_last_scan_age_seconds{scheduler="dataops"}'] == "90"
    assert samples["eurogas_scheduler_sources_scheduled"] == "10"


def test_jobs_feed_and_outbox() -> None:
    with _session() as session:
        for index, (status, finished) in enumerate(
            [
                ("FAILED", NOW - timedelta(minutes=10)),
                ("SUCCEEDED", NOW - timedelta(minutes=20)),
                ("FAILED", NOW - timedelta(hours=3)),  # outside the window
                ("RUNNING", None),
            ]
        ):
            session.add(
                JobRecord(
                    job_id=f"job-{index}",
                    kind="REPORT",
                    status=status,
                    principal="tester",
                    created_at_utc=NOW - timedelta(hours=4),
                    finished_at_utc=finished,
                )
            )
        session.add(
            MarketQuoteRecord(
                quote_id="q1",
                source_system="TRAYPORT",
                venue="TRAYPORT",
                instrument_id="TTF-M1",
                hub="TTF",
                product="M1",
                delivery_start_utc=NOW,
                delivery_end_utc=NOW + timedelta(days=30),
                currency="EUR",
                unit="EUR/MWh",
                observed_at_utc=NOW - timedelta(seconds=30),
                received_at_utc=NOW - timedelta(seconds=28),
                source_reference="ref",
                freshness="live",
                quality_score=1.0,
                simulated=False,
            )
        )
        event = MarketEventRecord(
            event_id="e1",
            event_key="k1",
            revision=1,
            content_hash="h",
            source_id="src-ecb",
            event_type="price",
            subject_key="TTF",
            priority=1,
            ingested_at_utc=NOW,
        )
        session.add(event)
        session.flush()
        session.add(
            MarketEventDeliveryRecord(
                consumer="opportunities",
                event_seq=event.seq,
                status="pending",
                attempts=0,
                available_at_utc=NOW - timedelta(minutes=2),
            )
        )
        session.commit()
        samples = _samples(database_metric_text(session, now_utc=NOW))
    assert samples['eurogas_jobs_finished_last_hour{kind="REPORT",status="FAILED"}'] == "1"
    assert samples['eurogas_jobs_finished_last_hour{kind="REPORT",status="SUCCEEDED"}'] == "1"
    assert samples['eurogas_jobs_active{kind="REPORT"}'] == "1"
    assert samples['eurogas_feed_last_quote_age_seconds{source_system="TRAYPORT"}'] == "30"
    assert samples['eurogas_feed_receive_lag_seconds{source_system="TRAYPORT"}'] == "2"
    assert samples['eurogas_market_events_backlog{consumer="opportunities"}'] == "1"
    assert (
        samples['eurogas_market_events_oldest_due_age_seconds{consumer="opportunities"}'] == "120"
    )
    assert all(
        value == "1"
        for name, value in samples.items()
        if name.startswith("eurogas_metrics_collector_up")
    )
