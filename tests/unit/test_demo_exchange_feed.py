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


def test_the_feed_pauses_for_the_seed_clear_lock():
    """The seed and the feed use one lock key; without a PostgreSQL connection the feed runs."""

    feed = _feed()
    seed = _seed()
    assert feed.SEED_LOCK == seed.SEED_CLEAR_LOCK
    assert feed.seed_clear_in_progress(None) is False


# ---------------------------------------------------------------------------------------------
# The live screen (the continuous feed): cadence, coverage, coherence, session and notices
# ---------------------------------------------------------------------------------------------

SEED = FEED.with_name("seed_demo_desk.py")
#: 03:27 CET on a gas day with no planted L1 or W1 (gas day 2026-11-18): the hour the owner
#: looked at the public demo and nothing moved.
NIGHT = datetime(2026, 11, 19, 2, 27, tzinfo=UTC)


def _seed():
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("seed_demo_desk", module)
    spec.loader.exec_module(module)
    return sys.modules["seed_demo_desk"]


def _board(now=NIGHT):
    """The demo board of the gas day at ``now`` from a seasonal month-ahead per hub (no store)."""

    from datetime import date

    seed = _seed()
    market_module = seed._load_demo_market()
    market = seed._demo_market(market_module)
    anchors = {(hub, currency): (seed._curve_price(hub, date(2026, 12, 1)), now)
               for hub, currency in seed.DEMO_PRICE_HUBS}
    return seed, market, seed.demo_board_rows(market_module, market, anchors, now, [], fed=set())


def _screen(now=NIGHT, seed_text="cadence"):
    feed = _feed()
    _seed_module, market, rows = _board(now)
    anchors = feed.anchors_from_quotes(rows)
    screen = feed.LiveScreen(anchors, random.Random(seed_text), now, dislocations_per_hour=0.0)
    return feed, market, screen


def _run(screen, start, seconds, step=0.5):
    """Step the screen on a fake clock; returns every (time, quote) and print in order."""

    quotes, trades = [], []
    for n in range(1, int(seconds / step) + 1):
        now = start + timedelta(seconds=n * step)
        batch, printed = screen.step(now)
        assert all(datetime.fromisoformat(q["exchange_time"]) <= now for q in batch)
        quotes += batch
        trades += printed
    return quotes, trades


def test_every_demo_hub_is_quoted_on_its_own_clock_every_one_to_five_seconds():
    feed, _market, screen = _screen()
    quotes, trades = _run(screen, NIGHT, 600)
    hubs = {"TTF", "NBP", "THE", "PEG", "ZTP", "PSV", "CEGH", "PVB", "ETF"}
    # Every demo hub, the Danish one once: GTF is the OTC name of ETF, not a second hub.
    assert set(screen.hubs) == hubs
    times: dict[tuple[str, str], list[datetime]] = {}
    for quote in quotes:
        times.setdefault((quote["hub"], quote["product"]), []).append(
            datetime.fromisoformat(quote["exchange_time"]))
    for hub in hubs:
        for code in feed.FAST_PRODUCTS:
            stamps = times[(hub, code)]
            gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:], strict=False)]
            assert max(gaps) <= 5.0 + 1e-9, (hub, code)
            if code in feed.PROMPT_PRODUCTS:
                assert min(gaps) >= 1.0 - 1e-9, (hub, code)
            assert 600 / 5 <= len(stamps) <= 600 / 1 + 1
        for code in feed.BACK_CURVE:  # with the front, in whole-curve moves 20-60 s apart
            stamps = times[(hub, code)]
            gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:], strict=False)]
            assert stamps and 20.0 - 1e-9 <= min(gaps) and max(gaps) <= 60.0 + 1e-9
    per_second = len(quotes) / 600
    assert 15 < per_second < 30  # about 20 quotes a second across 207 instruments
    assert trades and len(trades) / 600 < 1.0  # the odd print
    assert all(q["trade_count"] is not None and q["prior_settlement"] for q in quotes)


def test_quotes_move_on_the_tick_and_stay_anchored_to_the_demo_board():
    feed, _market, screen = _screen(seed_text="anchored")
    anchors = {key: book.anchor for key, book in screen.books.items()}
    quotes, _trades = _run(screen, NIGHT, 3600, step=1.0)
    moved = set()
    last: dict[tuple[str, str], tuple[float, float]] = {}
    for quote in quotes:
        key = (quote["hub"], quote["product"])
        tick = screen.books[key].tick
        for side in ("bid", "ask"):
            assert abs(quote[side] / tick - round(quote[side] / tick)) < 1e-6
        assert quote["bid"] < quote["ask"]
        mid = (quote["bid"] + quote["ask"]) / 2
        if key == ("TTF", "WD"):
            mid -= feed.planted_p1(datetime.fromisoformat(quote["exchange_time"]))
        # Within a few tenths of the board (NBP in p/th: about 2.5 times the EUR/MWh figure).
        bound = 0.75 if quote["hub"] == "NBP" else 0.3
        assert abs(mid - anchors[key]) < bound, key
        if key in last and last[key] != (quote["bid"], quote["ask"]):
            moved.add(key)
        last[key] = (quote["bid"], quote["ask"])
    assert {key for key in screen.books if key[1] in ("DA", "M+1")} <= moved


def _latest(quotes):
    latest = {}
    for quote in quotes:
        latest[(quote["hub"], quote["product"])] = quote
    return latest


def test_no_arbitrage_within_a_hub_and_spreads_inside_the_route_cost_band():
    from eurogas_nexus.domain.market.products import resolve_product

    feed, market, screen = _screen(seed_text="coherent")
    trading_day = resolve_product("WD", datetime(2026, 11, 18).date()).first_gas_day
    months = {code: resolve_product(code, trading_day) for code in feed.CURVE_PRODUCTS}
    held: dict[tuple[str, str], dict] = {}
    checked_strips = checked_routes = 0
    for minute in range(60):
        start = NIGHT + timedelta(minutes=minute)
        quotes, _trades = _run(screen, start, 60, step=1.0)
        held.update(_latest(quotes))
        if minute < 2:
            continue  # every back-curve product has been requoted once
        for hub in screen.hubs:
            # A strip's bid never above its months' average offer, its offer never below
            # their average bid (day-weighted): buying one and selling the other loses.
            for strip in ("Q+1", "Q+2", "Q+3", "S+1"):
                period = months[strip]
                parts = [code for code, month in months.items() if month.kind == "month"
                         and period.first_gas_day <= month.first_gas_day <= period.last_gas_day]
                days = [(months[c].last_gas_day - months[c].first_gas_day).days + 1
                        for c in parts]
                total = sum(days)
                if total != (period.last_gas_day - period.first_gas_day).days + 1:
                    continue  # a month of the strip is not on the board
                bid = sum(held[(hub, c)]["bid"] * d for c, d in zip(parts, days, strict=True))
                ask = sum(held[(hub, c)]["ask"] * d for c, d in zip(parts, days, strict=True))
                assert held[(hub, strip)]["bid"] <= ask / total + 1e-9, (hub, strip)
                assert held[(hub, strip)]["ask"] >= bid / total - 1e-9, (hub, strip)
                checked_strips += 1
        # Locational: buying at one hub's mid and selling at another's nets below the
        # simulated route cost (DA and the front month), in EUR/MWh at the demo fixing.
        for code in ("DA", "M+1"):
            for (buy, sell), cost in market.route_costs.items():
                if (buy, code) not in held or (sell, code) not in held:
                    continue
                eur = {}
                for hub in (buy, sell):
                    mid = (held[(hub, code)]["bid"] + held[(hub, code)]["ask"]) / 2
                    eur[hub] = feed._pth_to_eur(mid) if hub == "NBP" else mid
                assert eur[sell] - eur[buy] - cost < 0.0, (code, buy, sell)
                checked_routes += 1
    assert checked_strips > 1000 and checked_routes > 1000


def test_the_planted_prompt_cases_still_hold_on_the_live_screen():
    feed, _market, screen = _screen(datetime(2026, 11, 19, 9, 0, tzinfo=UTC), "planted")
    p1, p2 = [], []
    start = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)  # 10:00 CET: P2 open, P1 from 10:10
    for n in range(1, 15 * 60 + 1):
        now = start + timedelta(seconds=n)
        screen.step(now)
        premium = screen.mid(("TTF", "WD")) - screen.mid(("TTF", "DA"))
        net = feed._pth_to_eur(screen.mid(("NBP", "DA"))) - screen.mid(("TTF", "DA")) - 1.88
        at = screen.t  # the screen's own time: its last quote
        if feed.planted_p1(at):
            p1.append(premium)
        if feed.planted_p2(at):
            p2.append(net)
        else:
            assert net <= -0.30 + 1e-9
    assert p1 and min(p1) > 0.3
    assert p2 and all(value == pytest.approx(0.80) for value in p2)


def test_the_demo_only_24_hour_session_switch():
    feed = _feed()
    assert feed.feed_session({}) == "exchange"  # anything not the demo keeps 07:00-19:00 CET
    assert feed.feed_session({"EUROGAS_NEXUS_DEMO_FEED_SESSION": "24h"}) == "24h"
    assert feed.feed_session({"EUROGAS_NEXUS_DEMO_FEED_SESSION": "exchange"}) == "exchange"
    assert not feed.in_session(NIGHT, "exchange")
    assert feed.in_session(NIGHT, "24h")
    assert feed.in_session(datetime(2026, 11, 19, 9, 0, tzinfo=UTC), "exchange")
    assert "real ICE Endex and EEX sessions differ" in feed.SESSION_LABELS["24h"]
    demo = FEED.with_name("start_public_demo.py").read_text(encoding="utf-8")
    assert '"EUROGAS_NEXUS_DEMO_FEED_SESSION": "24h"' in demo  # the hosted demo's default


def _store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'feed.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    from eurogas_nexus.db.session import get_session_factory

    get_session_factory.cache_clear() if hasattr(get_session_factory, "cache_clear") else None
    return engine


def _fake_clock(start):
    clock = {"now": start}

    def sleeper(seconds):
        clock["now"] += timedelta(seconds=seconds)

    return clock, sleeper


@pytest.mark.parametrize(("mode", "quoted"), [("24h", True), ("exchange", False)])
def test_at_night_the_demo_session_quotes_and_the_exchange_session_pauses(
    tmp_path, monkeypatch, mode, quoted
):
    from eurogas_nexus.db.models import IngestionRunRecord, MarketQuoteRecord

    engine = _store(tmp_path, monkeypatch)
    feed = _feed()
    monkeypatch.setattr(feed, "BOOK_EVERY_SECONDS", 10**9)
    clock, sleeper = _fake_clock(NIGHT)
    assert feed.run_continuous(0.0, clock=lambda: clock["now"], sleeper=sleeper,
                               stop_after=400, session_mode=mode) == 0
    with Session(engine) as session:
        count = session.query(MarketQuoteRecord).count()
        notes = " ".join(run.notes for run in session.query(IngestionRunRecord))
    if quoted:
        assert count > 400 and "24-hour demo session" in notes and "sessions differ" in notes
    else:
        assert count == 0 and "paused outside simulated trading hours" in notes


def test_new_ticks_raise_one_prices_notice_per_poll_and_nothing_between(tmp_path, monkeypatch):
    from eurogas_nexus.application.live_topics import topic_changes

    engine = _store(tmp_path, monkeypatch)
    feed = _feed()
    monkeypatch.setattr(feed, "BOOK_EVERY_SECONDS", 10**9)
    clock, sleeper = _fake_clock(NIGHT)
    feed.run_continuous(0.0, clock=lambda: clock["now"], sleeper=sleeper, stop_after=20,
                        session_mode="24h")
    with Session(engine) as session:
        notices = topic_changes(session, ("prices",), {"prices": None})
        assert [notice["topic"] for notice in notices] == ["prices"]
        cursor = notices[0]["cursor"]
        assert topic_changes(session, ("prices",), {"prices": cursor}) == []
    clock["now"] += timedelta(seconds=1)
    feed.run_continuous(0.0, clock=lambda: clock["now"], sleeper=sleeper, stop_after=5,
                        session_mode="24h")
    with Session(engine) as session:
        later = topic_changes(session, ("prices",), {"prices": cursor})
        assert len(later) == 1 and later[0]["changed_at"] > cursor


def test_quotes_older_than_an_hour_are_thinned_to_one_per_instrument_per_ten_minutes(
    tmp_path, monkeypatch
):
    from eurogas_nexus.db.models import MarketQuoteRecord

    engine = _store(tmp_path, monkeypatch)
    feed = _feed()
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
    delivery = datetime(2026, 11, 20, 5, 0, tzinfo=UTC)
    with Session(engine) as session:
        for n in range(3 * 360):  # three hours, one quote every 10 s, two instruments
            at = now - timedelta(seconds=10 * n)
            for instrument in ("A", "B"):
                session.add(MarketQuoteRecord(
                    quote_id=f"{instrument}-{n}", source_system="DEMO_Sim", venue="Demo",
                    instrument_id=instrument, hub="TTF", product="day-ahead",
                    delivery_start_utc=delivery, delivery_end_utc=delivery, bid_price=40.0,
                    ask_price=40.1, currency="EUR", unit="MWh", observed_at_utc=at,
                    received_at_utc=at, source_reference=feed.FEED_REFERENCE,
                    freshness="simulated", quality_score=0.0, simulated=True))
        session.commit()
        removed, until = feed._thin(session, now, None)
        session.commit()
        assert removed > 0 and until <= now - feed.RAW_KEEP
        rows = session.query(MarketQuoteRecord.instrument_id,
                             MarketQuoteRecord.observed_at_utc).all()
        recent = [r for r in rows if r[1].replace(tzinfo=UTC) >= until]
        older = [r for r in rows if r[1].replace(tzinfo=UTC) < until]
        assert len(recent) == 2 * 361  # the last hour (11:00-12:00) whole
        buckets = {(i, feed._bucket(at)) for i, at in older}
        assert len(older) == len(buckets)  # one per instrument and ten minutes
        # A second pass finds nothing new to thin.
        assert feed._thin(session, now, until)[0] == 0
