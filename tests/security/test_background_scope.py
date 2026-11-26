"""The process's own machinery runs in an explicit system scope under book isolation (H1).

Book isolation is on by default and a request starts deny-all until its caller is identified.
The scheduler, the gated upgrade command, the metrics exporter's database reads and the stream
poller read across books for the firm itself, never for a person: each sets the system scope
explicitly (``portfolio_scope.system_scope``), so a deny-all or a person's scope left in the
context (a thread started from a request, a copied context) can neither empty nor narrow what
it reads. The stream poller's two-entity test is ``test_stream_book_scope.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import eurogas_nexus.db.models  # noqa: F401  (registers every table, installs the scope events)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import TradingBookRecord
from eurogas_nexus.security import portfolio_scope


def _record(model, **values):
    from datetime import UTC, datetime

    from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric

    def utc_now():
        return datetime.now(UTC)

    for column in model.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        kind = column.type
        values[column.name] = (
            utc_now() if isinstance(kind, DateTime)
            else utc_now().date() if isinstance(kind, Date)
            else 1.0 if isinstance(kind, Float | Numeric)
            else 1 if isinstance(kind, Integer)
            else False if isinstance(kind, Boolean)
            else [] if kind.__class__.__name__ == "JSON"
            else "x"
        )
    return model(**values)


@pytest.fixture
def factory(monkeypatch):
    monkeypatch.delenv(portfolio_scope.ISOLATION_ENV, raising=False)  # on by default
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for book, entity in (("nl-book", "NL"), ("uk-book", "UK")):
            db.add(_record(TradingBookRecord, book_id=book, legal_entity=entity, region="NWE"))
        db.commit()
    return sessionmaker(engine)


@pytest.fixture
def deny_all():
    """What a request leaves in the context before its caller is identified."""

    token = portfolio_scope._current.set(portfolio_scope.DENY_ALL)
    yield
    portfolio_scope._current.reset(token)


def _books(factory) -> int:
    with factory() as session:
        return session.query(TradingBookRecord).count()


def test_isolation_is_on_and_a_deny_all_context_sees_no_book(factory, deny_all):
    assert portfolio_scope.isolation_enabled()
    assert _books(factory) == 0


def test_the_system_scope_reads_every_book_and_restores_the_context(factory, deny_all):
    with portfolio_scope.system_scope():
        assert _books(factory) == 2
        assert portfolio_scope.current_principal_ids() == ()
    assert portfolio_scope.current_scope() is portfolio_scope.DENY_ALL


def test_the_scheduler_runs_in_the_system_scope(factory, deny_all, monkeypatch):
    from scripts.ops import run_dataops_scheduler as scheduler

    seen = {}

    def run_loop(**_kwargs):
        seen["scope"] = portfolio_scope.current_scope()
        seen["books"] = _books(factory)
        return 0

    monkeypatch.setattr(scheduler, "run_loop", run_loop)
    assert scheduler.main(["--once"]) == 0
    assert seen == {"scope": None, "books": 2}


def test_the_upgrade_command_runs_in_the_system_scope(factory, deny_all, monkeypatch):
    from scripts.ops import upgrade_database

    seen = {}

    def cmd_plan(_args):
        seen["scope"] = portfolio_scope.current_scope()
        seen["books"] = _books(factory)
        return 0

    monkeypatch.setattr(upgrade_database, "cmd_plan", cmd_plan)
    assert upgrade_database.main(["plan"]) == 0
    assert seen == {"scope": None, "books": 2}


def test_the_metrics_exporter_reads_the_store_in_the_system_scope(factory, deny_all, monkeypatch):
    from eurogas_nexus.api.middleware import metrics_endpoint
    from eurogas_nexus.application import dataops_observability
    from eurogas_nexus.db import session as db_session

    def prometheus_metrics(session):
        return f"books {session.query(TradingBookRecord).count()}\n"

    monkeypatch.setattr(db_session, "resolve_database_url", lambda: "configured")
    monkeypatch.setattr(db_session, "get_session_factory", lambda: factory)
    monkeypatch.setattr(dataops_observability, "prometheus_metrics", prometheus_metrics)
    body = metrics_endpoint.render_exposition()
    assert "books 2\n" in body and "eurogas_metrics_database_up 1" in body
