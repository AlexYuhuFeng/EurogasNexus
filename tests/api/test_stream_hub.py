"""The process's one live-update poller: shared reads, per-connection entitlement, off the loop."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.api.routes.public.streaming import StreamGuard, _LiveStream, _RowStream
from eurogas_nexus.api.stream_hub import StreamHub, StreamLimitReached
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketQuoteRecord
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime.now(UTC).replace(microsecond=0)


def _principal(principal_id: str, *scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=principal_id,
        name=principal_id,
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("ANALYST",),
    )


def _quote(quote_id: str, source: str, at: datetime) -> MarketQuoteRecord:
    values = {"quote_id": quote_id, "source_system": source, "observed_at_utc": at}
    for column in MarketQuoteRecord.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        kind = column.type
        values[column.name] = (
            at
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
    return MarketQuoteRecord(**values)


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_quote("q-eex", "EEX", NOW + timedelta(seconds=1)))
        session.add(_quote("q-ice", "ICE_ENDEX", NOW + timedelta(seconds=2)))
        session.commit()
    return engine


class _Counter:
    """Counts the statements that read the quotes table, and the threads that ran them."""

    def __init__(self, engine) -> None:
        self.quote_reads = 0
        self.threads: set[int] = set()
        event.listen(engine, "before_cursor_execute", self._seen)

    def _seen(self, _conn, _cursor, statement, *_args) -> None:
        self.threads.add(threading.get_ident())
        if "FROM market_quotes" in statement:
            self.quote_reads += 1


def _hub(engine) -> StreamHub:
    return StreamHub(
        interval=lambda: 3600.0,
        session_factory=lambda: (lambda: Session(engine)),
        warning=streaming.warning_event,
        refused=streaming.refused_event,
        autostart=False,  # the test runs each poll itself
    )


def _drain(sub) -> list[str]:
    out: list[str] = []
    while not sub.queue.empty():
        chunks, _done = sub.queue.get_nowait()
        out.extend(chunks)
    return out


def test_one_read_serves_every_stream_and_each_gets_only_what_its_caller_may_see(engine):
    """Fan-out keeps entitlement per connection: the quotes are read once per poll for all
    streams, and each connection receives only the rows its own caller is licensed for."""

    counter = _Counter(engine)
    since = (NOW, "")

    async def drive():
        hub = _hub(engine)
        callers = [_principal(f"p-eex-{n}", "EEX") for n in range(5)]
        callers += [_principal(f"p-ice-{n}", "ICE_ENDEX") for n in range(5)]
        subs = []
        for caller in callers:
            state = _RowStream(
                "quotes",
                streaming._fetch_new_quotes,
                "observed_at_utc",
                "quote_id",
                since,
                StreamGuard("quotes", caller),
                (),
            )
            subs.append(hub.subscribe(state, caller.principal_id))
        hub.poll(subs)
        await asyncio.sleep(0)  # the poller hands batches over through the loop
        return [(sub.principal_id, _drain(sub)) for sub in subs]

    received = asyncio.run(drive())
    assert counter.quote_reads == 1
    for principal_id, chunks in received:
        sent = "".join(chunks)
        if principal_id.startswith("p-eex"):
            assert "q-eex" in sent and "q-ice" not in sent
        else:
            assert "q-ice" in sent and "q-eex" not in sent


def test_live_notices_fan_out_by_licence_with_reads_independent_of_the_stream_count(engine):
    def reads_for(count: int) -> tuple[int, list[str]]:
        counter = _Counter(engine)

        async def drive():
            hub = _hub(engine)
            subs = []
            for n in range(count):
                licence = "EEX" if n % 2 == 0 else "NONE"
                guard = StreamGuard("live", _principal(f"p{n}", licence))
                state = _LiveStream(("prices",), NOW, True, guard, None)
                subs.append(hub.subscribe(state, f"p{n}"))
            hub.poll(subs)
            await asyncio.sleep(0)
            return ["".join(_drain(sub)) for sub in subs]

        sent = asyncio.run(drive())
        return counter.quote_reads, sent

    few_reads, few = reads_for(2)
    many_reads, many = reads_for(12)
    assert few_reads == many_reads == 1
    for n, sent in enumerate(many):
        assert "event: ready" in sent
        # Licensed callers hear of the EEX quote; an unlicensed one hears nothing.
        assert ("event: change" in sent) is (n % 2 == 0)


def test_the_poller_reads_off_the_event_loop_thread(engine, monkeypatch):
    counter = _Counter(engine)
    monkeypatch.setattr(
        "eurogas_nexus.db.session.get_session_factory", lambda: (lambda: Session(engine))
    )

    async def drive():
        loop_thread = threading.get_ident()
        stream = streaming._event_stream(
            "quotes",
            streaming._fetch_new_quotes,
            "observed_at_utc",
            "quote_id",
            (NOW, ""),
            guard=StreamGuard("quotes", _principal("p-loop", "EEX")),
        )
        first = await asyncio.wait_for(stream.__anext__(), timeout=5)
        await stream.aclose()
        return loop_thread, first

    loop_thread, first = asyncio.run(drive())
    assert "q-eex" in first
    assert counter.threads and loop_thread not in counter.threads


def test_a_caller_past_the_stream_cap_is_refused(engine, monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_STREAMS_PER_PRINCIPAL", "2")

    async def drive():
        hub = _hub(engine)
        state = lambda: _LiveStream(("prices",), NOW, False, None, None)  # noqa: E731
        first = hub.subscribe(state(), "p-many")
        hub.subscribe(state(), "p-many")
        with pytest.raises(StreamLimitReached):
            hub.subscribe(state(), "p-many")
        hub.subscribe(state(), "p-other")
        hub.unsubscribe(first)
        hub.subscribe(state(), "p-many")  # a closed tab frees its place
        return hub.streams_of("p-many"), hub.stats.refused_over_cap

    assert asyncio.run(drive()) == (2, 1)


def _counter_value(name: str) -> float:
    from eurogas_nexus.application import process_metrics

    for line in process_metrics.render().splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    return 0.0


def test_a_failed_poll_is_logged_as_json_and_counted(engine):
    """The store unreachable: the poller's error reaches the JSON log (once, not every 1.5 s)
    and the poll and failure counters the scrape sums over processes."""

    import json
    import logging

    from eurogas_nexus.core.structured_logging import JsonFormatter

    def unreachable():
        raise ConnectionError("could not connect to the store")

    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(JsonFormatter("eurogas-nexus-api"))
    hub_logger = logging.getLogger("eurogas_nexus.api.stream_hub")
    hub_logger.addHandler(handler)
    polls_before = _counter_value("eurogas_stream_polls_total")
    failures_before = _counter_value("eurogas_stream_poll_failures_total")
    try:

        async def drive():
            hub = StreamHub(
                interval=lambda: 3600.0,
                session_factory=lambda: unreachable,
                warning=streaming.warning_event,
                autostart=False,
            )
            sub = hub.subscribe(_LiveStream(("prices",), NOW, False, None, None), "p-log")
            hub.poll([sub])
            hub.poll([sub])
            await asyncio.sleep(0)
            return hub.stats.failed_polls, _drain(sub)

        failed, delivered = asyncio.run(drive())
    finally:
        hub_logger.removeHandler(handler)
    assert failed == 2
    assert delivered  # the stream got the warning event instead of silence
    errors = [json.loads(line) for line in records]
    assert len(errors) == 1
    assert errors[0]["level"] == "error"
    assert errors[0]["logger"] == "eurogas_nexus.api.stream_hub"
    assert errors[0]["error_type"] == "ConnectionError"
    assert "could not reach the store" in errors[0]["message"]
    assert _counter_value("eurogas_stream_polls_total") == polls_before + 2
    assert _counter_value("eurogas_stream_poll_failures_total") == failures_before + 2


def test_a_read_the_stream_recovers_from_is_still_logged_once(tmp_path):
    """The usual outage: the session opens, the stream's own read fails and the stream answers
    with a warning event. The poller logs it (with the database error) and counts the poll."""

    import json
    import logging

    from eurogas_nexus.core.structured_logging import JsonFormatter

    gone = create_engine(f"sqlite:///{tmp_path / 'missing' / 'store.db'}")  # cannot open
    records: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(JsonFormatter("eurogas-nexus-api"))
    hub_logger = logging.getLogger("eurogas_nexus.api.stream_hub")
    hub_logger.addHandler(handler)
    try:

        async def drive():
            hub = _hub(gone)
            sub = hub.subscribe(
                _RowStream(
                    "quotes",
                    streaming._fetch_new_quotes,
                    "observed_at_utc",
                    "quote_id",
                    (NOW, ""),
                    StreamGuard("quotes", _principal("p-gone", "EEX")),
                    (),
                ),
                "p-gone",
            )
            hub.poll([sub])
            hub.poll([sub])
            await asyncio.sleep(0)
            return hub.stats.failed_polls, _drain(sub)

        failed, delivered = asyncio.run(drive())
    finally:
        hub_logger.removeHandler(handler)
        gone.dispose()
    assert failed == 2
    assert any("RUNTIME_POSTGRESQL_UNAVAILABLE" in chunk for chunk in delivered)
    [error] = [json.loads(line) for line in records]
    assert error["level"] == "error" and error["error_type"] == "OperationalError"
    assert "stack" in error
