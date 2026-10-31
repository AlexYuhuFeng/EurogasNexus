"""The common foundation: ISO currencies and quote units, FX, dimensioned units, time."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from eurogas_nexus.domain.ontology.currency import (
    CURRENCIES,
    CurrencyError,
    FxRate,
    FxTable,
    Money,
    resolve_quote_unit,
)
from eurogas_nexus.domain.ontology.markets import MARKETS
from eurogas_nexus.domain.ontology.quantity import UnitError, convert, convert_price, price_unit
from eurogas_nexus.domain.ontology.timebase import (
    NaiveDatetimeError,
    business_date,
    office_local,
    require_utc,
)
from eurogas_nexus.domain.ontology.vocabulary import Currency as CurrencyEnum

D = date(2026, 10, 30)


def test_every_market_and_vocabulary_currency_is_iso():
    for m in MARKETS:
        assert m.currency in CURRENCIES, m.code
        price_unit(m.price_unit)  # every native quote parses
    for item in CurrencyEnum:
        assert item.value in CURRENCIES


def test_quote_units_resolve_to_iso_with_divisors():
    assert resolve_quote_unit("GBp") == ("GBP", 100)
    assert resolve_quote_unit("GBP") == ("GBP", 1)
    assert resolve_quote_unit("CNH") == ("CNY", 1)
    assert resolve_quote_unit("cny") == ("CNY", 1)
    with pytest.raises(CurrencyError):
        resolve_quote_unit("XYZ")
    assert Money(Decimal("1234.5"), "JPY").rounded() == Decimal("1234")
    assert Money(Decimal("10.005"), "EUR").rounded() == Decimal("10.00")


def test_fx_direct_inverse_and_pivot_and_no_guessing():
    table = FxTable.from_pivot_map({"GBP": 0.8, "USD": 1.25, "CNY": 8.0}, as_of=D, source="ECB")
    assert table.rate("EUR", "GBP") == 0.8
    assert table.rate("GBP", "EUR") == pytest.approx(1.25)
    assert table.rate("GBP", "CNY") == pytest.approx(10.0)
    assert table.rate("USD", "USD") == 1.0
    with pytest.raises(CurrencyError):
        table.rate("EUR", "CAD")
    newer = FxRate("EUR", "GBP", 0.9, date(2026, 10, 31), "ECB")
    table.add(newer)
    assert table.rate("EUR", "GBP") == 0.9


def test_units_convert_within_dimensions_only():
    assert convert(1, "MWh", "th") == pytest.approx(34.1214163, rel=1e-8)
    assert convert(1, "MWh", "GJ") == pytest.approx(3.6)
    assert convert(2, "mcm", "m3") == 2e6
    with pytest.raises(UnitError):
        convert(1, "mcm", "MWh")


def test_price_conversion_across_units_and_currencies():
    fx = FxTable.from_pivot_map({"GBP": 0.85}, as_of=D, source="ECB")
    # 85 p/th = 0.85 GBP/th = 29.003 GBP/MWh = 34.12 EUR/MWh
    eur = convert_price(85, "GBp/th", "EUR/MWh", fx)
    assert eur == pytest.approx(34.1214163, rel=1e-6)
    assert convert_price(3.6, "CAD/GJ", "CAD/MWh") == pytest.approx(12.96)
    with pytest.raises(UnitError):
        convert_price(70, "EUR/t", "EUR/MWh", fx)
    with pytest.raises(UnitError):
        convert_price(1, "USD/MMBtu", "EUR/MWh")  # no FX given


def test_time_rules():
    with pytest.raises(NaiveDatetimeError):
        require_utc(datetime(2026, 10, 30, 12))
    instant = datetime(2026, 10, 30, 4, 30, tzinfo=UTC)  # 05:30 Berlin (CET) before 06:00
    assert business_date(instant, "TTF") == date(2026, 10, 29)
    assert business_date(datetime(2026, 10, 30, 5, 30, tzinfo=UTC), "TTF") == date(2026, 10, 30)
    # NAESB: 09:00 Chicago (CDT, UTC-5) = 14:00 UTC
    assert business_date(datetime(2026, 10, 30, 13, 0, tzinfo=UTC), "HH") == date(2026, 10, 29)
    assert office_local(instant, "SG").hour == 12
