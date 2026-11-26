"""``/api/market/observations`` pages by keyset with a visible limit (backend audit A4c)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord

TOKEN = {"X-Eurogas-Api-Key": "test-public-api-token"}
NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'obs.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for index in range(25):
            # Pairs of rows share an instant: the id breaks the tie, so none is skipped.
            observed = NOW - timedelta(hours=index // 2)
            session.add(
                MarketObservationRecord(
                    observation_id=f"obs-{index:03d}",
                    market_venue="ECB" if index % 3 else "EEX",
                    product="TTF Month-Ahead" if index % 2 else "NBP Day-Ahead",
                    price=30.0 + index,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=observed,
                    period_end_utc=observed + timedelta(days=1),
                    observed_at_utc=observed,
                    source_system="ECB",
                    source_reference="test",
                    freshness="fresh",
                    quality_score=1.0,
                    research_only=True,
                    metadata_json={},
                )
            )
        session.commit()
    for name in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    return TestClient(create_app(Settings(api_profile="development")))


def _walk(client, **params):
    seen, cursor, pages = [], None, 0
    while True:
        query = {**params, **({"cursor": cursor} if cursor else {})}
        response = client.get("/api/market/observations", params=query, headers=TOKEN)
        assert response.status_code == 200, response.text
        body = response.json()
        continuation = body["meta"]["continuation"]
        assert continuation["returned"] == len(body["data"]) <= continuation["limit"]
        seen.extend(row["observation_id"] for row in body["data"])
        pages += 1
        if not continuation["has_more"]:
            assert continuation["cursor"] is None
            return seen, pages
        cursor = continuation["cursor"]


def test_every_row_once_newest_first_with_ties(client) -> None:
    seen, pages = _walk(client, limit=4)
    assert pages == 7
    assert len(seen) == len(set(seen)) == 25
    assert seen[0] in {"obs-000", "obs-001"}


def test_the_default_page_states_its_limit(client) -> None:
    body = client.get("/api/market/observations", headers=TOKEN).json()
    assert body["meta"]["continuation"]["limit"] == 1000
    assert body["meta"]["continuation"]["has_more"] is False
    assert len(body["data"]) == 25


def test_a_range_and_a_product_narrow_the_walk(client) -> None:
    window = {
        "from_utc": (NOW - timedelta(hours=3)).isoformat(),
        "to_utc": (NOW - timedelta(hours=1)).isoformat(),
    }
    seen, _ = _walk(client, limit=2, **window)
    assert sorted(seen) == [f"obs-{i:03d}" for i in range(2, 8)]
    ttf, _ = _walk(client, limit=5, product="TTF")
    assert len(ttf) == 12


def test_a_cursor_with_other_filters_and_a_naive_bound_are_refused(client) -> None:
    first = client.get("/api/market/observations", params={"limit": 3}, headers=TOKEN).json()
    cursor = first["meta"]["continuation"]["cursor"]
    other = client.get(
        "/api/market/observations", params={"limit": 3, "cursor": cursor, "product": "NBP"},
        headers=TOKEN,
    )
    assert other.status_code == 400
    assert other.json()["error"] == "page_cursor_filter_mismatch"
    naive = client.get(
        "/api/market/observations", params={"from_utc": "2026-11-26T00:00:00"}, headers=TOKEN
    )
    assert naive.status_code == 400
    assert naive.json()["error"] == "page_window_timezone_required"


def test_csv_pages_say_so_in_headers(client) -> None:
    response = client.get(
        "/api/market/observations", params={"format": "csv", "limit": 10}, headers=TOKEN
    )
    assert response.status_code == 200
    assert response.headers["x-eurogas-has-more"] == "true"
    assert response.headers["x-eurogas-page-limit"] == "10"
    assert response.headers["x-eurogas-next-cursor"]


def test_fx_pages_the_same_way(client) -> None:
    body = client.get("/api/market/fx", params={"limit": 5}, headers=TOKEN).json()
    assert body["meta"]["continuation"]["limit"] == 5
