"""QA-T-01/03/04: a quote carries its as-of, its staleness and the previous close.

- The mid is (bid + ask) / 2 or nothing: a one-sided quote and the last trade are never a mid
  (the backtest pool included).
- ``/api/market/quotes`` adds, per quote, the read instant, the quote's age against the
  source's declared cadence, and the newest daily close of the same hub and tenor before
  today (the desk's settlement source), with its day, kind and source. All fields additive.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.projections.market_reads import annotate_quotes
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord, MarketQuoteRecord

NOW = datetime(2026, 11, 24, 13, 50, tzinfo=UTC)
DA_START = datetime(2026, 11, 25, 5, 0, tzinfo=UTC)
DEC = datetime(2026, 12, 1, tzinfo=UTC)


def _quote(**overrides) -> dict:
    row = {
        "quote_id": "q", "source_system": "EEX_Sim", "hub": "TTF", "product": "day-ahead",
        "delivery_start_utc": DA_START, "bid_price": 41.405, "ask_price": 41.470,
        "last_price": 41.475, "currency": "EUR", "unit": "MWh",
        "observed_at_utc": NOW - timedelta(seconds=20), "simulated": True,
        "prior_settlement_price": None,
    }
    row.update(overrides)
    return row


def _close(day: date, price: float, **overrides) -> dict:
    row = {
        "hub": "TTF", "hub_resolved": True, "tenor": "day-ahead", "source_system": "DEMO_Sim",
        "day": day, "observed_at_utc": datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        "period_start_utc": None, "settlement": False, "price": price, "price_mwh": price,
        "unit_mwh": "EUR/MWh", "simulated": True,
    }
    row.update(overrides)
    return row


def test_previous_close_is_the_newest_before_today_of_the_same_hub_and_tenor() -> None:
    closes = [
        _close(date(2026, 11, 20), 40.10),
        _close(date(2026, 11, 23), 41.20, settlement=True),
        _close(date(2026, 11, 24), 41.90),  # today's print is not a previous close
        _close(date(2026, 11, 23), 99.0, tenor="within-day"),
        _close(date(2026, 11, 23), 35.0, hub="NBP", unit_mwh="GBP/MWh"),
    ]
    [row] = annotate_quotes([_quote()], closes, now=NOW)
    assert row["close_price"] == 41.20
    assert row["close_day"] == "2026-11-23"
    assert row["close_kind"] == "settlement"
    assert row["close_source_system"] == "DEMO_Sim"
    assert row["close_simulated"] is True
    # Existing fields are kept as they were (the change is additive).
    assert row["bid_price"] == 41.405 and row["last_price"] == 41.475


def test_a_close_in_another_currency_basis_is_not_used() -> None:
    [row] = annotate_quotes([_quote(currency="GBP")], [_close(date(2026, 11, 23), 41.2)], now=NOW)
    assert row["close_price"] is None and row["close_kind"] is None


def test_month_ahead_close_must_be_the_same_delivery_month() -> None:
    quote = _quote(product="month-ahead", delivery_start_utc=DEC)
    closes = [
        _close(date(2026, 11, 20), 42.0, tenor="month-ahead", period_start_utc=DEC),
        _close(date(2026, 11, 23), 50.0, tenor="month-ahead",
               period_start_utc=datetime(2027, 1, 1, tzinfo=UTC)),
    ]
    [row] = annotate_quotes([quote], closes, now=NOW)
    assert row["close_price"] == 42.0 and row["close_day"] == "2026-11-20"


def test_without_a_stored_close_the_feed_prior_settlement_is_used_without_a_day() -> None:
    [row] = annotate_quotes([_quote(prior_settlement_price=41.47)], [], now=NOW)
    assert row["close_price"] == 41.47
    assert row["close_day"] is None
    assert row["close_kind"] == "prior_settlement"


def test_age_and_staleness_follow_the_source_cadence() -> None:
    fresh, old, undeclared = annotate_quotes(
        [
            _quote(),
            _quote(observed_at_utc=NOW - timedelta(days=2)),
            _quote(source_system="NO_SUCH_FEED"),
        ],
        [],
        now=NOW,
    )
    assert fresh["as_of_utc"] == NOW.isoformat()
    assert fresh["age_seconds"] == 20.0
    assert fresh["stale_after_seconds"] == 60  # EEX declares a one-minute cadence
    assert fresh["freshness_state"] == "FRESH"
    assert old["age_seconds"] == 2 * 86_400
    assert old["freshness_state"] == "STALE"
    # No declared cadence is never read as fresh.
    assert undeclared["stale_after_seconds"] is None
    assert undeclared["freshness_state"] == "UNKNOWN"


def _record(quote_id: str, **overrides) -> MarketQuoteRecord:
    values = {
        "quote_id": quote_id, "source_system": "EEX_Sim", "venue": "EEX (simulated)",
        "instrument_id": f"EEX-TTF-{quote_id}", "hub": "TTF", "product": "within-day",
        "delivery_start_utc": NOW, "delivery_end_utc": NOW + timedelta(days=1),
        "bid_price": None, "ask_price": 41.5, "last_price": 45.0, "currency": "EUR",
        "unit": "MWh", "observed_at_utc": NOW, "received_at_utc": NOW,
        "source_reference": "test", "freshness": "simulated", "quality_score": 0.0,
        "simulated": True,
    }
    values.update(overrides)
    return MarketQuoteRecord(**values)


def test_quotes_route_carries_as_of_staleness_and_previous_close(tmp_path, monkeypatch) -> None:
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'quotes.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                _record("live", product="day-ahead", bid_price=41.405, ask_price=41.470,
                        last_price=41.475, observed_at_utc=now, received_at_utc=now),
                _record("old", hub="NBP", product="day-ahead", bid_price=35.0,
                        ask_price=35.1, last_price=None, currency="GBP",
                        observed_at_utc=now - timedelta(days=2),
                        received_at_utc=now - timedelta(days=2)),
                MarketObservationRecord(
                    observation_id="close-ttf-da",
                    market_venue="Demo",
                    product="TTF day-ahead",
                    price=41.20,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=yesterday,
                    period_end_utc=now,
                    observed_at_utc=yesterday,
                    source_system="DEMO_Sim",
                    source_reference="test:close",
                    freshness="end_of_day",
                    quality_score=0.0,
                    research_only=True,
                    metadata_json={"hub": "TTF", "tenor": "day-ahead", "simulated": True},
                ),
            ]
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/market/quotes")

    assert response.status_code == 200
    rows = {row["quote_id"]: row for row in response.json()["data"]}
    live, old = rows["live"], rows["old"]
    assert live["as_of_utc"] and live["freshness_state"] == "FRESH"
    assert live["close_price"] == 41.2
    assert live["close_day"] == yesterday.date().isoformat()
    assert live["close_kind"] == "close"
    assert old["freshness_state"] == "STALE" and old["age_seconds"] >= 2 * 86_400 - 5
    assert old["close_price"] is None
