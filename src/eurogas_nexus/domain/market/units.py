"""Energy and price unit conversion for European gas.

Continental hubs (TTF, THE, PEG, ZTP, PSV, CEGH) quote EUR/MWh; NBP quotes pence
per therm (GBp/th); LNG and Henry Hub references quote USD/MMBtu. A desk compares
them all the time, so the conversion factors live in one place and FX is always an
explicit input - this module never looks up or invents an exchange rate.

Factors use the International Table BTU (1 BTU = 1055.05585262 J), which is the
basis for the UK therm used at NBP and for the MMBtu:

- 1 MWh = 3600 MJ = 34.1214163 therm = 3.41214163 MMBtu = 3.6 GJ;
- volume (m3, mcm) to energy needs a gross calorific value (kWh/m3) that differs by
  source and network, so it is a mandatory argument, never a default.

本模块集中管理欧洲天然气常用能量与价格单位换算（€/MWh、便士/撒姆、美元/MMBtu）；
汇率与热值必须由调用方显式提供，模块不会自行假设。
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from eurogas_nexus.domain.ontology.markets import Commodity, MarketStatus, markets
from eurogas_nexus.domain.ontology.quantity import UNITS as _ONTOLOGY_UNITS
from eurogas_nexus.domain.ontology.quantity import Dimension as _Dimension
from eurogas_nexus.domain.ontology.quantity import convert as _convert

BTU_JOULES = 1055.05585262
MJ_PER_MWH = 3600.0

#: Amount of each energy unit that equals one MWh. Derived from the ontology's unit table
#: (``domain.ontology.quantity``), the one place a conversion factor is written; ``therm``
#: is this module's historical spelling of the ontology's ``th``.
ENERGY_UNITS_PER_MWH: dict[str, float] = {
    ("therm" if code == "th" else code): 1.0 / unit.in_base
    for code, unit in _ONTOLOGY_UNITS.items()
    if unit.dimension is _Dimension.ENERGY and code != "MJ"
}

#: Supported price quotations: (currency, minor-unit divisor, energy unit).
PRICE_UNITS: dict[str, tuple[str, float, str]] = {
    "EUR/MWh": ("EUR", 1.0, "MWh"),
    "GBP/MWh": ("GBP", 1.0, "MWh"),
    "USD/MWh": ("USD", 1.0, "MWh"),
    "GBp/th": ("GBP", 100.0, "therm"),
    "USD/MMBtu": ("USD", 1.0, "MMBtu"),
    "EUR/GJ": ("EUR", 1.0, "GJ"),
    "CAD/GJ": ("CAD", 1.0, "GJ"),
    "EUR/kWh": ("EUR", 1.0, "kWh"),
}

#: Native quotation per gas and LNG market, for display next to normalised values. Read
#: from the market reference model (``domain.ontology.markets``), aliases included.
HUB_NATIVE_PRICE_UNIT: dict[str, str] = {
    key: m.price_unit
    for m in markets(
        commodity=(Commodity.NATURAL_GAS, Commodity.LNG),
        include=(MarketStatus.ACTIVE, MarketStatus.SUPERSEDED),
    )
    for key in (m.code, *m.aliases)
}

_ALIASES = {
    "P/TH": "GBp/th",
    "PENCE/THERM": "GBp/th",
    "GBX/TH": "GBp/th",
    "$/MMBTU": "USD/MMBtu",
    "€/MWH": "EUR/MWh",
}


#: The calorific value a desk assumes when a volume is quoted without one (kWh per m3, gross,
#: at the EU interoperability reference conditions below). It is an assumption, so every
#: figure computed with it says so; ``volume_to_mwh`` itself still requires it explicitly.
DESK_ASSUMED_GCV_KWH_PER_M3 = 11.0
#: Reference conditions of that value (Regulation (EU) 2015/703, Article 13).
DESK_GCV_REFERENCE_CONDITIONS = "GCV, combustion 25 °C, volume 0 °C, 101.325 kPa"
#: The range :func:`volume_to_mwh` accepts as a natural-gas GCV (kWh per m3).
GCV_RANGE_KWH_PER_M3 = (8.0, 13.0)


class UnitConversionError(ValueError):
    """Unknown unit, missing FX rate or missing calorific value."""


def canonical_price_unit(unit: str) -> str:
    """Return the canonical spelling of a price unit.

    Raises:
        UnitConversionError: When the unit is not supported.
    """

    upper = (unit or "").strip().upper()
    if upper in _ALIASES:
        return _ALIASES[upper]
    for known in PRICE_UNITS:
        if known.upper() == upper:
            return known
    raise UnitConversionError(f"unsupported price unit: {unit!r}")


def convert_energy(value: float, from_unit: str, to_unit: str) -> float:
    """Convert an energy quantity between :data:`ENERGY_UNITS_PER_MWH` units.

    Raises:
        UnitConversionError: When either unit is unknown.
    """

    for name in (from_unit, to_unit):
        if name not in ENERGY_UNITS_PER_MWH:
            raise UnitConversionError(f"unsupported energy unit: {name!r}")
    return _convert(value, _ontology_code(from_unit), _ontology_code(to_unit))


def _ontology_code(unit: str) -> str:
    return "th" if unit == "therm" else unit


def volume_to_mwh(cubic_metres: float, gcv_kwh_per_m3: float) -> float:
    """Convert a gas volume to energy with an explicit gross calorific value.

    Raises:
        UnitConversionError: When the calorific value is not a plausible natural-gas GCV.
    """

    low, high = GCV_RANGE_KWH_PER_M3
    if not low <= gcv_kwh_per_m3 <= high:
        raise UnitConversionError("gcv_kwh_per_m3 must be an explicit natural-gas GCV (8-13)")
    return cubic_metres * gcv_kwh_per_m3 / 1000.0


#: Energy in one cubic metre of liquid LNG (MWh, gross) a desk assumes when an operator states a
#: slot in m3 of LNG without its own factor. LNG of usual European import quality holds about
#: 6.1 to 6.9 MWh per m3 of liquid (about 570 to 610 m3 of gas at 10.5 to 11.5 kWh/m3); an
#: operator's own factor replaces it, and every figure computed with this one says so.
DESK_ASSUMED_LNG_MWH_PER_M3 = Decimal("6.5")
#: The range :func:`lng_m3_to_mwh` accepts as an LNG factor (MWh per m3 of liquid).
LNG_MWH_PER_M3_RANGE = (Decimal("5.5"), Decimal("7.5"))
#: Units a regas slot is stated in, and MWh per one unit where the factor is fixed.
#: ``m3_lng`` needs a stated factor (:func:`lng_m3_to_mwh`).
SLOT_ENERGY_UNITS: dict[str, Decimal | None] = {
    "MWh": Decimal(1),
    "GWh": Decimal(1000),
    "kWh": Decimal("0.001"),
    "MMBtu": Decimal(1) / Decimal(str(_convert(1.0, "MWh", "MMBtu"))),
    "therm": Decimal(1) / Decimal(str(_convert(1.0, "MWh", "th"))),
    "m3_lng": None,
}


def lng_m3_to_mwh(cubic_metres: Decimal, mwh_per_m3: Decimal) -> Decimal:
    """Liquid LNG volume (m3) to energy (MWh) with an explicit factor, exactly.

    Raises:
        UnitConversionError: When the factor is not a plausible LNG energy density.
    """

    low, high = LNG_MWH_PER_M3_RANGE
    if not low <= mwh_per_m3 <= high:
        raise UnitConversionError("mwh_per_m3 must be an explicit LNG factor (5.5-7.5)")
    return cubic_metres * mwh_per_m3


def slot_energy_mwh(quantity: Decimal, unit: str, factor: Decimal | None = None
                    ) -> tuple[Decimal, Decimal]:
    """A slot's energy in MWh and the factor used (MWh per one ``unit``), exactly.

    Raises:
        UnitConversionError: When the unit is unknown, or ``m3_lng`` comes without a factor.
    """

    if unit not in SLOT_ENERGY_UNITS:
        raise UnitConversionError(f"unsupported slot unit: {unit!r}")
    fixed = SLOT_ENERGY_UNITS[unit]
    if fixed is None:
        if factor is None:
            raise UnitConversionError("a slot in m3 of LNG needs its MWh per m3 factor")
        return lng_m3_to_mwh(quantity, factor), factor
    return quantity * fixed, fixed


def _fx_factor(currency_from: str, currency_to: str, eur_rates: Mapping[str, float]) -> float:
    """Units of ``currency_to`` per one ``currency_from`` via EUR-based rates.

    ``eur_rates`` maps currency -> units per 1 EUR (ECB reference convention). The
    conversion itself is the shared FX table (``domain.ontology.currency``).
    """

    from datetime import date

    from eurogas_nexus.domain.ontology.currency import CurrencyError, FxTable

    table = FxTable.from_pivot_map(
        {key: val for key, val in eur_rates.items() if val and float(val) > 0},
        as_of=date.min,
        source="caller",
    )
    try:
        return table.rate(currency_from, currency_to)
    except CurrencyError as exc:
        needed = " and ".join(
            f"EUR/{code}" for code in (currency_from, currency_to) if code != "EUR"
        )
        raise UnitConversionError(
            f"an FX rate from {currency_from} to {currency_to} is required: pass {needed}"
        ) from exc


def convert_price(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    eur_rates: Mapping[str, float] | None = None,
) -> float:
    """Convert a gas price between quotations.

    Args:
        value: Price in ``from_unit``.
        from_unit: Source quotation, e.g. ``EUR/MWh`` or ``GBp/th``.
        to_unit: Target quotation.
        eur_rates: Currency -> units per 1 EUR (e.g. ``{"GBP": 0.85, "USD": 1.08}``);
            required whenever the currencies differ.

    Returns:
        The price in ``to_unit``.

    Raises:
        UnitConversionError: Unknown unit or missing FX rate.
    """

    source_currency, source_minor, source_energy = PRICE_UNITS[canonical_price_unit(from_unit)]
    target_currency, target_minor, target_energy = PRICE_UNITS[canonical_price_unit(to_unit)]
    major_per_source_energy = value / source_minor
    # price per MWh in the source currency
    per_mwh = major_per_source_energy * ENERGY_UNITS_PER_MWH[source_energy]
    per_mwh_target_ccy = per_mwh * _fx_factor(source_currency, target_currency, eur_rates or {})
    return per_mwh_target_ccy / ENERGY_UNITS_PER_MWH[target_energy] * target_minor


def units_reference() -> dict:
    """The conversion factors a client may compute with, from this module and the ontology.

    Served with the ontology read (``GET /api/analysis/ontology``) so the web client's answer
    bar converts with these factors instead of a second table. Energy and volume units are
    given in their dimension's base (MWh, m3); price units as currency, minor-unit divisor
    and energy unit; the volume-to-energy line names its calorific value as an assumption.

    返回客户端换算所需的单位系数（来自本体单位表），客户端不得另建换算表。
    """

    from eurogas_nexus.domain.market.gas_day import DEFAULT_GAS_DAY_CALENDAR
    from eurogas_nexus.domain.ontology.quantity import UNITS as ontology_units

    def dimension(name: _Dimension) -> dict[str, float]:
        return {code: u.in_base for code, u in ontology_units.items() if u.dimension is name}

    return {
        "energy_in_mwh": dimension(_Dimension.ENERGY),
        "volume_in_m3": dimension(_Dimension.VOLUME),
        "price_units": {
            code: {
                "currency": currency,
                "divisor": divisor,
                "unit": _ontology_code(energy),
            }
            for code, (currency, divisor, energy) in PRICE_UNITS.items()
        },
        "price_aliases": dict(_ALIASES),
        "volume_to_energy": {
            "gcv_kwh_per_m3": DESK_ASSUMED_GCV_KWH_PER_M3,
            "reference_conditions": DESK_GCV_REFERENCE_CONDITIONS,
            "valid_range_kwh_per_m3": list(GCV_RANGE_KWH_PER_M3),
            "basis": "assumption",
        },
        "gas_day_calendar": DEFAULT_GAS_DAY_CALENDAR,
    }
