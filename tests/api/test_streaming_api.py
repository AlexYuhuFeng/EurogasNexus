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
