"""Streaming SSE endpoint tests (DB-free)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public.streaming import (
    _event_stream,
    _fetch_new_quotes,
    _sse,
)


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_sse_serialization_shape() -> None:
    payload = _sse({"a": 1}, event="quotes")
    assert payload == 'event: quotes\ndata: {"a": 1}\n\n'


def test_event_stream_emits_explicit_warning_when_db_unavailable() -> None:
    async def drive() -> str:
        generator = _event_stream("quotes", _fetch_new_quotes, "observed_at_utc")
        first = await generator.__anext__()
        await generator.aclose()
        return first

    first = asyncio.run(drive())
    assert "event: warning" in first
    assert "RUNTIME_POSTGRESQL_UNAVAILABLE" in first


def test_event_stream_yields_rows_from_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    rows = [
        {"quote_id": "q1", "observed_at_utc": None},
        {"quote_id": "q2", "observed_at_utc": None},
    ]

    def fetch(session, since):
        calls["n"] += 1
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
        generator = _event_stream("quotes", fetch, "observed_at_utc")
        events = [await generator.__anext__() for _ in range(2)]
        await generator.aclose()
        return events

    events = asyncio.run(drive())
    assert events[0].startswith("event: quotes")
    assert "q1" in events[0]
    assert events[1].startswith("event: quotes")
    assert "q2" in events[1]


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
