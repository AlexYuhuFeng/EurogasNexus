"""The application during a database outage, against a PostgreSQL that is stopped and started.

Opt-in (it runs Docker): ``EUROGAS_NEXUS_DOCKER_TESTS=1``. The fixture starts its own
throwaway ``postgres:16`` container on a free local port, never a configured store, and removes
it afterwards. It proves the rules of ``src/eurogas_nexus/db/resilience.py``:

- readiness fails (503, ``runtime_db_unavailable``) while the database is down and recovers
  by itself when it is back, through the same pooled engine;
- a write while the database is down fails loudly, and the same process writes again once it
  is back (the pool replaces its dead connections);
- start-up waits with backoff and connects as soon as the database answers;
- a connection lost during COMMIT is reported as "outcome unknown", never as "not saved";
- with failover hosts configured, an unreachable first host is skipped.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    os.environ.get("EUROGAS_NEXUS_DOCKER_TESTS") != "1" or shutil.which("docker") is None,
    reason="set EUROGAS_NEXUS_DOCKER_TESTS=1 (needs Docker) to stop and start a scratch PostgreSQL",
)

PASSWORD = "resilience-scratch"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _docker(*args: str, check: bool = True) -> str:
    return subprocess.run(
        ["docker", *args], check=check, capture_output=True, text=True, timeout=180
    ).stdout.strip()


def _wait_ready(url: str, seconds: float = 60) -> None:
    from eurogas_nexus.db.resilience import wait_for_database

    result = wait_for_database(url, timeout_seconds=seconds)
    assert result.ok, result


@pytest.fixture(scope="module")
def scratch():
    name = f"nexus-resilience-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    _docker(
        "run", "-d", "--name", name, "-e", f"POSTGRES_PASSWORD={PASSWORD}",
        "-e", "POSTGRES_DB=nexus", "-p", f"127.0.0.1:{port}:5432", "postgres:16",
    )
    url = f"postgresql+pg8000://postgres:{PASSWORD}@127.0.0.1:{port}/nexus"
    try:
        _wait_ready(url, 90)
        # The image restarts once after initialising; wait for the final server.
        time.sleep(2)
        _wait_ready(url, 60)
        from sqlalchemy import create_engine

        from eurogas_nexus.db.base import Base
        from eurogas_nexus.db.registry import get_metadata
        from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

        get_metadata()
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64))"
            )
            connection.exec_driver_sql(
                "INSERT INTO alembic_version VALUES (%s)", (DB_SCHEMA_REVISION,)
            )
        engine.dispose()
        yield {"name": name, "url": url, "port": port}
    finally:
        _docker("rm", "-f", name, check=False)


@pytest.fixture()
def database_env(scratch, monkeypatch):
    for variable in ("RUNTIME_STORE_DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DATABASE_URL", scratch["url"])
    monkeypatch.delenv("EUROGAS_NEXUS_DB_FAILOVER_HOSTS", raising=False)
    yield scratch
    from eurogas_nexus.db.session import dispose_cached_engines

    dispose_cached_engines()


def _audit_row(event_id: str):
    from eurogas_nexus.db.models import AuditEventRecord

    return AuditEventRecord(
        event_id=event_id,
        event_type="test",
        severity="info",
        principal="resilience-test",
        action="write",
        resource="test",
        outcome="recorded",
        detail="",
        event_ts_utc=datetime.now(UTC),
        source_system="test",
        human_review_required=False,
    )


def test_readiness_and_writes_through_a_stop_and_start(database_env) -> None:
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app
    from eurogas_nexus.db.models import AuditEventRecord
    from eurogas_nexus.db.session import get_session_factory

    factory = get_session_factory()
    client = TestClient(create_app())
    assert client.get("/api/health/ready").status_code == 200
    with factory() as session:
        session.add(_audit_row("before-outage"))
        session.commit()

    _docker("stop", "-t", "5", database_env["name"])
    try:
        started = time.monotonic()
        response = client.get("/api/health/ready")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "runtime_db_unavailable"
        assert time.monotonic() - started < 15
        # A write while the database is down fails loudly; nothing claims it was saved.
        with factory() as session:
            session.add(_audit_row("during-outage"))
            with pytest.raises(Exception) as caught:
                session.commit()
            from eurogas_nexus.db.resilience import is_connection_error

            assert is_connection_error(caught.value)
    finally:
        _docker("start", database_env["name"])
    _wait_ready(database_env["url"])

    # The same process, the same pool: readiness and writes recover without a restart.
    assert client.get("/api/health/ready").status_code == 200
    with factory() as session:
        session.add(_audit_row("after-outage"))
        session.commit()
        ids = {row.event_id for row in session.query(AuditEventRecord).all()}
    assert {"before-outage", "after-outage"} <= ids
    assert "during-outage" not in ids


def test_startup_waits_with_backoff_until_the_database_answers(database_env) -> None:
    from eurogas_nexus.db.resilience import wait_for_database_at_startup

    _docker("stop", "-t", "5", database_env["name"])
    timer = threading.Timer(4.0, lambda: _docker("start", database_env["name"]))
    timer.start()
    lines: list[str] = []
    try:
        result = wait_for_database_at_startup(
            component="test",
            environ={
                "DATABASE_URL": database_env["url"],
                "EUROGAS_NEXUS_DB_STARTUP_WAIT_SECONDS": "90",
            },
            emit=lines.append,
        )
    finally:
        timer.join()
    assert result.ok and result.attempts > 1, result
    assert any('"db.startup.retry"' in line for line in lines)
    _wait_ready(database_env["url"])


def test_a_connection_lost_during_commit_is_reported_as_unknown(database_env) -> None:
    from eurogas_nexus.db.models import AuditEventRecord
    from eurogas_nexus.db.resilience import CommitOutcomeUnknown
    from eurogas_nexus.db.session import get_engine, get_session_factory

    factory = get_session_factory()
    killer = get_engine(database_env["url"])
    with factory() as session:
        session.add(_audit_row("interrupted"))
        session.flush()
        pid = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        with killer.begin() as connection:
            connection.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
        with pytest.raises(CommitOutcomeUnknown):
            session.commit()
    killer.dispose()
    with factory() as session:
        # Here the server never received COMMIT, so the row is absent; the client could not
        # know that, which is why it is told "unknown" and must check before retrying.
        assert session.get(AuditEventRecord, "interrupted") is None


def test_failover_hosts_skip_an_unreachable_first_host(database_env, monkeypatch) -> None:
    from eurogas_nexus.db.session import get_engine

    dead_port = _free_port()
    url = database_env["url"].replace(f":{database_env['port']}/", f":{dead_port}/")
    monkeypatch.setenv("EUROGAS_NEXUS_DB_FAILOVER_HOSTS", f"127.0.0.1:{database_env['port']}")
    engine = get_engine(url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT pg_is_in_recovery()")).scalar() is False
            port = connection.execute(text("SELECT inet_server_port()")).scalar()
            assert port == 5432  # the container's own port: we reached the live server
    finally:
        engine.dispose()
    monkeypatch.setenv("EUROGAS_NEXUS_DB_FAILOVER_HOSTS", f"127.0.0.1:{_free_port()}")
    engine = get_engine(url, connect_timeout_seconds=2)
    try:
        with pytest.raises(Exception, match="no writable primary"):
            engine.connect()
    finally:
        engine.dispose()
