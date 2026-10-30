"""The market reference model is the one list of commodities, regions and pricing points."""

from datetime import date

import pytest

from eurogas_nexus.domain.market.gas_day import GAS_DAY_CALENDARS, gas_day_start_for_date
from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT, canonical_price_unit
from eurogas_nexus.domain.ontology.markets import (
    MARKETS,
    Commodity,
    MarketStatus,
    Region,
    UnknownMarket,
    european_gas_hubs,
    market,
    markets,
    quote_currency,
)
from eurogas_nexus.domain.ontology.vocabulary import MARKET_HUB_SUPERSESSIONS, MarketHub


def test_every_gas_hub_in_the_vocabulary_is_a_market():
    for hub in MarketHub:
        assert market(hub.value).commodity is Commodity.NATURAL_GAS
    for old, new in MARKET_HUB_SUPERSESSIONS.items():
        assert market(old).status is MarketStatus.SUPERSEDED
        assert market(old).superseded_by == new


def test_gas_calendars_exist_and_units_parse():
    for m in MARKETS:
        if m.commodity in (Commodity.NATURAL_GAS,) and m.calendar:
            assert m.calendar in GAS_DAY_CALENDARS, m.code
        if m.commodity in (Commodity.NATURAL_GAS, Commodity.LNG):
            assert canonical_price_unit(m.price_unit) == m.price_unit


def test_desk_conventions_come_from_the_model():
    assert quote_currency("NBP") == "GBP" and quote_currency("TTF") == "EUR"
    assert quote_currency("AECO") == "CAD"
    assert HUB_NATIVE_PRICE_UNIT["NBP"] == "GBp/th"
    assert market("etf").code == "TTF" and market("VTP").code == "CEGH"
    assert "NCG" not in european_gas_hubs() and "NCG" in european_gas_hubs(include_superseded=True)
    with pytest.raises(UnknownMarket):
        market("NOPE")


def test_new_commodities_and_regions_are_one_entry_away():
    assert {m.code for m in markets(commodity=Commodity.EMISSIONS)} >= {"EUA", "UKA"}
    assert market("API2").commodity is Commodity.COAL
    planned = markets(region=Region.NORTH_AMERICA, include=(MarketStatus.PLANNED,))
    assert {"AECO", "AESO", "TIER"} <= {m.code for m in planned}


def test_naesb_gas_day_starts_at_nine_central():
    start = gas_day_start_for_date(date(2026, 1, 15), "NAESB")
    assert (start.hour, start.minute) == (15, 0)  # 09:00 CST = 15:00 UTC
    summer = gas_day_start_for_date(date(2026, 7, 15), "NAESB")
    assert summer.hour == 14  # 09:00 CDT
