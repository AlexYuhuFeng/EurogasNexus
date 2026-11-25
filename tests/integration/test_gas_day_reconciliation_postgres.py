"""SCHED-1 on real PostgreSQL: the R1 break read, alerted once, withdrawn when it is fixed.

The same demo desk as ``tests/integration/test_gas_day_reconciliation.py`` in a disposable
schema: on the R1 gas day 2026-12-11 the TSO confirmed 4,800 of the 6,000 MWh nominated out to
Aldermoor (6,000 - 4,800 = 1,200 MWh cut). Also times one alert pass (criterion SCHED1-5,
evidence in 09 and 15).

Skipped unless an explicit PostgreSQL URL is configured (``EUROGAS_NEXUS_TEST_POSTGRES_URL`` or
``RUNTIME_STORE_DATABASE_URL``).
"""

from __future__ import annotations

import importlib.util
import os
import time
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.gas_day_reconciliation import queue_break_alerts, reconciliation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import GasDayNominationEventRecord, NotificationOutboxRecord
from eurogas_nexus.security.identity import AuthenticatedPrincipal

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; the test uses a disposable schema.",
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
DAY = date(2026, 12, 11)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 12, 11, hour, minute, tzinfo=UTC)


@contextmanager
def _session():
    url = make_url(_POSTGRES_URL)
    connect_args = {"timeout": 10} if url.get_driver_name() == "pg8000" else {"connect_timeout": 10}
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"sched1test_{uuid4().hex}"
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


def test_the_r1_break_is_read_alerted_and_withdrawn_on_postgresql(monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    spec = importlib.util.spec_from_file_location("seed_demo_desk_sched1_pg", SCRIPT)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    caller = Caller(AuthenticatedPrincipal(
        principal_id="p-sched", name="sched", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=("*",), roles=("ANALYST",)))
    with _session() as session:
        seed.seed(session, _at(9), history_days=3)
        session.commit()
        (item,) = reconciliation(session, caller, DAY, now=_at(23, 30))["breaks"]
        assert (item["kind"], item["mwh_at_risk"]) == ("lesser_rule_cut", 1_200)
        assert item["cash_out"]["value"] == 1_440

        started = time.perf_counter()
        first = queue_break_alerts(session, now=_at(23, 30))
        session.commit()
        elapsed = time.perf_counter() - started
        assert first["notified"] == 1
        print(f"\nSCHED-1 alert pass on PostgreSQL: {elapsed:.3f} s")
        assert elapsed < 30  # one worker pass; the budget is 30 minutes before the cut-off
        assert queue_break_alerts(session, now=_at(23, 35))["notified"] == 0
        session.commit()

        # Aldermoor renominates 6,000 and the TSO matches it: the alert is withdrawn.
        for status, minute in (("renominated", 40), ("confirmed", 45)):
            session.add(GasDayNominationEventRecord(
                event_id=f"pg-{status}", gas_day=DAY, line_ref="trade:demo-etrm-ald-1",
                hub="NBP", book_id="demo-uk-nbp", step="renomination", status=status,
                quantity_mwh=6_000.0, origin="import", recorded_by="test",
                recorded_at_utc=_at(23, minute), source_system="TEST",
                counterparty_quantity_mwh=6_000.0 if status == "confirmed" else None))
        session.commit()
        assert queue_break_alerts(session, now=_at(23, 50))["withdrawn"] == 1
        session.commit()
        titles = [row.title for row in session.query(NotificationOutboxRecord)
                  .filter(NotificationOutboxRecord.category == "nomination")
                  .order_by(NotificationOutboxRecord.created_at_utc)]
        assert len(titles) == 2 and titles[-1].startswith("Withdrawn:")
