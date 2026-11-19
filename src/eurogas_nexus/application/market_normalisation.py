"""Price normalisation: one service that puts a price, or a series, into a requested unit.

A desk compares TTF in EUR/MWh with NBP in p/th and Henry Hub in USD/MMBtu. Converting them
needs three facts, and this service states each one on every result:

- **factors** from the units authority (``domain.ontology.quantity`` through
  ``domain.market.units``; no second table): energy units per MWh and the quote divisor;
- **a heating value** only when a volume unit is involved (EUR/m3, GBP/mcm): the one the caller
  states, or the desk's assumed GCV, labelled as an assumption with its reference conditions;
- **FX** when the currencies differ: the ECB reference rate for spot or a prompt delivery, the
  forward for the delivery period otherwise (``domain.market.fx_forward``, design basis D.5).

The result is the value in the target unit, the native value it came from, a normalisation
record (factors, heating value, FX rate, method, dates) and a tolerance carried from the FX
method. A conversion that cannot be made is refused with the reason ("not convertible: no
EURGBP rate held"); nothing is guessed. A simulated input stays simulated after conversion, and a
simulated FX rate makes the converted figure simulated.

本服务把价格（或序列）换算为指定单位与币种：系数来自单位权威表，体积单位需热值（明示或
标注为假设），币种不同时按交割期使用即期或远期汇率；每个结果都带换算记录与容差，无法换算
时明确拒绝；模拟输入换算后仍标为模拟。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from eurogas_nexus.domain.market.fx_forward import (
    Delivery,
    FxConversionRate,
    FxForwardError,
    FxHoldings,
    conversion_rate,
)
from eurogas_nexus.domain.market.units import (
    DESK_ASSUMED_GCV_KWH_PER_M3,
    DESK_GCV_REFERENCE_CONDITIONS,
    GCV_RANGE_KWH_PER_M3,
    UnitConversionError,
    canonical_price_unit,
)
from eurogas_nexus.domain.ontology.quantity import (
    Dimension,
    PriceUnit,
    Unit,
    UnitError,
    price_unit,
    unit,
)

#: Price dimensions a gas price may be quoted per.
_PRICE_DIMENSIONS = (Dimension.ENERGY, Dimension.VOLUME)
#: Floating-point round trip allowance when no FX tolerance applies.
EXACT_TOLERANCE = 1e-9


class NormalisationError(ValueError):
    """The conversion cannot be made; ``code`` says why and the message names what is missing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_price_unit(text: str) -> PriceUnit:
    """A price unit through the units authority: ``p/th``, ``EUR/MWh``, ``USD/MMBtu``, ``EUR/m3``.

    Raises:
        NormalisationError: ``unsupported_price_unit``.
    """

    raw = (text or "").strip()
    try:
        spelled = canonical_price_unit(raw)
    except UnitConversionError:
        spelled = raw
    try:
        parsed = price_unit(spelled)
    except UnitError as exc:
        raise NormalisationError("unsupported_price_unit", str(exc)) from exc
    if parsed.unit.dimension not in _PRICE_DIMENSIONS:
        raise NormalisationError(
            "unsupported_price_unit", f"{raw} is not a price per unit of energy or volume"
        )
    return parsed


def display_unit(unit: PriceUnit) -> str:
    """How a desk writes the unit: ``p/th`` for pence per therm."""

    return "p/th" if (unit.currency, unit.divisor, unit.unit.code) == ("GBP", 100, "th") else (
        unit.text
    )


@dataclass(frozen=True)
class HeatingValue:
    """The gross calorific value used between energy and volume, and whether it was stated."""

    kwh_per_m3: float
    stated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "gcv_kwh_per_m3": self.kwh_per_m3,
            "reference_conditions": DESK_GCV_REFERENCE_CONDITIONS,
            "basis": "stated" if self.stated else "assumption",
        }


@dataclass(frozen=True)
class Conversion:
    """How one unit becomes another: the factor without FX, the heating value and the FX rate."""

    source: PriceUnit
    target: PriceUnit
    unit_factor: float
    heating_value: HeatingValue | None
    fx: FxConversionRate | None

    @property
    def factor(self) -> float:
        return self.unit_factor * (self.fx.rate if self.fx else 1.0)

    @property
    def simulated(self) -> bool:
        return bool(self.fx and self.fx.simulated)

    @property
    def tolerance_pct(self) -> float:
        return self.fx.tolerance_pct if self.fx else 0.0

    def record(self) -> dict[str, object]:
        """The normalisation record a result carries (G6: never silent)."""

        steps = [
            {
                "step": "unit",
                "from": display_unit(self.source),
                "to": f"{self.source.currency}/{self.target.unit.code}",
                "source_divisor": self.source.divisor,
                "source_unit_in_base": self.source.unit.in_base,
                "target_unit_in_base": self.target.unit.in_base,
                "target_divisor": self.target.divisor,
            }
        ]
        if self.heating_value is not None:
            steps.append({"step": "heating_value", **self.heating_value.as_dict()})
        if self.fx is not None:
            steps.append(
                {
                    "step": "fx",
                    "pair": f"{self.fx.base}{self.fx.quote}",
                    "rate": self.fx.rate,
                    "method": self.fx.method,
                    "label": self.fx.label,
                }
            )
        return {
            "from_unit": display_unit(self.source),
            "to_unit": display_unit(self.target),
            "unit_factor": self.unit_factor,
            "factor": self.factor,
            "steps": steps,
            "heating_value": self.heating_value.as_dict() if self.heating_value else None,
            "fx": self.fx.as_dict() if self.fx else None,
            "units_authority": "domain.ontology.quantity",
        }


def _heating_value(gcv_kwh_per_m3: float | None) -> HeatingValue:
    if gcv_kwh_per_m3 is None:
        return HeatingValue(DESK_ASSUMED_GCV_KWH_PER_M3, stated=False)
    low, high = GCV_RANGE_KWH_PER_M3
    if not low <= gcv_kwh_per_m3 <= high:
        raise NormalisationError(
            "implausible_heating_value",
            f"a natural-gas GCV must be {low}-{high} kWh/m3, not {gcv_kwh_per_m3}",
        )
    return HeatingValue(float(gcv_kwh_per_m3), stated=True)


def conversion(
    from_unit: str,
    to_unit: str,
    *,
    holdings: FxHoldings,
    as_of: date,
    delivery: Delivery | None = None,
    gcv_kwh_per_m3: float | None = None,
) -> Conversion:
    """The conversion from ``from_unit`` to ``to_unit`` for a price delivered in ``delivery``.

    Raises:
        NormalisationError: an unknown unit, an implausible heating value, or FX not held
            (``not_convertible``) or beyond the forward horizon (``beyond_horizon``).
    """

    source = parse_price_unit(from_unit)
    target = parse_price_unit(to_unit)
    # Price per base unit (MWh or m3) in the source currency's major unit.
    per_base = 1.0 / source.divisor / source.unit.in_base
    heating: HeatingValue | None = None
    if source.unit.dimension is not target.unit.dimension:
        heating = _heating_value(gcv_kwh_per_m3)
        mwh_per_m3 = heating.kwh_per_m3 / 1000.0
        if source.unit.dimension is Dimension.ENERGY:
            per_base *= mwh_per_m3  # per MWh -> per m3
        else:
            per_base /= mwh_per_m3  # per m3 -> per MWh
    elif gcv_kwh_per_m3 is not None:
        _heating_value(gcv_kwh_per_m3)  # validate even when unused
    unit_factor = per_base * target.unit.in_base * target.divisor
    fx: FxConversionRate | None = None
    if source.currency != target.currency:
        try:
            fx = conversion_rate(
                holdings, source.currency, target.currency, as_of=as_of, delivery=delivery
            )
        except FxForwardError as exc:
            code = "beyond_horizon" if exc.code == "beyond_horizon" else "not_convertible"
            raise NormalisationError(code, str(exc)) from exc
    return Conversion(source, target, unit_factor, heating, fx)


def _tolerance(value: float, conv: Conversion) -> dict[str, object]:
    if conv.fx is None or conv.fx.tolerance_pct == 0.0:
        return {"absolute": 0.0, "relative_pct": 0.0, "basis": "exact factors"}
    return {
        "absolute": abs(value) * conv.fx.tolerance_pct / 100.0,
        "relative_pct": conv.fx.tolerance_pct,
        "basis": "forward FX derived from overnight benchmark rates (D.5)",
    }


def normalise_value(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    holdings: FxHoldings,
    as_of: date,
    delivery: Delivery | None = None,
    simulated: bool = False,
    gcv_kwh_per_m3: float | None = None,
) -> dict[str, Any]:
    """One price in ``to_unit`` with its normalisation record and tolerance.

    Raises:
        NormalisationError: see :func:`conversion`.
    """

    conv = conversion(
        from_unit,
        to_unit,
        holdings=holdings,
        as_of=as_of,
        delivery=delivery,
        gcv_kwh_per_m3=gcv_kwh_per_m3,
    )
    converted = value * conv.factor
    is_simulated = bool(simulated or conv.simulated)
    return {
        "value": converted,
        "unit": display_unit(conv.target),
        "native": {"value": value, "unit": display_unit(conv.source)},
        "simulated": is_simulated,
        "input_class": _value_class(conv, is_simulated),
        "as_of": as_of.isoformat(),
        "delivery": delivery.as_dict() if delivery else None,
        "normalisation": conv.record(),
        "tolerance": _tolerance(converted, conv),
    }


# --------------------------------------------------------------------------- quantities

#: Time bases a quantity may be per: a day (a nomination, a position) or an hour (a flow).
_QUANTITY_PER = ("d", "h")
_QUANTITY_DIMENSIONS = (Dimension.ENERGY, Dimension.VOLUME)


@dataclass(frozen=True)
class QuantityUnit:
    """An amount of gas (``MWh``, ``th``, ``mcm``), optionally per day or hour (``MWh/d``)."""

    amount: Unit
    per: str | None

    @property
    def text(self) -> str:
        return f"{self.amount.code}/{self.per}" if self.per else self.amount.code


def parse_quantity_unit(text: str) -> QuantityUnit:
    """A quantity unit through the units authority: ``MWh/d``, ``th/d``, ``GWh/d``, ``mcm/d``.

    Raises:
        NormalisationError: ``unsupported_quantity_unit``.
    """

    raw = (text or "").strip()
    amount_text, _, per = raw.partition("/")
    per = per.strip().lower() or None
    if per in ("day",):
        per = "d"
    if per not in (None, *_QUANTITY_PER):
        raise NormalisationError("unsupported_quantity_unit", f"{raw} is not per day or per hour")
    try:
        amount = unit(amount_text.strip())
    except UnitError as exc:
        raise NormalisationError("unsupported_quantity_unit", str(exc)) from exc
    if amount.dimension not in _QUANTITY_DIMENSIONS:
        raise NormalisationError(
            "unsupported_quantity_unit", f"{raw} is not an amount of energy or volume"
        )
    return QuantityUnit(amount, per)


def normalise_quantity(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    simulated: bool = False,
    gcv_kwh_per_m3: float | None = None,
) -> dict[str, Any]:
    """A quantity in ``to_unit`` (``MWh/d`` → ``th/d``): fixed physical factors from the units
    authority, a heating value only between energy and volume, never FX.

    Raises:
        NormalisationError: an unknown unit, a different time basis (``MWh/d`` to ``MWh``), or an
            implausible heating value.
    """

    source = parse_quantity_unit(from_unit)
    target = parse_quantity_unit(to_unit)
    if source.per != target.per:
        raise NormalisationError(
            "time_basis_differs",
            f"{source.text} and {target.text} are not over the same time; nothing is assumed",
        )
    factor = source.amount.in_base
    heating: HeatingValue | None = None
    if source.amount.dimension is not target.amount.dimension:
        heating = _heating_value(gcv_kwh_per_m3)
        mwh_per_m3 = heating.kwh_per_m3 / 1000.0
        # in_base is MWh for energy and m3 for volume.
        if source.amount.dimension is Dimension.VOLUME:
            factor *= mwh_per_m3
        else:
            factor /= mwh_per_m3
    elif gcv_kwh_per_m3 is not None:
        _heating_value(gcv_kwh_per_m3)
    factor = factor / target.amount.in_base
    return {
        "value": value * factor,
        "unit": target.text,
        "native": {"value": value, "unit": source.text},
        "simulated": bool(simulated),
        "normalisation": {
            "from_unit": source.text,
            "to_unit": target.text,
            "factor": factor,
            "heating_value": heating.as_dict() if heating else None,
            "fx": None,
            "units_authority": "domain.ontology.quantity",
        },
        "tolerance": (
            {"absolute": 0.0, "relative_pct": 0.0, "basis": "exact factors"}
            if heating is None or heating.stated
            else {"absolute": None, "relative_pct": None, "basis": "assumed heating value"}
        ),
    }


def _value_class(conv: Conversion, simulated: bool) -> str:
    if simulated:
        return "simulated"
    if conv.fx is None:
        return "converted"
    return {"derived": "derived", "sourced": "converted", "reference": "converted"}.get(
        conv.fx.input_class, "converted"
    )


@dataclass(frozen=True)
class SeriesPoint:
    """One price of a series: its date (the FX as-of), value and delivery period."""

    day: date
    value: float
    delivery: Delivery | None = None


def normalise_series(
    points: Sequence[SeriesPoint],
    from_unit: str,
    to_unit: str,
    *,
    holdings: FxHoldings,
    simulated: bool = False,
    gcv_kwh_per_m3: float | None = None,
) -> dict[str, Any]:
    """Each point converted with the FX of its own date and delivery period (G5).

    Historical values use the rate of their own date, never today's. A point whose rate is not
    held is listed under ``refused`` with the reason, and its value is ``None``; the series is
    never filled.

    Raises:
        NormalisationError: an unknown unit or an implausible heating value (whole series).
    """

    parse_price_unit(from_unit)
    target = parse_price_unit(to_unit)
    if gcv_kwh_per_m3 is not None:
        _heating_value(gcv_kwh_per_m3)
    values: list[dict[str, Any]] = []
    refused: dict[str, int] = {}
    methods: set[str] = set()
    labels: list[str] = []
    any_simulated = bool(simulated)
    max_tolerance = 0.0
    latest: Conversion | None = None
    latest_day: date | None = None
    cache: dict[tuple[date, Delivery | None], Conversion | NormalisationError] = {}
    for point in points:
        key = (point.day, point.delivery)
        if key not in cache:
            try:
                cache[key] = conversion(
                    from_unit,
                    to_unit,
                    holdings=holdings,
                    as_of=point.day,
                    delivery=point.delivery,
                    gcv_kwh_per_m3=gcv_kwh_per_m3,
                )
            except NormalisationError as exc:
                if exc.code == "unsupported_price_unit":
                    raise
                cache[key] = exc
        found = cache[key]
        if isinstance(found, NormalisationError):
            refused[str(found)] = refused.get(str(found), 0) + 1
            values.append({"day": point.day.isoformat(), "value": None, "native": point.value})
            continue
        converted = point.value * found.factor
        any_simulated = any_simulated or found.simulated
        if found.fx is not None:
            methods.add(found.fx.method)
            if found.fx.label not in labels:
                labels.append(found.fx.label)
        max_tolerance = max(max_tolerance, found.tolerance_pct)
        if latest_day is None or point.day >= latest_day:
            latest, latest_day = found, point.day
        values.append(
            {
                "day": point.day.isoformat(),
                "value": converted,
                "native": point.value,
                "fx_rate": found.fx.rate if found.fx else None,
                "fx_method": found.fx.method if found.fx else None,
                "fx_value_date": (
                    found.fx.value_date.isoformat() if found.fx and found.fx.value_date else None
                ),
                "tolerance_abs": abs(converted) * found.tolerance_pct / 100.0,
            }
        )
    return {
        "unit": display_unit(target),
        "native_unit": display_unit(parse_price_unit(from_unit)),
        "simulated": any_simulated,
        "points": values,
        "converted": sum(1 for item in values if item["value"] is not None),
        "refused": [{"reason": reason, "points": count} for reason, count in refused.items()],
        "fx_methods": sorted(methods),
        "fx_labels": labels,
        "max_tolerance_pct": max_tolerance,
        "latest": latest.record() if latest else None,
    }


# --- loading what the product holds, for a caller -------------------------------------------


def load_holdings(who: Any) -> FxHoldings:
    """The FX reference rates, licensed forwards and benchmark fixings the caller may read.

    ``who`` is an API request or a :class:`~eurogas_nexus.application.caller.Caller`. An
    unconfigured store holds nothing (every cross-currency conversion is then refused).

    Raises:
        SQLAlchemyError: when the runtime store is configured but unavailable.
    """

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.projections.market_reads import (
        filter_entitled_rows,
        fx_observations,
    )
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return FxHoldings()
    principal = caller_of(who).principal
    with get_session_factory()() as session:
        fx_rows = fx_observations(session)
        rate_rows = _interest_rate_rows(session)
    return FxHoldings.from_rows(
        filter_entitled_rows(principal, fx_rows, source_key="source_system"),
        filter_entitled_rows(principal, rate_rows, source_key="source_system"),
    )


def _interest_rate_rows(session: Any) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import InterestRateObservationRecord

    return [
        {
            "benchmark_id": record.benchmark_id,
            "value_date": record.value_date,
            "rate_pct": record.rate_pct,
            "source_system": record.source_system,
            "source_reference": record.source_reference,
        }
        for record in session.query(InterestRateObservationRecord).all()
    ]


def points_from_closes(
    closes: Iterable[tuple[date, float, Delivery | None]],
) -> list[SeriesPoint]:
    """Series points from ``(day, value, delivery)`` tuples."""

    return [SeriesPoint(day, value, delivery) for day, value, delivery in closes]
