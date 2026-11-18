"""The demo market simulator: coherent by construction, planted cases exactly where documented."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord, MarketQuoteRecord

DEMO = Path(__file__).resolve().parents[2] / "scripts" / "demo"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", DEMO / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


SEED = _load("seed_demo_desk")
MARKET = _load("demo_market")
SEEDED_AT = datetime(2026, 11, 13, 9, tzinfo=UTC)  # a Friday


@pytest.fixture(scope="module")
def store():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        SEED.seed(session, SEEDED_AT, history_days=60)
        session.commit()
        yield session


def _closes(session, hub: str, tenor: str) -> dict[date, MarketObservationRecord]:
    rows = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_reference == "demo:market",
                MarketObservationRecord.product.like(f"{hub} %"))
        .all()
    )
    return {
        row.observed_at_utc.date(): row for row in rows if row.metadata_json["tenor"] == tenor
    }


def _market():
    return MARKET.DemoMarket(SEED._curve_price, eur_per_mwh_to_native=SEED._native_price)


@pytest.mark.parametrize("hub", ["TTF", "NBP", "CEGH", "PVB"])
def test_quarters_seasons_and_years_are_the_day_weighted_average_of_their_months(hub):
    market = _market()
    day, month_ahead = date(2026, 11, 13), 38.4 if hub != "NBP" else 33.1
    tick = MARKET.tick_of(hub)
    for code in ("Q+1", "Q+2", "S+1", "S+2", "Cal+1"):
        period, _start, _end = SEED._delivery(code, day)
        strip = market.strip(hub, day, month_ahead, period.first_gas_day, period.last_gas_day)
        months, weights = [], []
        month = period.first_gas_day
        while month <= period.last_gas_day:
            nxt = MARKET.month_start(month, 1)
            months.append(MARKET.round_to_tick(
                SEED._native_price(hub, market.month_price(hub, day, month_ahead, month)), tick))
            weights.append((nxt - month).days)
            month = nxt
        average = sum(price * weight for price, weight in zip(months, weights, strict=True))
        average /= sum(weights)
        assert abs(MARKET.round_to_tick(SEED._native_price(hub, strip), tick) - average) <= tick


def test_every_board_quote_is_two_sided_on_the_tick_and_labelled_simulated(store):
    quotes = store.query(MarketQuoteRecord).filter(
        MarketQuoteRecord.source_reference == "demo:market").all()
    hubs = {quote.hub for quote in quotes}
    assert hubs == {hub for hub, _ in SEED.DEMO_PRICE_HUBS}
    for hub in hubs:
        labels = {quote.product for quote in quotes if quote.hub == hub}
        assert {"WD", "DA", "WE", "Q1-27", "Sum-27", "Win-27", "Cal-27"} <= labels, hub
    for quote in quotes:
        meta = quote.metadata_json
        tick = meta["tick"]
        assert quote.simulated is True and quote.source_system.endswith("_Sim")
        assert meta["native_bid"] < meta["native_mid"] < meta["native_ask"], quote.quote_id
        for side in ("native_bid", "native_ask"):
            assert abs(meta[side] / tick - round(meta[side] / tick)) < 1e-6, quote.quote_id
        assert quote.bid_price < quote.ask_price
    nbp = next(q for q in quotes if q.hub == "NBP" and q.product == "DA")
    assert nbp.metadata_json["native_unit"] == "GBp/th"


def test_closes_cover_the_history_for_every_rolling_product(store):
    for tenor in MARKET.HISTORY_TENORS:
        days = _closes(store, "TTF", tenor)
        assert len(days) >= 55, tenor
    row = next(iter(_closes(store, "TTF", "day-ahead").values()))
    assert row.metadata_json["simulated"] is True and row.source_system == "DEMO_Sim"


def test_prompt_products_stay_around_the_front_month(store):
    market = _market()
    for day, row in _closes(store, "THE", "day-ahead").items():
        month_ahead = SEED._month_ahead_history(store, "THE", day - timedelta(days=1))[day][0]
        front = market.month_price("THE", day, month_ahead, MARKET.month_start(day))
        assert abs(row.price - front) < 2.0


def test_l1_and_w1_hold_exactly_on_their_planted_days(store):
    ttf = _closes(store, "TTF", "day-ahead")
    nbp = _closes(store, "NBP", "day-ahead")
    wd = _closes(store, "TTF", "within-day")
    l1_days = w1_days = 0
    for day, ttf_row in ttf.items():
        net = nbp[day].price / MARKET.DEMO_EURGBP - ttf_row.price - MARKET.BBL_ROUTE_COST_EUR_MWH
        if MARKET.l1_planted(day):
            l1_days += 1
            assert net > 0.5, day
            assert nbp[day].metadata_json.get("demo_planted_case") == "L1-nbp-over-ttf-da"
        else:
            assert net < 0, day
        gap = wd[day].price - ttf_row.price
        if MARKET.w1_planted(day):
            w1_days += 1
            assert gap > 1.0, day
        else:
            assert abs(gap) <= 0.25 + 1e-6, day
    assert l1_days >= 2 and w1_days >= 2
    for hub, _currency in SEED.DEMO_PRICE_HUBS:
        if hub == "TTF":
            continue
        da = _closes(store, hub, "day-ahead")
        for day, row in _closes(store, hub, "within-day").items():
            assert abs(row.price - da[day].price) <= 0.25 + 1e-6, (hub, day)


def test_t1_only_cegh_winter_over_summer_exceeds_storage_cost(store):
    newest = max(_closes(store, "TTF", "day-ahead"))
    exceeding = set()
    for hub, _currency in SEED.DEMO_PRICE_HUBS:
        summer = _closes(store, hub, "sum-27")[newest].price
        winter = _closes(store, hub, "win-27")[newest].price
        spread = winter - summer
        if hub == "NBP":
            spread /= MARKET.DEMO_EURGBP
        if spread > MARKET.STORAGE_COST_EUR_MWH:
            exceeding.add(hub)
    assert exceeding == {"CEGH"}


def test_roll_forward_over_a_weekend_and_a_month_turn_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        friday = datetime(2026, 11, 27, 9, tzinfo=UTC)
        SEED.seed(session, friday, history_days=20)
        session.commit()
        for later in (friday + timedelta(days=3), datetime(2026, 12, 2, 9, tzinfo=UTC)):
            first = SEED.roll_forward(session, later)
            session.commit()
            assert first["market_close_rows"] > 0
            snapshot = {
                row.observation_id: row.price
                for row in session.query(MarketObservationRecord).filter(
                    MarketObservationRecord.source_reference == "demo:market")
            }
            again = SEED.roll_forward(session, later)
            session.commit()
            assert again["market_close_rows"] == 0 and again["market_quote_rows"] == 0
            after = {
                row.observation_id: row.price
                for row in session.query(MarketObservationRecord).filter(
                    MarketObservationRecord.source_reference == "demo:market")
            }
            assert after == snapshot
        board = {q.product for q in session.query(MarketQuoteRecord).filter(
            MarketQuoteRecord.hub == "TTF",
            MarketQuoteRecord.observed_at_utc >= datetime(2026, 12, 2, tzinfo=UTC))}
        assert {"DA", "WD", "BOM", "Jan-27", "Q1-27"} <= board


def test_the_shared_random_sequence_is_untouched():
    """The market draws from its own named stream: the seed's other series are as before."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        SEED.seed(session, SEEDED_AT, history_days=10)
        session.commit()
        before = {
            row.observation_id: row.price
            for row in session.query(MarketObservationRecord).filter(
                MarketObservationRecord.source_reference == "demo:history")
        }
    original = SEED.seed_demo_market
    try:
        SEED.seed_demo_market = lambda *_args, **_kwargs: {}
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            SEED.seed(session, SEEDED_AT, history_days=10)
            session.commit()
            without = {
                row.observation_id: row.price
                for row in session.query(MarketObservationRecord).filter(
                    MarketObservationRecord.source_reference == "demo:history")
            }
    finally:
        SEED.seed_demo_market = original
    assert before == without


def test_the_seed_script_runs_main_only_after_every_definition():
    """The script is run as ``python seed_demo_desk.py``: code after the ``__main__`` guard
    is not defined when main() runs (the demo market did exactly that once)."""

    import ast

    tree = ast.parse((DEMO / "seed_demo_desk.py").read_text(encoding="utf-8"))
    last = tree.body[-1]
    assert isinstance(last, ast.If) and "__main__" in ast.unparse(last.test)
