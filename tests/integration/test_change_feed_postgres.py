"""DATA-1 change feed on PostgreSQL: no committed event is ever skipped.

Transaction A draws its ``seq`` first and commits last; transaction B draws a later ``seq``
and commits first. A feed ordered by ``seq`` alone would hand out B's cursor and never show A.
The feed holds B back while A is open, then serves A before B.

Run with ``RUNTIME_STORE_DATABASE_URL`` set to a PostgreSQL store migrated to head.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.change_feed import START, parse_cursor, read_changes
from eurogas_nexus.db.models import MarketEventRecord
from eurogas_nexus.domain.market_events import MarketEvent

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="RUNTIME_STORE_DATABASE_URL not PostgreSQL",
)

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture()
def store():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    source = f"src-pg-data1-{uuid4().hex[:8]}"
    yield engine, source
    with Session(engine) as session:
        session.query(MarketEventRecord).filter(MarketEventRecord.source_id == source).delete()
        session.commit()
    engine.dispose()


def _event(source: str, month: int) -> MarketEvent:
    return MarketEvent(
        source_id=source,
        event_type="price.updated",
        subject_key=f"{source}:2027-{month:02d}",
        ingested_at_utc=NOW,
        payload={"settlement": str(30 + month)},
    )


def _record(session, event_id: str) -> MarketEventRecord:
    return session.query(MarketEventRecord).filter_by(event_id=event_id).one()


def _subjects(engine, source, after=START):
    with Session(engine) as session:
        page = read_changes(session, None, after=after, subject_prefix=source, limit=100)
        session.rollback()
    return [change["subject_key"] for change in page.changes], page


def test_the_writer_id_is_stamped_by_the_database(store):
    engine, source = store
    assert "writer_txid" in {c["name"] for c in inspect(engine).get_columns("market_events")}
    with Session(engine) as session:
        published = outbox.publish(session, _event(source, 1))
        session.commit()
        record = _record(session, published.event_id)
        assert record.writer_txid is not None and record.writer_txid > 0


def test_an_event_committed_late_with_an_early_seq_is_not_skipped(store):
    engine, source = store
    a, b = Session(engine), Session(engine)
    try:
        first = outbox.publish(a, _event(source, 1))
        a.flush()  # A holds seq n, uncommitted
        first_seq = _record(a, first.event_id).seq
        second = outbox.publish(b, _event(source, 2))
        b.commit()  # B has seq n+1, committed
        assert first_seq < _record(b, second.event_id).seq
        b.rollback()  # end B's read transaction, which would hold the horizon

        seen, page = _subjects(engine, source)
        assert seen == []  # B waits: A, which began earlier, is still open
        cursor = parse_cursor(page.next_cursor)

        a.commit()
        seen, page = _subjects(engine, source, after=cursor)
        assert seen == [f"{source}:2027-01", f"{source}:2027-02"]  # A first, then B
        seen, _ = _subjects(engine, source, after=parse_cursor(page.next_cursor))
        assert seen == []
    finally:
        a.close()
        b.close()


def test_a_rolled_back_writer_releases_the_feed(store):
    engine, source = store
    a, b = Session(engine), Session(engine)
    try:
        outbox.publish(a, _event(source, 3))
        a.flush()
        outbox.publish(b, _event(source, 4))
        b.commit()
        assert _subjects(engine, source)[0] == []
        a.rollback()
        assert _subjects(engine, source)[0] == [f"{source}:2027-04"]
    finally:
        a.close()
        b.close()
