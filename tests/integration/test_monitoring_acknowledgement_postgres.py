"""PostgreSQL-authoritative monitoring acknowledgement semantics.

The API-level tests prove the route's decisions against a SQLite fixture; these
run the repository transition against the configured runtime store (CI: the
PostgreSQL 16 service) because the condition that makes acknowledgement safe -
"exactly one transition, decided by the database" - is a property of the
database, not of the process. Like the other integration tests, this module is
skipped unless a PostgreSQL URL and the explicit acknowledgement-test opt-in
are configured. These tests commit synthetic rows and must target a disposable
test database, never a developer's running desk database. They run no migrations.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import MonitoringAlertRecord
from eurogas_nexus.db.repositories.monitoring import acknowledge_monitoring_alert

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql")
    or os.environ.get("EUROGAS_NEXUS_ACK_INTEGRATION_TEST") != "1",
    reason="Requires disposable PostgreSQL and explicit opt-in; use run_postgres_ci.sh",
)


def _engine():
    return create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)


def _insert_alert(engine, alert_id: str, *, status: str = "open") -> None:
    now = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MonitoringAlertRecord(
                alert_id=alert_id,
                fingerprint=f"ack-it:{alert_id}",
                category="data_source",
                alert_type="ingestion_failed",
                severity="warning",
                status=status,
                title_en="Integration acknowledgement alert",
                title_zh_cn="集成确认告警",
                message_en="Created by the acknowledgement integration test.",
                message_zh_cn="由确认集成测试创建。",
                entity_type="data_source",
                entity_id="INTEGRATION",
                event_time_utc=now,
                detected_at_utc=now,
                updated_at_utc=now,
                acknowledged_at_utc=None,
                resolved_at_utc=now if status == "resolved" else None,
                occurrence_count=1,
                evidence_snapshot={},
                source_refs=[],
                warnings=[],
                llm_provider_id="DEEPSEEK",
                llm_status="not_requested",
                llm_summary_en=None,
                llm_summary_zh_cn=None,
                llm_last_attempt_at_utc=None,
                simulated=True,
                human_review_required=True,
            )
        )
        session.commit()


def test_acknowledgement_transitions_once_and_repeats_preserve_timestamp() -> None:
    engine = _engine()
    alert_id = f"alert-ack-it-{uuid4().hex[:12]}"
    _insert_alert(engine, alert_id)
    first_at = datetime(2026, 7, 1, 11, 0, tzinfo=UTC)
    second_at = first_at + timedelta(hours=1)

    with Session(engine) as session:
        row, transitioned = acknowledge_monitoring_alert(session, alert_id, now_utc=first_at)
        assert transitioned is True
        assert row.status == "acknowledged"
        session.commit()

    with Session(engine) as session:
        row, transitioned = acknowledge_monitoring_alert(session, alert_id, now_utc=second_at)
        assert transitioned is False
        assert row.status == "acknowledged"
        assert row.acknowledged_at_utc == first_at
        session.commit()

    # A resolved alert is outside the transition condition: it can never reopen.
    resolved_id = f"alert-ack-it-{uuid4().hex[:12]}"
    _insert_alert(engine, resolved_id, status="resolved")
    with Session(engine) as session:
        row, transitioned = acknowledge_monitoring_alert(
            session, resolved_id, now_utc=first_at
        )
        assert transitioned is False
        assert row.status == "resolved"
        assert row.acknowledged_at_utc is None
        session.commit()


def test_rollback_leaves_the_alert_open() -> None:
    engine = _engine()
    alert_id = f"alert-ack-it-{uuid4().hex[:12]}"
    _insert_alert(engine, alert_id)

    with Session(engine) as session:
        _row, transitioned = acknowledge_monitoring_alert(
            session, alert_id, now_utc=datetime(2026, 7, 1, 11, 0, tzinfo=UTC)
        )
        assert transitioned is True
        # The acknowledgement and its audit row share a transaction in the route; a
        # transaction that cannot complete must leave no half-written transition.
        session.rollback()

    with Session(engine) as session:
        row = session.get(MonitoringAlertRecord, alert_id)
        assert row.status == "open"
        assert row.acknowledged_at_utc is None


def test_concurrent_acknowledgements_have_exactly_one_winning_transition() -> None:
    engine = _engine()
    alert_id = f"alert-ack-it-{uuid4().hex[:12]}"
    _insert_alert(engine, alert_id)

    barrier = threading.Barrier(2)
    times = {
        "first": datetime(2026, 7, 1, 11, 0, tzinfo=UTC),
        "second": datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    }

    def _acknowledge(label: str) -> bool:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            _row, transitioned = acknowledge_monitoring_alert(
                session, alert_id, now_utc=times[label]
            )
            session.commit()
            return transitioned

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            label: pool.submit(_acknowledge, label) for label in ("first", "second")
        }
        outcomes = {label: future.result(timeout=30) for label, future in futures.items()}

    # PostgreSQL decides: the conditional UPDATE under the row lock lets exactly one
    # acknowledgement win, and the loser observes the committed transition.
    assert sum(1 for transitioned in outcomes.values() if transitioned) == 1
    winner = next(label for label, transitioned in outcomes.items() if transitioned)
    with Session(engine) as session:
        row = session.get(MonitoringAlertRecord, alert_id)
        assert row.status == "acknowledged"
        assert row.acknowledged_at_utc == times[winner]
