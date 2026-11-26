"""TimescaleDB absent (ADR Decision 39): on plain PostgreSQL migration 0090 changes nothing.

Run with ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` set to a PostgreSQL server **without** the
timescaledb extension (the test skips where the extension is available, because it proves
the absent case). Each test works in a throw-away schema with every model's table.

The last test widens the three planned primary keys to ``(id, time)`` exactly as the
conversion does on a TimescaleDB server, and shows every writer of those tables still works
against that key on plain PostgreSQL. It cannot show the hypertable or compression step.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401 - registers every model
from eurogas_nexus.db import timescale
from eurogas_nexus.db.base import Base

_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not _URL.startswith("postgresql"),
    reason="set EUROGAS_NEXUS_TEST_POSTGRES_URL to a PostgreSQL server without TimescaleDB",
)
MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / (
    "0090_timescale_optional.py"
)

_CATALOGUE_SQL = """
SELECT 'column' AS kind, table_name || '.' || column_name || ' ' || data_type
       || ' ' || is_nullable AS item
FROM information_schema.columns WHERE table_schema = current_schema()
UNION ALL
SELECT 'constraint', conrelid::regclass::text || ' ' || conname || ' '
       || pg_get_constraintdef(oid)
FROM pg_constraint WHERE connamespace = current_schema()::regnamespace
UNION ALL
SELECT 'index', indexdef FROM pg_indexes WHERE schemaname = current_schema()
UNION ALL
SELECT 'extension', extname::text FROM pg_extension
UNION ALL
SELECT 'relation', relname || ' ' || relkind::text FROM pg_class
WHERE relnamespace = current_schema()::regnamespace
ORDER BY 1, 2
"""


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    admin = sa.create_engine(_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        available = connection.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'")
        ).first()
    if available is not None:
        admin.dispose()
        pytest.skip("this server has timescaledb; the test proves the absent case")
    schema = f"timescale_absent_{uuid.uuid4().hex[:12]}"
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    def _pin(dbapi_connection, _record) -> None:
        autocommit = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f'SET search_path TO "{schema}"')
        finally:
            cursor.close()
            dbapi_connection.autocommit = autocommit

    active = sa.create_engine(_URL)
    sa.event.listen(active, "connect", _pin)
    Base.metadata.create_all(active)
    try:
        yield active
    finally:
        active.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def _catalogue(connection) -> list[tuple[str, str]]:
    return [tuple(row) for row in connection.execute(sa.text(_CATALOGUE_SQL))]


def _migration():
    spec = importlib.util.spec_from_file_location("pg_0090_timescale_optional", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mode", ["off", "auto", ""])
def test_the_migration_is_a_no_op_without_the_extension(engine, monkeypatch, mode):
    monkeypatch.setenv(timescale.ENV_VAR, mode)
    migration = _migration()
    with engine.begin() as connection:
        before = _catalogue(connection)
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert _catalogue(connection) == before
        migration.downgrade()
        assert _catalogue(connection) == before
        assert timescale.state(connection) == "absent"
        assert not timescale.is_active(connection)


def test_require_stops_the_migration_and_changes_nothing(engine, monkeypatch):
    monkeypatch.setenv(timescale.ENV_VAR, "require")
    migration = _migration()
    with engine.connect() as connection:
        before = _catalogue(connection)
    with pytest.raises(timescale.TimescaleRequiredError, match="not installed"):
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
    with engine.connect() as connection:
        assert _catalogue(connection) == before


def test_the_catalogue_shows_no_blocker_and_the_status_reads_absent(engine):
    with engine.connect() as connection:
        facts = timescale.server_facts(connection)
        assert facts.dialect == "postgresql"
        assert facts.installed_version is None and facts.available_version is None
        for plan in timescale.HYPERTABLE_PLANS:
            current = timescale.table_facts(connection, plan)
            assert current.primary_key == (plan.key_column,)
            assert timescale.catalogue_blockers(current, plan) == []
        report = timescale.status(connection, mode="auto")
    assert report["state"] == "absent"
    assert report["would_convert"] is False


def test_writers_keep_working_against_the_widened_primary_key(engine):
    from eurogas_nexus.application.market_ticks import ingest_ticks
    from eurogas_nexus.application.retention import prune_expired_rows
    from eurogas_nexus.db.models import (
        MarketQuoteRecord,
        MarketTradeRecord,
        RawPayloadArchiveRecord,
    )
    from eurogas_nexus.db.repositories.market_intelligence import upsert_market_quotes
    from eurogas_nexus.db.repositories.raw_archive import archive_raw_payload

    with engine.begin() as connection:
        for plan in timescale.HYPERTABLE_PLANS:
            current = timescale.table_facts(connection, plan)
            # Only the key change: plain PostgreSQL has no create_hypertable.
            for statement in timescale.conversion_statements(plan, current)[:2]:
                connection.execute(sa.text(statement))
            widened = timescale.table_facts(connection, plan)
            assert widened.primary_key == (plan.key_column, plan.time_column)
            assert timescale.catalogue_blockers(widened, plan) == []

    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as session:
        archive_raw_payload(
            session, archive_id="raw-widened-1", source_system="ENTSOG", dataset="flows",
            source_reference="page:1", payload_text="{}", payload_sha256="0" * 64,
            record_count=0, received_at_utc=now,
        )
        tick = {"hub": "TTF", "product": "DA", "bid": 30.0, "ask": 30.2,
                "exchange_time": (now - timedelta(seconds=5)).isoformat(), "sequence": "1"}
        trade = {"hub": "TTF", "product": "DA", "price": 30.1, "qty": 10, "trade_id": "T1",
                 "exchange_time": (now - timedelta(seconds=4)).isoformat()}
        ingest_ticks(session, source_system="EEX_Sim", quotes=[tick], trades=[trade],
                     simulated_allowed=True, received_at=now, evaluate=False)
        # The same batch again is recognised by id and stored once.
        ingest_ticks(session, source_system="EEX_Sim", quotes=[tick], trades=[trade],
                     simulated_allowed=True, received_at=now, evaluate=False)
        quote = session.query(MarketQuoteRecord).one()
        row = {column.name: getattr(quote, column.name)
               for column in MarketQuoteRecord.__table__.columns}
        row["bid_price"] = 29.9
        upsert_market_quotes(session, [row])  # ORM merge by quote_id updates in place
        old = dict(row, quote_id="old-quote",
                   observed_at_utc=now - timedelta(days=60))
        upsert_market_quotes(session, [old])
        session.commit()

        assert session.query(RawPayloadArchiveRecord).count() == 1
        assert session.get(RawPayloadArchiveRecord, "raw-widened-1") is not None
        assert session.query(MarketTradeRecord).count() == 1
        assert session.query(MarketQuoteRecord).count() == 2
        assert session.get(MarketQuoteRecord, quote.quote_id).bid_price == 29.9

        summary = prune_expired_rows(session, now_utc=now)
        session.commit()
        assert summary["market_quotes_deleted"] == 1
        assert session.query(MarketQuoteRecord).count() == 1
