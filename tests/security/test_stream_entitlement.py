"""An open stream sends a caller only what the REST reads would, and notices revocation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.api.routes.public.streaming import StreamGuard, _event_stream
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    IdentityPrincipalRecord,
    TradingBookRecord,
)
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime(2026, 11, 12, 9, tzinfo=UTC)


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p-trader",
        name="trader",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("ANALYST",),
    )


def _record(model, **values):
    """A row with every required column filled, so the test names only what matters."""

    for column in model.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        kind = column.type
        values[column.name] = (
            NOW if isinstance(kind, DateTime)
            else 1.0 if isinstance(kind, Float)
            else 1 if isinstance(kind, Integer)
            else False if isinstance(kind, Boolean)
            else [] if kind.__class__.__name__ == "JSON"
            else "x"
        )
    return model(**values)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_quotes_from_an_unlicensed_source_are_not_streamed(session):
    rows = [
        {"quote_id": "q1", "source_system": "EEX", "observed_at_utc": NOW},
        {"quote_id": "q2", "source_system": "ICE_OCM", "observed_at_utc": NOW},
        {"quote_id": "q3", "source_system": None, "observed_at_utc": NOW},
    ]
    guard = StreamGuard("quotes", _principal("EEX"))
    assert [row["quote_id"] for row in guard(session, rows)] == ["q1"]
    assert guard.__class__("quotes", _principal())(session, rows) == []


def test_an_opportunity_change_follows_the_opportunitys_own_read_rule(session, monkeypatch):
    """M7: the stream serves the opportunity engine; a change is streamed to a caller who may
    read the opportunity (every source family, and every book unless it is a market item)."""

    for book in ("uk-nbp", "nl-ttf"):
        session.add(_record(TradingBookRecord, book_id=book, legal_entity="E", region="NWE"))
    session.commit()
    rows = [
        {"opportunity_id": "o1", "lane": "must_act", "book_ids": ["uk-nbp"], "source_families": []},
        {"opportunity_id": "o2", "lane": "market", "book_ids": [], "source_families": ["EEX"]},
        {"opportunity_id": "o3", "lane": "market", "book_ids": [], "source_families": []},
        {"opportunity_id": "o4", "lane": "could_act", "book_ids": ["nl-ttf"], "sent": False},
    ]
    # Isolation switched off explicitly (it is on by default since security review H1).
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "false")
    every = StreamGuard("opportunity", _principal("*"))(session, rows)
    assert [row["opportunity_id"] for row in every] == ["o1", "o2", "o3"]  # o4 never shown
    unlicensed = StreamGuard("opportunity", _principal())(session, rows)
    assert [row["opportunity_id"] for row in unlicensed] == ["o1", "o3"]
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    regional = StreamGuard("opportunity", _principal("BOOKS:BOOK:nl-ttf", "EEX"))
    assert [row["opportunity_id"] for row in regional(session, rows)] == ["o2", "o3"]


def test_a_limits_alert_is_streamed_only_to_callers_who_see_its_books(session, monkeypatch):
    rows = [
        {"alert_id": "a1", "category": "limits", "evidence_snapshot": {"book_ids": ["uk-nbp"]}},
        {"alert_id": "a2", "category": "physical", "evidence_snapshot": {}},
    ]
    # Isolation switched off explicitly: every alert, as before.
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "false")
    assert len(StreamGuard("alerts", _principal())(session, rows)) == 2
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    regional = StreamGuard("alerts", _principal("BOOKS:BOOK:nl-ttf"))
    assert [row["alert_id"] for row in regional(session, rows)] == ["a2"]
    head_office = StreamGuard("alerts", _principal("BOOKS:*"))
    assert len(head_office(session, rows)) == 2


def test_a_withdrawn_scope_and_a_disabled_identity_reach_the_open_stream(session):
    session.add(
        _record(
            IdentityPrincipalRecord,
            principal_id="p-trader",
            name="trader",
            role="ANALYST",
            roles=["ANALYST"],
            status="ACTIVE",
            data_scopes=["EEX"],
        )
    )
    session.commit()
    rows = [{"quote_id": "q1", "source_system": "EEX", "observed_at_utc": NOW}]
    guard = StreamGuard("quotes", _principal("EEX"))
    assert guard(session, rows) == rows

    record = session.get(IdentityPrincipalRecord, "p-trader")
    record.data_scopes = []
    session.commit()
    assert guard(session, rows) == rows  # not yet re-read
    guard._checked_at -= timedelta(seconds=streaming.REAUTH_SECONDS + 1)
    assert guard(session, rows) == []  # scope withdrawn

    record.status = "DISABLED"
    session.commit()
    guard._checked_at -= timedelta(seconds=streaming.REAUTH_SECONDS + 1)
    assert guard(session, rows) is None  # identity disabled: the stream must end


def test_the_stream_skips_withheld_rows_for_good_and_ends_on_revocation(monkeypatch):
    rows = [
        {"quote_id": "q1", "source_system": "ICE_OCM", "observed_at_utc": NOW},
        {"quote_id": "q2", "source_system": "EEX", "observed_at_utc": NOW + timedelta(seconds=1)},
    ]
    cursors = []

    def fetch(_session, cursor):
        cursors.append(cursor)
        return rows if len(cursors) == 1 else []

    class _Factory:
        def __call__(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, *_):
            return False

    monkeypatch.setattr("eurogas_nexus.db.session.get_session_factory", lambda: _Factory())
    monkeypatch.setattr(streaming, "POLL_SECONDS", 0)
    state = {"calls": 0}

    def guard(_session, batch):
        state["calls"] += 1
        if state["calls"] == 2:
            return None
        return [row for row in batch if row["source_system"] == "EEX"]

    async def drive():
        return [event async for event in _event_stream(
            "quotes", fetch, "observed_at_utc", "quote_id", None, guard=guard
        )]

    events = asyncio.run(drive())
    assert len(events) == 2
    assert "q2" in events[0] and "q1" not in events[0]
    assert "event: revoked" in events[1]
    # The second poll starts after q2: the withheld q1 is never fetched again.
    assert cursors[1] == (NOW + timedelta(seconds=1), "q2")
