"""Authentic ECMWF GRIB2 decoding through an optional, lazy ecCodes binding.

The transport module returns exact bytes from one indexed GRIB message.  This
module validates the GRIB2 container and the ecCodes metadata against the exact
run/step/2t request before asking ecCodes for one nearest grid point per explicit
location.  A missing or incompatible ecCodes installation is a typed error, not a
mock fallback and not a skipped test.

Unit mechanics tests inject a fake binding.  Such tests prove mechanics only; only
root's isolated real-ecCodes probe can establish that authentic provider GRIB
decodes on this host.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from numbers import Integral, Real

from eurogas_nexus.ingestion.ecmwf_open_data import (
    GRID_NAME,
    MAX_FIELD_BYTES,
    PARAM_ID,
    PARAM_UNITS,
    EcmwfField,
    EcmwfFieldReference,
    EcmwfOpenDataRequest,
)

DECODER_LIBRARY = "ecCodes"
MIN_ECCODES_VERSION = (2, 50, 0)
KELVIN_OFFSET = 273.15
_EXPECTED_GRID_TYPE = "regular_ll"
_EXPECTED_NI = 1440
_EXPECTED_NJ = 721
_VERSION_RE = re.compile(r"^\s*(\d+)\.(\d+)(?:\.(\d+))?")
_INT_TEXT_RE = re.compile(r"^[+-]?\d+$")
_UNSET = object()


class EcmwfGribError(RuntimeError):
    """Base decoder error with a stable machine-readable code."""

    code = "ecmwf_grib_error"


class EcmwfDecoderUnavailableError(EcmwfGribError):
    code = "ecmwf_decoder_unavailable"


class EcmwfDecoderVersionError(EcmwfGribError):
    code = "ecmwf_decoder_version_unsupported"


class EcmwfGribValidationError(EcmwfGribError):
    code = "ecmwf_grib_invalid"


class EcmwfGribHashMismatchError(EcmwfGribError):
    code = "ecmwf_grib_hash_mismatch"


class EcmwfGribReferenceMismatchError(EcmwfGribError):
    code = "ecmwf_grib_reference_mismatch"


class EcmwfGribMetadataError(EcmwfGribError):
    code = "ecmwf_grib_metadata_missing"


class EcmwfGribParamMismatchError(EcmwfGribError):
    code = "ecmwf_grib_param_mismatch"


class EcmwfGribUnitMismatchError(EcmwfGribError):
    code = "ecmwf_grib_unit_mismatch"


class EcmwfGribInstantMismatchError(EcmwfGribError):
    code = "ecmwf_grib_step_type_mismatch"


class EcmwfGribRunMismatchError(EcmwfGribError):
    code = "ecmwf_grib_run_mismatch"


class EcmwfGribValidityMismatchError(EcmwfGribError):
    code = "ecmwf_grib_validity_mismatch"


class EcmwfGribGridMismatchError(EcmwfGribError):
    code = "ecmwf_grib_grid_mismatch"


class EcmwfGribPointError(EcmwfGribError):
    code = "ecmwf_grib_point_invalid"


class EcmwfGribValueMissingError(EcmwfGribError):
    code = "ecmwf_grib_value_missing"


@dataclass(frozen=True, slots=True)
class EcmwfDecoderMetadata:
    """Validated decoder/library, grid, run and validity provenance."""

    decoder_library: str
    decoder_version: str
    param_id: int
    units: str
    step_type: str
    grid_type: str
    grid_ni: int
    grid_nj: int
    data_date: date
    data_time_utc: datetime
    validity_at_utc: datetime
    forecast_step_hours: int
    request_sha256: str


@dataclass(frozen=True, slots=True)
class EcmwfPoint:
    """One explicit input location mapped to an actual nearest grid cell."""

    reference: EcmwfFieldReference
    point_id: str
    requested_latitude: float
    requested_longitude: float
    grid_latitude: float
    grid_longitude: float
    distance_km: float
    temperature_kelvin: float
    temperature_celsius: float

    @property
    def grib_sha256(self) -> str:
        return self.reference.grib_sha256


@dataclass(frozen=True, slots=True)
class EcmwfDecodedField:
    reference: EcmwfFieldReference
    metadata: EcmwfDecoderMetadata
    points: tuple[EcmwfPoint, ...]


def _parse_version(raw: object) -> tuple[int, int, int]:
    match = _VERSION_RE.match(str(raw)) if raw is not None else None
    if match is None:
        raise EcmwfDecoderVersionError("ecCodes version is unavailable or malformed")
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


def _grib2_declared_length(data: bytes) -> int:
    if len(data) < 20:
        raise EcmwfGribValidationError("GRIB message is too short")
    if len(data) > MAX_FIELD_BYTES:
        raise EcmwfGribValidationError("GRIB message exceeds the 32 MiB bound")
    if data[0:4] != b"GRIB":
        raise EcmwfGribValidationError("missing GRIB magic")
    if data[7] != 2:
        raise EcmwfGribValidationError("only GRIB edition 2 is supported")
    declared = int.from_bytes(data[8:16], "big")
    if declared != len(data):
        raise EcmwfGribValidationError("declared GRIB length does not equal the message length")
    if data[-4:] != b"7777":
        raise EcmwfGribValidationError("missing GRIB end marker 7777")
    return declared


def _as_int(value: object, key: str) -> int:
    if isinstance(value, bool):
        raise EcmwfGribMetadataError(f"{key} is not an integer")
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, str) and _INT_TEXT_RE.fullmatch(value.strip()):
        return int(value.strip())
    raise EcmwfGribMetadataError(f"{key} is not an integer")


def _as_text(value: object, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise EcmwfGribMetadataError(f"{key} is not text")
    return value


def _as_float(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise EcmwfGribMetadataError(f"{key} is not numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EcmwfGribMetadataError(f"{key} is not finite")
    return result


def _parse_date(value: object, key: str) -> date:
    raw = str(value).strip()
    if not re.fullmatch(r"\d{8}", raw):
        raise EcmwfGribMetadataError(f"{key} is not YYYYMMDD")
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError as exc:
        raise EcmwfGribMetadataError(f"{key} is not a real date") from exc


def _minutes_of_day(value: object, key: str) -> int:
    if isinstance(value, str):
        if not value.strip().isdigit() or len(value.strip()) > 4:
            raise EcmwfGribMetadataError(f"{key} is not HHMM")
        text = value.strip()
        number = int(text)
        if len(text) <= 2:
            hour, minute = number, 0
        else:
            hour, minute = number // 100, number % 100
    else:
        number = _as_int(value, key)
        hour, minute = number // 100, number % 100
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise EcmwfGribMetadataError(f"{key} is not a valid time")
    return hour * 60 + minute


def _utc_minute(value: datetime, key: str) -> int:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset != timedelta(0):
        raise EcmwfGribValidityMismatchError(f"{key} is not UTC")
    utc_value = value.astimezone(UTC)
    return utc_value.hour * 60 + utc_value.minute


class EcmwfGribDecoder:
    """Lazy ecCodes decoder with a narrow fake-binding seam for unit mechanics."""

    def __init__(self, *, binding: object = _UNSET) -> None:
        self._binding = binding
        self._version: tuple[int, int, int] | None = None
        self._version_text: str | None = None

    def _resolve_binding(self) -> object:
        if self._binding is _UNSET:
            try:
                import eccodes  # type: ignore[import-not-found]
            except ImportError as exc:
                raise EcmwfDecoderUnavailableError(
                    "ecCodes Python binding is not installed"
                ) from exc
            self._binding = eccodes
        if self._binding is None:
            raise EcmwfDecoderUnavailableError("ecCodes Python binding is unavailable")
        binding = self._binding
        required = (
            "codes_new_from_message",
            "codes_get",
            "codes_grib_find_nearest",
            "codes_release",
        )
        if any(not callable(getattr(binding, name, None)) for name in required):
            raise EcmwfDecoderUnavailableError("ecCodes Python binding is incomplete")
        raw_version = getattr(binding, "__version__", None)
        self._version = _parse_version(raw_version)
        self._version_text = str(raw_version)
        if self._version < MIN_ECCODES_VERSION:
            raise EcmwfDecoderVersionError(
                f"ecCodes {MIN_ECCODES_VERSION[0]}.{MIN_ECCODES_VERSION[1]} or newer is required"
            )
        return binding

    @property
    def library_version(self) -> str | None:
        return self._version_text

    @staticmethod
    def _required(binding: object, handle: object, key: str) -> object:
        try:
            return binding.codes_get(handle, key)  # type: ignore[attr-defined]
        except Exception as exc:
            raise EcmwfGribMetadataError(f"required ecCodes key {key} is missing") from exc

    @staticmethod
    def _optional(binding: object, handle: object, key: str) -> object | None:
        try:
            return binding.codes_get(handle, key)  # type: ignore[attr-defined]
        except Exception:
            return None

    def decode(self, field: EcmwfField) -> EcmwfDecodedField:
        if not isinstance(field, EcmwfField):
            raise EcmwfGribValidationError("field must be EcmwfField")
        request = field.run.request
        if not isinstance(request, EcmwfOpenDataRequest):
            raise EcmwfGribValidationError("field has no typed request")
        expected_request_hash = request.fingerprint()
        if (
            field.run.request_sha256 != expected_request_hash
            or field.reference.request_sha256 != expected_request_hash
        ):
            raise EcmwfGribReferenceMismatchError("request hash does not match the field reference")
        actual_hash = hashlib.sha256(field.grib_bytes).hexdigest()
        if actual_hash != field.grib_sha256 or actual_hash != field.reference.grib_sha256:
            raise EcmwfGribHashMismatchError("GRIB bytes do not match the returned hash")
        if (
            field.reference.run_date != request.run_date
            or field.reference.cycle_hour != request.cycle_hour
            or field.reference.step_hours != request.step_hours
            or field.reference.valid_at_utc != request.valid_at_utc
        ):
            raise EcmwfGribReferenceMismatchError(
                "field reference run/validity does not match the request"
            )

        _grib2_declared_length(field.grib_bytes)
        binding = self._resolve_binding()
        version_text = self._version_text
        if version_text is None:
            raise EcmwfDecoderUnavailableError("ecCodes binding version is unavailable")

        handle: object | None = None
        try:
            try:
                handle = binding.codes_new_from_message(field.grib_bytes)  # type: ignore[attr-defined]
            except Exception as exc:
                raise EcmwfGribValidationError("ecCodes rejected the GRIB message") from exc
            if handle is None:
                raise EcmwfGribValidationError("ecCodes returned no GRIB handle")

            param_id = _as_int(self._required(binding, handle, "paramId"), "paramId")
            if param_id != PARAM_ID:
                raise EcmwfGribParamMismatchError("GRIB paramId is not 167")
            units = _as_text(self._required(binding, handle, "units"), "units")
            if units != PARAM_UNITS:
                raise EcmwfGribUnitMismatchError("GRIB units are not K")
            step_type = _as_text(self._required(binding, handle, "stepType"), "stepType")
            if step_type.lower() != "instant":
                raise EcmwfGribInstantMismatchError("GRIB stepType is not instant")

            data_date = _parse_date(self._required(binding, handle, "dataDate"), "dataDate")
            data_time_minutes = _minutes_of_day(
                self._required(binding, handle, "dataTime"), "dataTime"
            )
            validity_date = _parse_date(
                self._required(binding, handle, "validityDate"), "validityDate"
            )
            validity_minutes = _minutes_of_day(
                self._required(binding, handle, "validityTime"), "validityTime"
            )
            step_hours = _as_int(self._required(binding, handle, "step"), "step")

            run_minute = request.cycle_hour * 60
            if data_date != request.run_date or data_time_minutes != run_minute:
                raise EcmwfGribRunMismatchError("GRIB data date/time is not the requested run")
            if step_hours != request.step_hours:
                raise EcmwfGribValidityMismatchError("GRIB step is not the requested step")
            request_valid = request.valid_at_utc
            if (
                validity_date != request_valid.date()
                or validity_minutes != request_valid.hour * 60 + request_valid.minute
            ):
                raise EcmwfGribValidityMismatchError(
                    "GRIB validity date/time is not the requested UTC validity"
                )
            if _utc_minute(request_valid, "request validity") != validity_minutes:
                raise EcmwfGribValidityMismatchError("GRIB validity has a timezone mismatch")

            grid_type = _as_text(
                self._required(binding, handle, "gridType"), "gridType"
            )
            grid_ni = _as_int(self._required(binding, handle, "Ni"), "Ni")
            grid_nj = _as_int(self._required(binding, handle, "Nj"), "Nj")
            if (
                grid_type != _EXPECTED_GRID_TYPE
                or grid_ni != _EXPECTED_NI
                or grid_nj != _EXPECTED_NJ
            ):
                raise EcmwfGribGridMismatchError(
                    f"GRIB grid is not IFS {GRID_NAME} {_EXPECTED_GRID_TYPE}"
                )

            missing_value = self._optional(binding, handle, "missingValue")
            missing_float: float | None
            try:
                missing_float = None if missing_value is None else float(missing_value)
            except (TypeError, ValueError):
                missing_float = None

            points: list[EcmwfPoint] = []
            for location in request.locations:
                try:
                    nearest = binding.codes_grib_find_nearest(  # type: ignore[attr-defined]
                        handle,
                        float(location.latitude),
                        float(location.longitude),
                        npoints=1,
                    )
                except Exception as exc:
                    raise EcmwfGribPointError(
                        f"nearest-point lookup failed for {location.point_id}"
                    ) from exc
                if not isinstance(nearest, (list, tuple)) or len(nearest) != 1:
                    raise EcmwfGribPointError(
                        "nearest-point lookup did not return exactly one point"
                    )
                point = nearest[0]
                if not isinstance(point, Mapping):
                    raise EcmwfGribPointError("nearest-point result is not a mapping")
                for key in ("lat", "lon", "distance", "value"):
                    if key not in point:
                        raise EcmwfGribPointError(f"nearest-point result has no {key}")
                grid_latitude = _as_float(point["lat"], "nearest lat")
                grid_longitude = _as_float(point["lon"], "nearest lon")
                distance_km = _as_float(point["distance"], "nearest distance")
                raw_value = point["value"]
                if raw_value is None:
                    raise EcmwfGribValueMissingError(
                        f"nearest value is missing for {location.point_id}"
                    )
                try:
                    temperature_kelvin = float(raw_value)
                except (TypeError, ValueError) as exc:
                    raise EcmwfGribValueMissingError(
                        f"nearest value is missing for {location.point_id}"
                    ) from exc
                if (
                    not math.isfinite(temperature_kelvin)
                    or temperature_kelvin <= 0.0
                    or (
                        missing_float is not None
                        and temperature_kelvin == missing_float
                    )
                ):
                    raise EcmwfGribValueMissingError(
                        f"nearest value is missing or non-finite for {location.point_id}"
                    )
                if not -90.0 <= grid_latitude <= 90.0:
                    raise EcmwfGribPointError("nearest latitude is outside [-90, 90]")
                # ECMWF regular_ll values may use either [-180, 180] or [0, 360].
                if not -180.0 <= grid_longitude <= 360.0:
                    raise EcmwfGribPointError("nearest longitude is outside provider conventions")
                if distance_km < 0.0:
                    raise EcmwfGribPointError("nearest distance is negative")
                points.append(
                    EcmwfPoint(
                        reference=field.reference,
                        point_id=location.point_id,
                        requested_latitude=location.latitude,
                        requested_longitude=location.longitude,
                        grid_latitude=grid_latitude,
                        grid_longitude=grid_longitude,
                        distance_km=distance_km,
                        temperature_kelvin=temperature_kelvin,
                        temperature_celsius=temperature_kelvin - KELVIN_OFFSET,
                    )
                )

            metadata = EcmwfDecoderMetadata(
                decoder_library=DECODER_LIBRARY,
                decoder_version=version_text,
                param_id=param_id,
                units=units,
                step_type=step_type,
                grid_type=grid_type,
                grid_ni=grid_ni,
                grid_nj=grid_nj,
                data_date=data_date,
                data_time_utc=datetime(
                    data_date.year,
                    data_date.month,
                    data_date.day,
                    data_time_minutes // 60,
                    data_time_minutes % 60,
                    tzinfo=UTC,
                ),
                validity_at_utc=datetime(
                    validity_date.year,
                    validity_date.month,
                    validity_date.day,
                    validity_minutes // 60,
                    validity_minutes % 60,
                    tzinfo=UTC,
                ),
                forecast_step_hours=step_hours,
                request_sha256=expected_request_hash,
            )
            return EcmwfDecodedField(
                reference=field.reference,
                metadata=metadata,
                points=tuple(points),
            )
        finally:
            if handle is not None:
                try:
                    binding.codes_release(handle)  # type: ignore[attr-defined]
                except Exception:
                    # Cleanup is attempted unconditionally; never mask a validation or
                    # point-extraction error with a release diagnostic.
                    pass


def decode_field(field: EcmwfField, *, binding: object = _UNSET) -> EcmwfDecodedField:
    """Convenience entry point; production callers normally reuse a decoder."""

    return EcmwfGribDecoder(binding=binding).decode(field)
