"""Real PostgreSQL point-in-time reads for National Gas demand-target revisions.

Each test creates a uniquely named disposable schema, seeds synthetic development
revisions, and exercises the actual repository query.  No source is fetched or
activated, no business table is touched, and the repository must not write or
commit.  The module is skipped unless an explicit PostgreSQL URL is configured,
following the existing opt-in unique-schema integration pattern.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.repositories.demand import (
    DemandTargetReadOverflow,
    DemandTargetReadValidationError,
    read_demand_target_revisions,
)

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
    schema = f"demandtargettest_{uuid4().hex}"
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


def test_reads_one_format_with_receipt_cutoff_order_and_no_side_effects():
    rows = [
        _row("a-day1-early", available_at=RECEIVED),
        _row("b-day1-late", available_at=RECEIVED + timedelta(hours=4)),
        _row(
            "c-day2-rest",
            gas_day=DAY_TWO,
            available_at=RECEIVED + timedelta(hours=3),
            source_format="REST",
        ),
        _row("d-day2-early", gas_day=DAY_TWO, available_at=RECEIVED + timedelta(hours=1)),
        _row("e-day2-late", gas_day=DAY_TWO, available_at=RECEIVED + timedelta(hours=8)),
    ]
    with _session() as session:
        session.add_all(rows)
        session.flush()
        before = _count(session)

        early_csv_rows = read_demand_target_revisions(
            session,
            provider_item_id="PUBOB637",
            source_format="CSV",
            gas_day_from=DAY_ONE,
            gas_day_to=DAY_TWO,
            available_at_utc=RECEIVED + timedelta(hours=2),
            limit=10,
        )
        assert [row.record_id for row in early_csv_rows] == [
            "a-day1-early",
            "d-day2-early",
        ]
        assert len(early_csv_rows) == 2
        assert [row.source_format for row in early_csv_rows] == ["CSV", "CSV"]
        assert _count(session) == before
        assert not session.new and not session.dirty and not session.deleted

        csv_rows = read_demand_target_revisions(
            session,
            provider_item_id="PUBOB637",
            source_format="CSV",
            gas_day_from=DAY_ONE,
            gas_day_to=DAY_TWO,
            available_at_utc=RECEIVED + timedelta(hours=6),
            limit=10,
        )
        assert [row.record_id for row in csv_rows] == [
            "a-day1-early",
            "b-day1-late",
            "d-day2-early",
        ]
        assert len(csv_rows) == 3
        assert [row.source_format for row in csv_rows] == ["CSV", "CSV", "CSV"]
        assert all(isinstance(row, NationalGasActualDemandRecord) for row in csv_rows)
        assert _count(session) == before
        assert not session.new and not session.dirty and not session.deleted

        full = read_demand_target_revisions(
            session,
            provider_item_id="PUBOB637",
            source_format="CSV",
            gas_day_from=DAY_ONE,
            gas_day_to=DAY_TWO,
            available_at_utc=RECEIVED + timedelta(hours=9),
            limit=10,
        )
        assert [row.record_id for row in full] == [
            "a-day1-early",
            "b-day1-late",
            "d-day2-early",
            "e-day2-late",
        ]

        rest_rows = read_demand_target_revisions(
            session,
            provider_item_id="PUBOB637",
            source_format="REST",
            gas_day_from=DAY_ONE,
            gas_day_to=DAY_TWO,
            available_at_utc=RECEIVED + timedelta(hours=9),
            limit=10,
        )
        assert [row.record_id for row in rest_rows] == ["c-day2-rest"]


def test_aware_offset_cutoff_is_converted_and_late_receipts_are_excluded():
    cutoff_offset = timezone(timedelta(hours=2))
    with _session() as session:
        session.add_all(
            [
                _row("included", available_at=datetime(2026, 10, 23, 12, 0, tzinfo=UTC)),
                _row(
                    "excluded",
                    available_at=datetime(2026, 10, 23, 12, 0, 1, tzinfo=UTC),
                ),
            ]
        )
        session.flush()

        rows = read_demand_target_revisions(
            session,
            provider_item_id="PUBOB637",
            source_format="CSV",
            gas_day_from=DAY_ONE,
            gas_day_to=DAY_ONE,
            available_at_utc=datetime(2026, 10, 23, 14, 0, tzinfo=cutoff_offset),
            limit=10,
        )

        assert [row.record_id for row in rows] == ["included"]
        assert rows[0].available_at_utc == datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def test_limit_plus_one_overflow_refuses_instead_of_trimming():
    with _session() as session:
        session.add_all(
            [
                _row("one", gas_day=date(2026, 10, 21)),
                _row("two", gas_day=date(2026, 10, 22)),
                _row("three", gas_day=date(2026, 10, 23)),
            ]
        )
        session.flush()

        with pytest.raises(DemandTargetReadOverflow) as caught:
            read_demand_target_revisions(
                session,
                provider_item_id="PUBOB637",
                source_format="CSV",
                gas_day_from=date(2026, 10, 1),
                gas_day_to=date(2026, 10, 31),
                available_at_utc=RECEIVED,
                limit=2,
            )
        assert caught.value.code == "DEMAND_TARGET_READ_OVERFLOW"
        assert _count(session) == 3
        assert not session.dirty and not session.deleted


@pytest.mark.parametrize(
    "overrides",
    [
        {"available_at_utc": datetime(2026, 10, 23, 12, 0)},
        {"gas_day_from": date(2026, 10, 31), "gas_day_to": date(2026, 10, 1)},
        {"gas_day_from": None, "gas_day_to": date(2026, 10, 1)},
        {"provider_item_id": "UNKNOWN"},
        {"source_format": "csv"},
        {"limit": True},
        {"limit": 0},
        {"limit": 10_001},
    ],
)
def test_invalid_read_arguments_are_refused_before_query(overrides):
    arguments = {
        "provider_item_id": "PUBOB637",
        "source_format": "CSV",
        "gas_day_from": date(2026, 10, 1),
        "gas_day_to": date(2026, 10, 31),
        "available_at_utc": RECEIVED,
        "limit": 10,
    }
    arguments.update(overrides)

    with _session() as session:
        with pytest.raises(DemandTargetReadValidationError) as caught:
            read_demand_target_revisions(session, **arguments)
        assert caught.value.code == "DEMAND_TARGET_READ_VALIDATION_ERROR"
        assert _count(session) == 0
