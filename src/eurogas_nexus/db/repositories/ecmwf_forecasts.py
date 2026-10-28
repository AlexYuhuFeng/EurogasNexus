"""Append-only persistence for decoded ECMWF Open Data 2t point forecasts.

The repository reuses the existing ``forecast_observations`` table.  It does not
create a weather store, activate a source, grant access, or turn an explicit
input location into an observing station.  Every decoded point must be bound to
an existing series and canonical entity by an explicit
``EcmwfForecastPointBinding``.  The repository never infers one series/entity for
the whole field and never creates a series, canonical entity or source mapping.

Only the local receipt completion time is used for ``available_at_utc``.  The
provider's ``Last-Modified`` header is retained as separate provenance and is not
treated as proof of historical first availability.  Physical temperatures are
stored as binary floats; they are approximate physical measurements, not money.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.research import (
    CanonicalEntityRecord,
    ForecastObservationRecord,
    SeriesDefinitionRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.ingestion.ecmwf_grib import (
    EcmwfDecodedField,
    EcmwfPoint,
)
from eurogas_nexus.ingestion.ecmwf_open_data import (
    PARAM_ID,
    PARAM_UNITS,
    EcmwfField,
    EcmwfOpenDataRequest,
    EcmwfSource,
)

SOURCE_SYSTEM = "ECMWF_OPEN_DATA"
MODEL_PROVIDER = "ECMWF"
CANONICAL_UNIT = "degC"
QUALITY_STATE = "FORECAST"
KELVIN_OFFSET = 273.15
TEMPERATURE_TOLERANCE = 1e-9
_QUERY_CHUNK = 400
_RECORD_SCHEMA = "ecmwf-open-data-forecast-observation/v3"
_BATCH_SCHEMA = "ecmwf-open-data-forecast-batch/v2"
_POINT_METHOD_VERSION = "ecmwf-2t-nearest-grid/v1"
_DEG_C_UNITS = frozenset({"degC", "°C"})
_LEGACY_LICENSED_SOURCE_CLASSES = frozenset(
    {"WEATHER", "LICENSED", "LICENSED_WEATHER", "COMMERCIAL_WEATHER"}
)
_APPROVED_POINT_MAPPING_SOURCE_TYPES = frozenset({"GRID_POINT", "POINT"})


class EcmwfForecastPersistenceError(RuntimeError):
    """Base repository failure with a stable operator-safe code."""

    code = "ECMWF_FORECAST_PERSISTENCE_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class EcmwfForecastValidationError(EcmwfForecastPersistenceError):
    """The supplied transport/decoded pair is not internally consistent."""

    code = "ECMWF_FORECAST_VALIDATION_ERROR"


class EcmwfForecastSeriesError(EcmwfForecastPersistenceError):
    """The explicit existing series/identity cannot accept this field."""

    code = "ECMWF_FORECAST_SERIES_INVALID"


class EcmwfForecastConflict(EcmwfForecastPersistenceError):
    """An existing point identity conflicts semantically with the requested append."""

    code = "ECMWF_FORECAST_CONFLICT"


@dataclass(frozen=True)
class EcmwfForecastPointBinding:
    """Explicit identity binding for exactly one decoded point.

    One binding must be supplied for every decoded point.  The binding is input
    only: the repository resolves the existing series, canonical entity and
    source mapping and never creates any of them.
    """

    point_id: str
    series_id: str
    entity_id: str


@dataclass(frozen=True)
class EcmwfForecastInsertSummary:
    """Deterministic batch accounting; it makes no source-activation claim."""

    rows_seen: int
    inserted: int
    duplicates: int
    batch_identity: str
    forecast_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class _ResolvedPointBinding:
    """Validated existing rows for one explicit point binding."""

    binding: EcmwfForecastPointBinding
    series: SeriesDefinitionRecord
    canonical_entity: CanonicalEntityRecord
    mapping: SourceEntityMappingRecord


def append_ecmwf_forecast(
    session: Session,
    *,
    bindings: Sequence[EcmwfForecastPointBinding],
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    ingested_at_utc: datetime,
) -> EcmwfForecastInsertSummary:
    """Append one decoded field as one existing observation per bound point.

    Every decoded point must appear exactly once in ``bindings``.  Each binding
    names an existing series/entity pair and must resolve through exactly one
    approved, active ECMWF Open Data point mapping valid at the forecast validity
    instant.  The caller owns the outer transaction.  A nested savepoint makes a
    conflict discovered after earlier rows in this batch atomic, and the SQLite
    BEGIN helper ensures that savepoint is not silently the outermost transaction.
    """

    if not isinstance(transport, EcmwfField):
        raise EcmwfForecastValidationError("transport must be EcmwfField")
    if not isinstance(decoded, EcmwfDecodedField):
        raise EcmwfForecastValidationError("decoded must be EcmwfDecodedField")
    bindings_by_point = _normalize_bindings(bindings, decoded)
    ingested = _explicit_utc(ingested_at_utc, "ingested_at_utc")

    _validate_transport_pair(transport, decoded)
    run = transport.run
    receipt = _explicit_utc(run.receipt_completed_at_utc, "receipt_completed_at_utc")
    if ingested < receipt:
        raise EcmwfForecastValidationError(
            "ingested_at_utc must not precede the actual local receipt"
        )

    valid_start = _explicit_utc(decoded.metadata.validity_at_utc, "forecast validity")
    resolved_by_point = _resolve_point_bindings(
        session,
        bindings_by_point=bindings_by_point,
        decoded=decoded,
        valid_at_utc=valid_start,
    )

    batch_identity, content_identities, rows = _build_rows(
        resolved_by_point=resolved_by_point,
        transport=transport,
        decoded=decoded,
        valid_start=valid_start,
        ingested_at_utc=ingested,
    )
    expected = {
        row.forecast_observation_id: _expected_signature(
            row,
            content_sha256=content_identities[row.forecast_observation_id],
        )
        for row in rows
    }

    _ensure_sqlite_begin(session)
    duplicates = 0
    pending: list[ForecastObservationRecord] = []
    try:
        with session.begin_nested():
            existing_by_id = _load_existing_by_id(session, tuple(expected))
            for row in rows:
                old = existing_by_id.get(row.forecast_observation_id)
                if old is None:
                    pending.append(row)
                    continue
                if _record_signature(old) != expected[row.forecast_observation_id]:
                    raise EcmwfForecastConflict(
                        "existing forecast observation id has different semantic content"
                    )
                duplicates += 1

            if pending:
                session.add_all(pending)
                session.flush()
    except IntegrityError as exc:
        raise EcmwfForecastConflict(
            "database uniqueness refused a conflicting forecast observation"
        ) from exc

    return EcmwfForecastInsertSummary(
        rows_seen=len(rows),
        inserted=len(pending),
        duplicates=duplicates,
        batch_identity=batch_identity,
        forecast_observation_ids=tuple(row.forecast_observation_id for row in rows),
    )


def _validate_transport_pair(
    transport: EcmwfField, decoded: EcmwfDecodedField
) -> EcmwfOpenDataRequest:
    request = transport.run.request
    if not isinstance(request, EcmwfOpenDataRequest):
        raise EcmwfForecastValidationError("transport has no typed ECMWF request")
    if decoded.reference != transport.reference:
        raise EcmwfForecastValidationError(
            "decoded reference does not exactly match the transport reference"
        )

    grib_bytes = transport.grib_bytes
    if not isinstance(grib_bytes, bytes) or not grib_bytes:
        raise EcmwfForecastValidationError("transport GRIB bytes must be non-empty bytes")
    actual_grib_hash = hashlib.sha256(grib_bytes).hexdigest()
    if (
        actual_grib_hash != transport.grib_sha256
        or actual_grib_hash != transport.reference.grib_sha256
        or actual_grib_hash != decoded.reference.grib_sha256
    ):
        raise EcmwfForecastValidationError("GRIB bytes do not match all reference hashes")

    expected_request_hash = request.fingerprint()
    if (
        transport.run.request_sha256 != expected_request_hash
        or transport.reference.request_sha256 != expected_request_hash
        or decoded.metadata.request_sha256 != expected_request_hash
    ):
        raise EcmwfForecastValidationError("request hash does not match the typed request")

    if (
        transport.reference.run_date != request.run_date
        or transport.reference.cycle_hour != request.cycle_hour
        or transport.reference.step_hours != request.step_hours
        or transport.reference.valid_at_utc != request.valid_at_utc
        or transport.run.issued_at_utc != request.issued_at_utc
        or transport.run.valid_at_utc != request.valid_at_utc
    ):
        raise EcmwfForecastValidationError("request/reference run or validity does not match")

    if not isinstance(transport.run.source, EcmwfSource) or not isinstance(
        transport.reference.source, EcmwfSource
    ):
        raise EcmwfForecastValidationError("transport source is not a typed ECMWF source")
    if transport.reference.source not in {EcmwfSource.ECMWF, EcmwfSource.AWS}:
        raise EcmwfForecastValidationError("transport source is not ECMWF Open Data")
    if transport.run.source != transport.reference.source:
        raise EcmwfForecastValidationError("transport run/reference source disagree")
    if (
        transport.run.origin != transport.reference.origin
        or transport.run.asset_url != transport.reference.asset_url
    ):
        raise EcmwfForecastValidationError("transport run/reference locator disagree")

    start = _explicit_utc(transport.run.request_started_at_utc, "request_started_at_utc")
    receipt = _explicit_utc(transport.run.receipt_completed_at_utc, "receipt_completed_at_utc")
    if receipt < start:
        raise EcmwfForecastValidationError("receipt completed before the request started")
    if transport.run.provider_last_modified_utc is not None:
        _explicit_utc(transport.run.provider_last_modified_utc, "provider_last_modified_utc")
    if not str(transport.run.availability_basis):
        raise EcmwfForecastValidationError("availability basis is missing")
    if not transport.run.origin or not transport.run.asset_url or not transport.run.index_url:
        raise EcmwfForecastValidationError("transport origin/asset/index locator is missing")
    if not isinstance(transport.content_range, str) or not transport.content_range:
        raise EcmwfForecastValidationError("transport content_range is missing")
    if transport.asset_total_bytes < len(grib_bytes):
        raise EcmwfForecastValidationError("transport asset_total_bytes is invalid")

    index = transport.index
    if index.raw_sha256 != transport.reference.index_sha256:
        raise EcmwfForecastValidationError("index hash does not match the reference")
    selected = index.selected
    if selected.row_offset != transport.reference.index_row_offset:
        raise EcmwfForecastValidationError("index row offset does not match the reference")
    if selected.param_id != PARAM_ID:
        raise EcmwfForecastValidationError("selected index row is not paramId 167")
    if selected.units is not None and selected.units != PARAM_UNITS:
        raise EcmwfForecastValidationError("selected index row does not declare kelvin")
    if selected.run_date is not None and selected.run_date != request.run_date:
        raise EcmwfForecastValidationError("selected index run date disagrees")
    if selected.cycle_hour is not None and selected.cycle_hour != request.cycle_hour:
        raise EcmwfForecastValidationError("selected index cycle disagrees")
    if selected.step_hours is not None and selected.step_hours != request.step_hours:
        raise EcmwfForecastValidationError("selected index step disagrees")
    if selected.byte_length != len(grib_bytes):
        raise EcmwfForecastValidationError(
            "selected index byte length does not equal the exact transport message"
        )

    metadata = decoded.metadata
    if metadata.param_id != PARAM_ID or metadata.units != PARAM_UNITS:
        raise EcmwfForecastValidationError("decoder metadata is not 2t in kelvin")
    if metadata.step_type.strip().lower() != "instant":
        raise EcmwfForecastValidationError("decoder metadata is not an instantaneous field")
    if metadata.forecast_step_hours != request.step_hours:
        raise EcmwfForecastValidationError("decoder step does not match the request")
    if metadata.validity_at_utc != transport.reference.valid_at_utc:
        raise EcmwfForecastValidationError("decoder validity does not match the reference")
    if metadata.data_date != request.run_date:
        raise EcmwfForecastValidationError("decoder data date does not match the run")
    if metadata.data_time_utc != request.issued_at_utc:
        raise EcmwfForecastValidationError("decoder data time does not match the issue time")
    if (
        metadata.grid_type != "regular_ll"
        or metadata.grid_ni != 1440
        or metadata.grid_nj != 721
    ):
        raise EcmwfForecastValidationError("decoder grid is not the reviewed IFS 0p25 grid")
    if not metadata.decoder_library or not metadata.decoder_version:
        raise EcmwfForecastValidationError("decoder library/version provenance is missing")

    locations = request.locations
    if len(decoded.points) != len(locations):
        raise EcmwfForecastValidationError("decoded point count does not match the request")
    for point, location in zip(decoded.points, locations, strict=True):
        _validate_point(point, transport, location)

    return request


def _validate_point(point: EcmwfPoint, transport: EcmwfField, location: Any) -> None:
    if not isinstance(point, EcmwfPoint):
        raise EcmwfForecastValidationError("decoded points must be EcmwfPoint values")
    if point.reference != transport.reference:
        raise EcmwfForecastValidationError("decoded point reference does not match transport")
    if point.point_id != location.point_id:
        raise EcmwfForecastValidationError("decoded point id/order does not match the request")
    if (
        point.requested_latitude != location.latitude
        or point.requested_longitude != location.longitude
    ):
        raise EcmwfForecastValidationError(
            "decoded requested coordinates do not match the request"
        )
    coordinates = (
        point.requested_latitude,
        point.requested_longitude,
        point.grid_latitude,
        point.grid_longitude,
        point.distance_km,
        point.temperature_kelvin,
        point.temperature_celsius,
    )
    if not all(isinstance(value, float) and math.isfinite(value) for value in coordinates):
        raise EcmwfForecastValidationError("decoded point contains a non-finite value")
    if not -90.0 <= point.requested_latitude <= 90.0:
        raise EcmwfForecastValidationError("requested latitude is outside [-90, 90]")
    if not -180.0 <= point.requested_longitude <= 180.0:
        raise EcmwfForecastValidationError("requested longitude is outside [-180, 180]")
    if not -90.0 <= point.grid_latitude <= 90.0:
        raise EcmwfForecastValidationError("nearest latitude is outside [-90, 90]")
    if not -180.0 <= point.grid_longitude <= 360.0:
        raise EcmwfForecastValidationError("nearest longitude is outside provider conventions")
    if point.distance_km < 0.0:
        raise EcmwfForecastValidationError("nearest distance is negative")
    if point.temperature_kelvin <= 0.0:
        raise EcmwfForecastValidationError("temperature is not physically positive kelvin")
    if not math.isclose(
        point.temperature_celsius,
        point.temperature_kelvin - KELVIN_OFFSET,
        rel_tol=0.0,
        abs_tol=TEMPERATURE_TOLERANCE,
    ):
        raise EcmwfForecastValidationError(
            "temperature Celsius does not match kelvin within tolerance"
        )


def _normalize_bindings(
    bindings: Sequence[EcmwfForecastPointBinding],
    decoded: EcmwfDecodedField,
) -> dict[str, EcmwfForecastPointBinding]:
    """Require exactly one well-formed binding for every decoded point id."""

    if isinstance(bindings, (str, bytes)) or not isinstance(bindings, Sequence):
        raise EcmwfForecastValidationError(
            "bindings must be a sequence of EcmwfForecastPointBinding values"
        )
    decoded_point_ids = [point.point_id for point in decoded.points]
    if len(bindings) != len(decoded_point_ids):
        raise EcmwfForecastValidationError(
            "bindings must contain exactly one entry for every decoded point"
        )

    by_point: dict[str, EcmwfForecastPointBinding] = {}
    for binding in bindings:
        if not isinstance(binding, EcmwfForecastPointBinding):
            raise EcmwfForecastValidationError(
                "bindings must be EcmwfForecastPointBinding values"
            )
        point_id = _require_text(binding.point_id, "binding point_id")
        _require_text(binding.series_id, "binding series_id")
        _require_text(binding.entity_id, "binding entity_id")
        if point_id in by_point:
            raise EcmwfForecastValidationError(
                f"duplicate binding for decoded point {point_id}"
            )
        by_point[point_id] = binding

    if set(by_point) != set(decoded_point_ids):
        raise EcmwfForecastValidationError(
            "bindings must exactly match the decoded point ids, once each"
        )
    return by_point


def _resolve_point_bindings(
    session: Session,
    *,
    bindings_by_point: Mapping[str, EcmwfForecastPointBinding],
    decoded: EcmwfDecodedField,
    valid_at_utc: datetime,
) -> dict[str, _ResolvedPointBinding]:
    """Resolve all existing identities in bounded batched SELECTs."""

    series_by_id = _load_series(
        session, {binding.series_id for binding in bindings_by_point.values()}
    )
    entities_by_id = _load_canonical_entities(
        session, {binding.entity_id for binding in bindings_by_point.values()}
    )
    mappings_by_point = _load_point_mappings(session, tuple(bindings_by_point))

    resolved: dict[str, _ResolvedPointBinding] = {}
    for point in decoded.points:
        binding = bindings_by_point[point.point_id]
        series = series_by_id.get(binding.series_id)
        if series is None:
            raise EcmwfForecastSeriesError(
                f"series_id {binding.series_id!r} does not exist for point {point.point_id}"
            )
        if series.entity_id != binding.entity_id:
            raise EcmwfForecastSeriesError(
                f"entity_id {binding.entity_id!r} does not match series "
                f"{binding.series_id!r} for point {point.point_id}"
            )
        _validate_series(series)
        entity = entities_by_id.get(binding.entity_id)
        if entity is None:
            raise EcmwfForecastSeriesError(
                f"canonical entity {binding.entity_id!r} does not exist for point "
                f"{point.point_id}"
            )
        mapping = _select_active_point_mapping(
            mappings_by_point.get(point.point_id, ()),
            point_id=point.point_id,
            valid_at_utc=valid_at_utc,
        )
        if mapping.canonical_entity_id != binding.entity_id:
            raise EcmwfForecastSeriesError(
                f"identity mapping for {point.point_id} does not resolve to the "
                "explicitly bound canonical entity"
            )
        resolved[point.point_id] = _ResolvedPointBinding(
            binding=binding,
            series=series,
            canonical_entity=entity,
            mapping=mapping,
        )
    return resolved


def _validate_series(series: SeriesDefinitionRecord) -> None:
    if series.native_unit not in _DEG_C_UNITS:
        raise EcmwfForecastSeriesError(
            "existing series native_unit must be degC (or the canonical degree-C symbol)"
        )
    if "instant" not in series.temporal_type.strip().lower():
        raise EcmwfForecastSeriesError("existing series temporal_type must be instantaneous")
    if series.source_class.strip().upper() in _LEGACY_LICENSED_SOURCE_CLASSES:
        raise EcmwfForecastSeriesError(
            "existing series is declared as legacy licensed weather; open-data rows "
            "must not silently change that rights basis"
        )


def _select_active_point_mapping(
    candidates: Sequence[SourceEntityMappingRecord],
    *,
    point_id: str,
    valid_at_utc: datetime,
) -> SourceEntityMappingRecord:
    """Return the one approved active mapping valid at the forecast instant."""

    active = [
        mapping
        for mapping in candidates
        if str(mapping.mapping_status or "").strip().upper() == "ACTIVE"
        and _db_utc(mapping.valid_from_utc) <= valid_at_utc
        and (
            mapping.valid_to_utc is None
            or _db_utc(mapping.valid_to_utc) > valid_at_utc
        )
    ]
    if not active:
        raise EcmwfForecastSeriesError(
            f"no active approved ECMWF_OPEN_DATA identity mapping is valid for {point_id}"
        )
    if len(active) > 1:
        raise EcmwfForecastSeriesError(
            f"active ECMWF_OPEN_DATA identity mapping is ambiguous for {point_id}"
        )
    mapping = active[0]
    if (
        str(mapping.source_entity_type or "").strip().upper()
        not in _APPROVED_POINT_MAPPING_SOURCE_TYPES
    ):
        raise EcmwfForecastSeriesError(
            f"ECMWF_OPEN_DATA identity mapping for {point_id} is not an approved point mapping"
        )
    return mapping


def _load_series(
    session: Session, series_ids: Sequence[str]
) -> dict[str, SeriesDefinitionRecord]:
    found: dict[str, SeriesDefinitionRecord] = {}
    for chunk in _chunks(sorted(set(series_ids))):
        for series in session.scalars(
            select(SeriesDefinitionRecord).where(
                SeriesDefinitionRecord.series_id.in_(chunk)
            )
        ):
            found[series.series_id] = series
    return found


def _load_canonical_entities(
    session: Session, entity_ids: Sequence[str]
) -> dict[str, CanonicalEntityRecord]:
    found: dict[str, CanonicalEntityRecord] = {}
    for chunk in _chunks(sorted(set(entity_ids))):
        for entity in session.scalars(
            select(CanonicalEntityRecord).where(
                CanonicalEntityRecord.canonical_entity_id.in_(chunk)
            )
        ):
            found[entity.canonical_entity_id] = entity
    return found


def _load_point_mappings(
    session: Session, point_ids: Sequence[str]
) -> dict[str, list[SourceEntityMappingRecord]]:
    found: dict[str, list[SourceEntityMappingRecord]] = {}
    for chunk in _chunks(sorted(set(point_ids))):
        for mapping in session.scalars(
            select(SourceEntityMappingRecord)
            .where(
                SourceEntityMappingRecord.source_id == SOURCE_SYSTEM,
                SourceEntityMappingRecord.source_identifier.in_(chunk),
            )
            .order_by(SourceEntityMappingRecord.mapping_id)
        ):
            found.setdefault(mapping.source_identifier, []).append(mapping)
    return found


def _build_rows(
    *,
    resolved_by_point: Mapping[str, _ResolvedPointBinding],
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    valid_start: datetime,
    ingested_at_utc: datetime,
) -> tuple[str, dict[str, str], list[ForecastObservationRecord]]:
    run = transport.run
    request = run.request
    receipt = _explicit_utc(run.receipt_completed_at_utc, "receipt_completed_at_utc")
    issued = _explicit_utc(run.issued_at_utc, "forecast_issued_at")
    provider_last_modified = (
        None
        if run.provider_last_modified_utc is None
        else _explicit_utc(run.provider_last_modified_utc, "provider_last_modified_utc")
    )
    horizon = f"{request.step_hours}h"
    batch_identity = _sha256_json(
        _batch_payload(
            resolved_by_point=resolved_by_point,
            transport=transport,
            decoded=decoded,
            valid_start=valid_start,
        )
    )

    rows: list[ForecastObservationRecord] = []
    content_identities: dict[str, str] = {}
    for point in decoded.points:
        resolved = resolved_by_point[point.point_id]
        series = resolved.series
        binding = resolved.binding
        record_identity = _record_identity(
            series_id=series.series_id,
            entity_id=binding.entity_id,
            mapping_id=resolved.mapping.mapping_id,
            transport=transport,
            decoded=decoded,
            point=point,
            valid_start=valid_start,
        )
        record_id = "ecmwf-" + _sha256_json(record_identity)
        content_payload = {
            "schema": _RECORD_SCHEMA,
            "source_system": SOURCE_SYSTEM,
            "source_field_version": _source_field_version(
                transport=transport,
                decoded=decoded,
                valid_start=valid_start,
            ),
            "point_id": point.point_id,
            "series": _series_snapshot(series),
            "canonical_entity": _canonical_entity_snapshot(resolved.canonical_entity),
            "identity_mapping": _mapping_snapshot(resolved.mapping),
            "binding": {
                "point_id": point.point_id,
                "series_id": series.series_id,
                "entity_id": binding.entity_id,
                "identity_mapping_id": resolved.mapping.mapping_id,
            },
            "decoder": _decoder_identity(decoded),
            "method_version": _POINT_METHOD_VERSION,
            "requested": [point.requested_latitude, point.requested_longitude],
            "nearest": [point.grid_latitude, point.grid_longitude],
            "distance_km": point.distance_km,
            "unit": CANONICAL_UNIT,
            "temperature_kelvin": point.temperature_kelvin,
            "temperature_celsius": point.temperature_celsius,
        }
        content_sha256 = _sha256_json(content_payload)
        content_identities[record_id] = content_sha256
        provenance = _provenance(
            resolved=resolved,
            transport=transport,
            decoded=decoded,
            point=point,
            valid_start=valid_start,
            batch_identity=batch_identity,
            content_sha256=content_sha256,
            availability_basis=run.availability_basis,
            provider_last_modified=provider_last_modified,
        )
        rows.append(
            ForecastObservationRecord(
                forecast_observation_id=record_id,
                series_id=series.series_id,
                entity_id=binding.entity_id,
                forecast_issued_at=issued,
                forecast_valid_start=valid_start,
                # The existing schema requires a non-null end.  An instantaneous
                # field is represented as a zero-length interval; provenance
                # separately records the true absent end (null).
                forecast_valid_end=valid_start,
                horizon=horizon,
                value=point.temperature_celsius,
                unit=CANONICAL_UNIT,
                source_system=SOURCE_SYSTEM,
                model_provider=MODEL_PROVIDER,
                available_at_utc=receipt,
                ingested_at_utc=ingested_at_utc,
                provenance=provenance,
                quality_state=QUALITY_STATE,
            )
        )
    return batch_identity, content_identities, rows


def _batch_payload(
    *,
    resolved_by_point: Mapping[str, _ResolvedPointBinding],
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    valid_start: datetime,
) -> dict[str, Any]:
    run = transport.run
    request = run.request
    return {
        "schema": _BATCH_SCHEMA,
        "source_system": SOURCE_SYSTEM,
        "bindings": [
            {
                "point_id": point.point_id,
                "series": _series_snapshot(resolved_by_point[point.point_id].series),
                "canonical_entity": _canonical_entity_snapshot(
                    resolved_by_point[point.point_id].canonical_entity
                ),
                "identity_mapping": _mapping_snapshot(
                    resolved_by_point[point.point_id].mapping
                ),
            }
            for point in decoded.points
        ],
        "request_sha256": run.request_sha256,
        "grib_sha256": transport.grib_sha256,
        "index_sha256": transport.reference.index_sha256,
        "issued_at_utc": _iso(run.issued_at_utc),
        "valid_at_utc": _iso(valid_start),
        "run_date": request.run_date.isoformat(),
        "cycle_hour": request.cycle_hour,
        "step_hours": request.step_hours,
        "unit": CANONICAL_UNIT,
        "decoder_library": decoded.metadata.decoder_library,
        "decoder_version": decoded.metadata.decoder_version,
        "points": [
            [
                point.point_id,
                point.requested_latitude,
                point.requested_longitude,
                point.grid_latitude,
                point.grid_longitude,
                point.distance_km,
                point.temperature_kelvin,
                point.temperature_celsius,
            ]
            for point in decoded.points
        ],
    }


def _series_snapshot(series: SeriesDefinitionRecord) -> dict[str, Any]:
    """Semantic series identity bound into the batch/content hashes."""

    return {
        "series_id": series.series_id,
        "name": series.name,
        "metric_type": series.metric_type,
        "entity_type": series.entity_type,
        "entity_id": series.entity_id,
        "product_id": series.product_id,
        "direction": series.direction,
        "source_class": series.source_class,
        "native_frequency": series.native_frequency,
        "native_unit": series.native_unit,
        "currency": series.currency,
        "temporal_type": series.temporal_type,
        "availability_semantics": series.availability_semantics,
        "schema_version": series.schema_version,
    }


def _canonical_entity_snapshot(entity: CanonicalEntityRecord) -> dict[str, Any]:
    """Canonical identity content bound into the batch/content hashes."""

    return {
        "canonical_entity_id": entity.canonical_entity_id,
        "entity_type": entity.entity_type,
        "canonical_code": entity.canonical_code,
        "display_name": entity.display_name,
        "description": entity.description,
        "metadata_json": entity.metadata_json,
    }


def _mapping_snapshot(mapping: SourceEntityMappingRecord) -> dict[str, Any]:
    """Approved mapping identity bound into the batch/content hashes."""

    return {
        "mapping_id": mapping.mapping_id,
        "canonical_entity_id": mapping.canonical_entity_id,
        "source_id": mapping.source_id,
        "source_entity_type": mapping.source_entity_type,
        "source_identifier": mapping.source_identifier,
        "valid_from_utc": _iso(mapping.valid_from_utc),
        "valid_to_utc": (
            None if mapping.valid_to_utc is None else _iso(mapping.valid_to_utc)
        ),
        "mapping_status": mapping.mapping_status,
        "confidence": mapping.confidence,
        "evidence": mapping.evidence,
    }


def _record_identity(
    *,
    series_id: str,
    entity_id: str,
    mapping_id: str,
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    point: EcmwfPoint,
    valid_start: datetime,
) -> dict[str, Any]:
    """Hash only the immutable per-point identity, never the output value.

    The whole-batch request fingerprint and index/receipt metadata are capture
    context, not point identity: adding an unrelated requested location must not
    create a new identity for an already persisted point.
    """

    return {
        "schema": _RECORD_SCHEMA,
        "source_system": SOURCE_SYSTEM,
        "source_field_version": _source_field_version(
            transport=transport,
            decoded=decoded,
            valid_start=valid_start,
        ),
        "series_id": series_id,
        "entity_id": entity_id,
        "identity_mapping_id": mapping_id,
        "decoder": _decoder_identity(decoded),
        "method_version": _POINT_METHOD_VERSION,
        "point_id": point.point_id,
        "requested_coordinates": [point.requested_latitude, point.requested_longitude],
        "nearest_coordinates": [point.grid_latitude, point.grid_longitude],
    }


def _source_field_version(
    *,
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    valid_start: datetime,
) -> dict[str, Any]:
    """Stable provider-field version, independent of capture and request scope."""

    request = transport.run.request
    metadata = decoded.metadata
    return {
        "grib_sha256": transport.grib_sha256,
        "run_date": request.run_date.isoformat(),
        "cycle_hour": request.cycle_hour,
        "step_hours": request.step_hours,
        "valid_at_utc": _iso(valid_start),
        "param_id": metadata.param_id,
        "units": metadata.units,
        "grid": {
            "type": metadata.grid_type,
            "ni": metadata.grid_ni,
            "nj": metadata.grid_nj,
        },
    }


def _decoder_identity(decoded: EcmwfDecodedField) -> dict[str, str]:
    metadata = decoded.metadata
    return {
        "library": metadata.decoder_library,
        "version": metadata.decoder_version,
    }


def _provenance(
    *,
    resolved: _ResolvedPointBinding,
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    point: EcmwfPoint,
    valid_start: datetime,
    batch_identity: str,
    content_sha256: str,
    availability_basis: Any,
    provider_last_modified: datetime | None,
) -> dict[str, Any]:
    run = transport.run
    request = run.request
    reference = transport.reference
    selected = transport.index.selected
    metadata = decoded.metadata
    series = resolved.series
    binding = resolved.binding
    mapping = resolved.mapping
    return {
        "schema": _RECORD_SCHEMA,
        "source_system": SOURCE_SYSTEM,
        "source_origin_class": SOURCE_SYSTEM,
        "legacy_licensed_weather": False,
        "provider": MODEL_PROVIDER,
        "provider_source": run.source.value,
        "provider_origin": run.origin,
        "request_sha256": request.fingerprint(),
        "grib_sha256": transport.grib_sha256,
        "source_field_version": _source_field_version(
            transport=transport,
            decoded=decoded,
            valid_start=valid_start,
        ),
        "index_sha256": transport.reference.index_sha256,
        "batch_identity": batch_identity,
        "content_sha256": content_sha256,
        "series": _series_snapshot(series),
        "entity_id": binding.entity_id,
        "identity_mapping_ids": [mapping.mapping_id],
        "binding": {
            "point_id": point.point_id,
            "series_id": series.series_id,
            "entity_id": binding.entity_id,
            "identity_mapping_id": mapping.mapping_id,
        },
        "canonical_entity": _canonical_entity_snapshot(resolved.canonical_entity),
        "identity_mapping": _mapping_snapshot(mapping),
        "request": {
            "sha256": request.fingerprint(),
            "run_date": request.run_date.isoformat(),
            "cycle_hour": request.cycle_hour,
            "step_hours": request.step_hours,
            "locations": [
                {
                    "point_id": location.point_id,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                }
                for location in request.locations
            ],
        },
        "reference": {
            "source": reference.source.value,
            "origin": reference.origin,
            "asset_url": reference.asset_url,
            "request_sha256": reference.request_sha256,
            "grib_sha256": reference.grib_sha256,
            "index_sha256": reference.index_sha256,
            "index_row_offset": reference.index_row_offset,
            "run_date": reference.run_date.isoformat(),
            "cycle_hour": reference.cycle_hour,
            "step_hours": reference.step_hours,
            "valid_at_utc": _iso(reference.valid_at_utc),
        },
        "grib": {
            "sha256": transport.grib_sha256,
            "size_bytes": len(transport.grib_bytes),
            "content_range": transport.content_range,
            "asset_total_bytes": transport.asset_total_bytes,
        },
        "index": {
            "raw_sha256": transport.index.raw_sha256,
            "raw_size_bytes": transport.index.raw_size_bytes,
            "row_count": transport.index.row_count,
            "selected": {
                "row_offset": selected.row_offset,
                "row_sha256": selected.row_sha256,
                "row_json": selected.row_json,
                "param_id": selected.param_id,
                "short_name": selected.short_name,
                "name": selected.name,
                "units": selected.units,
                "level_type": selected.level_type,
                "level": selected.level,
                "data_type": selected.data_type,
                "stream": selected.stream,
                "run_date": (
                    None if selected.run_date is None else selected.run_date.isoformat()
                ),
                "cycle_hour": selected.cycle_hour,
                "step_hours": selected.step_hours,
                "byte_offset": selected.byte_offset,
                "byte_length": selected.byte_length,
                "param_id_basis": (
                    None if selected.param_id_basis is None else selected.param_id_basis.value
                ),
            },
        },
        "run": {
            "directory_url": run.directory_url,
            "asset_url": run.asset_url,
            "index_url": run.index_url,
            "request_started_at_utc": _iso(run.request_started_at_utc),
            "receipt_completed_at_utc": _iso(run.receipt_completed_at_utc),
            "forecast_issued_at_utc": _iso(run.issued_at_utc),
            "forecast_valid_at_utc": _iso(run.valid_at_utc),
            "provider_last_modified_utc": (
                None if provider_last_modified is None else _iso(provider_last_modified)
            ),
            "availability_basis": str(availability_basis),
            "listing_pages": [
                {"url": page.url, "sha256": page.sha256} for page in run.listing_pages
            ],
        },
        "decoder": {
            "library": metadata.decoder_library,
            "version": metadata.decoder_version,
            "param_id": metadata.param_id,
            "units": metadata.units,
            "step_type": metadata.step_type,
            "grid_type": metadata.grid_type,
            "grid_ni": metadata.grid_ni,
            "grid_nj": metadata.grid_nj,
            "data_date": metadata.data_date.isoformat(),
            "data_time_utc": _iso(metadata.data_time_utc),
            "validity_at_utc": _iso(metadata.validity_at_utc),
            "forecast_step_hours": metadata.forecast_step_hours,
            "request_sha256": metadata.request_sha256,
        },
        "point": {
            "point_id": point.point_id,
            "requested_coordinates": {
                "latitude": point.requested_latitude,
                "longitude": point.requested_longitude,
            },
            "nearest_grid_coordinates": {
                "latitude": point.grid_latitude,
                "longitude": point.grid_longitude,
            },
            "distance_km": point.distance_km,
            "temperature_kelvin": point.temperature_kelvin,
            "temperature_celsius": point.temperature_celsius,
            "represents_observing_station": False,
        },
        "receipt": {
            "receipt_completed_at_utc": _iso(run.receipt_completed_at_utc),
            "provider_last_modified_utc": (
                None if provider_last_modified is None else _iso(provider_last_modified)
            ),
            "provider_last_modified_is_historical_availability_proof": False,
        },
        "availability": {
            "available_at_utc": _iso(run.receipt_completed_at_utc),
            "basis": "actual_local_receipt_completion",
            "provider_last_modified_role": "provider_metadata_only",
        },
        "temporal": {
            "scope": "instant",
            "forecast_valid_start": _iso(run.valid_at_utc),
            "forecast_valid_end": None,
            "database_end_representation": "zero_length_interval_due_to_existing_non_null_schema",
        },
        "quality": {
            "values": "physical_temperature_binary_float",
            "approximation": "declared_approximate_not_financial",
            "quality_state": QUALITY_STATE,
        },
    }


def _load_existing_by_id(
    session: Session, record_ids: Sequence[str]
) -> dict[str, ForecastObservationRecord]:
    found: dict[str, ForecastObservationRecord] = {}
    for chunk in _chunks(sorted(record_ids)):
        for record in session.scalars(
            select(ForecastObservationRecord).where(
                ForecastObservationRecord.forecast_observation_id.in_(chunk)
            )
        ):
            found[record.forecast_observation_id] = record
    return found


def _expected_signature(record: ForecastObservationRecord, *, content_sha256: str) -> tuple:
    return (
        record.forecast_observation_id,
        record.series_id,
        record.entity_id,
        _iso(record.forecast_issued_at),
        _iso(record.forecast_valid_start),
        _iso(record.forecast_valid_end),
        record.horizon,
        float(record.value).hex(),
        record.unit,
        record.source_system,
        record.model_provider,
        record.quality_state,
        content_sha256,
    )


def _record_signature(record: ForecastObservationRecord) -> tuple:
    provenance = record.provenance or {}
    return (
        record.forecast_observation_id,
        record.series_id,
        record.entity_id,
        _iso(record.forecast_issued_at),
        _iso(record.forecast_valid_start),
        _iso(record.forecast_valid_end),
        record.horizon,
        float(record.value).hex(),
        record.unit,
        record.source_system,
        record.model_provider,
        record.quality_state,
        provenance.get("content_sha256"),
    )


def _ensure_sqlite_begin(session: Session) -> None:
    """Force a real SQLite transaction before opening the batch savepoint.

    pysqlite defers BEGIN until the first DML statement.  Without this, the
    savepoint is the outermost transaction and releasing it commits rows that a
    later outer rollback cannot remove.
    """

    connection = session.connection()
    if connection.dialect.name != "sqlite":
        return
    dbapi_connection = connection.connection.driver_connection
    if not dbapi_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")


def _chunks(values: Sequence[str]):
    for start in range(0, len(values), _QUERY_CHUNK):
        yield values[start : start + _QUERY_CHUNK]


def _sha256_json(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EcmwfForecastValidationError(f"{name} must be non-empty text")
    return value


def _explicit_utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise EcmwfForecastValidationError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise EcmwfForecastValidationError(f"{name} must be an aware UTC datetime")
    return value.astimezone(UTC)


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _db_utc(value).isoformat()
