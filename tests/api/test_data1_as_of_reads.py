"""DATA-1 (lesson P1): prices, FX and observations read "as known at T".

A settlement is stored in place and corrected by overwrite; change capture keeps each figure
as a revision of one outbox event. A read as of an instant answers with the revision current
then, its number, its publication time and when this store first held it. Without ``as_of``
nothing changes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.as_of_reads import AsOfError, parse_as_of
from eurogas_nexus.application.market_event_capture import capture_rows
from eurogas_nexus.application.price_resolver import open_price_book
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

TRADE = datetime(2026, 11, 20, 17, 30, tzinfo=UTC)  # Friday's close
FIRST = datetime(2026, 11, 20, 18, 0, tzinfo=UTC)  # first received
CORRECTED = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)  # correction received on Monday


def _settlement(price: float, *, source: str = "EEX") -> MarketObservationRecord:
    return MarketObservationRecord(
        observation_id=f"obs-{source.lower()}-ttf-2027-01-20261120",
        market_venue=source,
        product="TTF",
        price=price,
        unit="MWh",
        currency="EUR",
        period_start_utc=datetime(2027, 1, 1, tzinfo=UTC),
        period_end_utc=datetime(2027, 2, 1, tzinfo=UTC),
        observed_at_utc=TRADE,
        source_system=source,
        source_reference="operator-export:test.csv",
        source_record_id=None,
        freshness="current",
        quality_score=1.0,
        research_only=False,
        metadata_json={"hub": "TTF", "settlement": True},
    )


def _fixing(rate: float) -> FxObservationRecord:
    return FxObservationRecord(
        observation_id="fx-ecb-eurgbp-20261120",
        pair="EURGBP",
        base_currency="EUR",
        quote_currency="GBP",
        rate=rate,
        rate_type="reference",
        value_date="2026-11-20",
        observed_at_utc=datetime(2026, 11, 20, 15, 0, tzinfo=UTC),
        source_system="ECB",
        source_reference="ecb",
        source_record_id=None,
        freshness="current",
        research_only=False,
        metadata_json={},
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'asof.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        stored = session.merge(_settlement(80.0))
        fixing = session.merge(_fixing(0.8700))
        capture_rows(session, settlements=[stored], fixings=[fixing], now_utc=FIRST)
        session.commit()
    with Session(engine) as session:
        stored = session.merge(_settlement(81.5))  # the correction overwrites the row
        fixing = session.merge(_fixing(0.8712))
        capture_rows(session, settlements=[stored], fixings=[fixing], now_utc=CORRECTED)
        session.commit()
    keys = {}
    with Session(engine) as session:
        for name, scopes in (("all", ["*"]), ("public", [])):
            owner = create_identity_principal(
                session, name=f"desk-{name}", display_name=name, role="ANALYST",
                data_scopes=scopes,
            )
            _, bearer = create_identity_api_key(
                session, owner.principal_id, display_name=name, scopes=scopes or ["ECB"]
            )
            keys[name] = bearer
        session.commit()

    def client(who: str = "all") -> TestClient:
        return TestClient(
            create_app(),
            headers={"X-Eurogas-Identity": keys[who], "X-Eurogas-Api-Key": "test-public-api-token"},
        )

    return engine, client


def _data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_a_settlement_reads_as_known_before_and_after_its_correction(store):
    _, client = store
    api = client()
    current = _data(api.get("/api/market/observations"))
    assert [row["price"] for row in current] == [81.5]
    assert "revision" not in current[0]  # without as_of nothing changes

    friday = _data(api.get("/api/market/observations", params={"as_of": "2026-11-21T08:00:00Z"}))
    assert len(friday) == 1
    assert friday[0]["price"] == 80.0
    assert friday[0]["revision"] == 1
    assert friday[0]["revision_basis"] == "market_event"
    assert friday[0]["published_at_utc"] == TRADE.isoformat()
    assert friday[0]["known_from_utc"] == FIRST.isoformat()
    assert friday[0]["as_of_utc"] == "2026-11-21T08:00:00+00:00"

    monday = _data(api.get("/api/market/observations", params={"as_of": "2026-11-23T10:00:00Z"}))
    assert monday[0]["price"] == 81.5 and monday[0]["revision"] == 2
    assert monday[0]["known_from_utc"] == CORRECTED.isoformat()

    # Before the store first held the close, it was not known, though its trade day is past.
    early = _data(api.get("/api/market/observations", params={"as_of": "2026-11-20T17:45:00Z"}))
    assert early == []


def test_an_fx_fixing_reads_as_known_at_an_instant(store):
    _, client = store
    api = client()
    before = _data(api.get("/api/market/fx", params={"as_of": "2026-11-22T00:00:00Z"}))
    after = _data(api.get("/api/market/fx", params={"as_of": "2026-11-23T12:00:00Z"}))
    assert before[0]["rate"] == pytest.approx(0.87) and before[0]["revision"] == 1
    assert after[0]["rate"] == pytest.approx(0.8712) and after[0]["revision"] == 2
    assert "revision" not in _data(api.get("/api/market/fx"))[0]


def test_the_price_strip_reads_the_curve_as_known_at_an_instant(store):
    _, client = store
    api = client()
    params = {"hub": "TTF", "start": "2027-01", "months": 2}
    friday = _data(api.get("/api/market/prices", params={**params, "as_of": "2026-11-21T08:00Z"}))
    assert [row["month"] for row in friday] == ["2027-01", "2027-02"]
    jan = friday[0]
    assert jan["value"] == pytest.approx(80.0) and jan["kind"] == "settlement"
    assert jan["revision"] == 1 and jan["known_from_utc"] == FIRST.isoformat()
    assert jan["published_at_utc"] == TRADE.isoformat()
    # A month with no price is still a row, with empty price fields (stable shape).
    assert friday[1]["value"] is None and friday[1]["revision"] is None
    assert set(friday[1]) == set(jan)

    monday = _data(api.get("/api/market/prices", params={**params, "as_of": "2026-11-23T09:30Z"}))
    assert monday[0]["value"] == pytest.approx(81.5) and monday[0]["revision"] == 2

    live = api.get("/api/market/prices", params=params).json()
    assert live["data"][0]["value"] == pytest.approx(81.5)
    assert live["data"][0]["revision"] == 2 and live["meta"]["as_of_utc"] is None
    assert live["meta"]["columns"][:2] == ["hub", "month"]


def test_a_correction_not_yet_captured_is_reported_as_pending(store):
    engine, _ = store
    with Session(engine) as session:
        session.merge(_settlement(82.0))  # stored, capture not run
        session.commit()
        later = CORRECTED + timedelta(hours=1)
        book = open_price_book(session, None, now=later, with_versions=True)
        resolved = book.month("TTF", "2027-01")
        assert resolved.value == pytest.approx(82.0)  # the live book reads the stored row
        assert book.versions[resolved.reference].basis == "capture_pending"
        known = open_price_book(session, None, known_at=CORRECTED + timedelta(hours=1))
        assert known.month("TTF", "2027-01").value == pytest.approx(81.5)


def test_a_tick_is_known_from_its_receipt(store):
    engine, _ = store
    observed = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MarketQuoteRecord(
                quote_id="q-1", source_system="ICE_OCM", source_record_id=None, venue="ICE",
                instrument_id="TTF-JAN27", hub="TTF", product="M+2",
                delivery_start_utc=datetime(2027, 1, 1, tzinfo=UTC),
                delivery_end_utc=datetime(2027, 2, 1, tzinfo=UTC),
                bid_price=82.4, ask_price=82.6, last_price=None, bid_quantity_mwh=None,
                ask_quantity_mwh=None, currency="EUR", unit="EUR/MWh",
                observed_at_utc=observed, received_at_utc=observed + timedelta(minutes=2),
                source_reference="feed", freshness="current", quality_score=1.0,
                simulated=False, metadata_json={},
            )
        )
        session.commit()
        before = open_price_book(session, None, known_at=observed + timedelta(minutes=1))
        assert before.month("TTF", "2027-01").kind == "settlement"
        after = open_price_book(session, None, known_at=observed + timedelta(minutes=3))
        tick = after.month("TTF", "2027-01")
        assert tick.kind == "live_tick" and tick.value == pytest.approx(82.5)
        version = after.versions[tick.reference]
        assert version.revision == 1 and version.basis == "tick"
        assert version.known_from_utc == observed + timedelta(minutes=2)


def test_entitlement_still_applies_to_as_of_reads(store):
    _, client = store
    public = client("public")
    monday = {"as_of": "2026-11-23T10:00Z"}
    assert _data(public.get("/api/market/observations", params=monday)) == []
    strip = _data(
        public.get(
            "/api/market/prices",
            params={"hub": "TTF", "start": "2027-01", "months": 1, "as_of": "2026-11-23T10:00Z"},
        )
    )
    assert strip[0]["value"] is None  # the EEX close is not this caller's to read


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"as_of": "yesterday"}, "as_of_invalid"),
        ({"as_of": "2099-01-01T00:00:00Z"}, "as_of_in_future"),
    ],
)
def test_an_unusable_as_of_is_refused(store, params, code):
    _, client = store
    response = client().get("/api/market/observations", params=params)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({}, "hub_required"),
        ({"hub": "NOWHERE"}, "hub_unknown"),
        ({"hub": "TTF", "start": "2027/01"}, "start_invalid"),
    ],
)
def test_an_unusable_strip_is_refused(store, params, code):
    _, client = store
    response = client().get("/api/market/prices", params=params)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_as_of_parsing():
    now = datetime(2026, 11, 24, 12, tzinfo=UTC)
    assert parse_as_of(None) is None and parse_as_of("  ") is None
    assert parse_as_of("2026-11-20T17:30:00Z", now=now) == TRADE
    assert parse_as_of("2026-11-20T18:30:00+01:00", now=now) == TRADE
    assert parse_as_of("2026-11-20T17:30:00", now=now) == TRADE  # naive is UTC
    assert parse_as_of("2026-11-20", now=now) == datetime(2026, 11, 20, tzinfo=UTC)
    with pytest.raises(AsOfError):
        parse_as_of("2026-11-24T12:06:00Z", now=now)
