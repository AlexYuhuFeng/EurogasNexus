"""Pool sizing per process, the API's statement timeout and the pool-exhaustion counters."""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import create_engine, text

from eurogas_nexus.db import session as db_session


def test_request_threads_follow_the_pool_less_the_background_connections():
    env = {"EUROGAS_NEXUS_DB_POOL_SIZE": "8", "EUROGAS_NEXUS_DB_MAX_OVERFLOW": "4"}
    assert db_session.api_thread_limit(env) == 8 + 4 - db_session.API_BACKGROUND_CONNECTIONS
    assert db_session.api_thread_limit({**env, "EUROGAS_NEXUS_API_THREADS": "20"}) == 20
    assert db_session.api_thread_limit({"EUROGAS_NEXUS_DB_POOL_SIZE": "1"}) >= 4


def test_the_statement_timeout_is_the_apis_only(monkeypatch):
    monkeypatch.setattr(db_session, "_API_PROCESS", False)
    # A worker reading the same environment file gets no limit.
    assert db_session.statement_timeout_ms({"EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS": "500"}) is None
    db_session.use_api_statement_timeout()
    assert db_session.statement_timeout_ms({}) == db_session.API_STATEMENT_TIMEOUT_MS
    assert db_session.statement_timeout_ms({"EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS": "500"}) == 500
    assert db_session.statement_timeout_ms({"EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS": "0"}) is None


def test_the_pool_counts_waits_and_timeouts_when_it_is_exhausted(tmp_path, monkeypatch):
    counters = db_session.PoolCounters()
    monkeypatch.setattr(db_session, "_POOL_COUNTERS", counters)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'pool.db'}",
        poolclass=db_session.CountingQueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.2,
    )
    held = engine.connect()
    held.execute(text("select 1"))
    from sqlalchemy.exc import TimeoutError as PoolTimeout

    with pytest.raises(PoolTimeout):
        engine.connect()
    released = threading.Timer(0.1, held.close)
    released.start()
    with engine.connect() as connection:  # waits for the one connection to come back
        connection.execute(text("select 1"))
    snapshot = counters.snapshot()
    assert snapshot["timeouts"] == 1
    assert snapshot["checkouts"] == 2
    assert snapshot["waits"] >= 2  # the timed-out checkout and the one that waited
    assert snapshot["wait_seconds"] >= 0.25
    engine.dispose()


def test_the_metrics_publish_the_pool_and_poller_counters():
    from eurogas_nexus.application.dataops_observability import _serving_metric_lines

    names = {line.split()[0] for line in _serving_metric_lines() if not line.startswith("#")}
    assert {
        "eurogas_db_pool_checkouts_total",
        "eurogas_db_pool_waits_total",
        "eurogas_db_pool_timeouts_total",
        "eurogas_db_pool_wait_seconds_total",
    } <= names


def test_credential_checks_do_not_wait_behind_busy_request_threads():
    """Every request thread busy with a long computation: a sign-in, a session check or a
    stream's opening still gets its credential checked at once, on the identity threads."""

    import asyncio
    import time

    import anyio.to_thread

    from eurogas_nexus.api.dependencies import identity

    async def scenario() -> float:
        anyio.to_thread.current_default_thread_limiter().total_tokens = 1
        release = threading.Event()
        busy = asyncio.ensure_future(anyio.to_thread.run_sync(release.wait))
        await asyncio.sleep(0.05)  # the one request thread is now taken
        started = time.monotonic()
        assert await identity.run_in_threadpool(lambda value: value * 2, 21) == 42
        waited = time.monotonic() - started
        release.set()
        await busy
        return waited

    assert asyncio.run(scenario()) < 1.0
