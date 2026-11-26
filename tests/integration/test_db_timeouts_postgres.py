"""The database timeouts on a real PostgreSQL (the demo's 5-second socket defect).

Runs when ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set (the PostgreSQL CI job). Proves that

(a) a statement longer than the old 5 s socket bound succeeds on a non-API engine;
(b) a statement past the API's statement timeout (set low here) is cancelled by the server,
    answered as the coded 503 ``runtime_db_timeout`` with ``Retry-After``, counted, and the
    pooled connection serves the next request;
(c) a host that accepts the connection but never answers still fails within the connect bound.
"""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest
from sqlalchemy import text

from eurogas_nexus.db import session as db_session

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="needs EUROGAS_NEXUS_TEST_POSTGRES_URL (the PostgreSQL CI job)",
)


@pytest.fixture(autouse=True)
def _role(monkeypatch):
    monkeypatch.setattr(db_session, "_API_PROCESS", False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS", raising=False)


def test_a_statement_longer_than_the_old_socket_bound_succeeds_on_a_worker_engine():
    engine = db_session.get_engine(_POSTGRES_URL, pool_size=1, max_overflow=0)
    try:
        started = time.monotonic()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT pg_sleep(6), 1")).one()[1] == 1
        assert time.monotonic() - started >= 6
    finally:
        engine.dispose()


def test_the_api_statement_timeout_is_the_servers_and_answers_the_coded_error(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.error_handlers import register_error_handlers
    from eurogas_nexus.api.middleware.database_failure import DatabaseFailureMiddleware

    # The API's own configuration path, with the limit set low for the test.
    monkeypatch.setattr(db_session, "_API_PROCESS", True)
    monkeypatch.setenv("EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS", "1000")
    engine = db_session.get_engine(_POSTGRES_URL, pool_size=1, max_overflow=0)
    factory = db_session.create_session_factory(engine)
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(DatabaseFailureMiddleware)

    @app.get("/slow")
    def slow():
        with factory() as session:
            session.execute(text("SELECT pg_sleep(3)"))
        return {"ok": True}

    @app.get("/quick")
    def quick():
        with factory() as session:
            return {"value": session.execute(text("SELECT 41 + 1")).scalar_one()}

    before = db_session.pool_counters().snapshot()
    client = TestClient(app, raise_server_exceptions=False)
    try:
        started = time.monotonic()
        response = client.get("/slow")
        elapsed = time.monotonic() - started
        assert response.status_code == 503, response.text
        body = response.json()
        assert body["error"] == "runtime_db_timeout" and body["recoverability"] == "retry"
        assert response.headers["retry-after"] == "5"
        assert 0.9 <= elapsed < 3, elapsed  # the server's 1 s limit, not the 3 s sleep
        # The one pooled connection was returned rolled back and serves the next request.
        again = client.get("/quick")
        assert again.status_code == 200 and again.json() == {"value": 42}
        assert engine.pool.checkedout() == 0
        after = db_session.pool_counters().snapshot()
        assert after["statement_timeouts"] == before["statement_timeouts"] + 1
        assert after["connections_lost"] == before["connections_lost"]
    finally:
        engine.dispose()


def test_a_host_that_never_answers_fails_within_the_connect_bound():
    # A listener that accepts (the kernel completes the handshake) and never speaks: the
    # driver waits for the server's first message, which never comes.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    held: list[socket.socket] = []
    stop = threading.Event()

    def accept() -> None:
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                held.append(listener.accept()[0])
            except OSError:
                continue

    thread = threading.Thread(target=accept, daemon=True)
    thread.start()
    engine = db_session.get_engine(
        f"postgresql+pg8000://nobody:nothing@127.0.0.1:{port}/none",
        connect_timeout_seconds=2,
        pool_pre_ping=False,
    )
    try:
        started = time.monotonic()
        with pytest.raises(Exception) as caught:  # noqa: PT011 - the driver's own error class
            engine.connect()
        elapsed = time.monotonic() - started
        assert 1.5 <= elapsed < 4, elapsed
        from eurogas_nexus.core.db_errors import database_failure

        assert database_failure(caught.value) == "unavailable"
    finally:
        engine.dispose()
        stop.set()
        thread.join(timeout=2)
        for connection in held:
            connection.close()
        listener.close()
