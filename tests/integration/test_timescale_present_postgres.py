"""TimescaleDB present (ADR Decision 39): migration 0093 converts the three planned tables, the
writers keep working on compressed chunks, a second run changes nothing, and the downgrade
leaves the hypertables as they are.

Run with ``EUROGAS_NEXUS_TEST_TIMESCALE_URL`` set to a PostgreSQL server with the TimescaleDB
Community Edition preloaded (for example the ``timescale/timescaledb:latest-pg16`` image, whose
defaults are ``shared_preload_libraries = timescaledb`` and ``timescaledb.license =
timescale``) and a role that may create databases. Each test works in a throw-away database
holding every model's table.

The full ``alembic upgrade head`` / ``downgrade`` round trip on such a server is in
``docs/deployment/TIMESCALEDB.md`` ("Proof"), run by hand because it needs a whole database.
"""

from __future__ import annotations

import hashlib
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

_URL = os.environ.get("EUROGAS_NEXUS_TEST_TIMESCALE_URL", "")
pytestmark = pytest.mark.skipif(
    not _URL.startswith("postgresql"),
    reason="set EUROGAS_NEXUS_TEST_TIMESCALE_URL to a PostgreSQL server with TimescaleDB",
)
MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / (
    "0093_timescale_optional.py"
)
PLANNED = [plan.table for plan in timescale.HYPERTABLE_PLANS]


@pytest.fixture
def engine() -> Iterator[sa.Engine]:
    """A fresh database holding every model's table, without the extension created: the
    conversion creates it (``CREATE EXTENSION``), as on a first upgrade."""

    admin = sa.create_engine(_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        facts = timescale.server_facts(connection)
    decision = timescale.decide("auto", facts)
    if not decision.enabled:
        admin.dispose()
        pytest.skip(f"this server cannot run TimescaleDB: {decision.reason}")
    database = f"timescale_present_{uuid.uuid4().hex[:12]}"
    with admin.connect() as connection:
        connection.execute(sa.text(f'CREATE DATABASE "{database}"'))
    active = sa.create_engine(sa.make_url(_URL).set(database=database))
    Base.metadata.create_all(active)
    try:
        yield active
    finally:
        active.dispose()
        with admin.connect() as connection:
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        admin.dispose()


def _migration():
    spec = importlib.util.spec_from_file_location("ts_0093_timescale_optional", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hypertables_or_none(connection) -> dict[str, bool]:
    """``_hypertables``, or empty where the extension is not created in the database."""

    view = sa.text("SELECT to_regclass('timescaledb_information.hypertables')")
    if connection.execute(view).scalar() is None:
        return {}
    return _hypertables(connection)


def _hypertables(connection) -> dict[str, bool]:
    rows = connection.execute(
        sa.text(
            "SELECT hypertable_name, compression_enabled FROM timescaledb_information.hypertables "
            "WHERE hypertable_schema = current_schema()"
        )
    ).all()
    return {str(name): bool(compressed) for name, compressed in rows}


def test_off_leaves_the_tables_plain_even_where_the_extension_is_installed(engine, monkeypatch):
    monkeypatch.setenv(timescale.ENV_VAR, "off")
    migration = _migration()
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert _hypertables_or_none(connection) == {}
        # The image's template database may already hold the extension.
        assert timescale.state(connection) in ("available", "installed")


def test_auto_converts_the_three_tables_and_a_second_run_changes_nothing(engine, monkeypatch):
    monkeypatch.setenv(timescale.ENV_VAR, "auto")
    migration = _migration()
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert _hypertables(connection) == dict.fromkeys(PLANNED, True)
        assert timescale.state(connection) == "active"
        for plan in timescale.HYPERTABLE_PLANS:
            current = timescale.table_facts(connection, plan)
            assert current.primary_key == (plan.key_column, plan.time_column)
            assert timescale.catalogue_blockers(current, plan) == []
        # Idempotent: the same apply (scripts/ops/timescale.py apply) finds them done.
        again = timescale.apply(connection, mode="require")
        assert again.converted == [] and sorted(again.already) == sorted(PLANNED)
        assert again.failed == {}
        # The downgrade leaves the hypertables (a conversion is not reversed by a migration).
        migration.downgrade()
        assert _hypertables(connection) == dict.fromkeys(PLANNED, True)
        # The observation tables, the outbox and the audit log stay plain.
        assert not set(timescale.SKIPPED_TABLES) & set(_hypertables(connection))


def test_writers_work_on_compressed_chunks(engine):
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
        report = timescale.apply(connection, mode="require")
        assert sorted(report.converted) == sorted(PLANNED)

    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as session:
        archive_raw_payload(
            session, archive_id="raw-ts-1", source_system="ENTSOG", dataset="flows",
            source_reference="page:1", payload_text="{}",
            payload_sha256=hashlib.sha256(b"{}").hexdigest(),
            record_count=0, received_at_utc=now - timedelta(days=40),
        )
        tick = {"hub": "TTF", "product": "DA", "bid": 30.0, "ask": 30.2,
                "exchange_time": (now - timedelta(seconds=5)).isoformat(), "sequence": "1"}
        trade = {"hub": "TTF", "product": "DA", "price": 30.1, "qty": 10, "trade_id": "T1",
                 "exchange_time": (now - timedelta(seconds=4)).isoformat()}
        ingest_ticks(session, source_system="EEX_Sim", quotes=[tick], trades=[trade],
                     simulated_allowed=True, received_at=now, evaluate=False)
        quote = session.query(MarketQuoteRecord).one()
        quote_id = quote.quote_id
        row = {column.name: getattr(quote, column.name)
               for column in MarketQuoteRecord.__table__.columns}
        old = dict(row, quote_id="old-quote", observed_at_utc=now - timedelta(days=60))
        upsert_market_quotes(session, [old])
        session.commit()

    # Compress every chunk now, as the policy would once the rows are old enough.
    with engine.begin() as connection:
        for table in PLANNED:
            connection.execute(
                sa.text(f"SELECT compress_chunk(c, if_not_compressed => true) "
                        f"FROM show_chunks('{table}'::regclass) c")
            )
        compressed = connection.execute(
            sa.text("SELECT count(*) FROM timescaledb_information.chunks "
                    "WHERE hypertable_schema = current_schema() AND is_compressed")
        ).scalar()
        assert compressed >= 3

    with Session(engine) as session:
        # Reads, an ORM merge that updates a compressed row, the same tick batch again
        # (recognised by id) and the retention delete all work on compressed chunks.
        upsert_market_quotes(session, [dict(row, bid_price=29.9)])
        ingest_ticks(session, source_system="EEX_Sim", quotes=[tick], trades=[trade],
                     simulated_allowed=True, received_at=now, evaluate=False)
        session.commit()
        assert session.get(RawPayloadArchiveRecord, "raw-ts-1") is not None
        assert session.query(MarketTradeRecord).count() == 1
        assert session.query(MarketQuoteRecord).count() == 2
        assert session.get(MarketQuoteRecord, quote_id).bid_price == 29.9
        summary = prune_expired_rows(session, now_utc=now)
        session.commit()
        assert summary["market_quotes_deleted"] == 1
        assert session.query(MarketQuoteRecord).count() == 1
