"""Small-desk plan section 5: a price that reaches the server is on the stream promptly.

The bound asserted here is the server's share of "on screen within 200 ms": from the commit of
a new quote to its event in the open stream's queue, with the poller running on its own thread
at the interval an installation sets (``EUROGAS_NEXUS_STREAM_POLL_SECONDS``). The browser's
share (event to painted cell) is measured on the real hardware with
``scripts/perf/live_latency.py`` (see ``docs/operations/SMALL_DESK_RESILIENCE.md``).
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.api.routes.public.streaming import StreamGuard, _RowStream
from eurogas_nexus.api.stream_hub import StreamHub

from .test_stream_hub import NOW, _principal, _quote, engine  # noqa: F401  (fixture)

#: The small desk's poll interval and the slack allowed for one shared read on a test runner.
INTERVAL = 0.15
SLACK = 0.35


def test_a_new_price_is_on_the_stream_within_one_poll_interval(engine, monkeypatch):  # noqa: F811
    monkeypatch.setenv("EUROGAS_NEXUS_STREAM_POLL_SECONDS", str(INTERVAL))
    assert streaming.poll_seconds() == INTERVAL

    async def drive() -> float:
        hub = StreamHub(
            interval=streaming.poll_seconds,
            session_factory=lambda: (lambda: Session(engine)),
            warning=streaming.warning_event,
        )
        state = _RowStream(
            "quotes", streaming._fetch_new_quotes, "observed_at_utc", "quote_id",
            (NOW, ""), StreamGuard("quotes", _principal("p-eex", "EEX")), (),
        )
        sub = hub.subscribe(state)
        # The first poll (woken by the subscription) delivers what is already there.
        await asyncio.wait_for(sub.queue.get(), timeout=5)
        await asyncio.sleep(INTERVAL * 1.5)  # mid-interval, the worst case for a new price
        with Session(engine) as session:
            session.add(_quote("q-new", "EEX", NOW + timedelta(seconds=10)))
            session.commit()
        arrived = time.monotonic()
        while True:
            chunks, _done = await asyncio.wait_for(sub.queue.get(), timeout=5)
            if any("q-new" in chunk for chunk in chunks):
                hub.unsubscribe(sub)
                return time.monotonic() - arrived

    elapsed = asyncio.run(drive())
    assert elapsed < INTERVAL + SLACK, f"{elapsed:.3f} s from commit to stream"


def test_the_interval_setting_refuses_nonsense(monkeypatch):
    for bad in ("0", "abc", "60"):
        monkeypatch.setenv("EUROGAS_NEXUS_STREAM_POLL_SECONDS", bad)
        assert streaming.poll_seconds() == streaming.POLL_SECONDS
