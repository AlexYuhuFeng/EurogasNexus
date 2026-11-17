"""Price normalisation service: factors from the units authority, heating value, FX, tolerance.

Golden figures carry their arithmetic in the docstrings; the reconciliation test checks the
property that converting a price to another unit and back returns it within the tolerance.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from eurogas_nexus.application.market_normalisation import (
    NormalisationError,
    SeriesPoint,
    conversion,
    normalise_series,
    normalise_value,
)
from eurogas_nexus.domain.market.fx_forward import Delivery, FxHoldings
from eurogas_nexus.domain.market.units import DESK_ASSUMED_GCV_KWH_PER_M3, ENERGY_UNITS_PER_MWH

AS_OF = date(2026, 11, 16)


def _holdings(source: str = "ECB", days: int = 1) -> FxHoldings:
    fx, fixings = [], []
    for back in range(days):
        day = (AS_OF - timedelta(days=back)).isoformat()
        fx += [
            {"pair": "EURGBP", "rate": 0.87, "rate_type": "reference", "value_date": day,
             "source_system": source},
            {"pair": "EURUSD", "rate": 1.16, "rate_type": "reference", "value_date": day,
             "source_system": source},
        ]
        fixings += [
            {"benchmark_id": "SONIA", "value_date": day, "rate_pct": 3.75, "source_system": "BOE"},
            {"benchmark_id": "ESTR", "value_date": day, "rate_pct": 1.90, "source_system": "ECB"},
            {"benchmark_id": "SOFR", "value_date": day, "rate_pct": 4.30,
             "source_system": "NYFED"},
        ]
    return FxHoldings.from_rows(fx, fixings)


def _month(year: int, month: int) -> Delivery:
    first = date(year, month, 1)
    last = (date(year + month // 12, month % 12 + 1, 1)) - timedelta(days=1)
    return Delivery(first, last, "month", f"{first:%b-%y}")


def test_same_currency_unit_change_uses_the_authority_factors():
    """30.00 EUR/MWh in EUR/MMBtu = 30 / 3.41214163 = 8.7921 (no FX, exact factors)."""

    result = normalise_value(30.0, "EUR/MWh", "EUR/MMBtu", holdings=FxHoldings(), as_of=AS_OF)
    assert result["value"] == pytest.approx(30.0 / ENERGY_UNITS_PER_MWH["MMBtu"])
    assert round(result["value"], 4) == 8.7921
    assert result["normalisation"]["fx"] is None
    assert result["normalisation"]["heating_value"] is None
    assert result["tolerance"] == {"absolute": 0.0, "relative_pct": 0.0, "basis": "exact factors"}


def test_usd_mmbtu_to_eur_mwh_at_spot():
    """10.20 USD/MMBtu at EUR/USD 1.16 (spot) in EUR/MWh.

    10.20 × 3.41214163 = 34.80384 USD/MWh; ÷ 1.16 = 30.0033 EUR/MWh.
    """

    result = normalise_value(10.20, "USD/MMBtu", "EUR/MWh", holdings=_holdings(), as_of=AS_OF)
    assert round(result["value"], 4) == 30.0033
    assert result["normalisation"]["fx"]["pair"] == "USDEUR"


def test_volume_unit_needs_a_heating_value_and_says_whether_it_is_assumed():
    """30.00 EUR/MWh in EUR/m3 at the desk's assumed GCV 11.0 kWh/m3 = 30 × 0.011 = 0.33.

    At a stated GCV of 10.5 kWh/m3 it is 30 × 0.0105 = 0.315 EUR/m3.
    """

    assumed = normalise_value(30.0, "EUR/MWh", "EUR/m3", holdings=FxHoldings(), as_of=AS_OF)
    assert assumed["value"] == pytest.approx(30.0 * DESK_ASSUMED_GCV_KWH_PER_M3 / 1000)
    assert assumed["normalisation"]["heating_value"]["basis"] == "assumption"
    stated = normalise_value(
        30.0, "EUR/MWh", "EUR/m3", holdings=FxHoldings(), as_of=AS_OF, gcv_kwh_per_m3=10.5
    )
    assert stated["value"] == pytest.approx(0.315)
    assert stated["normalisation"]["heating_value"]["basis"] == "stated"
    with pytest.raises(NormalisationError) as bad:
        normalise_value(
            30.0, "EUR/MWh", "EUR/m3", holdings=FxHoldings(), as_of=AS_OF, gcv_kwh_per_m3=40
        )
    assert bad.value.code == "implausible_heating_value"


def test_impossible_conversions_are_refused_never_guessed():
    with pytest.raises(NormalisationError, match="not convertible: no EURGBP rate held") as fx:
        normalise_value(78.0, "p/th", "EUR/MWh", holdings=FxHoldings(), as_of=AS_OF)
    assert fx.value.code == "not_convertible"
    with pytest.raises(NormalisationError) as unit:
        normalise_value(30.0, "EUR/MWh", "EUR/t", holdings=FxHoldings(), as_of=AS_OF)
    assert unit.value.code == "unsupported_price_unit"
    with pytest.raises(NormalisationError) as cal:
        normalise_value(
            78.0, "p/th", "EUR/MWh", holdings=_holdings(), as_of=AS_OF,
            delivery=Delivery(date(2029, 1, 1), date(2029, 12, 31), "calendar_year", "Cal-29"),
        )
    assert cal.value.code == "beyond_horizon"


def test_simulated_stays_simulated_and_simulated_fx_makes_it_simulated():
    sim_price = normalise_value(
        30.0, "EUR/MWh", "EUR/MMBtu", holdings=FxHoldings(), as_of=AS_OF, simulated=True
    )
    assert sim_price["simulated"] and sim_price["input_class"] == "simulated"
    sim_fx = normalise_value(
        78.0, "p/th", "EUR/MWh", holdings=_holdings(source="DEMO_Sim"), as_of=AS_OF
    )
    assert sim_fx["simulated"] and sim_fx["input_class"] == "simulated"
    real = normalise_value(
        78.0, "p/th", "EUR/MWh", holdings=_holdings(), as_of=AS_OF, delivery=_month(2027, 1)
    )
    assert not real["simulated"] and real["input_class"] == "derived"


def test_series_uses_each_days_own_fx_and_lists_refusals():
    """Three points: two days with FX held, one (20 days back) without; the third is refused."""

    holdings = _holdings(days=2)
    points = [
        SeriesPoint(AS_OF - timedelta(days=1), 26.6147047, _month(2027, 1)),
        SeriesPoint(AS_OF, 26.6147047, _month(2027, 1)),
        SeriesPoint(AS_OF - timedelta(days=20), 26.6147047, _month(2027, 1)),
    ]
    result = normalise_series(points, "GBP/MWh", "EUR/MWh", holdings=holdings)
    assert result["converted"] == 2
    assert result["refused"] == [
        {"reason": "not convertible: no EURGBP rate held", "points": 1}
    ]
    today = [p for p in result["points"] if p["day"] == AS_OF.isoformat()][0]
    assert round(today["value"], 3) == 30.500
    assert today["fx_method"] == "derived: covered interest parity"
    yesterday = [p for p in result["points"] if p["day"] == "2026-11-15"][0]
    # One day further from 15 Jan: a slightly different forward, from that day's facts.
    assert yesterday["fx_rate"] != today["fx_rate"]
    assert result["fx_labels"] == ["derived (interest parity from SONIA, €STR, flat rate)"]
    assert result["latest"]["fx"]["spot"]["value_date"] == AS_OF.isoformat()


UNITS = ("EUR/MWh", "p/th", "GBP/MWh", "USD/MMBtu", "EUR/GJ", "USD/MWh", "EUR/m3", "GBP/mcm")


def test_reconciliation_round_trip_returns_the_input_within_tolerance():
    """Property: normalise(a → b → a) = a within the conversion's tolerance.

    For every pair of units over random prices and delivery periods (spot, months up to two
    years out, and seasons), converting there and back uses one rate and its inverse, so the
    round trip is exact to floating point; the tolerance carried is the FX tolerance of D.5.
    """

    holdings = _holdings()
    rng = random.Random(20261116)
    deliveries = [None, _month(2026, 12), _month(2027, 1), _month(2027, 9), _month(2028, 6),
                  Delivery(date(2027, 10, 1), date(2028, 3, 31), "season", "Win-27")]
    for _ in range(400):
        a, b = rng.sample(UNITS, 2)
        value = rng.uniform(0.5, 150.0)
        delivery = rng.choice(deliveries)
        there = normalise_value(value, a, b, holdings=holdings, as_of=AS_OF, delivery=delivery)
        back = normalise_value(
            there["value"], b, a, holdings=holdings, as_of=AS_OF, delivery=delivery
        )
        allowed = max(back["tolerance"]["absolute"], 1e-9 * value)
        assert back["value"] == pytest.approx(value, abs=allowed), (a, b, delivery)
        assert back["value"] == pytest.approx(value, rel=1e-12)


def test_conversion_record_states_factors_and_fx():
    conv = conversion(
        "p/th", "EUR/MWh", holdings=_holdings(), as_of=AS_OF, delivery=_month(2027, 1)
    )
    record = conv.record()
    assert record["from_unit"] == "p/th"
    assert record["to_unit"] == "EUR/MWh"
    # 1 p/th = 0.01 GBP/th = 0.341214163 GBP/MWh
    assert record["unit_factor"] == pytest.approx(0.341214163)
    assert [step["step"] for step in record["steps"]] == ["unit", "fx"]
    assert record["fx"]["method"] == "derived: covered interest parity"
    assert record["units_authority"] == "domain.ontology.quantity"
