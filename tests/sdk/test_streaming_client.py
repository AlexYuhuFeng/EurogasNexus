"""SDK streaming client tests (P2 SSE resume)."""

import httpx

from eurogas_nexus.sdk.streaming import iter_sse, stream_events

SSE_TEXT = (
    "id: 2026-07-01T10:00:00+00:00|q1\n"
    "event: quotes\n"
    'data: {"quote_id": "q1", "price": 31.4}\n'
    "\n"
    ": heartbeat\n"
    "id: 2026-07-01T10:00:01+00:00|q2\n"
    "event: quotes\n"
    'data: {"quote_id": "q2", "price": 31.5}\n'
    'data: {"extra": true}\n'
    "\n"
)


def test_iter_sse_parses_events_with_ids() -> None:
    events = list(iter_sse(SSE_TEXT.splitlines(keepends=True)))

    assert len(events) == 2
    assert events[0]["event"] == "quotes"
    assert events[0]["id"] == "2026-07-01T10:00:00+00:00|q1"
    assert events[0]["data"] == '{"quote_id": "q1", "price": 31.4}'
    assert events[1]["id"] == "2026-07-01T10:00:01+00:00|q2"
    assert events[1]["data"].startswith('{"quote_id": "q2"')


def test_iter_sse_joins_multi_line_data_and_drops_comments() -> None:
    events = list(iter_sse(SSE_TEXT.splitlines(keepends=True)))
    assert "\n" in events[1]["data"]
    assert not any("heartbeat" in str(event) for event in events)


def test_iter_sse_defaults_event_name() -> None:
    events = list(iter_sse(["data: x\n", "\n"]))
    assert events[0]["event"] == "message"
    assert events[0]["id"] is None


def test_stream_events_sends_last_event_id_and_parses_json(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            return iter(
                [
                    "id: 2026-07-01T10:00:00+00:00|q1",
                    "event: quotes",
                    'data: {"quote_id": "q1"}',
                    "",
                ]
            )

    def fake_stream(method, url, *, headers, timeout):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(httpx, "stream", fake_stream)

    events = list(
        stream_events(
            "http://example.test",
            "stream/quotes",
            last_event_id="2026-07-01T09:59:00+00:00|q0",
        )
    )

    assert captured["method"] == "GET"
    assert captured["url"] == "http://example.test/api/stream/quotes"
    assert captured["headers"]["Last-Event-ID"] == "2026-07-01T09:59:00+00:00|q0"
    assert events[0]["data"] == {"quote_id": "q1"}
