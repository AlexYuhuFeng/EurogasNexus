"""Typed native-unit physical observation reads for RFC 0005.

This is an opt-in SDK surface.  It preserves the provider's exact numeric token
strings and the backend-normalized canonical quantities, but never performs
unit conversions, calorific-value arithmetic or financial arithmetic.  Those
numerics remain owned by the backend.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationInfo,
    field_validator,
    model_validator,
)

from eurogas_nexus_sdk._transport import (
    SdkProtocolError,
    SdkResult,
    api_url,
    get_envelope,
)

NormalizerVersion = Literal["entsog-native-units-v1"]
QuantityKind = Literal["energy", "volume"]
RateBasis = Literal["day", "hour"]

_EXACT_NUMERIC = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?\Z"
)
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")

# Declared RFC 0005 v1 canonical unit labels.  Validation is lexical only; no
# numerical conversion or backend unit-normalizer import is performed here.
_CANONICAL_UNITS: dict[str, tuple[QuantityKind, RateBasis]] = {
    "kWh/day": ("energy", "day"),
    "MWh/day": ("energy", "day"),
    "kWh/hour": ("energy", "hour"),
    "MWh/hour": ("energy", "hour"),
    "m3/day": ("volume", "day"),
    "m3/hour": ("volume", "hour"),
    "mcm/day": ("volume", "day"),
    "mcm/hour": ("volume", "hour"),
}

# Exact backend aliases accepted in the original provider unit_text.  Keys are
# compared after trim + casefold + m³ -> m3.
_UNIT_TEXT_ALIASES: dict[str, tuple[QuantityKind, RateBasis]] = {
    "kwh/d": ("energy", "day"),
    "kwh/day": ("energy", "day"),
    "mwh/d": ("energy", "day"),
    "mwh/day": ("energy", "day"),
    "kwh/h": ("energy", "hour"),
    "mwh/h": ("energy", "hour"),
    "m3/d": ("volume", "day"),
    "m3/day": ("volume", "day"),
    "m3/h": ("volume", "hour"),
    "mcm/d": ("volume", "day"),
    "mcm/day": ("volume", "day"),
    "mcm/h": ("volume", "hour"),
}


def _exact_numeric_text(
    value: Any, field: str, *, allow_surrounding_whitespace: bool = False
) -> str:
    """Return an exact finite numeric string without changing its token."""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be an exact numeric string")
    token = value.strip() if allow_surrounding_whitespace else value
    if _EXACT_NUMERIC.fullmatch(token) is None:
        raise ValueError(f"{field} must be an exact finite numeric string")
    try:
        parsed = Decimal(token)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be an exact finite numeric string") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be an exact finite numeric string")
    return value


def _unit_text_signature(value: str) -> tuple[QuantityKind, RateBasis] | None:
    key = value.strip().casefold().replace("m³", "m3")
    return _UNIT_TEXT_ALIASES.get(key)


def _parse_aware_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an aware UTC timestamp string")
    text = value.strip()
    if not text:
        raise ValueError(f"{field} must be an aware UTC timestamp string")
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an aware UTC timestamp string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be an aware UTC timestamp string")
    return parsed.astimezone(UTC)


def _normalize_utc_text(value: Any, field: str) -> str:
    parsed = _parse_aware_utc(value, field)
    return parsed.isoformat().replace("+00:00", "Z")


class NativeRate(BaseModel):
    """One exact native-rate payload emitted by the backend normalizer.

    The provider token (``value_text``), the normalized value and the canonical
    quantity are strings so trailing zeros, exponent notation and zero values
    are never rewritten by the SDK.  Exactly one canonical quantity is present,
    according to ``quantity_kind``.
    """

    model_config = ConfigDict(extra="forbid")

    value_text: str
    unit_text: str
    native_value: str
    normalized_unit: str
    quantity_kind: QuantityKind
    rate_basis: RateBasis
    energy_kwh_per_day: str | None
    volume_mcm_per_day: str | None
    normalizer_version: NormalizerVersion

    @field_validator("value_text", mode="before")
    @classmethod
    def _value_text(cls, value: Any, info: ValidationInfo) -> str:
        return _exact_numeric_text(
            value, info.field_name, allow_surrounding_whitespace=True
        )

    @field_validator("native_value", mode="before")
    @classmethod
    def _native_value(cls, value: Any, info: ValidationInfo) -> str:
        return _exact_numeric_text(value, info.field_name)

    @field_validator("energy_kwh_per_day", "volume_mcm_per_day", mode="before")
    @classmethod
    def _optional_numeric(cls, value: Any, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _exact_numeric_text(value, info.field_name)

    @field_validator("unit_text", "normalized_unit", mode="before")
    @classmethod
    def _unit_text(cls, value: Any, info: ValidationInfo) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{info.field_name} must be a non-blank string")
        return value

    @model_validator(mode="after")
    def _canonical_quantity(self) -> NativeRate:
        if self.quantity_kind == "energy":
            if self.energy_kwh_per_day is None or self.volume_mcm_per_day is not None:
                raise ValueError(
                    "energy native rates require energy_kwh_per_day and no "
                    "volume_mcm_per_day"
                )
        else:
            if self.volume_mcm_per_day is None or self.energy_kwh_per_day is not None:
                raise ValueError(
                    "volume native rates require volume_mcm_per_day and no "
                    "energy_kwh_per_day"
                )

        canonical = _CANONICAL_UNITS.get(self.normalized_unit)
        if canonical is None:
            raise ValueError(
                "normalized_unit must be a declared entsog-native-units-v1 "
                "canonical unit"
            )
        normalized_kind, normalized_basis = canonical
        if normalized_kind != self.quantity_kind:
            raise ValueError(
                "normalized_unit dimension does not match quantity_kind"
            )
        if normalized_basis != self.rate_basis:
            raise ValueError("normalized_unit rate basis does not match rate_basis")

        unit_signature = _unit_text_signature(self.unit_text)
        if unit_signature is None:
            raise ValueError(
                "unit_text must be a supported entsog-native-units-v1 alias"
            )
        unit_kind, unit_basis = unit_signature
        if unit_kind != self.quantity_kind:
            raise ValueError("unit_text dimension does not match quantity_kind")
        if unit_basis != self.rate_basis:
            raise ValueError("unit_text rate basis does not match rate_basis")
        return self


class _NativePhysicalBase(BaseModel):
    """Projected native observation fields shared by flows and capacities."""

    model_config = ConfigDict(extra="allow")

    observation_id: str
    source_record_id: str
    point_id: str
    point_name: str
    direction: str
    period_start_utc: str
    period_end_utc: str
    observed_at_utc: str | None = None
    source_system: Literal["ENTSOG"]
    operator_key: str | None = None
    flow_status: str | None = None
    period_type: str | None = None
    source_reference: str
    research_only: bool
    quantity_basis: Literal["native"]
    normalizer_version: NormalizerVersion
    native_rate_json: NativeRate
    raw_archive_id: str | None = None
    payload_sha256: str | None = None
    received_at_utc: str | None = None

    @field_validator(
        "observation_id",
        "source_record_id",
        "point_id",
        mode="before",
    )
    @classmethod
    def _identifier(cls, value: Any, info: ValidationInfo) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name} must be a string id")
        return value

    @field_validator("operator_key", "raw_archive_id", mode="before")
    @classmethod
    def _optional_identifier(cls, value: Any, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        return _NativePhysicalBase._identifier(value, info)

    @field_validator(
        "period_start_utc",
        "period_end_utc",
        "observed_at_utc",
        "received_at_utc",
        mode="before",
    )
    @classmethod
    def _utc_text(cls, value: Any, info: ValidationInfo) -> str | None:
        if value is None:
            if info.field_name in {"period_start_utc", "period_end_utc"}:
                raise ValueError(f"{info.field_name} must be an aware UTC timestamp")
            return None
        return _normalize_utc_text(value, info.field_name)

    @field_validator("payload_sha256", mode="before")
    @classmethod
    def _valid_sha256(cls, value: Any, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise ValueError(f"{info.field_name} must be a 64-character SHA-256")
        return value.lower()

    @model_validator(mode="after")
    def _cross_field_constraints(self) -> _NativePhysicalBase:
        if self.normalizer_version != self.native_rate_json.normalizer_version:
            raise ValueError(
                "top-level normalizer_version must match native_rate_json"
            )
        start = _parse_aware_utc(self.period_start_utc, "period_start_utc")
        end = _parse_aware_utc(self.period_end_utc, "period_end_utc")
        if start >= end:
            raise ValueError(
                "period_start_utc must be strictly before period_end_utc"
            )
        return self


class NativeFlow(_NativePhysicalBase):
    """One projected native-unit physical flow observation."""

    kind: str


class NativeCapacity(_NativePhysicalBase):
    """One projected native-unit physical capacity observation."""

    capacity_type: str


def _query_params(point_id: str | None, limit: int) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
        raise ValueError("limit must be an integer between 1 and 2000")
    if point_id is not None:
        if not isinstance(point_id, str):
            raise ValueError("point_id must be a string")
        if not point_id.strip():
            raise ValueError("point_id must be non-blank")
        if len(point_id) > 128:
            raise ValueError("point_id must be at most 128 characters")
    params: dict[str, Any] = {"quantity_basis": "native", "limit": limit}
    if point_id is not None:
        params["point_id"] = point_id
    return params


def fetch_native_flows_result(
    base_url: str,
    *,
    point_id: str | None = None,
    limit: int = 200,
) -> SdkResult[list[NativeFlow]]:
    """Fetch projected native-unit flows, preserving envelope metadata."""

    params = _query_params(point_id, limit)
    data, meta = get_envelope(api_url(base_url, "physical/flows"), params=params)
    if not isinstance(data, list):
        raise SdkProtocolError("Native physical flow data must be a JSON list.")
    return SdkResult([NativeFlow.model_validate(row) for row in data], meta)


def fetch_native_capacity_result(
    base_url: str,
    *,
    point_id: str | None = None,
    limit: int = 200,
) -> SdkResult[list[NativeCapacity]]:
    """Fetch projected native-unit capacities, preserving envelope metadata."""

    params = _query_params(point_id, limit)
    data, meta = get_envelope(api_url(base_url, "physical/capacity"), params=params)
    if not isinstance(data, list):
        raise SdkProtocolError("Native physical capacity data must be a JSON list.")
    return SdkResult([NativeCapacity.model_validate(row) for row in data], meta)


def fetch_native_flows(
    base_url: str,
    *,
    point_id: str | None = None,
    limit: int = 200,
) -> list[NativeFlow]:
    """Fetch projected native-unit flows without envelope metadata."""

    return fetch_native_flows_result(
        base_url, point_id=point_id, limit=limit
    ).data


def fetch_native_capacity(
    base_url: str,
    *,
    point_id: str | None = None,
    limit: int = 200,
) -> list[NativeCapacity]:
    """Fetch projected native-unit capacities without envelope metadata."""

    return fetch_native_capacity_result(
        base_url, point_id=point_id, limit=limit
    ).data
