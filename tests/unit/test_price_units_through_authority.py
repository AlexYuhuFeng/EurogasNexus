"""Prices are read through the unit authority, never by assuming a unit (demo NBP fix).

The imports store NBP per MWh in GBP with the native p/th value in the metadata; the desk
reads NBP in p/th. A row stored in p/th (a legacy or third-party feed) used to be dropped
silently by every reader (they filtered on ``MWh``); now each reader converts it through
``domain.market.units`` and anything multiplied by MWh uses the per-MWh price.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.projections.daily_closes import daily_rows, in_native_unit, per_mwh
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.domain.market.units import convert_price
from eurogas_nexus.security.identity import AuthenticatedPrincipal

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 7, 7, tzinfo=UTC)


def _caller() -> Caller:
    return Caller(AuthenticatedPrincipal(
        principal_id="p", name="a", principal_type="USER", role="ANALYST", status="ACTIVE",
        data_scopes=("DEMO", "BOOKS:*", "ICE"), roles=("ANALYST",),
    ))


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'p.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    return engine


def _row(oid, unit, currency, price, back=1):
    return MarketObservationRecord(
        observation_id=oid, market_venue="Demo", product="NBP month-ahead", price=price,
        unit=unit, currency=currency,
        period_start_utc=datetime(2026, 12, 1, tzinfo=UTC),
        period_end_utc=datetime(2027, 1, 1, tzinfo=UTC),
        observed_at_utc=NOW - timedelta(days=back), source_system="DEMO_Sim",
        source_reference="t", freshness="end_of_day", quality_score=0.0, research_only=True,
        metadata_json={"hub": "NBP", "tenor": "month-ahead", "simulated": True},
    )


def test_per_mwh_and_native_conversions_are_the_authoritys():
    assert per_mwh(84.5, "GBp/th")[1] == "GBP/MWh"
    assert per_mwh(84.5, "GBp/th")[0] == pytest.approx(convert_price(84.5, "GBp/th", "GBP/MWh"))
    assert per_mwh(31.4, "EUR/MWh") == (31.4, "EUR/MWh")
    assert per_mwh(10.0, "EUR/t") is None  # not a gas price per unit of energy
    shown, unit = in_native_unit("NBP", 28.83, "GBP/MWh")
    assert unit == "GBp/th" and shown == pytest.approx(convert_price(28.83, "GBP/MWh", "GBp/th"))
    assert in_native_unit("TTF", 31.4, "EUR/MWh") == (31.4, "EUR/MWh")
    assert in_native_unit("HH", 3.1, "EUR/MWh") == (3.1, "EUR/MWh")  # native needs FX: kept


def test_a_row_stored_in_pence_per_therm_is_read_not_dropped(store):
    with Session(store) as session:
        session.add(_row("a", "GBp/th", "GBP", 84.5))
        session.add(_row("b", "GBP/MWh", "GBP", 28.0, back=2))
        session.commit()
    rows = {row["price"]: row for row in daily_rows(_caller(), date(2026, 10, 1), NOW.date())}
    assert set(rows) == {84.5, 28.0}
    assert rows[84.5]["unit"] == "GBp/th" and rows[84.5]["unit_mwh"] == "GBP/MWh"
    assert rows[84.5]["price_mwh"] == pytest.approx(convert_price(84.5, "GBp/th", "GBP/MWh"))
    assert rows[28.0]["price_mwh"] == 28.0


def test_marks_and_the_curve_use_the_per_mwh_price(store):
    from eurogas_nexus.application.position_inputs import curve_quotes, ladder_inputs

    with Session(store) as session:
        session.add(_row("a", "GBp/th", "GBP", 84.5))
        session.commit()
    quotes = curve_quotes(_caller(), date(2026, 10, 1), NOW.date())
    assert [q.price for q in quotes] == [pytest.approx(convert_price(84.5, "GBp/th", "GBP/MWh"))]
    inputs = ladder_inputs(_caller(), NOW.date(), NOW.date(), NOW.date() + timedelta(days=60))
    closes = inputs.closes["NBP"]
    assert list(closes.values()) == [pytest.approx(convert_price(84.5, "GBp/th", "GBP/MWh"))]


def test_the_demo_seed_keeps_the_native_quote_beside_the_per_mwh_price(store):
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(store) as session:
        seed.seed(session, NOW)
        session.commit()
        nbp = session.query(MarketObservationRecord).filter(
            MarketObservationRecord.observation_id.like("demo-NBP-%")).all()
        ttf = session.query(MarketObservationRecord).filter(
            MarketObservationRecord.observation_id.like("demo-TTF-%")).first()
    assert nbp and all(row.unit == "GBP/MWh" and row.metadata_json["simulated"] for row in nbp)
    for row in nbp:
        native = row.metadata_json["native"]
        assert native["unit"] == "GBp/th"
        assert native["price"] == round(convert_price(row.price, "GBP/MWh", "GBp/th"), 4)
    assert "native" not in ttf.metadata_json  # EUR/MWh is TTF's native quote
