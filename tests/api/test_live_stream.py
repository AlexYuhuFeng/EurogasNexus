"""The live stream: per-topic change notices, job progress, heartbeats and resume."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.api.routes.public.streaming import (
    StreamGuard,
    _live_event_id,
    _live_stream,
    _parse_live_id,
)
from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.live_topics import (
    job_events,
    outbox_changes,
    outbox_start,
    parse_topics,
    topic_changes,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    JobRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    ScreenOrderObservationRecord,
    TradingBookRecord,
)
from eurogas_nexus.domain.market_events import MarketEvent
from eurogas_nexus.security import portfolio_scope
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


def _principal(*scopes: str, principal_id: str = "p-trader") -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=principal_id,
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
            NOW
            if isinstance(kind, DateTime)
            else 1.0
            if isinstance(kind, Float)
            else 1
            if isinstance(kind, Integer)
            else False
            if isinstance(kind, Boolean)
            else []
            if kind.__class__.__name__ == "JSON"
            else "x"
        )
    return model(**values)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _quote(quote_id: str, source: str, at: datetime) -> MarketQuoteRecord:
    return _record(MarketQuoteRecord, quote_id=quote_id, source_system=source, observed_at_utc=at)


def test_topics_are_parsed_in_a_stable_order_and_unknown_names_dropped():
    assert parse_topics("jobs, Prices,nonsense,alerts") == ("prices", "alerts", "jobs")
    assert parse_topics(None) == ()


def test_a_price_notice_needs_a_quote_the_caller_is_licensed_for(session):
    session.add(_quote("q1", "ICE_OCM", NOW + timedelta(seconds=1)))
    session.commit()
    cursors = {"prices": NOW}
    [notice] = topic_changes(session, ("prices",), cursors, _principal("EEX"))
    # The unlicensed quote moves the cursor but is not announced.
    assert notice["visible"] is False
    assert notice["cursor"] == NOW + timedelta(seconds=1)

    session.add(_quote("q2", "EEX", NOW + timedelta(seconds=2)))
    session.commit()
    [notice] = topic_changes(session, ("prices",), cursors, _principal("EEX"))
    assert notice["visible"] is True
    assert notice["changed_at"] == NOW + timedelta(seconds=2)


def test_a_new_settlement_on_the_curve_is_a_price_change(session):
    session.add(
        _record(
            MarketObservationRecord,
            observation_id="o1",
            source_system="EEX",
            observed_at_utc=NOW + timedelta(minutes=1),
        )
    )
    session.commit()
    [notice] = topic_changes(session, ("prices",), {"prices": NOW}, _principal("EEX"))
    assert notice["visible"] is True


def test_nothing_after_the_cursor_is_no_notice(session):
    session.add(_quote("q1", "EEX", NOW - timedelta(seconds=5)))
    session.commit()
    assert topic_changes(session, ("prices",), {"prices": NOW}, _principal("EEX")) == []


def test_a_trade_counts_only_for_callers_who_see_its_book(session, monkeypatch):
    monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
    for book in ("nl-ttf", "uk-nbp"):
        session.add(_record(TradingBookRecord, book_id=book, legal_entity="E", region="R"))
    session.add(
        _record(
            ScreenOrderObservationRecord,
            order_observation_id="t1",
            book_id="uk-nbp",
            observed_at_utc=NOW + timedelta(seconds=1),
        )
    )
    session.commit()
    regional = _principal("BOOKS:BOOK:nl-ttf")
    [notice] = topic_changes(session, ("trades",), {"trades": NOW}, regional)
    assert notice["visible"] is False
    head_office = _principal("BOOKS:*")
    [notice] = topic_changes(session, ("trades",), {"trades": NOW}, head_office)
    assert notice["visible"] is True


def _job(job_id: str, owner: str, status: str, progress: float) -> JobRecord:
    return _record(
        JobRecord,
        job_id=job_id,
        kind="dataset_build",
        status=status,
        principal="trader",
        owner_principal_id=owner,
        progress=progress,
        created_at_utc=NOW,
    )


def test_jobs_are_the_callers_own_and_sent_again_only_when_they_move(session):
    from eurogas_nexus.db.models import IdentityPrincipalRecord

    for principal_id in ("p-trader", "p-other"):
        session.add(_record(IdentityPrincipalRecord, principal_id=principal_id, name=principal_id))
    session.add(_job("j1", "p-trader", "RUNNING", 0.25))
    session.add(_job("j2", "p-other", "RUNNING", 0.5))
    session.commit()
    seen: dict = {}
    first = job_events(session, _principal(), NOW, seen)
    assert [job["job_id"] for job in first] == ["j1"]
    assert first[0]["progress"] == 0.25 and first[0]["status"] == "RUNNING"
    assert set(first[0]) >= {"job_id", "kind", "status", "progress", "step"}
    assert job_events(session, _principal(), NOW, seen) == []  # unchanged: nothing

    job = session.get(JobRecord, "j1")
    job.progress = 1.0
    job.status = "SUCCEEDED"
    job.finished_at_utc = NOW + timedelta(seconds=30)
    session.commit()
    [done] = job_events(session, _principal(), NOW, seen)
    assert done["status"] == "SUCCEEDED" and done["progress"] == 1.0


def test_a_live_event_id_round_trips_and_is_kept_within_the_resume_limit():
    at = NOW - timedelta(minutes=2)
    assert _parse_live_id(_live_event_id(at), NOW) == (at, None)
    assert _parse_live_id(_live_event_id(at, "c1-0-42"), NOW) == (at, "c1-0-42")
    assert _parse_live_id(_live_event_id(at, "not-a-cursor"), NOW) == (at, None)
    assert _parse_live_id("2026-11-26T09:00:00+00:00|q1", NOW) is None  # another stream's id
    assert _parse_live_id("live|nonsense", NOW) is None
    old, _ = _parse_live_id(_live_event_id(NOW - timedelta(days=1)), NOW)
    assert old == NOW - timedelta(seconds=streaming.LIVE_RESUME_LIMIT_SECONDS)
    assert _parse_live_id(_live_event_id(NOW + timedelta(hours=1)), NOW) == (NOW, None)


def _price_event(at: datetime, source: str = "EEX", price: str = "41.2") -> MarketEvent:
    return MarketEvent(
        source_id=source,
        event_type="price.updated",
        subject_key="hub:TTF:2027-01",
        ingested_at_utc=at,
        market_time_utc=datetime(2026, 11, 25, 17, 30, tzinfo=UTC),
        published_at_utc=datetime(2026, 11, 25, 17, 30, tzinfo=UTC),
        payload={"price": price, "unit": "MWh", "currency": "EUR"},
        identity=f"hub:TTF:2027-01|{source}|2026-11-25",
    )


def test_outbox_events_become_one_notice_per_topic_from_the_cursor(session):
    outbox.publish(session, _price_event(NOW - timedelta(hours=1)))
    session.commit()
    start = outbox_start(session)
    assert outbox_changes(session, ("prices",), start, _principal("EEX")) == ([], start)

    outbox.publish(session, _price_event(NOW + timedelta(seconds=1), price="41.5"))
    outbox.publish(session, _price_event(NOW + timedelta(seconds=2), source="ICE_ENDEX"))
    session.commit()
    notices, cursor = outbox_changes(session, ("prices", "outages"), start, _principal("EEX"))
    assert cursor != start
    # Two events, one of a family the caller is not licensed for: one notice, at the visible one.
    assert [(n["topic"], n["changed_at"]) for n in notices] == [
        ("prices", NOW + timedelta(seconds=1))
    ]
    assert outbox_changes(session, ("prices",), cursor, _principal("EEX")) == ([], cursor)
    # A page that does not show prices is not told about them.
    assert outbox_changes(session, ("tariffs",), start, _principal("EEX"))[0] == []


class _Factory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, *_):
        return False


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    out = []
    for chunk in chunks:
        fields = dict(line.split(": ", 1) for line in chunk.strip().splitlines())
        out.append((fields["event"], json.loads(fields["data"])))
    return out


def test_the_stream_says_ready_then_one_notice_per_changed_topic(session, monkeypatch):
    session.add(_quote("q1", "EEX", NOW + timedelta(seconds=1)))
    session.add(_quote("q2", "EEX", NOW + timedelta(seconds=2)))
    session.commit()
    monkeypatch.setattr("eurogas_nexus.db.session.get_session_factory", lambda: _Factory(session))
    monkeypatch.setattr(streaming, "POLL_SECONDS", 0)
    monkeypatch.setattr(streaming, "LIVE_HEARTBEAT_SECONDS", 0)
    guard = StreamGuard("live", _principal("EEX"))

    async def drive():
        stream = _live_stream(("prices", "tariffs"), NOW, True, guard)
        chunks = [await stream.__anext__() for _ in range(4)]
        await stream.aclose()
        return chunks

    chunks = asyncio.run(drive())
    events = _events(chunks)
    assert events[0][0] == "ready"
    assert events[0][1]["topics"] == ["prices", "tariffs"]
    assert events[0][1]["resumed_from"] is not None
    # Two quotes in one poll: one notice (the burst is coalesced).
    assert events[1][0] == "change"
    assert events[1][1]["topic"] == "prices"
    assert events[1][1]["changed_at"].startswith("2026-11-26T09:00:02")
    # The earliest table cursor, then the outbox position.
    assert chunks[1].startswith("id: live|2026-11-26T09:00:00+00:00|c1-")
    assert events[2][0] == "heartbeat"
    # The next poll finds nothing new: only the heartbeat.
    assert events[3][0] == "heartbeat"


def test_the_live_stream_ends_when_the_caller_is_revoked(session, monkeypatch):
    monkeypatch.setattr("eurogas_nexus.db.session.get_session_factory", lambda: _Factory(session))
    monkeypatch.setattr(streaming, "POLL_SECONDS", 0)

    class Revoked:
        principal = _principal()

        def _still_authorised(self, _session):
            return False

    async def drive():
        return [chunk async for chunk in _live_stream(("prices",), NOW, False, Revoked())]

    events = _events(asyncio.run(drive()))
    assert [name for name, _ in events] == ["ready", "revoked"]


def test_the_endpoint_is_registered():
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app

    paths = TestClient(create_app()).app.openapi()["paths"]
    assert "/api/stream/live" in paths
