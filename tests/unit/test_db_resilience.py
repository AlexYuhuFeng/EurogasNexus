"""Behaviour during a database failover, without a database (db/resilience.py).

The same rules against a PostgreSQL that is really stopped and started are in
tests/integration/test_db_failover_resilience_postgres.py.
"""

from __future__ import annotations

import random

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import exc as sa_exc

from eurogas_nexus.api.error_handlers import register_error_handlers
from eurogas_nexus.db.resilience import (
    CommitOutcomeUnknown,
    backoff_delays,
    failover_hosts,
    is_connection_error,
    is_read_only_error,
    startup_wait_seconds,
    wait_for_database,
    wait_for_database_at_startup,
)


def _pg_error(cls_name: str, sqlstate: str | None, message: str = "boom"):
    import pg8000.dbapi as dbapi

    original = getattr(dbapi, cls_name)({"C": sqlstate, "M": message} if sqlstate else message)
    wrapper = {
        "InterfaceError": sa_exc.InterfaceError,
        "OperationalError": sa_exc.OperationalError,
        "ProgrammingError": sa_exc.ProgrammingError,
        "DatabaseError": sa_exc.DatabaseError,
    }[cls_name]
    return wrapper("SELECT 1", {}, original)


def test_connection_failures_are_recognised_and_data_errors_are_not() -> None:
    assert is_connection_error(_pg_error("InterfaceError", None, "network error"))
    assert is_connection_error(_pg_error("OperationalError", None, "no writable primary: a"))
    assert is_connection_error(_pg_error("DatabaseError", "57P01", "terminating connection"))
    assert is_connection_error(ConnectionRefusedError())
    assert is_connection_error(CommitOutcomeUnknown("x").with_traceback(None)) is False
    assert not is_connection_error(_pg_error("ProgrammingError", "42P01", "no such table"))
    assert not is_connection_error(_pg_error("DatabaseError", "23505", "duplicate key"))
    assert not is_connection_error(ValueError("bad input"))
    assert is_read_only_error(_pg_error("DatabaseError", "25006", "read-only transaction"))


def test_backoff_grows_to_its_cap_with_bounded_jitter() -> None:
    delays = backoff_delays(initial=0.5, maximum=8.0, jitter=0.2, rng=random.Random(7))
    values = [next(delays) for _ in range(8)]
    assert 0.4 <= values[0] <= 0.6
    assert 0.8 <= values[1] <= 1.2
    assert all(value <= 8.0 for value in values)
    assert values[-1] >= 6.4


def test_wait_retries_a_lost_database_until_it_answers() -> None:
    calls = {"probe": 0}
    clock = {"now": 0.0}

    def probe():
        calls["probe"] += 1
        if calls["probe"] < 4:
            raise ConnectionRefusedError()

    def sleep(seconds):
        clock["now"] += seconds

    retries = []
    result = wait_for_database(
        timeout_seconds=60,
        probe=probe,
        sleep=sleep,
        clock=lambda: clock["now"],
        delays=iter([1.0, 2.0, 4.0]),
        on_retry=lambda attempt, error, delay: retries.append((attempt, error, delay)),
    )
    assert result.ok and result.attempts == 4 and result.waited_seconds == 7.0
    assert [r[0] for r in retries] == [1, 2, 3]
    assert retries[0][1] == "ConnectionRefusedError"


def test_wait_gives_up_at_its_deadline_and_does_not_hide_other_errors() -> None:
    clock = {"now": 0.0}

    def sleep(seconds):
        clock["now"] += seconds

    def down():
        raise ConnectionRefusedError()

    result = wait_for_database(
        timeout_seconds=5, probe=down, sleep=sleep, clock=lambda: clock["now"],
        delays=iter([2.0] * 10),
    )
    assert not result.ok and result.last_error == "ConnectionRefusedError"
    assert result.waited_seconds == 5.0

    def broken():
        raise _pg_error("ProgrammingError", "28P01", "password authentication failed")

    with pytest.raises(sa_exc.ProgrammingError):
        wait_for_database(timeout_seconds=5, probe=broken, sleep=sleep)


def test_startup_wait_is_off_unless_configured() -> None:
    assert startup_wait_seconds({}) == 0.0
    assert startup_wait_seconds({"EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS": "60"}) == 60.0
    assert startup_wait_seconds({"EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS": "x"}) == 0.0
    assert wait_for_database_at_startup(component="t", environ={"DATABASE_URL": "x"}) is None
    lines = []
    result = wait_for_database_at_startup(
        component="worker",
        environ={"DATABASE_URL": "postgresql://h/db", "EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS": "1"},
        emit=lines.append,
        probe=lambda: None,
    )
    assert result.ok and '"db.startup.ready"' in lines[-1]


def test_failover_hosts_setting() -> None:
    assert failover_hosts({}) == []
    assert failover_hosts(
        {"EUROGAS_NEXUS_DB_FAILOVER_HOSTS": "pg-node2:5432, pg-node3"}
    ) == [("pg-node2", 5432), ("pg-node3", 5432)]
    with pytest.raises(ValueError):
        failover_hosts({"EUROGAS_NEXUS_DB_FAILOVER_HOSTS": "pg-node2:abc"})


def _app_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/write")
    def write():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_a_lost_database_answers_503_retry_not_500() -> None:
    response = _app_raising(_pg_error("InterfaceError", None, "network error")).post("/write")
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "runtime_db_unavailable"
    assert body["recoverability"] == "retry"
    assert "nothing was saved" in body["detail"]["message"]
    assert response.headers["Retry-After"] == "5"


def test_an_interrupted_commit_says_the_outcome_is_unknown() -> None:
    response = _app_raising(CommitOutcomeUnknown("lost during COMMIT")).post("/write")
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "runtime_db_commit_unconfirmed"
    assert body["recoverability"] == "after_user_action"
    assert "may or may not have been saved" in body["detail"]["message"]


def test_other_faults_stay_500() -> None:
    response = _app_raising(_pg_error("DatabaseError", "23505", "duplicate")).post("/write")
    assert response.status_code == 500
    assert response.json()["error"] == "internal"


def test_a_commit_that_loses_its_connection_raises_commit_outcome_unknown(tmp_path) -> None:
    from sqlalchemy import Column, Integer, MetaData, Table, event

    from eurogas_nexus.db.session import create_session_factory, get_engine

    engine = get_engine(f"sqlite+pysqlite:///{tmp_path.as_posix()}/c.sqlite")
    table = Table("t", MetaData(), Column("id", Integer, primary_key=True))
    table.metadata.create_all(engine)
    factory = create_session_factory(engine)

    @event.listens_for(engine, "commit")
    def _lose_connection(_connection):
        raise _pg_error("InterfaceError", None, "network error")

    with factory() as session:
        session.execute(table.insert().values(id=1))
        with pytest.raises(CommitOutcomeUnknown) as caught:
            session.commit()
        assert is_connection_error(caught.value.__cause__)

    event.remove(engine, "commit", _lose_connection)
    # A failure before COMMIT is not "unknown": it propagates as the database error itself.
    with factory() as session:
        session.execute(table.insert().values(id=2))
        session.commit()
        with pytest.raises(sa_exc.IntegrityError):
            session.execute(table.insert().values(id=2))
            session.commit()
