"""Package G routes: GET /api/publications/calendar and /api/publications/sources, and the
administrator's POST /api/publications/sources/{id}/confirm.

SQLite runtime store, the real app; the calendar is a workbook written for the tests and is
read through an in-memory fetcher (no network).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.publication_watch import check_publication
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.publications.registry import watched_publication
from tests.fixtures.news_seed import store
from tests.fixtures.publication_seed import FILE_2627, PublicationFetcher, calendar_xlsx

PUBLIC = "test-public-api-token"


@pytest.fixture()
def api(tmp_path, monkeypatch):
    url, engine = store(tmp_path, "publications.sqlite")
    now = datetime.now(UTC)
    headers = {}
    item = watched_publication("entsog-cam-auction-calendar")
    with Session(engine) as session:
        check_publication(session, item, fetch=PublicationFetcher({FILE_2627: calendar_xlsx()}),
                          now=now - timedelta(days=2))
        # A later version the parser cannot read: the old dates stay, a person is asked.
        check_publication(session, item,
                          fetch=PublicationFetcher({FILE_2627: calendar_xlsx(rename_header=True)}),
                          now=now - timedelta(hours=1))
        for name, role in (("analyst", "ANALYST"), ("admin", "ADMIN")):
            principal = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, principal.principal_id, display_name="t", scopes=["*"]
            )
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return TestClient(create_app()), headers


def test_the_source_list_states_every_publication(api):
    client, headers = api
    response = client.get("/api/publications/sources", headers=headers["analyst"])
    assert response.status_code == 200, response.text
    rows = {row["publication_id"]: row for row in response.json()["data"]["rows"]}
    assert rows["entsog-cam-auction-calendar"]["state"] == "needs_confirmation"
    assert rows["entsog-cam-auction-calendar"]["pending_url"] == FILE_2627
    assert rows["eex-trading-calendar"]["state"] == "hand_maintained"
    assert rows["the-imbalance-prices"]["state"] == "link_only"
    assert rows["the-imbalance-prices"]["terms_quote"]


def test_the_calendar_carries_sources_and_marks_what_is_hand_maintained(api):
    client, headers = api
    response = client.get("/api/publications/calendar", params={"days": 400},
                          headers=headers["analyst"])
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["data"]["items"]
    kinds = {item["kind"] for item in items}
    assert {"non_trading_day", "source_changed"} <= kinds
    assert all(item["source"]["basis"] for item in items)
    assert any("hand-maintained" in warning for warning in body["meta"]["warnings"])


def test_only_an_administrator_confirms_a_changed_source(api):
    client, headers = api
    path = "/api/publications/sources/entsog-cam-auction-calendar/confirm"
    assert client.post(path, headers=headers["analyst"]).status_code == 403
    response = client.post(path, headers=headers["admin"])
    assert response.status_code == 200, response.text
    assert response.json()["data"]["row"]["state"] == "current"
    assert client.post(path, headers=headers["admin"]).status_code == 409
    assert client.post("/api/publications/sources/nope/confirm",
                       headers=headers["admin"]).status_code == 404
