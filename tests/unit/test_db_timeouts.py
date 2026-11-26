"""The database timeouts, one meaning each (db/session.py, core/db_errors.py).

Before the fix, ``get_engine`` passed its 5 s connect bound to pg8000 as ``timeout``, which
pg8000 keeps on the socket for every read: every statement longer than 5 s failed on the
client while the server went on running it. Connecting keeps the short bound; after the
connection is made the socket's timeout is only a safety net above the statement timeout, and
a statement the server cancels answers the coded 503 with a retry hint.
"""

from __future__ import annotations

import socket

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool

from eurogas_nexus.core import db_errors
from eurogas_nexus.db import session as db_session

URL = "postgresql+pg8000://user:secret@127.0.0.1:1/none"


class _Socket:
    def __init__(self) -> None:
        self.timeout = 5.0
        self.options: dict[tuple[int, int], int] = {}

    def settimeout(self, value) -> None:
        self.timeout = value

    def setsockopt(self, level, option, value) -> None:
        self.options[(level, option)] = value


class _Pg8000Connection:
    def __init__(self) -> None:
        self._usock = _Socket()


def _tune(engine) -> _Socket:
    connection = _Pg8000Connection()
    for listener in engine.pool.dispatch.connect:
        if "_tune_socket" in getattr(listener, "__qualname__", ""):
            listener(connection, None)
    return connection._usock


@pytest.fixture(autouse=True)
def _not_the_api(monkeypatch):
    monkeypatch.setattr(db_session, "_API_PROCESS", False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS", raising=False)


def test_pg8000_gets_the_connect_bound_and_keepalives_only():
    assert db_session.driver_connect_args("postgresql+pg8000", 5) == {
        "timeout": 5,
        "tcp_keepalive": True,
    }
    libpq = db_session.driver_connect_args("postgresql+psycopg", 5)
    assert libpq["connect_timeout"] == 5 and libpq["keepalives"] == 1


def test_a_worker_connection_has_no_socket_cut_off_after_connecting():
    sock = _tune(db_session.get_engine(URL))
    assert sock.timeout is None  # statements bounded by the server (none for workers)
    assert sock.options[(socket.SOL_SOCKET, socket.SO_KEEPALIVE)] == 1
    if hasattr(socket, "TCP_KEEPIDLE"):
        assert sock.options[(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE)] == 30


def test_an_api_connection_waits_past_its_statement_timeout(monkeypatch):
    monkeypatch.setattr(db_session, "_API_PROCESS", True)
    sock = _tune(db_session.get_engine(URL))
    assert sock.timeout == 30 + db_session.SOCKET_TIMEOUT_MARGIN_SECONDS
    monkeypatch.setenv("EUROGAS_NEXUS_DB_STATEMENT_TIMEOUT_MS", "2000")
    assert _tune(db_session.get_engine(URL)).timeout == 2 + db_session.SOCKET_TIMEOUT_MARGIN_SECONDS


def test_explicit_timeouts_and_a_one_off_engine():
    engine = db_session.get_engine(URL, statement_timeout=None, socket_timeout_seconds=90.0)
    assert _tune(engine).timeout == 90.0
    one_off = db_session.get_engine(URL, one_off=True, statement_timeout=None)
    assert isinstance(one_off.pool, NullPool)
    assert _tune(one_off).timeout is None


def test_the_socket_timeout_follows_the_statement_timeout():
    assert db_session.socket_timeout_for(None) is None
    assert db_session.socket_timeout_for(0) is None
    assert db_session.socket_timeout_for(30_000) == 30 + db_session.SOCKET_TIMEOUT_MARGIN_SECONDS


class _Pg8000Error(Exception):
    """Shaped as pg8000 raises it: the server's fields in args[0]."""


_Pg8000Error.__module__ = "pg8000.exceptions"


class _SqlAlchemyError(Exception):
    def __init__(self, orig) -> None:
        super().__init__("wrapped")
        self.orig = orig


_SqlAlchemyError.__module__ = "sqlalchemy.exc"


def _cancelled() -> Exception:
    return _SqlAlchemyError(
        _Pg8000Error({"C": "57014", "M": "canceling statement due to statement timeout"})
    )


def test_a_cancelled_statement_and_a_lost_store_are_told_apart():
    assert db_errors.sqlstate(_cancelled()) == "57014"
    assert db_errors.database_failure(_cancelled()) == "timeout"
    lock = _SqlAlchemyError(_Pg8000Error({"C": "55P03"}))
    assert db_errors.database_failure(lock) == "timeout"
    lost = _SqlAlchemyError(_Pg8000Error({"C": "08006"}))
    lost.connection_invalidated = True
    assert db_errors.database_failure(lost) == "unavailable"
    wrapped_socket = _SqlAlchemyError(TimeoutError("timed out"))
    assert db_errors.database_failure(wrapped_socket) == "unavailable"
    # Another client's network error is not the store being unavailable.
    assert db_errors.database_failure(TimeoutError("provider")) is None
    assert db_errors.database_failure(ValueError("x")) is None


def test_pool_counters_count_cancelled_statements_and_lost_connections():
    counters = db_session.PoolCounters()
    counters.record_failure(statement_timeout=True, connection_lost=False)
    counters.record_failure(statement_timeout=False, connection_lost=True)
    snapshot = counters.snapshot()
    assert snapshot["statement_timeouts"] == 1 and snapshot["connections_lost"] == 1


def _app() -> FastAPI:
    from eurogas_nexus.api.error_handlers import register_error_handlers
    from eurogas_nexus.api.middleware.database_failure import DatabaseFailureMiddleware

    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(DatabaseFailureMiddleware)

    @app.get("/uncaught")
    def uncaught():
        raise _cancelled()

    @app.get("/caught")
    def caught():
        try:
            raise _cancelled()
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail={"code": "runtime_db_unavailable"}
            ) from exc

    @app.get("/lost")
    def lost():
        raise _SqlAlchemyError(ConnectionResetError("reset"))

    @app.get("/bug")
    def bug():
        raise ValueError("a programming error")

    return app


def test_the_api_answers_a_cancelled_statement_with_the_coded_503():
    client = TestClient(_app(), raise_server_exceptions=False)
    for path in ("/uncaught", "/caught"):
        response = client.get(path)
        assert response.status_code == 503, path
        body = response.json()
        assert body["error"] == "runtime_db_timeout", path
        assert body["recoverability"] == "retry" and body["family"] == "DEPENDENCY"
        assert response.headers["retry-after"] == str(db_errors.DB_RETRY_AFTER_SECONDS)
    lost = client.get("/lost")
    assert lost.status_code == 503 and lost.json()["error"] == "runtime_db_unavailable"
    assert client.get("/bug").status_code == 500
