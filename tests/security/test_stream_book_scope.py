"""Two legal entities on one stream poller: each connection receives only its own books (H1).

The process's one poller (``api/stream_hub.py``) reads once for every open stream, so its own
reads run in an explicit system scope; each connection's fan-out then applies that
connection's caller: book scope (default-deny isolation), licensed data scopes, and the
commercial boundary. These tests run the poller the way the API does, with isolation on and
with an unrelated request scope left in the polling thread, and check that no row or notice of
one entity reaches the other's stream, that a caller with no ``BOOKS:`` scope sees nothing,
and that a caller who loses commercial access has the stream ended.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import eurogas_nexus.db.models  # noqa: F401  (registers every table, installs the scope events)
from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.api.routes.public.streaming import StreamGuard, _LiveStream, _RowStream
from eurogas_nexus.api.stream_hub import StreamHub
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    IdentityPrincipalRecord,
    OpportunityRecord,
    ScreenOrderObservationRecord,
    TradingBookRecord,
)
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime.now(UTC).replace(microsecond=0)
LATER = NOW + timedelta(minutes=30)
NL_BOOK, UK_BOOK = "nl-book", "LEAKUK-book"


def _record(model, **values):
    for column in model.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        kind = column.type
        values[column.name] = (
            NOW if isinstance(kind, DateTime)
            else NOW.date() if isinstance(kind, Date)
            else 1.0 if isinstance(kind, Float | Numeric)
            else 1 if isinstance(kind, Integer)
            else False if isinstance(kind, Boolean)
            else [] if kind.__class__.__name__ == "JSON"
            else "x"
        )
    return model(**values)


def _principal(principal_id: str, *scopes: str, roles=("ANALYST",)) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=principal_id,
        name=principal_id,
        principal_type="USER",
        role=roles[0],
        status="ACTIVE",
        data_scopes=scopes,
        roles=roles,
        auth_method="session",
    )


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.delenv(portfolio_scope.ISOLATION_ENV, raising=False)  # on by default
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(_record(TradingBookRecord, book_id=NL_BOOK, legal_entity="NL", region="NWE"))
        db.add(_record(TradingBookRecord, book_id=UK_BOOK, legal_entity="UK", region="UK"))
        for book, opp in ((NL_BOOK, "opp-nl"), (UK_BOOK, "opp-LEAKUK")):
            db.add(
                _record(
                    OpportunityRecord,
                    opportunity_id=opp,
                    opp_key=opp,
                    lane="must_act",
                    state="actionable",
                    surfaced=True,
                    book_ids=[book],
                    source_families=[],
                    last_changed_utc=NOW + timedelta(seconds=1 if book == NL_BOOK else 2),
                    expires_at_utc=LATER,
                )
            )
        # A booked trade per entity, at different times (the notice names the time).
        db.add(_record(ScreenOrderObservationRecord, order_observation_id="t-nl",
                       book_id=NL_BOOK, observed_at_utc=NOW + timedelta(seconds=3)))
        db.add(_record(ScreenOrderObservationRecord, order_observation_id="t-uk",
                       book_id=UK_BOOK, observed_at_utc=NOW + timedelta(seconds=4)))
        for pid, role, scopes in (
            ("p-nl", "ANALYST", ["BOOKS:ENTITY:NL"]),
            ("p-uk", "ANALYST", ["BOOKS:ENTITY:UK"]),
            ("p-none", "ANALYST", []),
        ):
            db.add(_record(IdentityPrincipalRecord, principal_id=pid, name=pid, role=role,
                           roles=[role], status="ACTIVE", data_scopes=scopes))
        db.commit()
    return engine


def _hub(engine) -> StreamHub:
    return StreamHub(
        interval=lambda: 3600.0,
        session_factory=lambda: (lambda: Session(engine)),
        warning=streaming.warning_event,
        autostart=False,
    )


def _opportunity_stream(principal) -> _RowStream:
    return _RowStream(
        "opportunity",
        streaming._fetch_new_opportunities,
        "changed_at_utc",
        "opportunity_id",
        (NOW - timedelta(seconds=1), ""),
        StreamGuard("opportunity", principal),
        (),
    )


def _live_stream(principal) -> _LiveStream:
    return _LiveStream(
        ("trades",), NOW - timedelta(seconds=1), False, StreamGuard("live", principal), None
    )


def _drain(sub) -> str:
    out = []
    while not sub.queue.empty():
        chunks, _done = sub.queue.get_nowait()
        out.extend(chunks)
    return "".join(out)


def _run(engine, states, ambient: portfolio_scope.BookScope | None) -> list[str]:
    """One poll as the poller thread runs it, with ``ambient`` left in the thread's context
    (a thread started from a request, or a copied context)."""

    async def drive():
        hub = _hub(engine)
        subs = [hub.subscribe(state) for state in states]
        token = portfolio_scope._current.set(ambient)
        try:
            hub.poll(subs)
        finally:
            portfolio_scope._current.reset(token)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        return [_drain(sub) for sub in subs]

    return asyncio.run(drive())


AMBIENTS = {
    "none": None,
    "deny-all": portfolio_scope.DENY_ALL,
    "nl-request": portfolio_scope.scope_from_data_scopes(("BOOKS:ENTITY:NL",)),
}


@pytest.mark.parametrize("ambient", sorted(AMBIENTS))
def test_each_entity_streams_only_its_own_opportunities(engine, ambient):
    nl, uk, none = _run(
        engine,
        [
            _opportunity_stream(_principal("p-nl", "BOOKS:ENTITY:NL")),
            _opportunity_stream(_principal("p-uk", "BOOKS:ENTITY:UK")),
            _opportunity_stream(_principal("p-none")),
        ],
        AMBIENTS[ambient],
    )
    assert "opp-nl" in nl and "LEAKUK" not in nl
    # The UK caller gets its row even when the polling thread was left an NL request scope:
    # the poller reads in its own system scope, the fan-out narrows per caller.
    assert "opp-LEAKUK" in uk and "opp-nl" not in uk
    assert "opp-" not in none  # no BOOKS: scope, no position (default deny)


@pytest.mark.parametrize("ambient", sorted(AMBIENTS))
def test_each_entity_hears_only_of_its_own_trades(engine, ambient):
    nl, uk, none = _run(
        engine,
        [
            _live_stream(_principal("p-nl", "BOOKS:ENTITY:NL")),
            _live_stream(_principal("p-uk", "BOOKS:ENTITY:UK")),
            _live_stream(_principal("p-none")),
        ],
        AMBIENTS[ambient],
    )
    # A notice names the newest change the caller may see (the event id is the cursor, which
    # moves past every row and says nothing about whose it was).
    nl_at = f'"changed_at": "{(NOW + timedelta(seconds=3)).isoformat()}"'
    uk_at = f'"changed_at": "{(NOW + timedelta(seconds=4)).isoformat()}"'
    assert nl_at in nl and uk_at not in nl
    assert uk_at in uk and nl_at not in uk
    assert "event: change" not in none


def test_the_poller_restores_the_threads_own_scope(engine):
    ambient = AMBIENTS["nl-request"]
    _run(engine, [_opportunity_stream(_principal("p-uk", "BOOKS:ENTITY:UK"))], ambient)
    assert portfolio_scope.current_scope() is None  # the test's own context, untouched


def test_a_stream_without_a_caller_gets_nothing(engine):
    (sent,) = _run(engine, [_opportunity_stream(None)], None)
    assert "opp-" not in sent and "revoked" in sent


def test_a_withdrawn_book_scope_and_a_lost_commercial_role_reach_the_open_stream(engine):
    guard = StreamGuard("opportunity", _principal("p-uk", "BOOKS:ENTITY:UK"))
    rows = [{"opportunity_id": "o", "lane": "must_act", "book_ids": [UK_BOOK]}]
    with Session(engine) as db:
        assert guard(db, rows) == rows
        record = db.get(IdentityPrincipalRecord, "p-uk")
        record.data_scopes = ["BOOKS:ENTITY:NL"]
        db.commit()
        guard._checked_at -= timedelta(seconds=streaming.REAUTH_SECONDS + 1)
        assert guard(db, rows) == []  # moved to another entity: UK rows stop at once
        record.role, record.roles = "ADMIN", ["ADMIN"]
        db.commit()
        guard._checked_at -= timedelta(seconds=streaming.REAUTH_SECONDS + 1)
        assert guard(db, rows) is None  # platform administration only: the stream ends
