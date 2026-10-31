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

from eurogas_nexus.domain.ontology.markets import Commodity, MarketStatus, markets

BTU_JOULES = 1055.05585262
MJ_PER_MWH = 3600.0

#: Amount of each energy unit that equals one MWh.
ENERGY_UNITS_PER_MWH: dict[str, float] = {
    "MWh": 1.0,
    "kWh": 1000.0,
    "GWh": 0.001,
    "TWh": 0.000001,
    "GJ": 3.6,
    "therm": MJ_PER_MWH * 1e6 / (BTU_JOULES * 100_000),
    "MMBtu": MJ_PER_MWH * 1e6 / (BTU_JOULES * 1_000_000),
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

    try:
        mwh = value / ENERGY_UNITS_PER_MWH[from_unit]
        return mwh * ENERGY_UNITS_PER_MWH[to_unit]
    except KeyError as exc:
        raise UnitConversionError(f"unsupported energy unit: {exc.args[0]!r}") from exc


def volume_to_mwh(cubic_metres: float, gcv_kwh_per_m3: float) -> float:
    """Convert a gas volume to energy with an explicit gross calorific value.

    Raises:
        UnitConversionError: When the calorific value is not a plausible natural-gas GCV.
    """

    if not 8.0 <= gcv_kwh_per_m3 <= 13.0:
        raise UnitConversionError("gcv_kwh_per_m3 must be an explicit natural-gas GCV (8-13)")
    return cubic_metres * gcv_kwh_per_m3 / 1000.0


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
        raise UnitConversionError(
            f"explicit EUR/{currency_from}/{currency_to} FX rate required"
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
