"""The demo re-seed against a feed-sized quote table on real PostgreSQL.

The hosted demo failed to start on 2026-11-26: on a re-seed, ``seed_demo_desk._clear``
deleted every simulated ``market_quotes`` row in one statement. The continuous feed leaves
hundreds of thousands to millions of rows, and ``db.session.get_engine`` gives pg8000 a
5 s socket ``timeout`` that applies to every statement, so the DELETE raised
``TimeoutError: timed out`` and the start exited FATAL. The clear now deletes in bounded,
committed batches.

This module proves the fix where SQLite cannot: a real PostgreSQL schema, 200,000 simulated
quotes, and a re-seed under a strict per-statement (pg8000 socket) timeout. Only the
simulated source's rows may go. Skipped unless ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set;
``scripts/ci/run_postgres_ci.sh`` runs it. Set ``EUROGAS_NEXUS_TEST_SEED_QUOTES`` to raise
the inserted count (the 1,000,000-row measurement uses it).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketQuoteRecord
from eurogas_nexus.db.session import default_driver_url

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Set EUROGAS_NEXUS_TEST_POSTGRES_URL: the test uses a disposable PostgreSQL schema.",
)

ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "scripts" / "demo" / "seed_demo_desk.py"
FEED_SCRIPT = ROOT / "scripts" / "demo" / "exchange_feed.py"

#: The feed-sized table this test re-seeds over. 200,000 is the regression size; the
#: 1,000,000-row timing run sets EUROGAS_NEXUS_TEST_SEED_QUOTES.
QUOTES = int(os.environ.get("EUROGAS_NEXUS_TEST_SEED_QUOTES", "200000"))
#: A strict per-statement socket timeout: every clear batch (and every other statement the
#: re-seed runs) must finish inside it, or pg8000 raises TimeoutError and this test fails.
STATEMENT_TIMEOUT_SECONDS = 2.0


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo_desk_clear_pg", SEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses in the script resolve their module here
    spec.loader.exec_module(module)
    return module


def _feed_module():
    spec = importlib.util.spec_from_file_location("exchange_feed_clear_pg", FEED_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextmanager
def _session(statement_timeout: float = STATEMENT_TIMEOUT_SECONDS):
    url = make_url(default_driver_url(_POSTGRES_URL))
    driver = url.get_driver_name()
    connect_args = (
        {"timeout": statement_timeout}
        if driver == "pg8000"
        else {"connect_timeout": int(statement_timeout) or 1}
    )
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"democleartest_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.commit()
        with engine.connect() as connection:
            connection.execute(text(f'SET search_path TO "{schema}"'))
            Base.metadata.create_all(connection)
            connection.commit()
            with Session(bind=connection) as session:
                yield session
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _insert_quotes(session, count: int, *, prefix: str, source: str) -> None:
    """Insert ``count`` quotes in chunks the strict socket timeout accepts.

    One multi-row VALUES statement per chunk: pg8000's ``executemany`` would make a round trip
    per row, and a million rows would dominate the test. 1,000 rows x 19 columns stays under
    PostgreSQL's 65,535-parameter limit for a statement.
    """

    table = MarketQuoteRecord.__table__
    now = datetime(2026, 11, 26, 9, tzinfo=UTC)
    for offset in range(0, count, 1_000):
        session.execute(
            table.insert().values(
                [
                    {
                        "quote_id": f"{prefix}-{n}",
                        "source_system": source,
                        "venue": "Demo",
                        "instrument_id": f"i-{n % 225}",
                        "hub": ("TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF")[
                            n % 9
                        ],
                        "product": ("WD", "DA", "WE", "M+1", "Q+1", "S+1")[n % 6],
                        "delivery_start_utc": now + timedelta(minutes=n % 2880),
                        "delivery_end_utc": now + timedelta(days=1, minutes=n % 2880),
                        "bid_price": 30.0,
                        "ask_price": 30.1,
                        "currency": "EUR",
                        "unit": "EUR/MWh",
                        "observed_at_utc": now + timedelta(minutes=n % 2880),
                        "received_at_utc": now,
                        "source_reference": "feed:simulated-exchange",
                        "freshness": "live",
                        "quality_score": 1.0,
                        "simulated": True,
                    }
                    for n in range(offset, min(offset + 1_000, count))
                ]
            )
        )
    session.commit()


def test_a_reseed_clears_a_feed_sized_quote_table_within_the_statement_timeout():
    seed = _seed_module()
    seeded_at = datetime(2026, 11, 26, 9, tzinfo=UTC)
    with _session() as session:
        seed.seed(session, seeded_at, history_days=5)
        session.commit()
        _insert_quotes(session, QUOTES, prefix="feed-before", source=seed.SOURCE)
        _insert_quotes(session, 1_000, prefix="real-keep", source="TEST_REAL")
        assert (
            session.query(func.count(MarketQuoteRecord.quote_id))
            .filter(MarketQuoteRecord.quote_id.like("feed-before-%"))
            .scalar()
            == QUOTES
        )

        started = time.monotonic()
        seed.seed(session, seeded_at + timedelta(minutes=1), history_days=5)
        session.commit()
        elapsed = time.monotonic() - started
        print(f"\nre-seed over {QUOTES:,} simulated quotes: {elapsed:.1f}s", flush=True)

        # Every simulated row the feed left is gone (bounded batches, all matched).
        remaining = (
            session.query(func.count(MarketQuoteRecord.quote_id))
            .filter(MarketQuoteRecord.quote_id.like("feed-before-%"))
            .scalar()
        )
        assert remaining == 0
        # Nothing of another source was touched.
        assert (
            session.query(func.count(MarketQuoteRecord.quote_id))
            .filter(MarketQuoteRecord.quote_id.like("real-keep-%"))
            .scalar()
            == 1_000
        )
        # The seed's own fresh quotes are present again.
        assert (
            session.query(func.count(MarketQuoteRecord.quote_id))
            .filter(MarketQuoteRecord.source_system == seed.SOURCE)
            .scalar()
            > 0
        )


def test_the_feed_pauses_while_the_seed_holds_the_clear_lock():
    """The seed's lock key and the feed's check: a live feed sees the clear and waits."""

    seed = _seed_module()
    feed = _feed_module()
    assert feed.SEED_LOCK == seed.SEED_CLEAR_LOCK
    assert feed.seed_clear_in_progress(None) is False  # SQLite / no lock connection

    url = make_url(default_driver_url(_POSTGRES_URL))
    driver = url.get_driver_name()
    connect_args = {"timeout": 10} if driver == "pg8000" else {"connect_timeout": 10}
    engine = create_engine(url, future=True, connect_args=connect_args)
    holder = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    probe = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        holder.execute(
            text("select pg_advisory_lock(:key)"), {"key": seed.SEED_CLEAR_LOCK}
        )
        assert feed.seed_clear_in_progress(probe) is True
        holder.execute(
            text("select pg_advisory_unlock(:key)"), {"key": seed.SEED_CLEAR_LOCK}
        )
        assert feed.seed_clear_in_progress(probe) is False
    finally:
        holder.close()
        probe.close()
        engine.dispose()
