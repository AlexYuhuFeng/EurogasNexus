"""Market reference model: commodities, regions and the pricing points a desk trades.

This is the reference-data backbone ("static data" in an ETRM): one definition per market
of what it is, where it is, what currency and unit it quotes in, which delivery calendar
and time zone it settles on, and whose licence its prices come under. Hub lists, unit
conventions and currency rules elsewhere in the code read from here instead of keeping
their own copies.

It is versioned code, reviewed like code. Runtime instances (observations, contracts,
positions) stay in PostgreSQL and refer to markets by ``code``. Adding a commodity or a
region is a data change here plus the ingestion and analytics that use it; nothing else
needs to know the list.

Calendars: ``EU-CAM-UTC-2025`` (European gas day, 06:00 CET/CEST), ``NAESB`` (North
American gas day, 09:00 Central), ``POWER-HOURLY`` (power and emissions trade calendar
days or hours in the market's time zone). A market with ``calendar=None`` has no delivery
calendar implemented yet and cannot be used for delivery-period arithmetic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Commodity(StrEnum):
    NATURAL_GAS = "natural_gas"
    LNG = "lng"
    POWER = "power"
    EMISSIONS = "emissions"
    COAL = "coal"


class Region(StrEnum):
    EUROPE = "europe"
    NORTH_AMERICA = "north_america"
    ASIA = "asia"
    GLOBAL = "global"


class MarketStatus(StrEnum):
    ACTIVE = "active"
    #: Kept for history; ``superseded_by`` names the successor (NCG and GASPOOL -> THE).
    SUPERSEDED = "superseded"
    #: Defined for architecture and reference; no ingestion or analytics yet.
    PLANNED = "planned"


@dataclass(frozen=True)
class Market:
    """One pricing point: a gas hub, LNG marker, power zone, emissions or coal benchmark."""

    code: str
    name: str
    commodity: Commodity
    region: Region
    country: str  # ISO 3166 alpha-2, or "EU"/"" for multi-country benchmarks
    currency: str  # ISO 4217 of the quote
    price_unit: str  # native quotation, e.g. "GBp/th", "EUR/MWh", "EUR/t"
    quantity_unit: str  # native quantity, e.g. "th/d", "MW", "t"
    timezone: str
    calendar: str | None
    status: MarketStatus = MarketStatus.ACTIVE
    superseded_by: str | None = None
    #: Source families whose licences cover settlement or screen prices for this market.
    price_sources: tuple[str, ...] = ()
    #: Public, commercially reusable price reference where one exists.
    public_reference: str | None = None
    #: Other names the same hub is written under (an old name, an exchange's or a TSO's
    #: name). Every intake resolves an alias to ``code``; nothing is stored under an alias.
    aliases: tuple[str, ...] = ()
    #: The name a venue lists this hub under, where venues differ (venue -> name), e.g.
    #: EEX lists the Danish hub as ETF and OTC/Energinet name it GTF. Display only: the
    #: hub's identity is ``code`` on every venue.
    venue_names: tuple[tuple[str, str], ...] = ()
    #: Power markets: the gas hub and carbon market that set a gas plant's fuel cost.
    gas_hub: str | None = None
    carbon_market: str | None = None


_EU_GAS = dict(
    commodity=Commodity.NATURAL_GAS,
    region=Region.EUROPE,
    currency="EUR",
    price_unit="EUR/MWh",
    quantity_unit="MW",
    timezone="Europe/Berlin",
    calendar="EU-CAM-UTC-2025",
)
_EU_GAS_SOURCES = ("EEX", "ICE_ENDEX", "Trayport")


def _eu_gas(code: str, name: str, country: str, **overrides) -> Market:
    fields = {**_EU_GAS, "price_sources": _EU_GAS_SOURCES, **overrides}
    return Market(code=code, name=name, country=country, **fields)


def _power(code: str, name: str, country: str, currency: str = "EUR", **overrides) -> Market:
    fields = dict(
        commodity=Commodity.POWER,
        region=Region.EUROPE,
        currency=currency,
        price_unit=f"{currency}/MWh",
        quantity_unit="MW",
        timezone="Europe/Brussels",
        calendar="POWER-HOURLY",
        price_sources=("EEX", "EPEX", "Nord_Pool", "ICE_ENDEX"),
        public_reference="ENTSO-E day-ahead price (A44)",
        carbon_market="EUA",
    )
    return Market(code=code, name=name, country=country, **{**fields, **overrides})


MARKETS: tuple[Market, ...] = (
    # European gas hubs.
    # TTF only: ETF is the Danish exchange hub, never an alias of the Dutch one (owner
    # decision 2026-11-15). No hub's aliases may name another registered hub
    # (tests/unit/test_market_reference.py guards this).
    _eu_gas("TTF", "Title Transfer Facility", "NL"),
    _eu_gas(
        "NBP",
        "National Balancing Point",
        "GB",
        currency="GBP",
        price_unit="GBp/th",
        quantity_unit="th/d",
        timezone="Europe/London",
        price_sources=("ICE_ENDEX", "Trayport"),
    ),
    _eu_gas("THE", "Trading Hub Europe", "DE"),
    # PEG Nord and TRS merged on 1 Nov 2018 into one zone, Trading Region France (TRF), whose
    # trading point is PEG: TRF is the zone's name for the same hub.
    _eu_gas("PEG", "Point d'Echange de Gaz", "FR", aliases=("TRF",)),
    _eu_gas("ZTP", "Zeebrugge Trading Point", "BE"),
    _eu_gas("PSV", "Punto di Scambio Virtuale", "IT", timezone="Europe/Rome"),
    _eu_gas("CEGH", "Central European Gas Hub (VTP)", "AT", aliases=("VTP",)),
    _eu_gas("PVB", "Punto Virtual de Balance", "ES", timezone="Europe/Madrid"),
    # Denmark (joint DK/SE balancing zone) has one virtual trading point, written two ways:
    # ETF (Exchange Transfer Facility) is the EEX product name, GTF (Gas Transfer Facility)
    # Energinet's and the OTC market's name, ENTSOG VTP-00001 "GTF (Bilateral Trading
    # Point)". One hub, one code (owner decision 2026-11-26, superseding the 2026-11-15
    # split): ETF, with GTF and the former exchange's name Gaspoint Nordic as aliases, so a
    # tick, a close, a contract or a map node written either way is the same hub. Assumption,
    # not verified against a licensed feed: EUR/MWh and MW on the European gas day.
    _eu_gas(
        "ETF",
        "Danish VTP: ETF (EEX) / GTF (OTC), joint DK/SE balancing zone",
        "DK",
        timezone="Europe/Copenhagen",
        price_sources=("EEX", "Trayport"),
        aliases=("GTF", "GASPOINT"),
        venue_names=(("EEX", "ETF"), ("OTC", "GTF"), ("Energinet", "GTF")),
    ),
    _eu_gas(
        "NCG",
        "NetConnect Germany",
        "DE",
        status=MarketStatus.SUPERSEDED,
        superseded_by="THE",
    ),
    _eu_gas(
        "GASPOOL",
        "Gaspool",
        "DE",
        status=MarketStatus.SUPERSEDED,
        superseded_by="THE",
    ),
    # LNG and other gas markers.
    Market(
        code="JKM",
        name="Japan Korea Marker",
        commodity=Commodity.LNG,
        region=Region.ASIA,
        country="",
        currency="USD",
        price_unit="USD/MMBtu",
        quantity_unit="MMBtu",
        timezone="Asia/Singapore",
        calendar=None,
        price_sources=("Platts", "ICE"),
    ),
    Market(
        code="HH",
        name="Henry Hub",
        commodity=Commodity.NATURAL_GAS,
        region=Region.NORTH_AMERICA,
        country="US",
        currency="USD",
        price_unit="USD/MMBtu",
        quantity_unit="MMBtu/d",
        timezone="America/Chicago",
        calendar="NAESB",
        price_sources=("CME", "ICE"),
        public_reference="EIA daily Henry Hub spot (RNGWHHD), public domain",
        aliases=("HENRY_HUB",),
    ),
    Market(
        code="AECO",
        name="AECO-C / NIT (Alberta)",
        commodity=Commodity.NATURAL_GAS,
        region=Region.NORTH_AMERICA,
        country="CA",
        currency="CAD",
        price_unit="CAD/GJ",
        quantity_unit="GJ/d",
        timezone="America/Edmonton",
        # The NGTL gas day is not modelled yet; add its calendar with the Canada desk.
        calendar=None,
        status=MarketStatus.PLANNED,
        price_sources=("NGX",),
    ),
    # European power (bidding zones).
    _power("DE_LU", "Germany-Luxembourg power", "DE", gas_hub="THE"),
    _power("FR", "France power", "FR", gas_hub="PEG", timezone="Europe/Paris"),
    _power("NL", "Netherlands power", "NL", gas_hub="TTF", timezone="Europe/Amsterdam"),
    _power("BE", "Belgium power", "BE", gas_hub="ZTP"),
    _power(
        "GB",
        "Great Britain power",
        "GB",
        currency="GBP",
        timezone="Europe/London",
        price_sources=("EPEX", "Nord_Pool", "ICE_ENDEX"),
        gas_hub="NBP",
        carbon_market="UKA",
    ),
    Market(
        code="AESO",
        name="Alberta pool price",
        commodity=Commodity.POWER,
        region=Region.NORTH_AMERICA,
        country="CA",
        currency="CAD",
        price_unit="CAD/MWh",
        quantity_unit="MW",
        timezone="America/Edmonton",
        calendar="POWER-HOURLY",
        status=MarketStatus.PLANNED,
        public_reference="AESO pool price (public API, registration required)",
    ),
    # Emissions.
    Market(
        code="EUA",
        name="EU Allowance (EU ETS)",
        commodity=Commodity.EMISSIONS,
        region=Region.EUROPE,
        country="EU",
        currency="EUR",
        price_unit="EUR/t",
        quantity_unit="t",
        timezone="Europe/Berlin",
        calendar="POWER-HOURLY",
        price_sources=("ICE_ENDEX", "EEX"),
        public_reference="EEX primary auction clearing prices (published auction results)",
    ),
    Market(
        code="UKA",
        name="UK Allowance (UK ETS)",
        commodity=Commodity.EMISSIONS,
        region=Region.EUROPE,
        country="GB",
        currency="GBP",
        price_unit="GBP/t",
        quantity_unit="t",
        timezone="Europe/London",
        calendar="POWER-HOURLY",
        price_sources=("ICE_ENDEX",),
        public_reference="UK ETS auction clearing prices (ICE, published auction results)",
    ),
    Market(
        code="TIER",
        name="Alberta TIER emission offsets and performance credits",
        commodity=Commodity.EMISSIONS,
        region=Region.NORTH_AMERICA,
        country="CA",
        currency="CAD",
        price_unit="CAD/t",
        quantity_unit="t",
        timezone="America/Edmonton",
        calendar=None,
        status=MarketStatus.PLANNED,
    ),
    # Coal.
    Market(
        code="API2",
        name="API 2 coal, CIF ARA",
        commodity=Commodity.COAL,
        region=Region.EUROPE,
        country="",
        currency="USD",
        price_unit="USD/t",
        quantity_unit="t",
        timezone="Europe/London",
        calendar=None,
        price_sources=("ICE_ENDEX", "EEX", "Argus"),
        public_reference="World Bank Pink Sheet monthly coal prices (CC BY 4.0), monthly only",
    ),
)

_BY_CODE: dict[str, Market] = {}
for _market in MARKETS:
    for _key in (_market.code, *_market.aliases):
        if _key.upper() in _BY_CODE:
            raise ValueError(f"duplicate market code or alias: {_key}")
        _BY_CODE[_key.upper()] = _market


class UnknownMarket(KeyError):
    """The code names no market in the reference model."""


def market(code: str) -> Market:
    """The market for a code or alias (case-insensitive)."""

    try:
        return _BY_CODE[(code or "").strip().upper()]
    except KeyError as exc:
        raise UnknownMarket(code) from exc


def find_market(code: str) -> Market | None:
    return _BY_CODE.get((code or "").strip().upper())


def markets(
    *,
    commodity: Commodity | Iterable[Commodity] | None = None,
    region: Region | None = None,
    include: Iterable[MarketStatus] = (MarketStatus.ACTIVE,),
) -> tuple[Market, ...]:
    """Markets filtered by commodity, region and status (active only by default)."""

    commodities = (
        None
        if commodity is None
        else {commodity}
        if isinstance(commodity, Commodity)
        else set(commodity)
    )
    statuses = set(include)
    return tuple(
        m
        for m in MARKETS
        if (commodities is None or m.commodity in commodities)
        and (region is None or m.region is region)
        and m.status in statuses
    )


def canonical_hub(code: str | None) -> str | None:
    """The registry code a hub code or alias names (``GTF`` -> ``ETF``, ``VTP`` -> ``CEGH``).

    ``None`` for text that names no market. A superseded market (NCG) keeps its own code:
    its history is not its successor's price.
    """

    found = find_market(code or "")
    return found.code if found else None


def venue_name(code: str, venue: str) -> str:
    """The name ``venue`` lists hub ``code`` under (``ETF`` on EEX, ``GTF`` OTC)."""

    found = market(code)
    return dict(found.venue_names).get(venue, found.code)


def market_codes(**filters) -> tuple[str, ...]:
    return tuple(m.code for m in markets(**filters))


def quote_currency(code: str, default: str = "EUR") -> str:
    """Currency a market quotes in; ``default`` for codes outside the model."""

    found = find_market(code)
    return found.currency if found else default


def european_gas_hubs(*, include_superseded: bool = False) -> tuple[str, ...]:
    statuses = (MarketStatus.ACTIVE, MarketStatus.SUPERSEDED) if include_superseded else None
    return market_codes(
        commodity=Commodity.NATURAL_GAS,
        region=Region.EUROPE,
        **({"include": statuses} if statuses else {}),
    )
