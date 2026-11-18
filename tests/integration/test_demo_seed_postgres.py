"""The demo seed and its roll-forward on real PostgreSQL.

Two faults stopped the demo starting on its own PostgreSQL store (2026-11-18) and passed the
SQLite unit tests: a ``SELECT DISTINCT`` over a ``json`` column (PostgreSQL has no equality
operator for ``json``) and a demo benchmark fixing written for a day a real source had already
stored (unique on benchmark and day across sources). This module runs the seed, a real
public source's rows, and the roll-forward against PostgreSQL in a disposable schema.

Skipped unless an explicit PostgreSQL URL is configured (``EUROGAS_NEXUS_TEST_POSTGRES_URL`` or
``RUNTIME_STORE_DATABASE_URL``); ``scripts/ci/run_postgres_ci.sh`` runs it in CI.
"""

from __future__ import annotations

import importlib.util
import os
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
from eurogas_nexus.db.models import InterestRateObservationRecord, MarketObservationRecord

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; the test uses a disposable schema.",
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo_desk_pg", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _session():
    url = make_url(_POSTGRES_URL)
    connect_args = {"timeout": 10} if url.get_driver_name() == "pg8000" else {"connect_timeout": 10}
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"demoseedtest_{uuid4().hex}"
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


def test_seed_then_real_rows_then_roll_forward_on_postgresql():
    seed = _seed_module()
    seeded_at = datetime(2026, 11, 2, 9, tzinfo=UTC)
    later = seeded_at + timedelta(days=16)
    with _session() as session:
        seed.seed(session, seeded_at, history_days=20)
        session.commit()

        # A real public fixing for a day the roll-forward will also cover, and a real gas price
        # with its hub in the JSON metadata (the DISTINCT that failed read it).
        fixing_day = (later - timedelta(days=1)).date()
        session.add(
            InterestRateObservationRecord(
                observation_id="boe-sonia-test", benchmark_id="SONIA", currency="GBP",
                value_date=fixing_day, rate_pct=3.9, day_count="ACT/365F",
                source_system="BOE", source_reference="test", ingested_at_utc=later,
            )
        )
        session.add(
            MarketObservationRecord(
                observation_id="real-ttf-test", source_system="TEST_EXCHANGE",
                market_venue="TEST", source_reference="test",
                product="TTF month-ahead", price=31.0, unit="EUR/MWh", currency="EUR",
                observed_at_utc=later - timedelta(days=1),
                period_start_utc=later, period_end_utc=later + timedelta(days=30),
                freshness="daily", quality_score=1.0, research_only=True,
                metadata_json={"hub": "TTF", "tenor": "month-ahead"},
            )
        )
        session.commit()

        assert seed._real_price_hubs(session) == {"TTF"}
        counts = seed.roll_forward(session, later)
        session.commit()
        assert counts["rate_rows"] > 0

        sonia = (
            session.query(InterestRateObservationRecord)
            .filter(
                InterestRateObservationRecord.benchmark_id == "SONIA",
                InterestRateObservationRecord.value_date == fixing_day,
            )
            .all()
        )
        assert [row.source_system for row in sonia] == ["BOE"]
        # A second start the same day adds nothing and still succeeds.
        again = seed.roll_forward(session, later)
        session.commit()
        assert again["rate_rows"] == 0
        # The demo market (every product of every hub) writes and rolls on PostgreSQL too.
        assert counts["market_close_rows"] > 0 and counts["market_quote_rows"] > 0
        assert again["market_close_rows"] == 0 and again["market_quote_rows"] == 0
        assert session.query(func.count(MarketObservationRecord.observation_id)).scalar() > 0


def test_an_older_volume_is_topped_up_with_what_a_newer_seed_adds():
    """A volume an older build seeded lacks the newer fixtures; the start-up adds them once."""

    from eurogas_nexus.db.models import CreditLineRecord, MarketQuoteRecord, TsoTariffRecord
    from eurogas_nexus.db.models.decision import DecisionCaseRecord

    seed = _seed_module()
    seeded_at = datetime(2026, 11, 2, 9, tzinfo=UTC)
    later = seeded_at + timedelta(days=1)
    with _session() as session:
        seed.seed(session, seeded_at, history_days=15)
        session.commit()
        # What the previous release's seed did not write, or a tester changed.
        session.query(TsoTariffRecord).filter(
            TsoTariffRecord.document_id == seed.SIMULATED_TARIFF_DOCUMENT).delete()
        session.query(DecisionCaseRecord).filter(
            DecisionCaseRecord.case_id == seed.DEMO_REVIEW_CASE_ID).delete()
        session.query(CreditLineRecord).filter(CreditLineRecord.counterparty_id == "ALD").delete()
        session.get(CreditLineRecord, "RHM").limit_amount = 5_000_000  # a tester's change
        session.query(MarketObservationRecord).filter(
            MarketObservationRecord.source_reference == "demo:market").delete()
        session.query(MarketQuoteRecord).delete()
        session.commit()

        counts = seed.roll_forward(session, later)
        session.commit()
        assert counts["fixture_tariffs"] == len(seed.SIMULATED_TARIFFS)
        assert counts["fixture_review_case"] == 1
        assert counts["fixture_credit_lines"] == 1
        assert counts["market_quote_rows"] > 0
        assert session.get(CreditLineRecord, "RHM").limit_amount == 5_000_000
        assert session.get(DecisionCaseRecord, seed.DEMO_REVIEW_CASE_ID) is not None

        again = seed.roll_forward(session, later)
        session.commit()
        assert not any(key.startswith("fixture_") for key in again)
