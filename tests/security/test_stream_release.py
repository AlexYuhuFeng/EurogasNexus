"""A live stream's place under the per-person cap is freed the moment its connection closes.

The demo crawl (one person, one browser tab, 32 pages) logged a 429 on a stream on 20 pages:
the client held several streams per tab and re-opened one on every page, and a closed stream's
place was released only by the server's cancellation (or, failing that, the garbage
collector). These run a real server over a socket: a closed connection frees its place at once,
a quiet stream sends a keepalive (so a server that only notices a disconnect on a failed write
notices it), and no error or failed send can keep a place.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from eurogas_nexus.api.stream_hub import StreamHub
from eurogas_nexus.core import shared_cache as cache_module
from eurogas_nexus.security import rate_limit

OWNER = "p-trader"


class _Quiet:
    """A stream state that never has anything to say (the hub delivers nothing)."""

    started = False

    def want(self, reads) -> None:
        return None

    def poll(self, reads):
        self.started = True
        return [], False


class _NoSession:
    def __call__(self):
        return self

    def __enter__(self):
        return object()

    def __exit__(self, *_):
        return False


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv(rate_limit.STREAM_LIMIT_ENV, "2")
    rate_limit._STREAMS.clear()
    cache_module.use_cache(cache_module.MemoryCache())
    yield
    cache_module.use_cache(None)
    rate_limit._STREAMS.clear()


@pytest.fixture
def server(monkeypatch):
    """A real uvicorn on a free port serving one counted stream fed by a real poller."""

    monkeypatch.setattr(rate_limit, "STREAM_KEEPALIVE_SECONDS", 0.2)
    monkeypatch.setattr("eurogas_nexus.application.live_topics.Reads", lambda session: object())
    hub = StreamHub(interval=lambda: 0.05, session_factory=lambda: _NoSession(), warning=str)
    app = FastAPI()

    @app.get("/stream")
    async def stream():
        async def events():
            yield ": hello\n\n"
            async for chunk in hub.stream(_Quiet()):
                yield chunk

        return rate_limit.CountedStreamingResponse(rate_limit.open_counted_stream(OWNER, events()))

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not srv.started and time.monotonic() < deadline:
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}/stream", hub
    srv.should_exit = True
    thread.join(timeout=10)


def _settled(predicate, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_twenty_streams_opened_and_closed_in_turn_are_never_refused(server):
    url, hub = server
    statuses = []
    for _ in range(20):
        with httpx.Client(timeout=5) as client, client.stream("GET", url) as response:
            statuses.append(response.status_code)
            chunks = response.iter_raw()  # kept: a dropped iterator closes the connection
            next(chunks)
            assert rate_limit.open_streams(OWNER) == 1  # open and counted
    assert statuses == [200] * 20
    assert _settled(lambda: rate_limit.open_streams(OWNER) == 0)
    assert _settled(lambda: hub.open_streams() == 0)  # left the poller too


def test_a_third_stream_at_once_is_refused_with_the_coded_429(server):
    url, _hub = server
    with httpx.Client(timeout=5) as first, httpx.Client(timeout=5) as second:
        with first.stream("GET", url) as one, second.stream("GET", url) as two:
            held = [one.iter_raw(), two.iter_raw()]
            for chunks in held:
                next(chunks)
            assert rate_limit.open_streams(OWNER) == 2
            refused = httpx.get(url, timeout=5)
            assert refused.status_code == 429
            assert refused.headers["retry-after"] == "30"
            detail = refused.json()["detail"]
            assert detail["code"] == "rate_limited"
            assert detail["reason"] == "stream_limit_reached"
    # Both closed: the place is back at once.
    assert _settled(lambda: rate_limit.open_streams(OWNER) == 0)
    with httpx.Client(timeout=5) as again, again.stream("GET", url) as response:
        assert response.status_code == 200


def test_a_quiet_stream_sends_a_keepalive(server):
    url, _hub = server
    with httpx.Client(timeout=5) as client, client.stream("GET", url) as response:
        chunks = response.iter_text()
        seen = ""
        while rate_limit.KEEPALIVE_COMMENT not in seen:
            seen += next(chunks)
    assert _settled(lambda: rate_limit.open_streams(OWNER) == 0)


async def _quiet_forever():
    yield "event: one\ndata: {}\n\n"
    await asyncio.Event().wait()
    yield "never"


def test_a_failed_send_frees_the_place_at_once(monkeypatch):
    """A server that reports a disconnect only through a failed write (ASGI 2.4): the response
    closes its stream on the way out, without waiting for the garbage collector."""

    monkeypatch.setattr(rate_limit, "STREAM_KEEPALIVE_SECONDS", 0.05)
    response = rate_limit.CountedStreamingResponse(
        rate_limit.open_counted_stream(OWNER, _quiet_forever())
    )
    sent: list[dict] = []

    async def send(message):
        sent.append(message)
        if len(sent) > 2:
            raise OSError("the client went away")

    async def receive():
        await asyncio.Event().wait()

    scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    assert rate_limit.open_streams(OWNER) == 1
    with pytest.raises(Exception):  # noqa: B017 - ClientDisconnect, whichever class
        asyncio.run(response(scope, receive, send))
    assert rate_limit.open_streams(OWNER) == 0


def test_an_error_in_the_stream_frees_the_place():
    async def failing():
        yield "event: one\ndata: {}\n\n"
        raise RuntimeError("the store went away")

    stream = rate_limit.open_counted_stream(OWNER, failing())

    async def drain():
        return [chunk async for chunk in stream]

    with pytest.raises(RuntimeError):
        asyncio.run(drain())
    assert rate_limit.open_streams(OWNER) == 0


def test_a_cancelled_read_frees_the_place_and_ends_the_wrapped_stream():
    ended = asyncio.Event()

    async def watched():
        try:
            yield "event: one\ndata: {}\n\n"
            await asyncio.Event().wait()
        finally:
            ended.set()

    stream = rate_limit.open_counted_stream(OWNER, watched())

    async def drive():
        await stream.__anext__()
        reader = asyncio.ensure_future(stream.__anext__())
        await asyncio.sleep(0.01)
        reader.cancel()  # what the server does when the client disconnects
        with pytest.raises(asyncio.CancelledError):
            await reader
        assert rate_limit.open_streams(OWNER) == 0  # at once, before any clean-up ran
        await asyncio.wait_for(ended.wait(), timeout=2)

    asyncio.run(drive())
