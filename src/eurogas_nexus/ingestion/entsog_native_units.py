"""Strict, additive interpretation of ENTSOG native rate units.

This module reads an explicitly supplied provider numeric string and its explicit
unit.  It preserves the source text, keeps the native quantity in :class:`Decimal`,
and derives only same-dimension canonical rates.  In particular:

* energy rates become ``energy_kwh_per_day`` and never a volume;
* volume rates become ``volume_mcm_per_day`` and never an energy;
* no calorific value, gas composition, or energy/volume conversion is applied;
* hourly rates are scaled by exactly 24 hours per day.

The 24-hour scaling is a unit conversion, not a gas-day integration.  Actual
23/25-hour gas-day volume integration is a separate concern and is deliberately
not performed here.

This is a foundation for an additive native-unit schema/reader migration.  It
does not change the existing normalizers and must not be described as having
fixed their output until those integrations are made and tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, DecimalException, localcontext
from typing import Literal

NORMALIZER_VERSION = "entsog-native-units-v1"

MAX_VALUE_TEXT_LENGTH = 128
MAX_UNIT_TEXT_LENGTH = 32
MAX_ABS_NATIVE_VALUE = Decimal("1e36")
_MAX_ABS_DECIMAL_EXPONENT = 72

QuantityKind = Literal["energy", "volume"]
RateBasis = Literal["day", "hour"]

_ONE = Decimal(1)
_HOURS_PER_DAY = Decimal(24)
_KWH_PER_MWH = Decimal(1000)
_M3_PER_MCM = Decimal(1_000_000)

_NUMERIC_PATTERN = re.compile(
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",
    re.ASCII,
)


class EntsogNativeUnitError(ValueError):
    """Typed refusal with a stable ``code`` for callers and migration logs.

    Codes currently emitted are ``invalid_value_type``, ``blank_value``,
    ``value_too_long``, ``non_finite_value``, ``invalid_numeric_string``,
    ``value_out_of_bounds``, ``missing_unit``, ``invalid_unit_type``,
    ``unit_too_long`` and ``unsupported_unit``.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class EntsogNativeRate:
    """One exact native ENTSOG rate and its same-dimension canonical form."""

    value_text: str
    unit_text: str
    native_value: Decimal
    normalized_unit: str
    quantity_kind: QuantityKind
    rate_basis: RateBasis
    energy_kwh_per_day: Decimal | None
    volume_mcm_per_day: Decimal | None
    normalizer_version: str = field(init=False, default=NORMALIZER_VERSION)


@dataclass(frozen=True)
class _UnitSpec:
    normalized_unit: str
    quantity_kind: QuantityKind
    rate_basis: RateBasis
    multiplier: Decimal = _ONE
    divisor: Decimal = _ONE


_KWH_DAY = _UnitSpec("kWh/day", "energy", "day")
_MWH_DAY = _UnitSpec("MWh/day", "energy", "day", _KWH_PER_MWH)
_KWH_HOUR = _UnitSpec("kWh/hour", "energy", "hour", _HOURS_PER_DAY)
_MWH_HOUR = _UnitSpec(
    "MWh/hour",
    "energy",
    "hour",
    _HOURS_PER_DAY * _KWH_PER_MWH,
)
_M3_DAY = _UnitSpec("m3/day", "volume", "day", divisor=_M3_PER_MCM)
_M3_HOUR = _UnitSpec(
    "m3/hour",
    "volume",
    "hour",
    _HOURS_PER_DAY,
    _M3_PER_MCM,
)
_MCM_DAY = _UnitSpec("mcm/day", "volume", "day")
_MCM_HOUR = _UnitSpec("mcm/hour", "volume", "hour", _HOURS_PER_DAY)

# Keys are case-folded; the reviewed superscript cubic-metre alias is folded to
# ``m3`` before lookup.  Unknown dimensions are absent rather than treated as
# volume, so an energy/volume or power unit cannot silently fall through.
_UNIT_SPECS: dict[str, _UnitSpec] = {
    "kwh/d": _KWH_DAY,
    "kwh/day": _KWH_DAY,
    "mwh/d": _MWH_DAY,
    "mwh/day": _MWH_DAY,
    "kwh/h": _KWH_HOUR,
    "mwh/h": _MWH_HOUR,
    "m3/d": _M3_DAY,
    "m3/day": _M3_DAY,
    "m3/h": _M3_HOUR,
    "mcm/d": _MCM_DAY,
    "mcm/day": _MCM_DAY,
    "mcm/h": _MCM_HOUR,
}


def parse_entsog_native_rate(value_text: object, unit_text: object) -> EntsogNativeRate:
    """Read one explicit ENTSOG value/unit pair without inferring a basis.

    ``value_text`` must be the provider's original string.  Numbers, booleans,
    and guessed legacy scalar values are rejected instead of being stringified
    into apparent provenance.  Leading/trailing whitespace is tolerated for
    parsing, while the stored ``value_text`` and ``unit_text`` remain byte-for-byte
    the supplied strings.

    Raises:
        EntsogNativeUnitError: A ``ValueError`` subclass carrying a stable
            machine-readable ``code``.
    """

    native_value = _parse_native_value(value_text)
    spec = _parse_unit(unit_text)
    canonical = _canonical_value(native_value, spec)

    if spec.quantity_kind == "energy":
        energy_kwh_per_day: Decimal | None = canonical
        volume_mcm_per_day: Decimal | None = None
    else:
        energy_kwh_per_day = None
        volume_mcm_per_day = canonical

    return EntsogNativeRate(
        value_text=value_text,  # type: ignore[arg-type]
        unit_text=unit_text,  # type: ignore[arg-type]
        native_value=native_value,
        normalized_unit=spec.normalized_unit,
        quantity_kind=spec.quantity_kind,
        rate_basis=spec.rate_basis,
        energy_kwh_per_day=energy_kwh_per_day,
        volume_mcm_per_day=volume_mcm_per_day,
    )


def _parse_native_value(value_text: object) -> Decimal:
    if not isinstance(value_text, str):
        raise EntsogNativeUnitError(
            "invalid_value_type",
            "value must be the original numeric string, not a number or boolean",
        )
    if len(value_text) > MAX_VALUE_TEXT_LENGTH:
        raise EntsogNativeUnitError(
            "value_too_long",
            f"value text exceeds {MAX_VALUE_TEXT_LENGTH} characters",
        )

    text = value_text.strip()
    if not text:
        raise EntsogNativeUnitError("blank_value", "value text is blank")

    try:
        value = Decimal(text)
    except (DecimalException, ValueError, OverflowError):
        if _NUMERIC_PATTERN.fullmatch(text) is not None:
            raise EntsogNativeUnitError(
                "value_out_of_bounds",
                "numeric text is outside the supported decimal range",
            ) from None
        raise EntsogNativeUnitError(
            "invalid_numeric_string",
            "value text is not a finite signed decimal or scientific number",
        ) from None

    if not value.is_finite():
        raise EntsogNativeUnitError(
            "non_finite_value",
            "value text must be finite; NaN and infinity are refused",
        )

    # Decimal accepts underscores and a few spellings that are not part of the
    # deliberately narrow ENTSOG native-number contract.
    if _NUMERIC_PATTERN.fullmatch(text) is None:
        raise EntsogNativeUnitError(
            "invalid_numeric_string",
            "value text is not a finite signed decimal or scientific number",
        )

    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int) or abs(exponent) > _MAX_ABS_DECIMAL_EXPONENT:
        raise EntsogNativeUnitError(
            "value_out_of_bounds",
            "value exponent is outside the supported range",
        )
    if value.copy_abs() > MAX_ABS_NATIVE_VALUE:
        raise EntsogNativeUnitError(
            "value_out_of_bounds",
            "value magnitude is outside the supported range",
        )
    return value


def _parse_unit(unit_text: object) -> _UnitSpec:
    if unit_text is None:
        raise EntsogNativeUnitError("missing_unit", "unit is missing")
    if not isinstance(unit_text, str):
        raise EntsogNativeUnitError(
            "invalid_unit_type",
            "unit must be an explicit string",
        )
    if len(unit_text) > MAX_UNIT_TEXT_LENGTH:
        raise EntsogNativeUnitError(
            "unit_too_long",
            f"unit text exceeds {MAX_UNIT_TEXT_LENGTH} characters",
        )

    text = unit_text.strip()
    if not text:
        raise EntsogNativeUnitError("missing_unit", "unit is blank")

    key = text.casefold().replace("\u00b3", "3")
    spec = _UNIT_SPECS.get(key)
    if spec is None:
        raise EntsogNativeUnitError(
            "unsupported_unit",
            "unit is not an explicit supported energy or volume rate",
        )
    return spec


def _canonical_value(native_value: Decimal, spec: _UnitSpec) -> Decimal:
    if spec.multiplier == _ONE and spec.divisor == _ONE:
        return native_value

    digit_count = len(native_value.as_tuple().digits)
    with localcontext() as context:
        # The default 28-digit context would round long but valid provider
        # values.  Bound the local precision above every possible result digit
        # count; inputs themselves are length/exponent bounded.
        context.prec = max(64, digit_count + 32)
        scaled = native_value
        if spec.multiplier != _ONE:
            scaled = scaled * spec.multiplier
        if spec.divisor != _ONE:
            scaled = scaled / spec.divisor
        return scaled


__all__ = [
    "EntsogNativeRate",
    "EntsogNativeUnitError",
    "NORMALIZER_VERSION",
    "parse_entsog_native_rate",
]
