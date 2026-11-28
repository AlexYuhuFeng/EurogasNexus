"""The publishers' written consents through the API (owner, 2026-11-28).

``GET /api/publications/consents`` lists them; an administrator withdraws or restores one
(``POST .../withdraw``, ``.../restore``, audited); the board's quote read carries the published
prices fetched under them, dated, and a caller that presented nothing never gets them.
SQLite runtime store, the real app, documents written for the tests (no network).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.publication_watch import check_publication
from eurogas_nexus.db.models import MarketQuoteRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.publications.registry import watched_publication
from tests.fixtures import consented_seed as seed
from tests.fixtures.news_seed import store

PUBLIC = "test-public-api-token"


@pytest.fixture()
def api(tmp_path, monkeypatch):
    url, engine = store(tmp_path, "consents.sqlite")
    now = datetime.now(UTC)
    yesterday = (now - timedelta(days=1)).date()
    headers = {}
    with Session(engine) as session:
        fetch = seed.ConsentedFetcher(
            {seed.mibgas_url(now.year): seed.mibgas_csv([
                (yesterday - timedelta(days=1), "GDAES_D+1", yesterday, yesterday, "41.5"),
                (yesterday, "GDAES_D+1", yesterday + timedelta(days=1),
                 yesterday + timedelta(days=1), "40.25")])})
        check_publication(session, watched_publication("mibgas-prices"), fetch=fetch,
                          now=now, pause=lambda _s: None)
        # Plenty of newer simulated quotes: the published price still reaches the board.
        for index in range(30):
            session.add(MarketQuoteRecord(
                quote_id=f"sim-{index}", source_system="EEX_Sim", venue="EEX",
                instrument_id="x", hub="TTF", product="day-ahead",
                delivery_start_utc=now, delivery_end_utc=now + timedelta(days=1),
                bid_price=30.0, ask_price=30.2, currency="EUR", unit="EUR/MWh",
                observed_at_utc=now, received_at_utc=now, source_reference="sim",
                freshness="live", quality_score=1.0, simulated=True))
        for name, role in (("analyst", "ANALYST"), ("admin", "ADMIN")):
            principal = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=[]
            )
            _key, bearer = create_identity_api_key(
                session, principal.principal_id, display_name="t", scopes=["*"]
            )
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return TestClient(create_app()), headers, yesterday


def test_the_consents_are_listed_with_their_scope(api):
    client, headers, _day = api
    response = client.get("/api/publications/consents", headers=headers["analyst"])
    assert response.status_code == 200, response.text
    rows = {row["publisher_id"]: row for row in response.json()["data"]["rows"]}
    assert len(rows) == 12
    assert rows["mibgas"]["state"] == "in_force"
    assert rows["mibgas"]["basis"].endswith("not seen by the development team")


def test_only_an_administrator_withdraws_a_consent_and_the_data_is_marked(api):
    client, headers, _day = api
    path = "/api/publications/consents/mibgas/withdraw"
    assert client.post(path, json={"reason": "x"}, headers=headers["analyst"]).status_code == 403
    response = client.post(path, json={"reason": "publisher asked"}, headers=headers["admin"])
    assert response.status_code == 200, response.text
    assert response.json()["data"]["row"]["line"].startswith("consent withdrawn on ")
    assert client.post(path, json={}, headers=headers["admin"]).status_code == 409
    sources = client.get("/api/publications/sources", headers=headers["analyst"]).json()
    rows = {row["publication_id"]: row for row in sources["data"]["rows"]}
    assert rows["mibgas-prices"]["state"] == "consent_withdrawn"
    assert client.post("/api/publications/consents/nobody/withdraw", json={},
                       headers=headers["admin"]).status_code == 404
    restored = client.post("/api/publications/consents/mibgas/restore",
                           headers=headers["admin"])
    assert restored.status_code == 200 and restored.json()["data"]["row"]["state"] == "in_force"


def test_the_board_reads_the_published_price_dated_with_its_previous_publication(api):
    client, headers, day = api
    response = client.get("/api/market/quotes", params={"limit": 5}, headers=headers["analyst"])
    assert response.status_code == 200, response.text
    quotes = {q["quote_id"]: q for q in response.json()["data"]}
    quote = quotes["pub:mibgas:pvb-da"]
    assert quote["last_price"] == 40.25 and quote["bid_price"] is None
    assert quote["metadata_json"]["price_day"] == day.isoformat()
    assert quote["close_price"] == 41.5
    assert quote["close_day"] == (day - timedelta(days=1)).isoformat()


def test_a_caller_that_presented_nothing_never_gets_consented_prices(api, monkeypatch):
    from eurogas_nexus.core.config import Settings

    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    client = TestClient(create_app(Settings(api_profile="development",
                                            allow_anonymous_callers=True)))
    response = client.get("/api/market/quotes", params={"limit": 50})
    assert response.status_code == 200, response.text
    sources = {q["source_system"] for q in response.json()["data"]}
    assert "EEX_Sim" in sources and "MIBGAS" not in sources
    observations = client.get("/api/market/observations", params={"limit": 50})
    assert observations.status_code == 200
    assert not [r for r in observations.json()["data"] if r.get("source_system") == "MIBGAS"]
