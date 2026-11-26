"""Each person's own read and dismissed marks on monitoring alerts.

Acknowledging an alert is shared and audited; reading or dismissing it is personal. These
tests pin that a mark changes only the caller's list, that it never touches the shared alert
status, that an escalation, or a clear-and-return, brings a dismissed alert back, and that
the shared compatibility token (which is not a person) cannot keep marks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.models import MonitoringAlertRecord
from eurogas_nexus.security.permissions import Permission, permission_for_path
from tests.security.test_monitoring_acknowledgement import (
    _alert,
    _bearer,
    _headers,
    _prepare_db,
)

STATE_PATH = "/api/me/alert-state"


def _two_readers(tmp_path, monkeypatch):
    url = _prepare_db(tmp_path, monkeypatch, _alert("alert-a"), _alert("alert-b"))
    with Session(create_engine(url, future=True)) as session:
        _first, first = _bearer(session, name="reader-one", roles=["VIEWER"], scopes=["ENTSOG"])
        _second, second = _bearer(session, name="reader-two", roles=["VIEWER"], scopes=["ENTSOG"])
        session.commit()
    return url, first, second


def test_alert_marks_are_a_personal_read_permission() -> None:
    assert permission_for_path(STATE_PATH) is Permission.READ


def test_dismissing_hides_for_me_only_and_leaves_the_shared_status(tmp_path, monkeypatch) -> None:
    url, first, second = _two_readers(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(
        STATE_PATH,
        headers=_headers(first),
        json={"action": "dismiss", "alert_ids": ["alert-a", "alert-unknown"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["changed"] == 1
    assert body["not_found"] == ["alert-unknown"]
    assert body["alerts"]["alert-a"]["dismissed"] is True
    assert body["alerts"]["alert-a"]["read"] is True

    mine = client.get(STATE_PATH, headers=_headers(first)).json()["data"]["alerts"]
    theirs = client.get(STATE_PATH, headers=_headers(second)).json()["data"]["alerts"]
    assert set(mine) == {"alert-a"}
    assert theirs == {}
    with Session(create_engine(url, future=True)) as session:
        assert session.get(MonitoringAlertRecord, "alert-a").status == "open"

    restored = client.post(
        STATE_PATH, headers=_headers(first), json={"action": "restore", "alert_ids": ["alert-a"]}
    ).json()["data"]["alerts"]
    assert restored["alert-a"] == {
        "read": True,
        "dismissed": False,
        "read_at_utc": restored["alert-a"]["read_at_utc"],
        "dismissed_at_utc": None,
    }


def test_an_escalation_or_a_return_brings_a_dismissed_alert_back(tmp_path, monkeypatch) -> None:
    from eurogas_nexus.db.repositories.monitoring import resolve_absent_monitoring_alerts

    url, first, _second = _two_readers(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    client.post(
        STATE_PATH,
        headers=_headers(first),
        json={"action": "dismiss", "alert_ids": ["alert-a", "alert-b"]},
    )

    with Session(create_engine(url, future=True)) as session:
        # A level alert re-evaluated later with nothing new stays dismissed.
        steady = session.get(MonitoringAlertRecord, "alert-a")
        steady.event_time_utc = steady.event_time_utc + timedelta(hours=1)
        escalated = session.get(MonitoringAlertRecord, "alert-b")
        escalated.severity = "critical"
        session.commit()
    marks = client.get(STATE_PATH, headers=_headers(first)).json()["data"]["alerts"]
    assert set(marks) == {"alert-a"}

    with Session(create_engine(url, future=True)) as session:
        # alert-a clears; when it comes back it is new for everyone.
        resolve_absent_monitoring_alerts(
            session, {"test:alert-b"}, now_utc=datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
        )
        returned = session.get(MonitoringAlertRecord, "alert-a")
        returned.status = "open"
        returned.resolved_at_utc = None
        session.commit()
    assert client.get(STATE_PATH, headers=_headers(first)).json()["data"]["alerts"] == {}


def test_the_shared_token_keeps_no_marks(tmp_path, monkeypatch) -> None:
    _prepare_db(tmp_path, monkeypatch, _alert("alert-a"))
    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(
        STATE_PATH, headers=_headers(), json={"action": "read", "alert_ids": ["alert-a"]}
    )
    assert response.status_code in {401, 403}


def test_resolved_alerts_carry_no_marks(tmp_path, monkeypatch) -> None:
    url, first, _second = _two_readers(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    client.post(
        STATE_PATH, headers=_headers(first), json={"action": "read", "alert_ids": ["alert-a"]}
    )
    with Session(create_engine(url, future=True)) as session:
        row = session.get(MonitoringAlertRecord, "alert-a")
        row.status = "resolved"
        row.resolved_at_utc = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
        session.commit()
    assert client.get(STATE_PATH, headers=_headers(first)).json()["data"]["alerts"] == {}
