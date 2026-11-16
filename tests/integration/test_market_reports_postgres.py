"""Market-report records on real PostgreSQL: JSON snapshot round trip, listing, reader checks.

Runs in a throwaway schema with only the tables the store reads, so it works whether or not the
default schema is migrated.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.reports.catalogue import validate_plan
from eurogas_nexus.application.reports.engine import GeneratedReport, canonical_json, sha256
from eurogas_nexus.application.reports.render import render_report
from eurogas_nexus.application.reports.store import (
    list_reports,
    reader_may_see,
    rerender,
    store_report,
)
from eurogas_nexus.db.models import MarketReportRecord, TradingBookRecord
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; tables use a disposable schema.",
)
NOW = datetime(2026, 11, 16, 7, tzinfo=UTC)


def _caller(*scopes: str) -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id="p-1", name="analyst", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=scopes, roles=("ANALYST",)))


@contextmanager
def _session():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    schema = f"mrtest_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (MarketReportRecord, TradingBookRecord):
                model.__table__.create(bind=connection)
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _report(audience: str, books: list[str]) -> GeneratedReport:
    plan = validate_plan({"kind": "weekly", "audience": audience, "sections": ["storage"]},
                         now=NOW)
    snapshot = {
        "report_id": f"mr-{uuid4().hex[:12]}", "title": "Weekly", "kind": "weekly",
        "kind_label": "Weekly", "variant": None, "audience": audience, "question": None,
        "plan": plan.as_dict(), "period": {"start": "2026-11-09", "end": "2026-11-15"},
        "as_of": NOW.isoformat(), "generated_at": NOW.isoformat(), "generated_by": "analyst",
        "headline": "Storage 64.2% full, 中文 ok.", "key_points": [], "sections": [],
        "omitted": [], "simulated": False, "licensed": {"sources": []},
        "model_use": {"attempted": 0, "passed": 0, "sections": {}},
        "template_version": "market-report/1", "language": "en",
    }
    html = render_report(snapshot)
    return GeneratedReport(snapshot["report_id"], plan, snapshot, html,
                           sha256(canonical_json(snapshot)), sha256(html),
                           ["GIE"], [], books)


def test_a_record_round_trips_and_reopens_identically_on_postgres():
    with _session() as session:
        report = _report("internal", [])
        store_report(session, report, caller=_caller("BOOKS:*"), generated_by_type="USER",
                     trigger={"type": "user"}, now=NOW)
        record = session.get(MarketReportRecord, report.report_id)
        assert record.snapshot_json == report.snapshot
        assert rerender(record) == record.html
        assert sha256(canonical_json(record.snapshot_json)) == record.snapshot_sha256
        assert record.period_start == date(2026, 11, 9)
        assert [r["report_id"] for r in list_reports(session, _caller())] == [report.report_id]


def test_a_reader_outside_the_reports_books_is_refused_on_postgres(monkeypatch):
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    with _session() as session:
        session.add(TradingBookRecord(book_id="UK-1", name="UK", legal_entity="EGN-UK",
                                      region="europe", business="gas", base_currency="GBP",
                                      updated_by="t", updated_at_utc=NOW))
        session.flush()
        report = _report("internal", ["UK-1"])
        store_report(session, report, caller=_caller("BOOKS:*"), generated_by_type="USER",
                     trigger={"type": "user"}, now=NOW)
        record = session.get(MarketReportRecord, report.report_id)
        assert reader_may_see(session, record, _caller("BOOKS:BOOK:UK-1"))[0]
        assert reader_may_see(session, record, _caller("BOOKS:BOOK:US-1")) == (
            False, "report_contains_books_outside_scope")
        assert list_reports(session, _caller("BOOKS:BOOK:US-1")) == []
