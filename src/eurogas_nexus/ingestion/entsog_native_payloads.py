"""Exact native ENTSOG rate wire codec.

The native unit core remains the only parser of provider value/unit strings.
This module only serializes a parsed rate to the persisted JSON contract and
strictly revalidates persisted payloads before any consumer may use them.  It
has no database, API or application dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, DecimalException

from eurogas_nexus.ingestion.entsog_native_units import (
    NORMALIZER_VERSION,
    EntsogNativeRate,
    EntsogNativeUnitError,
    parse_entsog_native_rate,
)

NATIVE_RATE_JSON_KEYS: tuple[str, ...] = (
    "value_text",
    "unit_text",
    "native_value",
    "normalized_unit",
    "quantity_kind",
    "rate_basis",
    "energy_kwh_per_day",
    "volume_mcm_per_day",
    "normalizer_version",
)

_STRING_FIELDS = (
    "value_text",
    "unit_text",
    "normalized_unit",
    "quantity_kind",
    "rate_basis",
    "normalizer_version",
)


class NativeRateProjectionError(ValueError):
    """Typed refusal with a stable code and a payload-free message."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def serialize_native_rate(rate: EntsogNativeRate) -> dict[str, str | None]:
    """Serialize and revalidate one native rate to the exact JSON contract.

    ``EntsogNativeRate`` is frozen but has no constructor validation.  The wire
    candidate is therefore built from the instance attributes and then
    recomputed through :func:`validate_native_rate_payload`, which returns the
    trusted record.  A manually constructed or forged instance is refused exactly
    like a forged persisted payload.
    """

    if not isinstance(rate, EntsogNativeRate):
        raise NativeRateProjectionError(
            "native_rate_type_invalid",
            "native rate must be a parsed EntsogNativeRate",
        )
    candidate: dict[str, object] = {
        "value_text": rate.value_text,
        "unit_text": rate.unit_text,
        "native_value": _decimal_text(rate.native_value),
        "normalized_unit": rate.normalized_unit,
        "quantity_kind": rate.quantity_kind,
        "rate_basis": rate.rate_basis,
        "energy_kwh_per_day": _decimal_text(rate.energy_kwh_per_day),
        "volume_mcm_per_day": _decimal_text(rate.volume_mcm_per_day),
        "normalizer_version": rate.normalizer_version,
    }
    validated = validate_native_rate_payload(candidate, rate.normalizer_version)
    return _validated_rate_payload(validated)


def validate_native_rate_payload(
    payload: object,
    normalizer_version: str = NORMALIZER_VERSION,
) -> EntsogNativeRate:
    """Recompute and strictly verify one serialized native payload.

    The parser is rerun from the original ``value_text``/``unit_text``.  Every
    payload field must then match the recomputed record exactly, including the
    decimal text spelling, the applicable canonical dimension and the version.
    Extra and missing keys are refused.  No payload value is echoed in an
    exception message.
    """

    if not isinstance(payload, Mapping):
        raise NativeRateProjectionError(
            "invalid_native_rate_payload",
            "native rate payload must be an object",
        )
    if set(payload) != set(NATIVE_RATE_JSON_KEYS):
        raise NativeRateProjectionError(
            "invalid_native_rate_payload",
            "native rate payload must have exactly the declared keys",
        )
    if not isinstance(normalizer_version, str) or normalizer_version != NORMALIZER_VERSION:
        raise NativeRateProjectionError(
            "unsupported_normalizer_version",
            "requested native normalizer version is not supported",
        )
    for key in _STRING_FIELDS:
        if not isinstance(payload[key], str):
            raise NativeRateProjectionError(
                "invalid_native_rate_payload",
                "native rate string fields must be strings",
            )
    if payload["normalizer_version"] != normalizer_version:
        raise NativeRateProjectionError(
            "unsupported_normalizer_version",
            "native rate payload version does not match the requested version",
        )
    if not isinstance(payload["native_value"], str):
        raise NativeRateProjectionError(
            "invalid_native_rate_payload",
            "native decimal values must be exact strings",
        )

    try:
        rate = parse_entsog_native_rate(payload["value_text"], payload["unit_text"])
    except EntsogNativeUnitError:
        raise NativeRateProjectionError(
            "invalid_native_rate_source",
            "native rate source strings do not parse as a supported rate",
        ) from None

    if payload["normalized_unit"] != rate.normalized_unit:
        _refuse_field("normalized unit")
    if payload["quantity_kind"] != rate.quantity_kind:
        _refuse_field("quantity kind")
    if payload["rate_basis"] != rate.rate_basis:
        _refuse_field("rate basis")
    if payload["normalizer_version"] != rate.normalizer_version:
        _refuse_field("normalizer version")
    if not _matches_decimal(payload["native_value"], rate.native_value):
        _refuse_field("native value")
    if not _matches_optional_decimal(
        payload["energy_kwh_per_day"], rate.energy_kwh_per_day
    ):
        _refuse_field("energy quantity")
    if not _matches_optional_decimal(
        payload["volume_mcm_per_day"], rate.volume_mcm_per_day
    ):
        _refuse_field("volume quantity")
    return rate


def _validated_rate_payload(rate: EntsogNativeRate) -> dict[str, str | None]:
    return {
        "value_text": rate.value_text,
        "unit_text": rate.unit_text,
        "native_value": str(rate.native_value),
        "normalized_unit": rate.normalized_unit,
        "quantity_kind": rate.quantity_kind,
        "rate_basis": rate.rate_basis,
        "energy_kwh_per_day": _decimal_text(rate.energy_kwh_per_day),
        "volume_mcm_per_day": _decimal_text(rate.volume_mcm_per_day),
        "normalizer_version": rate.normalizer_version,
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _matches_decimal(text: object, expected: Decimal) -> bool:
    if not isinstance(text, str):
        return False
    try:
        parsed = Decimal(text)
    except (DecimalException, ValueError):
        return False
    return parsed.is_finite() and parsed == expected and text == str(expected)


def _matches_optional_decimal(text: object, expected: Decimal | None) -> bool:
    if expected is None:
        return text is None
    return _matches_decimal(text, expected)


def _refuse_field(name: str) -> None:
    raise NativeRateProjectionError(
        "invalid_native_rate_payload",
        f"native rate {name} does not match the original source strings",
    )


__all__ = [
    "NATIVE_RATE_JSON_KEYS",
    "NativeRateProjectionError",
    "serialize_native_rate",
    "validate_native_rate_payload",
]
