"""Problem reports to the IT desk and notification channels."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import NotificationOutboxRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

TOKEN = "test-public-api-token"


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'support.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    who = {}
    with Session(engine) as session:
        for name, role in (
            ("trader", "ANALYST"),
            ("other", "ANALYST"),
            ("it", "OPERATOR"),
            ("admin", "ADMIN"),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    return engine, who


def test_a_trader_reports_a_problem_and_the_it_desk_resolves_it(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    body = {
        "severity": "P2",
        "category": "data",
        "summary": "TTF prices stale since 09:10",
        "description": "The board shows yesterday's close.",
        "page": "Market > Curves",
        "client_context": {
            "failed_reads": [{"path": "/api/market/quotes", "correlation_id": "abc123"}]
        },
    }
    created = client.post("/api/support/reports", json=body, headers=who["trader"])
    assert created.status_code == 200, created.text
    report = created.json()["data"]
    assert report["report_id"].startswith("SR-") and report["status"] == "open"
    assert report["server_context"]["schema_revision"]
    with Session(engine) as session:
        (outbox,) = session.query(NotificationOutboxRecord).all()
    assert outbox.category == "support" and outbox.severity == "high"

    mine = client.get("/api/support/reports", headers=who["trader"]).json()["data"]
    assert mine["scope"] == "mine" and len(mine["rows"]) == 1
    assert client.get("/api/support/reports", headers=who["other"]).json()["data"]["rows"] == []
    assert client.get("/api/support/reports", headers=who["it"]).json()["data"]["scope"] == "all"

    path = f"/api/support/reports/{report['report_id']}"
    assert (
        client.patch(path, json={"status": "acknowledged"}, headers=who["trader"]).status_code
        == 403
    )
    no_note = client.patch(path, json={"status": "resolved"}, headers=who["it"])
    assert no_note.status_code == 422
    done = client.patch(
        path, json={"status": "resolved", "resolution": "ICE feed restarted"}, headers=who["it"]
    )
    assert done.status_code == 200 and done.json()["data"]["assignee"]


def test_channels_are_admin_only_and_webhook_urls_never_return(tmp_path, monkeypatch):
    # The credential key also keys API-key hashing, so it is set before identities exist.
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", "k" * 44)
    _engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    path = "/api/settings/notification-channels"
    assert client.get(path, headers=who["it"]).status_code == 403
    email = {
        "name": "IT desk",
        "kind": "email",
        "recipients": "it@example.com",
        "categories": ["support", "source"],
        "min_severity": "medium",
    }
    first = client.put(f"{path}/it", json=email, headers=who["admin"])
    assert first.status_code == 200, first.text
    hook = {
        "name": "Desk Teams",
        "kind": "webhook",
        "webhook_url": "https://example.webhook.office.com/abc/SECRETPART",
        "categories": ["alert"],
    }
    saved = client.put(f"{path}/desk", json=hook, headers=who["admin"])
    assert saved.status_code == 200, saved.text
    listed = client.get(path, headers=who["admin"]).json()["data"]["rows"]
    assert "SECRETPART" not in str(listed)
    plain = client.put(
        f"{path}/x", json={**hook, "webhook_url": "http://insecure"}, headers=who["admin"]
    )
    assert plain.status_code == 422
    test = client.post(f"{path}/it/test", headers=who["admin"]).json()["data"]
    assert test["sent"] is False and "not configured" in test["detail"]


def test_tariff_publication_register_flags_what_needs_action(tmp_path, monkeypatch):
    _engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    path = "/api/route-cost/tariff-publications"
    body = {
        "tso": "Gasunie Transport Services",
        "country": "NL",
        "gas_year": "2026/27",
        "status": "indicative",
        "url": "https://www.gasunietransportservices.nl/tariffs",
    }
    saved = client.put(f"{path}/gts-2026", json=body, headers=who["trader"])
    assert saved.status_code == 200, saved.text
    row = saved.json()["data"]
    # Gas year 2026/27 began on 1 October 2026 and only indicative prices are held.
    assert row["state"] == "in_force_without_final" and row["severity"] == "breach"
    assert row["final_due"] == "2026-06-06"
    final = client.put(f"{path}/gts-2026", json={**body, "status": "final"}, headers=who["trader"])
    assert final.json()["data"]["state"] == "final" and final.json()["data"]["published_on"]
    listed = client.get(path, headers=who["other"]).json()["data"]["rows"]
    assert listed[0]["publication_id"] == "gts-2026"
    insecure = client.put(f"{path}/x", json={**body, "url": "http://x"}, headers=who["trader"])
    assert insecure.status_code == 422
