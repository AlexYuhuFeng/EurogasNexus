"""A feed's bad prices are refused before they reach a strategy, a mark or the prompt panel.

Persona review P-03 (standard A7): a price a hundred times the market, a forward below zero,
a quote stamped in the future, a jump no market makes between two ticks, and a licensed
label delivered by a key without that licence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.market_ticks import ingest_ticks, publisher_refusal
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketQuoteRecord
from eurogas_nexus.domain.market.feed import (
    FeedError,
    check_jump,
    check_not_future,
    check_plausible_price,
)


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'feed.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _quote(product: str, bid: float, ask: float, at: datetime, hub: str = "TTF") -> dict:
    return {"hub": hub, "product": product, "exchange_time": at.isoformat(), "bid": bid,
            "ask": ask, "bid_qty": 10, "ask_qty": 10}


def test_bands_hold_crisis_prices_and_refuse_keying_errors():
    # TTF within-day near 340 and NBP day-ahead near 800 p/th were real in 2022.
    check_plausible_price(340.0, "EUR/MWh", product_kind="within_day", label="TTF WD")
    check_plausible_price(800.0, "GBp/th", product_kind="day_ahead", label="NBP DA")
    # Within-day has printed below zero; a forward month never has.
    check_plausible_price(-5.0, "EUR/MWh", product_kind="within_day", label="THE WD")
    with pytest.raises(FeedError, match="below the plausible floor"):
        check_plausible_price(-5.0, "EUR/MWh", product_kind="month", label="TTF Jan-27")
    with pytest.raises(FeedError, match="above the plausible ceiling"):
        check_plausible_price(3_100.0, "EUR/MWh", product_kind="month", label="TTF Jan-27")


def test_future_stamps_and_jumps_are_refused():
    now = datetime.now(UTC)
    check_not_future(now + timedelta(seconds=30), now, label="x")  # venue clock skew
    with pytest.raises(FeedError, match="after it was received"):
        check_not_future(now + timedelta(hours=1), now, label="x")
    check_jump(39.0, 31.0, label="x")
    check_jump(0.9, 0.2, label="x")  # near zero the ratio means nothing
    with pytest.raises(FeedError, match="keying or unit error"):
        check_jump(310.0, 31.0, label="x")
    with pytest.raises(FeedError, match="keying or unit error"):
        check_jump(3.1, 31.0, label="x")


def test_a_fat_finger_in_a_batch_stores_nothing(session):
    now = datetime.now(UTC) - timedelta(minutes=1)
    ingest_ticks(session, source_system="EEX", quotes=[_quote("DA", 31.0, 31.1, now)])
    session.commit()
    stored = session.query(MarketQuoteRecord).count()

    later = now + timedelta(seconds=20)
    for bad in (
        [_quote("DA", 310.0, 310.1, later)],  # ten times the last quote
        [_quote("DA", 3_100.0, 3_100.1, later)],  # a hundred times: above the ceiling
        [_quote("M+1", -31.1, -31.0, later)],  # a forward month below zero
        [_quote("DA", 31.0, 31.1, datetime.now(UTC) + timedelta(hours=2))],  # future
        # A good tick then a bad one: the whole batch goes back.
        [_quote("DA", 31.2, 31.3, later), _quote("DA", 93.0, 93.1, later + timedelta(1))],
    ):
        with pytest.raises(FeedError):
            ingest_ticks(session, source_system="EEX", quotes=bad)
        session.rollback()
    assert session.query(MarketQuoteRecord).count() == stored

    ingest_ticks(session, source_system="EEX", quotes=[_quote("DA", 33.0, 33.1, later)])
    assert session.query(MarketQuoteRecord).count() == stored + 1


def test_trade_prints_are_held_to_the_same_bands(session):
    now = datetime.now(UTC)
    with pytest.raises(FeedError, match="above the plausible ceiling"):
        ingest_ticks(session, source_system="EEX", quotes=[], trades=[
            {"trade_id": "t1", "hub": "TTF", "product": "M+1", "price": 3_150,
             "qty": 5, "exchange_time": now.isoformat()}])


def test_a_licensed_label_needs_its_own_grant():
    """Only a connector's service key with PUBLISH:<family> writes a venue's label (H4)."""

    def key(*scopes, kind="SERVICE", auth="identity_key"):
        return SimpleNamespace(data_scopes=scopes, principal_type=kind, auth_method=auth)

    star = key("*")
    reader = key("EEX")
    feed = key("PUBLISH:EEX")
    assert "may not deliver EEX" in publisher_refusal(star, "EEX")
    assert "may not deliver EEX" in publisher_refusal(reader, "EEX")
    assert publisher_refusal(feed, "EEX") is None
    assert publisher_refusal(feed, "ICE_OCM") is not None
    # A person, a browser session and the deployment token never publish a venue's price.
    assert "a person" in publisher_refusal(key("PUBLISH:EEX", kind="USER"), "EEX")
    assert publisher_refusal(key("PUBLISH:EEX", auth="session"), "EEX") is not None
    assert publisher_refusal(key("PUBLISH:EEX", auth="legacy_public_token"), "EEX") is not None
    # Simulated prices carry their label everywhere and need no licence.
    assert publisher_refusal(star, "EEX_Sim") is None
