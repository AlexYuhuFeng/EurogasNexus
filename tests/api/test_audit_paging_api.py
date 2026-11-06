"""Audit retrieval for investigations: time-bounded, deterministic, walkable (#59)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"
BASE_TS = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _prepare(tmp_path, monkeypatch) -> tuple[str, str, str]:
    url = f"sqlite+pysqlite:///{(tmp_path / 'audit.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(engine) as session:
        bearers = []
        for name, role in (("audit-admin", "ADMIN"), ("audit-analyst", "ANALYST")):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=[]
            )
            _key, bearer = create_identity_api_key(session, row.principal_id, display_name="t")
            bearers.append(bearer)
        # 25 matching events, five per timestamp (ties), plus noise from another action.
        for index in range(25):
            stamp = BASE_TS + timedelta(minutes=index // 5)
            session.add(_event(f"evt-{index:03d}", stamp, "probe"))
        for index in range(5):
            session.add(_event(f"noise-{index}", BASE_TS, "other"))
        session.commit()
    return url, bearers[0], bearers[1]


def _event(event_id: str, ts: datetime, action: str) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=event_id,
        event_type="test",
        severity="info",
        principal="investigated",
        action=action,
        resource="thing:1",
        outcome="ok",
        detail="",
        event_ts_utc=ts,
        source_system="test",
        human_review_required=False,
    )


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_every_matching_event_is_returned_exactly_once_across_pages(tmp_path, monkeypatch) -> None:
    url, admin, _analyst = _prepare(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    params = {"action": "probe", "limit": 7}
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        query = dict(params, **({"cursor": cursor} if cursor else {}))
        body = client.get("/api/audit", headers=_headers(admin), params=query).json()
        seen.extend(row["event_id"] for row in body["data"])
        continuation = body["meta"]["continuation"]
        pages += 1
        # Events written during the walk (the audit of each read, a new probe) never appear.
        with Session(create_engine(url, future=True)) as session:
            session.add(_event(f"late-{pages}", datetime.now(UTC), "probe"))
            session.commit()
        if not continuation["has_more"]:
            break
        cursor = continuation["cursor"]
    assert pages == 4
    assert len(seen) == len(set(seen)) == 25
    assert all(event_id.startswith("evt-") for event_id in seen)
    assert seen == sorted(seen, key=lambda value: (int(value[4:]) // 5, value), reverse=True)


def test_a_cursor_is_bound_to_its_filters_and_to_audit_read(tmp_path, monkeypatch) -> None:
    _url, admin, analyst = _prepare(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    first = client.get(
        "/api/audit", headers=_headers(admin), params={"action": "probe", "limit": 5}
    ).json()
    cursor = first["meta"]["continuation"]["cursor"]
    assert cursor

    mismatch = client.get(
        "/api/audit", headers=_headers(admin), params={"action": "other", "cursor": cursor}
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"]["error_code"] == "audit_cursor_filter_mismatch"

    for params in ({"action": "probe"}, {"action": "probe", "cursor": cursor}):
        refused = client.get("/api/audit", headers=_headers(analyst), params=params)
        assert refused.status_code in (401, 403)


def test_a_time_window_bounds_the_walk_and_needs_an_offset(tmp_path, monkeypatch) -> None:
    _url, admin, _analyst = _prepare(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    window = client.get(
        "/api/audit",
        headers=_headers(admin),
        params={
            "action": "probe",
            "start_utc": "2026-11-01T12:01:00Z",
            "end_utc": "2026-11-01T12:02:00+00:00",
        },
    ).json()
    assert sorted(row["event_id"] for row in window["data"]) == [
        f"evt-{index:03d}" for index in range(5, 15)
    ]
    assert window["meta"]["continuation"]["has_more"] is False

    naive = client.get(
        "/api/audit", headers=_headers(admin), params={"start_utc": "2026-11-01T12:00:00"}
    )
    assert naive.status_code == 400
    assert naive.json()["detail"]["error_code"] == "audit_window_timezone_required"
