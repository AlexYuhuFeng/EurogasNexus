"""DATA-1 (lesson P2): a client syncs only what changed, through a cursor over market events.

The feed is read-only, ordered, entitlement-filtered per caller and carries digests, never
values. The PostgreSQL ordering guarantee (no committed event is ever skipped) is tested in
``tests/integration/test_change_feed_postgres.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.change_feed import (
    ChangeFeedError,
    Cursor,
    parse_cursor,
    parse_kinds,
    read_changes,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.market_events import MarketEvent

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


def _price(price: str, *, at: datetime, source: str = "EEX") -> MarketEvent:
    return MarketEvent(
        source_id=source,
        event_type="price.updated",
        subject_key="hub:TTF:2027-01",
        ingested_at_utc=at,
        market_time_utc=datetime(2026, 11, 20, 17, 30, tzinfo=UTC),
        published_at_utc=datetime(2026, 11, 20, 17, 30, tzinfo=UTC),
        payload={"price": price, "unit": "MWh", "currency": "EUR"},
        identity="hub:TTF:2027-01|EEX|2026-11-20",
    )


def _fx(at: datetime) -> MarketEvent:
    return MarketEvent(
        source_id="ECB",
        event_type="fx.updated",
        subject_key="fx:EURGBP",
        ingested_at_utc=at,
        market_time_utc=datetime(2026, 11, 20, tzinfo=UTC),
        payload={"rate": "0.87", "rate_type": "reference", "value_date": "2026-11-20"},
    )


def _cargo(at: datetime) -> MarketEvent:
    return MarketEvent(
        source_id="desk-cargoes",
        event_type="cargo.changed",
        subject_key="cargo:SAB-0420",
        ingested_at_utc=at,
        payload={"digest": "abc"},
    )


@pytest.fixture
def feed(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'feed.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        outbox.publish(session, _price("80.0", at=NOW))
        outbox.publish(session, _fx(NOW + timedelta(minutes=1)))
        outbox.publish(session, _cargo(NOW + timedelta(minutes=2)))
        outbox.publish(session, _price("81.5", at=NOW + timedelta(minutes=3)))  # a correction
        session.commit()
    keys = {}
    with Session(engine) as session:
        for name, scopes in (
            ("all", ["*"]),
            ("public", ["ECB"]),
            ("one_book", ["ECB", "EEX", "BOOKS:BOOK:GAS-1"]),
        ):
            owner = create_identity_principal(
                session, name=f"feed-{name}", display_name=name, role="ANALYST",
                data_scopes=scopes,
            )
            _, bearer = create_identity_api_key(
                session, owner.principal_id, display_name=name, scopes=scopes
            )
            keys[name] = bearer
        session.commit()

    def client(who: str = "all") -> TestClient:
        return TestClient(
            create_app(),
            headers={"X-Eurogas-Identity": keys[who], "X-Eurogas-Api-Key": "test-public-api-token"},
        )

    return engine, client


def _page(response):
    assert response.status_code == 200, response.text
    body = response.json()
    return body["data"], body["meta"]


def test_a_client_pages_through_every_change_in_order_and_then_waits(feed):
    _, client = feed
    api = client()
    seen, cursor = [], None
    for _ in range(10):
        params = {"limit": 1, **({"after": cursor} if cursor else {})}
        data, meta = _page(api.get("/api/market/changes", params=params))
        seen.extend(data)
        cursor = meta["next_cursor"]
        if not meta["has_more"]:
            break
    assert [(c["event_type"], c["operation"], c["revision"]) for c in seen] == [
        ("price.updated", "insert", 1),
        ("fx.updated", "insert", 1),
        ("cargo.changed", "insert", 1),
        ("price.updated", "update", 2),
    ]
    correction = seen[-1]
    assert correction["supersedes_event_id"] == seen[0]["event_id"]
    assert correction["subject_key"] == "hub:TTF:2027-01"
    assert correction["dependency_keys"] == ["hub:TTF:2027-01"]
    assert "payload_json" not in correction and "price" not in correction  # a digest only
    assert correction["cursor"] == cursor

    # Nothing new: an empty page, the same cursor, nothing more to read.
    data, meta = _page(api.get("/api/market/changes", params={"after": cursor}))
    assert data == [] and meta["next_cursor"] == cursor and meta["has_more"] is False
    assert meta["retention"].startswith("full history")


def test_after_latest_starts_from_now_and_picks_up_the_next_change(feed):
    engine, client = feed
    api = client()
    data, meta = _page(api.get("/api/market/changes", params={"after": "latest"}))
    assert data == []
    cursor = meta["next_cursor"]
    with Session(engine) as session:
        outbox.publish(session, _price("82.0", at=NOW + timedelta(hours=1)))
        session.commit()
    data, _ = _page(api.get("/api/market/changes", params={"after": cursor}))
    assert [(c["event_type"], c["revision"]) for c in data] == [("price.updated", 3)]


def test_kinds_and_subject_narrow_the_feed(feed):
    _, client = feed
    api = client()
    fx, _ = _page(api.get("/api/market/changes", params={"kinds": "fx.updated"}))
    assert [c["subject_key"] for c in fx] == ["fx:EURGBP"]
    ttf, _ = _page(api.get("/api/market/changes", params={"subject": "hub:TTF"}))
    assert [c["revision"] for c in ttf] == [1, 2]
    both, _ = _page(
        api.get("/api/market/changes", params=[("kinds", "fx.updated"), ("kinds", "cargo.changed")])
    )
    assert [c["event_type"] for c in both] == ["fx.updated", "cargo.changed"]


def test_each_caller_sees_only_what_it_may_read(feed, monkeypatch):
    _, client = feed
    # Isolation switched off explicitly first (it is on by default since security review H1).
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "false")
    public, _ = _page(client("public").get("/api/market/changes"))
    # The EEX settlement is licensed and not this caller's; the cargo is the firm's book.
    assert [c["event_type"] for c in public] == ["fx.updated", "cargo.changed"]
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    one_book, meta = _page(client("one_book").get("/api/market/changes"))
    # With isolation on, a desk event needs every book; the licensed price is granted here.
    assert [c["event_type"] for c in one_book] == ["price.updated", "fx.updated", "price.updated"]
    assert "withheld" not in meta and "scanned" not in meta
    assert [c["event_type"] for c in _page(client().get("/api/market/changes"))[0]].count(
        "cargo.changed"
    ) == 1


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"after": "42"}, "cursor_invalid"),
        ({"after": "c1-x-1"}, "cursor_invalid"),
        ({"kinds": "price.moved"}, "kind_unknown"),
    ],
)
def test_a_bad_cursor_or_kind_is_refused(feed, params, code):
    _, client = feed
    response = client().get("/api/market/changes", params=params)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_cursor_text_round_trips_and_the_reader_works_without_http(feed):
    engine, _ = feed
    assert parse_cursor(Cursor(12, 34).text()) == Cursor(12, 34)
    assert parse_cursor(None) == Cursor(0, 0) and parse_cursor("latest") == "latest"
    with pytest.raises(ChangeFeedError):
        parse_cursor("c1-1")
    assert parse_kinds(["price.updated,fx.updated"]) == ("fx.updated", "price.updated")
    with Session(engine) as session:
        page = read_changes(session, None, limit=2)
        assert len(page.changes) == 2 and page.has_more is True
        rest = read_changes(session, None, after=parse_cursor(page.next_cursor), limit=10)
        assert len(rest.changes) == 2 and rest.has_more is False
        with pytest.raises(ChangeFeedError):
            read_changes(session, None, limit=0)
