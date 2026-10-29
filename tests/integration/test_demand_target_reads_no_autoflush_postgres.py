"""PostgreSQL regression: demand-target reads must not autoflush caller writes.

``read_demand_target_revisions`` is read-only, but a bare ``session.scalars``
would autoflush a pending caller write before querying.  This test seeds real
PostgreSQL rows, adds a pending same-table caller row, and proves the read
leaves that row pending: no flush event, no SQL insert, unchanged caller
transaction and session state.  The module is skipped unless an explicit
PostgreSQL URL is configured and uses the disposable-schema pattern.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.repositories.demand import read_demand_target_revisions

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; each test uses a disposable schema.",
)

DAY_ONE = date(2026, 10, 21)
DAY_TWO = date(2026, 10, 22)
RECEIVED = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def _row(
    record_id: str,
    *,
    gas_day: date = DAY_ONE,
    available_at: datetime = RECEIVED,
    source_format: str = "CSV",
    provider_item_id: str = "PUBOB637",
    value_text: str = "176.708",
):
    received = available_at
    return NationalGasActualDemandRecord(
        record_id=record_id,
        source_publication_id=f"pub-{record_id}",
        provider_item_id=provider_item_id,
        series_key=f"national-gas:actual:GB_NTS:D+1:{source_format}",
        region="GB_NTS",
        term="D+1",
        label="Demand Actual, NTS, D+1",
        gas_day=gas_day,
        period_start_utc=datetime.combine(gas_day, time(5, 0), tzinfo=UTC),
        period_end_utc=datetime.combine(gas_day + timedelta(days=1), time(5, 0), tzinfo=UTC),
        value_text=value_text,
        unit="mscm",
        received_at_utc=received,
        available_at_utc=available_at,
        ingested_at_utc=received,
        published_at_utc=None,
        applicable_at_raw=gas_day.strftime("%d/%m/%Y"),
        generated_at_raw=available_at.strftime("%d/%m/%Y %H:%M:%S"),
        applicable_at_naive=datetime.combine(gas_day, time(5, 0)),
        generated_at_naive=available_at.replace(tzinfo=None),
        quality_indicator=None,
        provisional_status="PROVISIONAL_INITIAL",
        is_provisional=True,
        raw_sha256="a" * 64,
        source_url="https://example.test/national-gas",
        hash_schema="national_gas_actual_demand.v1",
        value_is_blank=value_text == "",
        source_format=source_format,
        rest_provenance={"synthetic": True} if source_format == "REST" else None,
    )


@contextmanager
def _session():
    url = make_url(_POSTGRES_URL)
    connect_args = {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"demandtargetnoautoflush_{uuid4().hex}"
    schema_created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            NationalGasActualDemandRecord.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()


def _count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(NationalGasActualDemandRecord)
        )
        or 0
    )


def test_read_does_not_autoflush_pending_same_table_caller_write():
    with _session() as session:
        session.add_all(
            [
                _row("persisted-day1", available_at=RECEIVED),
                _row(
                    "persisted-day2",
                    gas_day=DAY_TWO,
                    available_at=RECEIVED + timedelta(hours=1),
                ),
            ]
        )
        session.flush()
        before = _count(session)
        caller_transaction = session.get_transaction()
        assert caller_transaction is not None

        pending = _row(
            "pending-unrelated",
            gas_day=date(2026, 11, 30),
            available_at=RECEIVED + timedelta(hours=2),
        )
        session.add(pending)
        flush_events: list[str] = []

        def _on_before_flush(*_args, **_kwargs):
            flush_events.append("before_flush")

        event.listen(session, "before_flush", _on_before_flush)
        try:
            rows = read_demand_target_revisions(
                session,
                provider_item_id="PUBOB637",
                source_format="CSV",
                gas_day_from=DAY_ONE,
                gas_day_to=DAY_TWO,
                available_at_utc=RECEIVED + timedelta(hours=9),
                limit=10,
            )
        finally:
            event.remove(session, "before_flush", _on_before_flush)

        assert [row.record_id for row in rows] == ["persisted-day1", "persisted-day2"]
        assert flush_events == []

        pending_state = inspect(pending)
        assert pending_state.pending is True
        assert pending_state.persistent is False
        assert pending_state.transient is False
        assert pending_state.detached is False
        assert pending in session.new
        assert len(session.new) == 1
        assert session.get_transaction() is caller_transaction
        assert session.in_transaction()
        assert session.is_active
        assert not session.dirty and not session.deleted

        # Count inside a test-side no_autoflush scope so the assertion itself
        # cannot flush the pending row it is meant to prove absent.
        with session.no_autoflush:
            stored_ids = set(
                session.scalars(select(NationalGasActualDemandRecord.record_id))
            )
            after = _count(session)
        assert after == before
        assert "pending-unrelated" not in stored_ids
        assert session.get_transaction() is caller_transaction
        assert pending in session.new
