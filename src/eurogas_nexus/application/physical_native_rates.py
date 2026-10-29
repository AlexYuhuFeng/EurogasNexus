"""Strict projection of validated ENTSOG native physical rates.

This module is the reusable read-side foundation for RFC0005.  It does not read
from a database, call a provider, or infer a unit, calorific value, gas station or
current time.  The ENTSOG native-rate core in
:mod:`eurogas_nexus.ingestion.entsog_native_units` remains the only parser.

A supported native row carries its persisted ``normalizer_version`` and
``native_rate_json`` columns.  Legacy ENTSOG rows may carry NULL in both columns;
they have no native payload and no admissible volume.  Row metadata is never a
native payload source.  Every field is re-derived from the original provider
strings before a row may be projected or its stored approximate volume may be
admitted.  A forged canonical value, a changed quantity dimension, an unknown
version, an extra/missing key or a non-string decimal is therefore a typed
refusal rather than a silently empty projection.

Legacy rows are deliberately different:

* a non-ENTSOG row may expose its explicit stored volume when that value is a
  finite number;
* an ENTSOG row with both native columns NULL is legacy and is refused for
  volume use;
* an ENTSOG row with only one native column populated is malformed and is a
  typed refusal, not a legacy row;
* a native ENTSOG energy row never yields a volume, even when the old float
  volume column contains a nonzero value.

Datetime values are emitted as UTC ISO-8601 strings.  An aware input is converted
to UTC.  A naive SQLite value is accepted only when an explicit aware UTC value
cross-checks it: ``normalized_period_start_utc``/``normalized_period_end_utc``
for the corresponding period edge, or ``source_receipt_at_utc``/
``received_at_utc`` for an observed/receipt instant.  Generic timezone labels and
boolean flags are not evidence, and no clock default is used.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, DecimalException
from typing import Any

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

_VOLUME_FIELDS = frozenset({"flow_mcm_d", "capacity_mcm_d"})
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


def row_volume_admissible(
    row: object,
    *,
    volume_field: str,
) -> bool:
    """Whether a row's stored volume may be used as an explicit volume value.

    ``volume_field`` must be chosen by the caller: ``flow_mcm_d`` for a flow row
    or ``capacity_mcm_d`` for a capacity row.  Non-ENTSOG legacy rows qualify
    only when the selected field is a finite number.  ENTSOG legacy rows (both
    native columns NULL) never qualify.  A partial native-column pair is a typed
    refusal.  A validated native volume qualifies only when the stored float
    equals ``float(canonical volume)`` exactly; a native energy row never
    qualifies, regardless of the old volume column.
    """

    _require_volume_field(volume_field)
    if not _is_entsog_source(_row_attr(row, "source_system")):
        return _is_finite_number(_row_attr(row, volume_field))

    columns = _native_columns(row)
    if columns is None:
        return False
    version, payload = columns
    rate = validate_native_rate_payload(payload, version)
    if rate.quantity_kind != "volume":
        return False
    return _stored_volume_matches(row, volume_field, rate)


def project_native_rate_row(
    row: object,
    *,
    volume_field: str,
) -> dict[str, Any]:
    """Project one validated native ENTSOG row without mutating legacy fields.

    The result carries the row/source/point/time identities, the validated
    ``native_rate_json`` contract, its top-level version and the available
    raw-archive lineage.  It never copies the legacy float volume into the
    projection, so an energy row cannot masquerade as a volume.  Non-ENTSOG and
    legacy-only ENTSOG rows are refused.
    """

    _require_volume_field(volume_field)
    if not _is_entsog_source(_row_attr(row, "source_system")):
        raise NativeRateProjectionError(
            "native_rate_source_unsupported",
            "native projection is available only for ENTSOG rows",
        )

    metadata = _metadata(row)
    rate = _require_native_rate(row)
    if rate.quantity_kind == "volume" and not _stored_volume_matches(
        row, volume_field, rate
    ):
        raise NativeRateProjectionError(
            "native_rate_volume_mismatch",
            "stored approximate volume disagrees with the native canonical volume",
        )

    period_start = _required_period_instant(row, metadata, "period_start_utc")
    period_end = _required_period_instant(row, metadata, "period_end_utc")
    if period_end <= period_start:
        raise NativeRateProjectionError(
            "native_rate_period_invalid",
            "period_end_utc must be after period_start_utc",
        )

    projected: dict[str, Any] = {
        "observation_id": _row_attr(row, "observation_id"),
        "source_record_id": _row_attr(row, "source_record_id"),
        "point_id": _row_attr(row, "point_id"),
        "point_name": _row_attr(row, "point_name"),
        "direction": _row_attr(row, "direction"),
    }
    if volume_field == "flow_mcm_d":
        projected["kind"] = _row_attr(row, "kind")
    else:
        projected["capacity_type"] = _row_attr(row, "capacity_type")
    projected.update(
        {
            "period_start_utc": period_start.isoformat(),
            "period_end_utc": period_end.isoformat(),
            "observed_at_utc": _utc_text(
                row, _row_attr(row, "observed_at_utc"), metadata, "observed_at_utc"
            ),
            "source_system": "ENTSOG",
            "operator_key": _optional_text(metadata, "operatorKey"),
            "flow_status": _optional_text(metadata, "flowStatus"),
            "period_type": _optional_text(metadata, "periodType"),
            "source_reference": _row_attr(row, "source_reference"),
            "research_only": _row_attr(row, "research_only"),
            "quantity_basis": "native",
            "normalizer_version": rate.normalizer_version,
            "native_rate_json": _validated_rate_payload(rate),
            "raw_archive_id": _optional_text(metadata, "raw_archive_id")
            or _optional_text(metadata, "archive_id"),
            "payload_sha256": _optional_text(metadata, "payload_sha256"),
            "received_at_utc": _received_at_text(row, metadata),
        }
    )
    return projected


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


def _require_volume_field(volume_field: object) -> None:
    if volume_field not in _VOLUME_FIELDS:
        raise NativeRateProjectionError(
            "unsupported_volume_field",
            "volume_field must be flow_mcm_d or capacity_mcm_d",
        )


def _row_attr(row: object, name: str, default: Any = None) -> Any:
    return getattr(row, name, default)


def _is_entsog_source(value: object) -> bool:
    return isinstance(value, str) and value.strip().casefold() == "entsog"


def _metadata(row: object) -> dict[str, Any]:
    value = _row_attr(row, "metadata_json")
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise NativeRateProjectionError(
            "native_rate_metadata_invalid",
            "row metadata must be an object when present",
        )
    return dict(value)


def _native_columns(row: object) -> tuple[object, object] | None:
    version = _row_attr(row, "normalizer_version")
    payload = _row_attr(row, "native_rate_json")
    if version is None and payload is None:
        return None
    if version is None or payload is None:
        raise NativeRateProjectionError(
            "native_rate_incomplete",
            "native rate columns must be both populated or both NULL",
        )
    return version, payload


def _require_native_rate(row: object) -> EntsogNativeRate:
    columns = _native_columns(row)
    if columns is None:
        raise NativeRateProjectionError(
            "native_rate_missing",
            "row has no persisted native rate payload",
        )
    version, payload = columns
    return validate_native_rate_payload(payload, version)


def _stored_volume_matches(
    row: object,
    volume_field: str,
    rate: EntsogNativeRate,
) -> bool:
    stored = _row_attr(row, volume_field)
    if not _is_finite_number(stored):
        return False
    if rate.volume_mcm_per_day is None:
        return False
    try:
        canonical = float(rate.volume_mcm_per_day)
    except (OverflowError, ValueError):
        return False
    if not math.isfinite(canonical):
        return False
    return float(stored) == canonical


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


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


def _required_period_instant(
    row: object,
    metadata: Mapping[str, Any],
    field: str,
) -> datetime:
    value = _row_attr(row, field)
    if value is None:
        raise NativeRateProjectionError(
            "native_rate_period_missing",
            f"{field} is required for a native physical projection",
        )
    return _utc_datetime(row, value, metadata, field)


def _utc_text(
    row: object,
    value: object,
    metadata: Mapping[str, Any],
    field: str,
) -> str | None:
    if value is None:
        return None
    return _utc_datetime(row, value, metadata, field).isoformat()


def _utc_datetime(
    row: object,
    value: object,
    metadata: Mapping[str, Any],
    field: str,
) -> datetime:
    parsed = _as_datetime(value, field)
    if _is_aware(parsed):
        return parsed.astimezone(UTC)
    if _naive_utc_evidence(row, metadata, field, parsed):
        return parsed.replace(tzinfo=UTC)
    raise NativeRateProjectionError(
        "native_rate_naive_datetime",
        f"{field} is naive and has no exact aware UTC cross-check",
    )


def _received_at_text(row: object, metadata: Mapping[str, Any]) -> str | None:
    candidates: list[tuple[str, object]] = []
    for key in ("received_at_utc", "source_receipt_at_utc"):
        value = metadata.get(key)
        if value is not None:
            candidates.append((key, value))
    row_received = _row_attr(row, "received_at_utc")
    if row_received is not None:
        candidates.append(("received_at_utc", row_received))
    if not candidates:
        return None

    parsed = [(key, _as_datetime(value, key)) for key, value in candidates]
    aware = [value.astimezone(UTC) for _, value in parsed if _is_aware(value)]
    if len(set(aware)) > 1:
        raise NativeRateProjectionError(
            "native_rate_metadata_conflict",
            "row carries conflicting receipt instants",
        )
    if aware:
        canonical = aware[0]
        for _, value in parsed:
            if _is_aware(value):
                continue
            if value != canonical.replace(tzinfo=None):
                raise NativeRateProjectionError(
                    "native_rate_metadata_conflict",
                    "row carries conflicting receipt instants",
                )
        return canonical.isoformat()

    first_key, first_value = parsed[0]
    return _utc_text(row, first_value, metadata, first_key)


def _as_datetime(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            pass
    raise NativeRateProjectionError(
        "native_rate_datetime_invalid",
        f"{field} must be an ISO-8601 instant",
    )


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _naive_utc_evidence(
    row: object,
    metadata: Mapping[str, Any],
    field: str,
    value: datetime,
) -> bool:
    if field == "period_start_utc":
        evidence_keys = ("normalized_period_start_utc",)
    elif field == "period_end_utc":
        evidence_keys = ("normalized_period_end_utc",)
    elif field in ("observed_at_utc", "received_at_utc"):
        evidence_keys = ("source_receipt_at_utc", "received_at_utc")
    else:
        return False

    for key in evidence_keys:
        if _aware_utc_crossmatch(metadata.get(key), value):
            return True
    if field in ("observed_at_utc", "received_at_utc"):
        return _aware_utc_crossmatch(_row_attr(row, "received_at_utc"), value)
    return False


def _aware_utc_crossmatch(evidence: object, value: datetime) -> bool:
    if evidence is None:
        return False
    try:
        parsed = _as_datetime(evidence, "UTC cross-check")
    except NativeRateProjectionError:
        return False
    return _is_aware(parsed) and parsed.astimezone(UTC).replace(tzinfo=None) == value


def _optional_text(metadata: Mapping[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise NativeRateProjectionError(
            "native_rate_metadata_invalid",
            f"{key} must be a nonempty string when present",
        )
    return value


__all__ = [
    "NATIVE_RATE_JSON_KEYS",
    "NativeRateProjectionError",
    "project_native_rate_row",
    "row_volume_admissible",
    "serialize_native_rate",
    "validate_native_rate_payload",
]
