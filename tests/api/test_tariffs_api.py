"""TAR-1 routes: GET /api/tariffs, /api/tariffs/publishers and /api/capacity/notices.

SQLite runtime store, the real app, an identity with no licensed grant; made-up figures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import tariff_book as book
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from tests.unit.test_tariff_book import entsog_row, lng_row

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'tariffs.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        reader = create_identity_principal(
            session, name="tariff-reader", display_name="Reader", role="ANALYST", data_scopes=[]
        )
        _, bearer = create_identity_api_key(
            session, reader.principal_id, display_name="reader", scopes=["*"]
        )
        session.merge(entsog_row(at=NOW - timedelta(days=2)))
        session.flush()
        book.capture_tariffs(session, now_utc=NOW - timedelta(days=2))
        session.merge(entsog_row(status="FINAL", at=NOW - timedelta(hours=1)))
        session.add(lng_row(at=NOW - timedelta(hours=1)))  # Fluxys: no permission recorded
        session.flush()
        book.capture_tariffs(session, now_utc=NOW - timedelta(hours=1))
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    )


def test_current_tariffs_are_labelled_and_a_restricted_terminal_is_left_out(client):
    response = client.get("/api/tariffs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["research_only"] is True
    rows = body["data"]["rows"]
    assert [(row["facility_id"], row["version"], row["status"]) for row in rows] == [
        ("ITP-1", 2, "FINAL")
    ]
    assert rows[0]["status_change"] == "INDICATIVE->FINAL"
    assert rows[0]["source_url"].startswith("https://transparency.entsog.eu/")
    # The Fluxys terminal row exists in the book but its terms need the firm's permission.
    assert (
        client.get("/api/tariffs", params={"publisher": "fluxys-lng"}).json()["data"]["rows"] == []
    )


def test_as_of_and_history(client):
    before = client.get(
        "/api/tariffs", params={"as_of": (NOW - timedelta(days=1)).isoformat()}
    ).json()["data"]
    assert [(row["version"], row["status"]) for row in before["rows"]] == [(1, "INDICATIVE")]
    assert before["as_of"] is not None
    history = client.get("/api/tariffs", params={"facility": "ITP-1", "history": "true"})
    assert [row["version"] for row in history.json()["data"]["rows"]] == [1, 2]
    refused = client.get("/api/tariffs", params={"history": "true"})
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "history_needs_scope"
    future = client.get("/api/tariffs", params={"as_of": "2999-01-01T00:00:00Z"})
    assert future.status_code == 422
    indicative = client.get("/api/tariffs", params={"status": "INDICATIVE"}).json()["data"]
    assert indicative["rows"] == []


def test_publishers_and_notices(client):
    publishers = client.get("/api/tariffs/publishers").json()["data"]["rows"]
    by_id = {row["publisher_id"]: row for row in publishers}
    assert by_id["entsog-tp"]["state"] == "current"
    assert by_id["entsog-tp"]["tariffs_final"] == 1
    assert by_id["fluxys-lng"]["state"] == "excluded"
    assert by_id["fluxys-lng"]["readable"] is False and by_id["fluxys-lng"]["tariffs_final"] is None
    assert by_id["storengy"]["access"] == "manual"
    notices = client.get("/api/capacity/notices", params={"days": 60}).json()
    rows = notices["data"]["rows"]
    assert rows and {row["basis"] for row in rows} == {"rule_derived"}
    assert rows == sorted(rows, key=lambda row: row["opens_at_utc"])
    assert any("rule_derived" in warning for warning in notices["meta"]["warnings"])
    bad = client.get("/api/capacity/notices", params={"kind": "pipeline"})
    assert bad.status_code == 422


def test_without_a_runtime_store_the_reads_degrade_and_say_so(monkeypatch):
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"})
    for path in ("/api/tariffs", "/api/tariffs/publishers", "/api/capacity/notices"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert response.json()["meta"]["warnings"], path
