"""RFC0005 stage C native ENTSOG observation normalization.

The adapter consumes :attr:`EntsogPage.numeric_lexeme_payload`, where JSON numbers
remain the provider's exact source lexemes.  It never converts a number through a
float before parsing: :func:`parse_entsog_native_rate` remains the single math
authority and :func:`serialize_native_rate` the shared strict wire codec.

The public legacy normalizers delegate here.  Native rows use a new deterministic
namespace (``entsog-flow-n1-``/``entsog-capacity-n1-``), so they are additive
representations rather than revisions of existing legacy rows.  An explicit,
aware response receipt is mandatory; provider update stamps and the ingest clock
are never fallbacks.
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.physical_native_rates import serialize_native_rate
from eurogas_nexus.ingestion.entsog_native_units import (
    NORMALIZER_VERSION,
    EntsogNativeRate,
    EntsogNativeUnitError,
    parse_entsog_native_rate,
)

_NATIVE_VALUE_BASIS = "source_string_or_numeric_lexeme"
_ABSENT_VALUE_TEXTS = frozenset({"", "na", "n/a", "-", "none"})
_PROVIDER_METADATA_KEYS = (
    "id",
    "pointKey",
    "pointLabel",
    "operatorKey",
    "operatorLabel",
    "tsoEicCode",
    "directionKey",
    "indicator",
    "flowStatus",
    "unit",
    "periodType",
    "lastUpdateDateTime",
    "timeZone",
)


class EntsogNativeObservationError(ValueError):
    """Typed refusal with a stable code and a payload-free message."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def native_entsog_flow_observations_from_json(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Normalize eligible ENTSOG flow records into native observation rows."""

    return _native_observation_rows(
        payload,
        observed_at_utc=observed_at_utc,
        capacity=False,
    )


def native_entsog_capacity_observations_from_json(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    """Normalize eligible ENTSOG capacity records into native observation rows."""

    return _native_observation_rows(
        payload,
        observed_at_utc=observed_at_utc,
        capacity=True,
    )


def _native_observation_rows(
    payload: dict[str, Any],
    *,
    observed_at_utc: datetime | None,
    capacity: bool,
) -> list[dict[str, Any]]:
    receipt = _require_receipt(observed_at_utc)
    # Local import: public_sources owns the private provider helpers and imports
    # this module lazily from its compatibility wrappers.
    from eurogas_nexus.ingestion.public_sources import (
        _capacity_indicator_type,
        _entsog_native_parse_instant,
        _entsog_native_time_context,
        _extract_records,
        _is_entsog_physical_flow_indicator,
        _metadata_subset,
    )

    contract, zone = _entsog_native_time_context(payload)
    rows: list[dict[str, Any]] = []
    for record in _extract_records(payload, "operationaldatas"):
        record_id = str(record.get("id") or "").strip()
        if not record_id:
            continue
        indicator = str(record.get("indicator") or ("capacity" if capacity else "physical flow"))
        capacity_type: str | None = None
        if capacity:
            capacity_type = _capacity_indicator_type(indicator)
            if capacity_type is None:
                continue
        elif not _is_entsog_physical_flow_indicator(indicator):
            continue

        period_start = _entsog_native_parse_instant(
            record.get("periodFrom"),
            contract=contract,
            zone=zone,
        )
        period_end = _entsog_native_parse_instant(
            record.get("periodTo"),
            contract=contract,
            zone=zone,
        )
        if period_start is None or period_end is None:
            continue
        if period_end <= period_start:
            raise EntsogNativeObservationError(
                "entsog_native_period_invalid",
                "native ENTSOG periods must end strictly after their start",
            )

        raw_value = record.get("value")
        if _native_value_absent(raw_value):
            continue
        if not isinstance(raw_value, str):
            raise EntsogNativeObservationError(
                "entsog_native_value_type_invalid",
                "native ENTSOG values must be original numeric strings, not numbers or booleans",
            )
        raw_unit = record.get("unit")
        if not isinstance(raw_unit, str):
            raise EntsogNativeObservationError(
                "entsog_native_unit_type_invalid",
                "native ENTSOG units must be explicit provider strings",
            )

        try:
            rate = parse_entsog_native_rate(raw_value, raw_unit)
        except EntsogNativeUnitError as exc:
            raise EntsogNativeObservationError(exc.code, exc.message) from None

        native_payload = serialize_native_rate(rate)
        canonical_volume = _canonical_volume(rate)
        kind = "capacity" if capacity else "flow"
        metadata = _metadata_subset(record, list(_PROVIDER_METADATA_KEYS))
        metadata.update(
            {
                "native_value_basis": _NATIVE_VALUE_BASIS,
                "normalized_period_start_utc": period_start.isoformat(),
                "normalized_period_end_utc": period_end.isoformat(),
                "source_receipt_at_utc": receipt.isoformat(),
                "availability_basis": "response_receipt",
            }
        )
        if capacity:
            metadata["capacity_type"] = capacity_type
        else:
            metadata["kind"] = "actual"

        row: dict[str, Any] = {
            "observation_id": _native_observation_id(kind, record_id),
            "point_id": str(record.get("pointKey") or record.get("pointLabel") or record_id),
            "point_name": str(record.get("pointLabel") or record.get("pointKey") or record_id),
            "direction": str(record.get("directionKey") or "unknown").lower()[:8],
            "original_value": float(rate.native_value),
            "original_unit": rate.unit_text,
            "period_start_utc": period_start,
            "period_end_utc": period_end,
            "observed_at_utc": receipt,
            "source_system": "ENTSOG",
            "source_reference": "entsog-operationaldatas",
            "source_record_id": record_id,
            "freshness": "live",
            "research_only": True,
            "normalizer_version": rate.normalizer_version,
            "native_rate_json": native_payload,
            "metadata_json": metadata,
        }
        if capacity:
            row["capacity_type"] = capacity_type
            row["capacity_mcm_d"] = canonical_volume
        else:
            row["kind"] = "actual"
            row["flow_mcm_d"] = canonical_volume
        rows.append(row)
    return rows


def _require_receipt(observed_at_utc: datetime | None) -> datetime:
    if observed_at_utc is None:
        raise EntsogNativeObservationError(
            "entsog_native_receipt_required",
            "an explicit aware ENTSOG response receipt is required",
        )
    if not isinstance(observed_at_utc, datetime):
        raise EntsogNativeObservationError(
            "entsog_native_receipt_invalid",
            "the ENTSOG response receipt must be a datetime",
        )
    if observed_at_utc.tzinfo is None or observed_at_utc.utcoffset() is None:
        raise EntsogNativeObservationError(
            "entsog_native_receipt_naive",
            "the ENTSOG response receipt must be timezone-aware",
        )
    return observed_at_utc.astimezone(UTC)


def _native_value_absent(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().casefold() in _ABSENT_VALUE_TEXTS


def _canonical_volume(rate: EntsogNativeRate) -> float | None:
    """Expose a volume only for a native volume rate; energy always stays ``None``."""

    if rate.quantity_kind != "volume" or rate.volume_mcm_per_day is None:
        return None
    value = float(rate.volume_mcm_per_day)
    if not math.isfinite(value):
        raise EntsogNativeObservationError(
            "entsog_native_volume_out_of_bounds",
            "canonical native volume is not representable as a finite float",
        )
    return value


def _native_observation_id(kind: str, record_id: str) -> str:
    """Stable RFC0005 namespace; the provider's own record id is not changed."""

    prefix = f"entsog-{kind}-n1-"
    material = "\x1f".join(
        ("ENTSOG", "operationaldatas", kind, record_id, NORMALIZER_VERSION)
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:48]
    max_length = 64 if kind == "flow" else 96
    return f"{prefix}{digest}"[:max_length]


__all__ = [
    "EntsogNativeObservationError",
    "native_entsog_capacity_observations_from_json",
    "native_entsog_flow_observations_from_json",
]
