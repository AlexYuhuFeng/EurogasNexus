"""Streaming SSE endpoint tests (DB-free)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.streaming import (
    _event_stream,
    _fetch_new_quotes,
    _initial_cursor,
    _parse_cursor,
    _sse,
)

TS_1 = datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC)
TS_2 = datetime(2026, 7, 1, 10, 0, 1, tzinfo=UTC)


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_sse_serialization_shape() -> None:
    payload = _sse({"a": 1}, event="quotes")
    assert payload == 'event: quotes\ndata: {"a": 1}\n\n'


def test_sse_event_id_line_comes_first() -> None:
    payload = _sse({"a": 1}, event="quotes", event_id="2026-07-01T10:00:00+00:00|q1")
    assert payload == (
        "id: 2026-07-01T10:00:00+00:00|q1\n"
        "event: quotes\n"
        'data: {"a": 1}\n\n'
    )


def test_event_stream_emits_explicit_warning_when_db_unavailable() -> None:
    async def drive() -> str:
        generator = _event_stream(
            "quotes", _fetch_new_quotes, "observed_at_utc", "quote_id", None
        )
        first = await generator.__anext__()
        await generator.aclose()
        return first

    first = asyncio.run(drive())
    assert "event: warning" in first
    assert "RUNTIME_POSTGRESQL_UNAVAILABLE" in first


def test_event_stream_yields_rows_with_ids_and_advances_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}
    rows = [
        {"quote_id": "q1", "observed_at_utc": TS_1},
        {"quote_id": "q2", "observed_at_utc": TS_2},
    ]

    def fetch(session, cursor):
        calls["n"] += 1
        if cursor is not None:
            return []
        return rows if calls["n"] == 1 else []

    def fake_session_factory():
        def make_session() -> MagicMock:
            return MagicMock()

        return make_session

    monkeypatch.setattr(
        "eurogas_nexus.db.session.get_session_factory",
        fake_session_factory,
    )

    async def drive() -> list[str]:
        generator = _event_stream(
            "quotes", fetch, "observed_at_utc", "quote_id", None
        )
        events = [await generator.__anext__() for _ in range(2)]
        await generator.aclose()
        return events

    events = asyncio.run(drive())
    assert events[0].startswith("id: 2026-07-01T10:00:00+00:00|q1\nevent: quotes")
    assert "q1" in events[0]
    assert events[1].startswith("id: 2026-07-01T10:00:01+00:00|q2\nevent: quotes")
    assert "q2" in events[1]


def test_cursor_resumes_exactly_after_timestamp_and_pk() -> None:
    # Rows sharing one timestamp with more rows than a page must resume by pk.
    cursor = _parse_cursor("2026-07-01T10:00:00+00:00|q199")
    assert cursor == (TS_1, "q199")

    def fake_fetch(session, cursor):
        return [{"cursor": cursor}]

    assert fake_fetch(None, _parse_cursor("2026-07-01T10:00:00+00:00|q199")) == [
        {"cursor": (TS_1, "q199")}
    ]


def test_parse_cursor_rejects_malformed_values() -> None:
    assert _parse_cursor(None) is None
    assert _parse_cursor("") is None
    assert _parse_cursor("not-a-cursor") is None
    assert _parse_cursor("2026-07-01T10:00:00+00:00") is None


def test_parse_cursor_accepts_naive_timestamp_as_utc() -> None:
    cursor = _parse_cursor("2026-07-01T10:00:00|q1")
    assert cursor == (TS_1, "q1")


def test_new_stream_connection_starts_at_current_time() -> None:
    request = Request({"type": "http", "headers": []})
    before = datetime.now(UTC)

    cursor = _initial_cursor(request)

    after = datetime.now(UTC)
    assert cursor is not None
    assert before <= cursor[0] <= after
    assert cursor[1] == ""


def test_reconnecting_stream_preserves_last_event_cursor() -> None:
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"last-event-id", b"2026-07-01T10:00:00+00:00|q199"),
            ],
        }
    )

    assert _initial_cursor(request) == (TS_1, "q199")


def test_stream_routes_and_pipeline_health_are_registered() -> None:
    from apps.api.main import app

    paths = set(app.openapi()["paths"])
    for path in [
        "/api/stream/quotes",
        "/api/stream/opportunities",
        "/api/stream/alerts",
        "/api/runtime/pipeline-health",
    ]:
        assert path in paths, f"{path} not registered"


def _map_store():
    from sqlalchemy import create_engine

    from eurogas_nexus.db.base import Base

    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    return engine


def _principal(scopes: tuple[str, ...]):
    from eurogas_nexus.security.identity import AuthenticatedPrincipal

    return AuthenticatedPrincipal(
        principal_id="p1",
        name="trader",
        principal_type="USER",
        role="TRADER",
        status="ACTIVE",
        data_scopes=scopes,
    )


def test_the_map_stream_names_the_groups_that_changed_after_the_cursor() -> None:
    """One change per group (group and time, no row), ordered, after the cursor."""

    from datetime import timedelta

    from sqlalchemy.orm import Session

    from eurogas_nexus.api.routes.public.streaming import _fetch_map_changes
    from eurogas_nexus.db.models import RegasSlotRecord
    from eurogas_nexus.ingestion.lng_positions import parse_regas_slots

    engine = _map_store()
    now = datetime.now(UTC)
    csv = (
        "slot_id,terminal_name,window_start,window_end,send_out_gwh_d,cargo_id,book_id\n"
        f"S1,Gate terminal,{(now + timedelta(days=3)).isoformat()},"
        f"{(now + timedelta(days=8)).isoformat()},190,C1,\n"
    )
    with Session(engine) as session:
        for row in parse_regas_slots(csv, source_system="ETRM", source_reference="t", now_utc=now):
            session.add(RegasSlotRecord(**row))
        session.commit()
        (notice,) = _fetch_map_changes(session, (now - timedelta(minutes=1), ""))
        assert notice["group"] == "slots" and notice["visible"] is True
        assert _fetch_map_changes(session, (now + timedelta(minutes=1), "")) == []


def test_a_caller_without_the_scope_gets_no_notice_for_that_family(monkeypatch) -> None:
    """A notice must not reveal a change in data the caller may not read: a licensed vessel
    feed's cargo moves the cursor for everyone and is announced only to a caller holding it."""

    from datetime import timedelta

    from sqlalchemy.orm import Session

    import eurogas_nexus.security.portfolio_scope as portfolio_scope
    from eurogas_nexus.api.routes.public.streaming import _fetch_map_changes
    from eurogas_nexus.db.models import LngCargoRecord
    from eurogas_nexus.ingestion.lng_positions import parse_lng_cargoes

    monkeypatch.setattr(portfolio_scope, "isolation_enabled", lambda: True)
    engine = _map_store()
    now = datetime.now(UTC)
    csv = (
        "cargo_id,vessel_name,status,load_port,load_lat,load_lon,destination_terminal,"
        "eta,position_lat,position_lon,position_at,track,energy_gwh,book_id\n"
        f"M1,Market Voyager,laden,Hammerfest,70.68,23.6,Gate terminal,"
        f"{(now + timedelta(days=3)).isoformat()},62.0,4.5,{now.isoformat()},,950,\n"
    )
    with Session(engine) as session:
        for row in parse_lng_cargoes(csv, source_system="Kpler", source_reference="t", now_utc=now):
            session.add(LngCargoRecord(**row))
        session.commit()
        since = (now - timedelta(minutes=1), "")
        (withheld,) = _fetch_map_changes(session, since, _principal(("BOOKS:*",)))
        assert withheld["group"] == "cargoes" and withheld["visible"] is False
        assert withheld["cursor"] >= since[0]
        (held,) = _fetch_map_changes(session, since, _principal(("BOOKS:*", "Kpler")))
        assert held["visible"] is True


def test_withheld_changes_move_the_cursor_and_are_not_announced(monkeypatch) -> None:
    import eurogas_nexus.api.routes.public.streaming as streaming
    import eurogas_nexus.db.session as db_session

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(db_session, "get_session_factory", lambda: (lambda: session))
    monkeypatch.setattr(streaming, "POLL_SECONDS", 0)
    cursors = []
    from datetime import timedelta

    later = datetime.now(UTC) + timedelta(hours=1)

    def notices(_session, cursor, _principal):
        cursors.append(cursor)
        if len(cursors) == 1:
            return [{"group": "flows", "changed_at": later, "visible": False, "cursor": later}]
        return [{"group": "outages", "changed_at": TS_2, "visible": True, "cursor": TS_2}]

    async def drive() -> str:
        generator = _event_stream(
            "alerts",
            lambda _s, _c: [],
            "updated_at_utc",
            "alert_id",
            None,
            notices=(("map", notices),),
        )
        first = await generator.__anext__()
        await generator.aclose()
        return first

    first = asyncio.run(drive())
    # The withheld flows change was not announced; it moved the cursor the next poll used.
    assert '"group": "outages"' in first and "flows" not in first
    assert cursors[1][0] == later


def test_map_notices_ride_on_the_alerts_stream_without_an_id(monkeypatch) -> None:
    """A notice is an ``event: map`` with no ``id:`` (the alerts' resume point is untouched)."""

    import eurogas_nexus.db.session as db_session

    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(db_session, "get_session_factory", lambda: (lambda: session))

    def notices(_session, _cursor, _principal):
        return [{"group": "outages", "changed_at": TS_2, "visible": True, "cursor": TS_2}]

    async def drive() -> str:
        generator = _event_stream(
            "alerts",
            lambda _s, _c: [],
            "updated_at_utc",
            "alert_id",
            None,
            notices=(("map", notices),),
        )
        first = await generator.__anext__()
        await generator.aclose()
        return first

    first = asyncio.run(drive())
    assert first.startswith("event: map\n")
    assert '"group": "outages"' in first
