"""Security-relevant changes need a second administrator who is not the requester (H7)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, IdentityPrincipalRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC = "test-public-api-token"


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'dc.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DUAL_CONTROL", "on")
    headers, ids = {}, {}
    with Session(engine) as session:
        for name in ("admin-a", "admin-b", "target"):
            row = create_identity_principal(
                session, name=name, display_name=name,
                role="ADMIN" if name != "target" else "VIEWER", data_scopes=[],
            )
            _key, bearer = create_identity_api_key(session, row.principal_id, display_name="t")
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}
            ids[name] = row.principal_id
        session.commit()
    return engine, TestClient(create_app()), headers, ids


def test_a_grant_waits_for_a_second_administrator(tmp_path, monkeypatch):
    engine, client, headers, ids = _setup(tmp_path, monkeypatch)
    path = f"/api/access/users/{ids['target']}"
    body = {"roles": ["ANALYST"], "data_scopes": ["BOOKS:*"]}
    pending = client.patch(path, json=body, headers=headers["admin-a"])
    assert pending.status_code == 409
    change_id = pending.json()["detail"]["change_id"]
    with Session(engine) as session:
        assert session.get(IdentityPrincipalRecord, ids["target"]).role == "VIEWER"

    # The requester cannot approve; nor apply without the approval.
    own = client.post(f"/api/access/privileged-changes/{change_id}/approve", json={},
                      headers=headers["admin-a"])
    assert own.status_code == 403
    early = client.patch(path, json=body,
                         headers={**headers["admin-a"], "X-Eurogas-Dual-Control": change_id})
    assert early.status_code == 403

    approved = client.post(f"/api/access/privileged-changes/{change_id}/approve", json={},
                           headers=headers["admin-b"])
    assert approved.status_code == 200, approved.text
    # A different body is not what was approved.
    other = client.patch(path, json={"roles": ["ADMIN"]},
                         headers={**headers["admin-a"], "X-Eurogas-Dual-Control": change_id})
    assert other.status_code == 403
    applied = client.patch(path, json=body,
                           headers={**headers["admin-a"], "X-Eurogas-Dual-Control": change_id})
    assert applied.status_code == 200, applied.text
    with Session(engine) as session:
        assert session.get(IdentityPrincipalRecord, ids["target"]).role == "ANALYST"
    # Used once.
    replay = client.patch(path, json=body,
                          headers={**headers["admin-a"], "X-Eurogas-Dual-Control": change_id})
    assert replay.status_code == 403


def test_an_approver_the_requester_provisioned_is_not_a_second_person(tmp_path, monkeypatch):
    engine, client, headers, ids = _setup(tmp_path, monkeypatch)
    from datetime import UTC, datetime

    from eurogas_nexus.db.repositories.audit import record_audit_event

    with Session(engine) as session:
        # admin-a created admin-b's account yesterday.
        record_audit_event(
            session, event_type="governance.identity", principal=ids["admin-a"],
            action="access.user.create", resource=f"identity_principal:{ids['admin-b']}",
            now_utc=datetime.now(UTC),
        )
        session.commit()
    pending = client.patch(f"/api/access/users/{ids['target']}", json={"roles": ["ANALYST"]},
                           headers=headers["admin-a"])
    change_id = pending.json()["detail"]["change_id"]
    refused = client.post(f"/api/access/privileged-changes/{change_id}/approve", json={},
                          headers=headers["admin-b"])
    assert refused.status_code == 403
    assert "within the last" in refused.json()["detail"]["message"]


def test_switching_four_eyes_off_is_itself_four_eyed_and_break_glass_is_loud(
    tmp_path, monkeypatch
):
    engine, client, headers, _ids = _setup(tmp_path, monkeypatch)
    body = {"four_eyes": {"risk.credit_line.update": False}}
    pending = client.put("/api/settings/organisation", json=body, headers=headers["admin-a"])
    assert pending.status_code == 409
    short = client.put("/api/settings/organisation", json=body,
                       headers={**headers["admin-a"], "X-Eurogas-Break-Glass": "urgent"})
    assert short.status_code == 403
    glass = client.put(
        "/api/settings/organisation", json=body,
        headers={**headers["admin-a"],
                 "X-Eurogas-Break-Glass": "single admin on call, risk head unreachable tonight"},
    )
    assert glass.status_code == 200, glass.text
    with Session(engine) as session:
        loud = session.query(AuditEventRecord).filter_by(action="security.break_glass.used").one()
        assert loud.severity == "critical"
    # Turning a control back on needs nobody else.
    back = client.put(
        "/api/settings/organisation",
        json={"four_eyes": {"risk.credit_line.update": True}},
        headers=headers["admin-a"],
    )
    assert back.status_code == 200


def test_dual_control_cannot_be_switched_off_in_release(monkeypatch):
    import pytest

    from eurogas_nexus.api.dual_control import assert_dual_control_setting_allowed

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    monkeypatch.setenv("EUROGAS_NEXUS_DUAL_CONTROL", "off")
    with pytest.raises(RuntimeError):
        assert_dual_control_setting_allowed()
