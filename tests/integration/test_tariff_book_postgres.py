"""TAR-1 on PostgreSQL: a changed tariff is a new version and one event in the read's own
transaction, and reaches the opportunity consumer; the time is measured.

What is measured (criterion TAR1-4, row in 15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md): from the
register row being written to the version and its ``tariff.changed`` event committed with it,
and from that commit to the ``opportunities`` consumer having processed the delivery. The poll
interval (hourly in the NC TAR publication weeks, daily otherwise) comes before this and is a
designed figure, not measured here. Figures are made up.

Run via ``scripts/ci/run_postgres_ci.sh`` (``RUNTIME_STORE_DATABASE_URL`` set, migrated to head).
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events
from eurogas_nexus.application import tariff_book as book
from eurogas_nexus.db.models import (
    MarketEventDeliveryRecord,
    MarketEventRecord,
    TariffVersionRecord,
    TsoTariffRecord,
)
from tests.unit.test_tariff_book import entsog_row

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="RUNTIME_STORE_DATABASE_URL not PostgreSQL; run via scripts/ci/run_postgres_ci.sh",
)

#: The budget this slice adds after a read (15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md).
WRITE_BUDGET_S = 2.0
CONSUMER_BUDGET_S = 5.0


@pytest.fixture()
def point():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    tag = f"PG-TAR-{uuid4().hex[:8]}"
    yield engine, tag
    with Session(engine) as session:
        tariff_id = entsog_row(point=tag).tariff_id
        events = [
            seq
            for (seq,) in session.query(MarketEventRecord.seq).filter(
                MarketEventRecord.subject_key.like(f"tariff:{tag}:%")
            )
        ]
        if events:
            session.query(MarketEventDeliveryRecord).filter(
                MarketEventDeliveryRecord.event_seq.in_(events)
            ).delete(synchronize_session=False)
            session.query(MarketEventRecord).filter(MarketEventRecord.seq.in_(events)).delete(
                synchronize_session=False
            )
        session.query(TariffVersionRecord).filter(TariffVersionRecord.facility_id == tag).delete(
            synchronize_session=False
        )
        session.query(TsoTariffRecord).filter(TsoTariffRecord.tariff_id == tariff_id).delete(
            synchronize_session=False
        )
        session.commit()
    engine.dispose()


def _write(engine, tag: str, *, value: float, status: str, at: datetime) -> tuple[float, dict]:
    """Store one register row and its versions in one transaction; seconds taken, result."""

    started = time.perf_counter()
    with Session(engine) as session:
        row = session.merge(entsog_row(value=value, status=status, at=at, point=tag))
        session.flush()
        result = book.record_register_rows(session, [row])
        session.commit()
    return time.perf_counter() - started, result.to_json()


def _consumed(engine, tag: str) -> float:
    """Seconds until the opportunities consumer has processed this point's latest event."""

    started = time.perf_counter()
    deadline = started + 30
    with Session(engine) as session:
        while time.perf_counter() < deadline:
            market_events.process(session, "opportunities")
            session.commit()
            latest = (
                session.query(MarketEventRecord)
                .filter(MarketEventRecord.subject_key.like(f"tariff:{tag}:%"))
                .order_by(MarketEventRecord.revision.desc())
                .first()
            )
            delivery = session.get(MarketEventDeliveryRecord, ("opportunities", latest.seq))
            if delivery is not None and delivery.status == "processed":
                return time.perf_counter() - started
            time.sleep(0.02)
    raise AssertionError("the opportunities consumer did not process the tariff event in 30 s")


def test_a_tariff_change_is_a_version_and_an_event_committed_together(point) -> None:
    engine, tag = point
    now = datetime.now(UTC).replace(microsecond=0)
    first_s, first = _write(
        engine, tag, value=4.0, status="INDICATIVE", at=now - timedelta(hours=1)
    )
    assert first["written"] == {"first": 1} and first["events"] == 1
    _consumed(engine, tag)

    write_s, final = _write(engine, tag, value=4.0, status="FINAL", at=now)
    consume_s = _consumed(engine, tag)
    assert final["written"] == {"status_change": 1} and final["events"] == 1
    print(
        f"TAR-1 latency: version+event write {write_s * 1000:.0f} ms "
        f"(first {first_s * 1000:.0f} ms), "
        f"commit to opportunities consumer {consume_s * 1000:.0f} ms"
    )
    assert write_s < WRITE_BUDGET_S and consume_s < CONSUMER_BUDGET_S

    with Session(engine) as session:
        held = (
            session.query(TariffVersionRecord)
            .filter(TariffVersionRecord.facility_id == tag)
            .order_by(TariffVersionRecord.version)
            .all()
        )
        assert [(row.version, row.status, row.status_change) for row in held] == [
            (1, "INDICATIVE", None),
            (2, "FINAL", "INDICATIVE->FINAL"),
        ]
        assert held[0].superseded_at_utc is not None and held[1].superseded_at_utc is None
        event = session.query(MarketEventRecord).filter_by(event_id=held[1].event_id).one()
        assert event.event_type == "tariff.changed" and event.revision == 2
        # As known before the final was recorded: the indicative version.
        before = book.list_tariffs(
            session,
            filters=book.TariffFilter(facility_id=tag),
            as_of=held[1].recorded_at_utc - timedelta(microseconds=1),
        )["rows"]
        assert [(row["version"], row["status"]) for row in before] == [(1, "INDICATIVE")]


def test_a_rolled_back_read_leaves_no_version_and_no_event(point) -> None:
    engine, tag = point
    with Session(engine) as session:
        row = session.merge(entsog_row(point=tag))
        session.flush()
        result = book.record_register_rows(session, [row])
        assert result.events == 1
        session.rollback()
    with Session(engine) as session:
        assert session.query(TariffVersionRecord).filter_by(facility_id=tag).count() == 0
        assert (
            session.query(MarketEventRecord)
            .filter(MarketEventRecord.subject_key.like(f"tariff:{tag}:%"))
            .count()
            == 0
        )
