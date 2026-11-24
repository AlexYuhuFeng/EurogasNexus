"""The market event outbox on PostgreSQL (M4): notify at commit, skip-locked claims, uniqueness.

Run via ``scripts/ci/run_postgres_ci.sh`` (``RUNTIME_STORE_DATABASE_URL`` set, migrated to head).
"""

from __future__ import annotations

import os
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.db.models import MarketEventRecord
from eurogas_nexus.domain.market_events import MarketEvent

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="RUNTIME_STORE_DATABASE_URL not PostgreSQL; run via scripts/ci/run_postgres_ci.sh",
)

NOW = datetime.now(UTC).replace(microsecond=0)


class Recorder:
    def __init__(self, name):
        self.name = name
        self.batches = []

    def accepts(self, record) -> bool:
        return record.source_id.startswith("src-pg-m4")

    def handle(self, session, records, *, now_utc):
        self.batches.append([record.event_id for record in records])
        return {"seen": len(records)}


@pytest.fixture()
def setup():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    source = f"src-pg-m4-{uuid4().hex[:8]}"
    consumer = Recorder(f"pg-recorder-{uuid4().hex[:8]}")
    outbox.register_consumer(consumer)
    yield engine, source, consumer
    outbox.unregister_consumer(consumer.name)
    with Session(engine) as session:
        session.query(MarketEventRecord).filter(MarketEventRecord.source_id == source).delete()
        session.commit()
    engine.dispose()


def _event(source, n):
    return MarketEvent(
        source_id=source,
        event_type="price.updated",
        subject_key=f"hub:TTF:2027-{n:02d}",
        ingested_at_utc=NOW,
        payload={"settlement": str(30 + n)},
    )


def test_notify_reaches_a_listener_only_at_commit(setup) -> None:
    engine, source, _consumer = setup
    listener = engine.raw_connection()
    try:
        listener.driver_connection.autocommit = True
        cursor = listener.cursor()
        cursor.execute(f"LISTEN {outbox.NOTIFY_CHANNEL}")
        notices = listener.driver_connection.notifications
        notices.clear()
        with Session(engine) as session:
            published = outbox.publish(session, _event(source, 1))
            cursor.execute("SELECT 1")
            assert not [n for n in notices if published.event_id in str(n)]
            session.commit()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            cursor.execute("SELECT 1")
            if [n for n in notices if published.event_id in str(n)]:
                break
            time.sleep(0.1)
        assert [n for n in notices if published.event_id in str(n)]
    finally:
        listener.close()


def test_two_workers_never_claim_the_same_delivery(setup) -> None:
    engine, source, consumer = setup
    with Session(engine) as session:
        ids = [outbox.publish(session, _event(source, n)).event_id for n in range(1, 5)]
        session.commit()
    first = Session(engine)
    second = Session(engine)
    try:
        held = outbox._due(first, consumer.name, NOW, limit=2)  # noqa: SLF001 - claim and hold
        assert len(held) == 2
        other = outbox._due(second, consumer.name, NOW, limit=10)  # noqa: SLF001
        held_seqs = {delivery.event_seq for delivery, _ in held}
        other_seqs = {delivery.event_seq for delivery, _ in other}
        assert len(other_seqs) == 2 and not held_seqs & other_seqs
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
    with Session(engine) as session:
        assert outbox.process(session, consumer.name, now_utc=NOW)["processed"] == 4
        session.commit()
    assert consumer.batches == [ids]


def test_a_concurrent_second_copy_of_a_revision_is_refused_by_the_store(setup) -> None:
    engine, source, _consumer = setup
    event = _event(source, 7)
    with Session(engine) as first:
        outbox.publish(first, event)
        first.commit()
    with Session(engine) as second:
        # What a racing publisher that read "nothing held" would write: the store refuses it.
        with pytest.raises(IntegrityError):
            second.execute(
                text(
                    "INSERT INTO market_events (event_id, event_key, revision, content_hash, "
                    "source_id, event_type, subject_key, priority, dependency_keys, "
                    "payload_json, ingested_at_utc) VALUES (:id, :key, 1, :hash, :src, "
                    "'price.updated', :subject, 2, '[]', '{}', :at)"
                ),
                {
                    "id": f"{event.event_id(1)}-copy",
                    "key": event.event_key,
                    "hash": event.content_hash,
                    "src": source,
                    "subject": event.subject_key,
                    "at": NOW,
                },
            )
        second.rollback()


def test_two_publishers_racing_on_one_event_write_it_once(setup) -> None:
    engine, source, _consumer = setup
    event = _event(source, 9)
    outcome = {}
    with Session(engine) as first:
        assert outbox.publish(first, event).kind.value == "new"

        def racer():
            with Session(engine) as second:
                # Blocks on the unique key until the first commits, then decides again.
                outcome["kind"] = outbox.publish(second, event).kind.value
                second.commit()

        thread = threading.Thread(target=racer)
        thread.start()
        time.sleep(0.5)
        first.commit()
        thread.join(timeout=10)
    assert outcome == {"kind": "duplicate"}
    with Session(engine) as session:
        rows = session.query(MarketEventRecord).filter(MarketEventRecord.source_id == source)
        assert rows.count() == 1
