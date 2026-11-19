"""The demo exchange feed: planted prompt cases on schedule, the continuous run through the tick
ingestion, its status line and its retention."""

from __future__ import annotations

import importlib.util
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base

FEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "exchange_feed.py"


def _feed():
    spec = importlib.util.spec_from_file_location("exchange_feed", FEED)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("exchange_feed", module)
    spec.loader.exec_module(module)
    return module


def test_planted_schedule_in_cet():
    feed = _feed()
    # 2026-11-19 is CET (UTC+1): 10:10 CET = 09:10 UTC.
    assert feed.planted_p1(datetime(2026, 11, 19, 9, 10, 30, tzinfo=UTC)) == pytest.approx(0.60)
    assert feed.planted_p1(datetime(2026, 11, 19, 10, 31, tzinfo=UTC)) == pytest.approx(-0.60)
    assert feed.planted_p1(datetime(2026, 11, 19, 9, 14, tzinfo=UTC)) == 0.0
    assert feed.planted_p2(datetime(2026, 11, 19, 9, 5, tzinfo=UTC))  # 10:05 CET
    assert feed.planted_p2(datetime(2026, 11, 19, 14, 9, tzinfo=UTC))  # 15:09 CET
    assert not feed.planted_p2(datetime(2026, 11, 19, 9, 10, tzinfo=UTC))
    assert feed.in_trading_hours(datetime(2026, 11, 19, 6, 0, tzinfo=UTC))  # 07:00 CET
    assert not feed.in_trading_hours(datetime(2026, 11, 19, 18, 0, tzinfo=UTC))  # 19:00 CET


def test_the_generator_lays_the_cases_on_the_path():
    feed = _feed()
    books = {key: feed.Book(*key, feed.FALLBACK[key], feed.FALLBACK[key], *spec, 0.0)
             for key, spec in feed.INSTRUMENTS.items()}
    start = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)  # 10:00 CET: P2 open, P1 from 10:10
    events = feed.session_events(random.Random(1), books, start, 15, 0.0, planted=True)
    p1, p2 = [], []
    for at, _quotes, _trades in events:
        premium = books[("TTF", "WD")].mid - books[("TTF", "DA")].mid
        net = feed._pth_to_eur(books[("NBP", "DA")].mid) - books[("TTF", "DA")].mid - 1.88
        if feed.planted_p1(at):
            p1.append(premium)
        if feed.planted_p2(at):
            p2.append(net)
        elif at > start + timedelta(minutes=10, seconds=5):
            assert net <= -0.30 + 1e-9
    assert p1 and min(p1) > 0.4  # the 0.60 planted premium over a near-zero usual one
    assert p2 and all(value == pytest.approx(0.80) for value in p2)


def test_continuous_run_writes_through_the_ingestion_with_status_and_retention(
    tmp_path, monkeypatch
):
    url = f"sqlite+pysqlite:///{(tmp_path / 'feed.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    from eurogas_nexus.db.models import (
        IngestionRunRecord,
        MarketQuoteRecord,
        MarketTradeRecord,
    )
    from eurogas_nexus.db.session import get_session_factory

    get_session_factory.cache_clear() if hasattr(get_session_factory, "cache_clear") else None
    feed = _feed()
    old = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)
    with Session(engine) as session:
        session.add(MarketQuoteRecord(
            quote_id="old", source_system="DEMO_Sim", venue="Demo", instrument_id="x",
            hub="TTF", product="day-ahead", delivery_start_utc=old, delivery_end_utc=old,
            bid_price=40.0, ask_price=40.1, currency="EUR", unit="MWh", observed_at_utc=old,
            received_at_utc=old, source_reference="feed:simulated-exchange",
            freshness="simulated", quality_score=0.0, simulated=True))
        session.commit()
    clock = {"now": datetime(2026, 11, 19, 9, 9, tzinfo=UTC)}  # 10:09 CET
    monkeypatch.setattr(feed, "PRUNE_EVERY", timedelta(seconds=30))
    monkeypatch.setattr(feed, "BOOK_EVERY_SECONDS", 10**9)

    def sleeper(seconds):
        clock["now"] += timedelta(seconds=seconds)

    assert feed.run_continuous(0.0, clock=lambda: clock["now"], sleeper=sleeper,
                               stop_after=150) == 0
    with Session(engine) as session:
        quotes = session.query(MarketQuoteRecord).filter(
            MarketQuoteRecord.source_reference == "feed:simulated-exchange").all()
        assert quotes and all(q.simulated and q.source_system == "DEMO_Sim" for q in quotes)
        assert "old" not in {q.quote_id for q in quotes}  # pruned after 48 hours
        assert {q.product for q in quotes} == {"within-day", "day-ahead"}
        assert any(q.vwap is not None for q in quotes)
        assert session.query(MarketTradeRecord).count() > 0
        runs = session.query(IngestionRunRecord).filter(
            IngestionRunRecord.source_id == "src-demo-exchange-feed").all()
        assert runs and "messages/s" in runs[0].notes and runs[0].status == "succeeded"


def test_the_feed_can_be_switched_off():
    feed = _feed()
    assert feed.feed_enabled({}) is True
    assert feed.feed_enabled({"EUROGAS_NEXUS_DEMO_EXCHANGE_FEED": "off"}) is False
