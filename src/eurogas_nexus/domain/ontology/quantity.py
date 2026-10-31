"""Units of measure with dimensions, and price units as currency per unit.

Every quantity belongs to a dimension (energy, volume, mass, emissions, power) and
converts through that dimension's base unit; a conversion across dimensions (volume to
energy, tonnes of coal to energy) needs a stated factor such as a calorific value and is
never implicit. Rates per day or per hour are the dimension's unit over time.

Price units read ``<currency or quote unit>/<unit>``: ``EUR/MWh``, ``GBp/th``,
``USD/MMBtu``, ``CAD/GJ``, ``EUR/t``, ``USD/t``, ``CNY/MWh``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from eurogas_nexus.domain.ontology.currency import CurrencyError, FxTable, resolve_quote_unit

BTU_JOULES = 1055.05585262  # International Table BTU, basis of the UK therm and the MMBtu


class Dimension(StrEnum):
    """What a unit measures; conversion is only within one dimension."""

    ENERGY = "energy"
    VOLUME = "volume"
    MASS = "mass"
    EMISSIONS = "emissions"
    POWER = "power"


@dataclass(frozen=True)
class Unit:
    """A unit and how many base units (MWh, m3, t, tCO2e, MW) it holds."""

    code: str
    dimension: Dimension
    in_base: float
    name: str = ""


_MWH_J = 3.6e9
UNITS: dict[str, Unit] = {
    u.code: u
    for u in (
        Unit("MWh", Dimension.ENERGY, 1.0, "megawatt hour"),
        Unit("kWh", Dimension.ENERGY, 1e-3, "kilowatt hour"),
        Unit("GWh", Dimension.ENERGY, 1e3, "gigawatt hour"),
        Unit("TWh", Dimension.ENERGY, 1e6, "terawatt hour"),
        Unit("GJ", Dimension.ENERGY, 1e9 / _MWH_J, "gigajoule"),
        Unit("MJ", Dimension.ENERGY, 1e6 / _MWH_J, "megajoule"),
        Unit("th", Dimension.ENERGY, 100_000 * BTU_JOULES / _MWH_J, "therm"),
        Unit("MMBtu", Dimension.ENERGY, 1_000_000 * BTU_JOULES / _MWH_J, "million BTU"),
        Unit("m3", Dimension.VOLUME, 1.0, "cubic metre"),
        Unit("mcm", Dimension.VOLUME, 1e6, "million cubic metres"),
        Unit("bcm", Dimension.VOLUME, 1e9, "billion cubic metres"),
        Unit("t", Dimension.MASS, 1.0, "tonne"),
        Unit("tCO2", Dimension.EMISSIONS, 1.0, "tonne of CO2 equivalent"),
        Unit("MW", Dimension.POWER, 1.0, "megawatt"),
    )
}
_ALIASES = {"THERM": "th", "MMBTU": "MMBtu", "TCO2E": "tCO2", "TONNE": "t", "MT": "t"}


class UnitError(ValueError):
    """Unknown unit or a conversion across dimensions."""


def unit(code: str) -> Unit:
    """The unit for a code or alias."""

    text = (code or "").strip()
    found = UNITS.get(text) or UNITS.get(_ALIASES.get(text.upper(), ""))
    if found is None:
        found = next((u for u in UNITS.values() if u.code.upper() == text.upper()), None)
    if found is None:
        raise UnitError(f"unknown unit {code!r}")
    return found


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert within one dimension."""

    source, target = unit(from_unit), unit(to_unit)
    if source.dimension is not target.dimension:
        raise UnitError(
            f"{source.code} is {source.dimension}, {target.code} is {target.dimension}: "
            "state a conversion factor (calorific value, emission factor)"
        )
    return value * source.in_base / target.in_base


@dataclass(frozen=True)
class PriceUnit:
    """``currency`` (after resolving quote units) per ``unit``, with the quote divisor."""

    text: str
    currency: str
    divisor: int
    unit: Unit


def price_unit(text: str) -> PriceUnit:
    """Parse ``EUR/MWh``, ``GBp/th``, ``USD/t`` and the like."""

    if "/" not in (text or ""):
        raise UnitError(f"price unit {text!r} must read <currency>/<unit>")
    money, per = text.strip().split("/", 1)
    try:
        code, divisor = resolve_quote_unit(money)
    except CurrencyError as exc:
        raise UnitError(str(exc)) from exc
    return PriceUnit(text.strip(), code, divisor, unit(per))


def convert_price(value: float, from_unit: str, to_unit: str, fx: FxTable | None = None) -> float:
    """Convert a price between units of the same dimension, and currencies through ``fx``."""

    source, target = price_unit(from_unit), price_unit(to_unit)
    if source.unit.dimension is not target.unit.dimension:
        raise UnitError(f"cannot convert {source.text} to {target.text}")
    per_base = value / source.divisor / source.unit.in_base
    if source.currency != target.currency:
        if fx is None:
            raise UnitError(f"an FX rate {source.currency}->{target.currency} is required")
        per_base = fx.convert(per_base, source.currency, target.currency)
    return per_base * target.unit.in_base * target.divisor
