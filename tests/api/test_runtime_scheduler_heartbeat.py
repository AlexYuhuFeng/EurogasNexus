"""The Runtime page's scheduler row reads the scheduler's own heartbeat (P1-C).

``/api/runtime/dependencies`` reports, for the data-operations scheduler, whether it beats,
how many sources it last had on a schedule and how many are registered, so the page never
infers "0 scheduled" from source rows a scheduler never created.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import DataOperationsHeartbeatRecord
from eurogas_nexus.domain.dataops.registry import source_definitions


def _client(tmp_path, monkeypatch, heartbeat: bool) -> TestClient:
    url = f"sqlite+pysqlite:///{(tmp_path / 'deps.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    if heartbeat:
        now = datetime.now(UTC)
        with Session(engine) as session:
            session.add(
                DataOperationsHeartbeatRecord(
                    heartbeat_id="primary",
                    last_heartbeat_at_utc=now - timedelta(seconds=30),
                    last_scan_at_utc=now - timedelta(seconds=40),
                    sources_scheduled=10,
                )
            )
            session.commit()
    engine.dispose()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return TestClient(create_app())


def test_no_scheduler_ever_ran(tmp_path, monkeypatch) -> None:
    data = _client(tmp_path, monkeypatch, heartbeat=False).get(
        "/api/runtime/dependencies"
    ).json()["data"]
    dataops = data["schedulers"]["dataops"]
    assert dataops["detail_code"] == "no_heartbeat"
    assert dataops["registered_sources"] == len(source_definitions())
    assert "sources_scheduled" not in dataops


def test_a_running_scheduler_reports_its_count(tmp_path, monkeypatch) -> None:
    data = _client(tmp_path, monkeypatch, heartbeat=True).get(
        "/api/runtime/dependencies"
    ).json()["data"]
    dataops = data["schedulers"]["dataops"]
    assert dataops["state"] == "AVAILABLE"
    assert dataops["sources_scheduled"] == 10
    assert dataops["last_scan_at_utc"]
