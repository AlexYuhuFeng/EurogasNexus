"""Monitoring acknowledgement is a governed, attributable write (Architecture V2).

Before this slice the alert-centre acknowledgement matched the READ ``/api/monitoring/``
family - any authenticated reader could acknowledge - and the route stored only
``acknowledged_at_utc``: no principal, no audit record. These tests pin the fixed posture:

* an explicit GOVERNED permission is declared before the READ family, so the write keeps
  the ANALYST floor and the commercial-data boundary;
* the actor is the authenticated principal resolved through ``acting_actor``, before any
  database change, and a request with no resolved identity is refused;
* the state transition and its audit event are one transaction, so a repeat, no-op or
  failed-audit acknowledgement cannot corrupt attribution.

The route's own decision is what is under test here; the PostgreSQL-authoritative
concurrency check lives in ``tests/integration``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, MonitoringAlertRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path

PUBLIC_TOKEN = "test-public-api-token"
ACK_PATH = "/api/monitoring/alerts/alert-test/acknowledge"


def _alert(
    alert_id: str = "alert-test",
    *,
    status: str = "open",
    acknowledged_at_utc: datetime | None = None,
    resolved_at_utc: datetime | None = None,
) -> MonitoringAlertRecord:
    now = datetime(2026, 7, 22, 8, 0, tzinfo=UTC)
    return MonitoringAlertRecord(
        alert_id=alert_id,
        fingerprint=f"test:{alert_id}",
        category="data_source",
        alert_type="ingestion_failed",
        severity="warning",
        status=status,
        title_en="ENTSOG ingestion failed",
        title_zh_cn="ENTSOG 数据更新失败",
        message_en="Latest run failed.",
        message_zh_cn="最近一次更新失败。",
        entity_type="data_source",
        entity_id="ENTSOG",
        event_time_utc=now,
        detected_at_utc=now,
        updated_at_utc=now,
        acknowledged_at_utc=acknowledged_at_utc,
        resolved_at_utc=resolved_at_utc,
        occurrence_count=1,
        evidence_snapshot={"run_id": "run-test"},
        source_refs=["ingestion-run:run-test"],
        warnings=[],
        llm_provider_id="DEEPSEEK",
        llm_status="pending",
        llm_summary_en=None,
        llm_summary_zh_cn=None,
        llm_last_attempt_at_utc=None,
        simulated=False,
        human_review_required=True,
    )


def _prepare_db(tmp_path, monkeypatch, *alerts: MonitoringAlertRecord) -> str:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'ack.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for alert in alerts:
            session.add(alert)
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _bearer(
    session: Session, *, name: str, roles: list[str], scopes: list[str]
) -> tuple[str, str]:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=roles[0],
        data_scopes=scopes,
    )
    row.roles = list(roles)
    _key, bearer = create_identity_api_key(session, row.principal_id, display_name="ack")
    return row.principal_id, bearer


def _headers(bearer: str | None = None) -> dict[str, str]:
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN}
    if bearer:
        headers["X-Eurogas-Identity"] = bearer
    return headers


def _audit_rows(url: str) -> list[AuditEventRecord]:
    with Session(create_engine(url, future=True)) as session:
        return (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "monitoring.alert.acknowledge")
            .all()
        )


def test_acknowledgement_is_a_governed_write_declared_before_the_read_family() -> None:
    """The write no longer hides inside the READ ``/api/monitoring/`` prefix."""

    assert permission_for_path(ACK_PATH) is Permission.GOVERNED
    assert permission_for_path("/api/monitoring/alerts") is Permission.READ
    assert permission_for_path("/api/monitoring/summary") is Permission.READ


def test_acknowledgement_routes_resolve_the_principal_before_the_database() -> None:
    """Both write paths refuse an identity-less request before any store access.

    The environment has no runtime database configured, so a route that touched the store
    first would answer its 503 instead; the 401 proves the actor is resolved up front.
    """

    from eurogas_nexus.api.routes.public.monitoring import acknowledge_alert as monitoring_ack
    from eurogas_nexus.api.routes.public.shadow import (
        ShadowAcknowledgeRequest,
        acknowledge_shadow_alert,
    )

    bare = SimpleNamespace(state=SimpleNamespace())
    with pytest.raises(HTTPException) as monitoring_denied:
        monitoring_ack("alert-test", bare)
    assert monitoring_denied.value.status_code == 401
    assert monitoring_denied.value.detail["error"] == "authentication_required"

    with pytest.raises(HTTPException) as shadow_denied:
        acknowledge_shadow_alert(
            "shadow-alert-1", ShadowAcknowledgeRequest(actor="spoofed"), bare
        )
    assert shadow_denied.value.status_code == 401
    assert shadow_denied.value.detail["error"] == "authentication_required"


def test_read_only_identity_is_refused_before_any_write(tmp_path, monkeypatch) -> None:
    url = _prepare_db(tmp_path, monkeypatch, _alert())
    with Session(create_engine(url, future=True)) as session:
        _principal_id, viewer_bearer = _bearer(
            session, name="ack-viewer", roles=["VIEWER"], scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(ACK_PATH, headers=_headers(viewer_bearer))

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "identity_role_forbidden"
    # Refused before any write: the alert is untouched and no audit row exists.
    with Session(create_engine(url, future=True)) as session:
        row = session.get(MonitoringAlertRecord, "alert-test")
        assert row.status == "open"
        assert row.acknowledged_at_utc is None
    assert _audit_rows(url) == []


def test_authorised_analyst_acknowledgement_is_attributed_in_the_audit_trail(
    tmp_path,
    monkeypatch,
) -> None:
    url = _prepare_db(tmp_path, monkeypatch, _alert())
    with Session(create_engine(url, future=True)) as session:
        analyst_id, analyst_bearer = _bearer(
            session, name="ack-analyst", roles=["ANALYST"], scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(ACK_PATH, headers=_headers(analyst_bearer))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "acknowledged"
    assert response.json()["data"]["acknowledged_at_utc"] is not None

    rows = _audit_rows(url)
    assert len(rows) == 1
    event = rows[0]
    assert event.principal == analyst_id
    assert event.resource == "monitoring_alert:alert-test"
    assert event.outcome == "acknowledged"
    assert event.event_ts_utc is not None
    assert f"actor_id={analyst_id}" in event.detail
    assert "role=ANALYST" in event.detail
    assert event.correlation_id == response.headers["x-request-id"]
    assert event.before_summary == {"status": "open"}
    assert event.after_summary["status"] == "acknowledged"


def test_administration_only_identity_is_refused_by_the_commercial_boundary(
    tmp_path,
    monkeypatch,
) -> None:
    url = _prepare_db(tmp_path, monkeypatch, _alert())
    with Session(create_engine(url, future=True)) as session:
        _admin_id, admin_bearer = _bearer(
            session, name="ack-admin", roles=["ADMIN"], scopes=[]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(ACK_PATH, headers=_headers(admin_bearer))

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "commercial_access_not_granted"
    with Session(create_engine(url, future=True)) as session:
        assert session.get(MonitoringAlertRecord, "alert-test").status == "open"
    assert _audit_rows(url) == []


def test_deployment_token_keeps_its_posture_and_missing_identity_is_refused(
    tmp_path,
    monkeypatch,
) -> None:
    """The compatibility principal acts for the deployment; no resolved identity is a 401."""

    url = _prepare_db(tmp_path, monkeypatch, _alert(), _alert("alert-unidentified"))

    client = TestClient(create_app(Settings(api_profile="release")))

    # No credential at all: the request is refused before the handler, and nothing is written.
    anonymous = client.post("/api/monitoring/alerts/alert-unidentified/acknowledge")
    assert anonymous.status_code == 401
    with Session(create_engine(url, future=True)) as session:
        assert session.get(MonitoringAlertRecord, "alert-unidentified").status == "open"
    assert _audit_rows(url) == []

    # The documented deployment token resolves to the compatibility principal, exactly as
    # every other governed write accepts it (acting_actor's documented carve-out).
    legacy = client.post(ACK_PATH, headers=_headers())
    assert legacy.status_code == 200, legacy.text
    rows = _audit_rows(url)
    assert len(rows) == 1
    assert rows[0].principal == "service:public-api"


def test_repeat_acknowledgement_preserves_original_attribution_and_audit(
    tmp_path,
    monkeypatch,
) -> None:
    url = _prepare_db(tmp_path, monkeypatch, _alert())
    with Session(create_engine(url, future=True)) as session:
        _first_id, first_bearer = _bearer(
            session, name="ack-first", roles=["ANALYST"], scopes=["ENTSOG"]
        )
        _second_id, second_bearer = _bearer(
            session, name="ack-second", roles=["ANALYST"], scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    first = client.post(ACK_PATH, headers=_headers(first_bearer))
    assert first.status_code == 200
    first_acknowledged_at = first.json()["data"]["acknowledged_at_utc"]

    repeat = client.post(ACK_PATH, headers=_headers(second_bearer))
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["data"]["status"] == "acknowledged"
    # The original acknowledger and timestamp survive; the repeat is a no-op.
    assert repeat.json()["data"]["acknowledged_at_utc"] == first_acknowledged_at
    # Exactly one successful transition, so exactly one attribution record.
    assert len(_audit_rows(url)) == 1


def test_resolved_alert_is_never_reopened_or_acknowledged(tmp_path, monkeypatch) -> None:
    resolved_at = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    url = _prepare_db(
        tmp_path,
        monkeypatch,
        _alert(status="resolved", resolved_at_utc=resolved_at),
    )
    with Session(create_engine(url, future=True)) as session:
        _analyst_id, analyst_bearer = _bearer(
            session, name="ack-resolved", roles=["ANALYST"], scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(ACK_PATH, headers=_headers(analyst_bearer))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "resolved"
    assert response.json()["data"]["acknowledged_at_utc"] is None
    with Session(create_engine(url, future=True)) as session:
        row = session.get(MonitoringAlertRecord, "alert-test")
        assert row.status == "resolved"
        assert row.acknowledged_at_utc is None
        assert row.resolved_at_utc is not None
    assert _audit_rows(url) == []


def test_missing_alert_is_a_404_without_an_audit_record(tmp_path, monkeypatch) -> None:
    url = _prepare_db(tmp_path, monkeypatch, _alert())
    with Session(create_engine(url, future=True)) as session:
        _analyst_id, analyst_bearer = _bearer(
            session, name="ack-missing", roles=["ANALYST"], scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(
        "/api/monitoring/alerts/alert-absent/acknowledge",
        headers=_headers(analyst_bearer),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "monitoring_alert_not_found"
    assert _audit_rows(url) == []


def test_audit_failure_rolls_back_the_acknowledgement(tmp_path, monkeypatch) -> None:
    """An acknowledgement that cannot be attributed must not be persisted."""

    url = _prepare_db(tmp_path, monkeypatch, _alert())
    with Session(create_engine(url, future=True)) as session:
        _analyst_id, analyst_bearer = _bearer(
            session, name="ack-rollback", roles=["ANALYST"], scopes=["ENTSOG"]
        )
        session.commit()

    def _fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit trail unavailable")

    monkeypatch.setattr(
        "eurogas_nexus.api.routes.public.monitoring._record_acknowledgement_audit",
        _fail_audit,
    )
    client = TestClient(
        create_app(Settings(api_profile="release")), raise_server_exceptions=False
    )
    response = client.post(ACK_PATH, headers=_headers(analyst_bearer))

    assert response.status_code == 500
    with Session(create_engine(url, future=True)) as session:
        row = session.get(MonitoringAlertRecord, "alert-test")
        assert row.status == "open"
        assert row.acknowledged_at_utc is None
    assert _audit_rows(url) == []
