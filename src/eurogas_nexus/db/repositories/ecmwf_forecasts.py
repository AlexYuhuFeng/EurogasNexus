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

import copy
import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import BigInteger, func, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.research import (
    CanonicalEntityRecord,
    ForecastObservationRecord,
    SeriesDefinitionRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.ingestion.ecmwf_archive_evidence import (
    ARCHIVE_ORIGIN_LABEL,
    archive_evidence_hash,
    archive_limitations,
    archive_method_hash,
    archive_policy_hash,
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
ARCHIVE_EVIDENCE_SCHEMA = "ecmwf-archive-persistence-evidence/v1"
_ARCHIVE_AVAILABILITY_BASIS = "ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION"
_ARCHIVE_BUCKET = "ecmwf-forecasts"
_ARCHIVE_LOOKUP_LIMIT = 16
_ARCHIVE_LOCK_BUDGET_SECONDS = 5.0
_ARCHIVE_LOCK_POLL_SECONDS = 0.05
_DEG_C_UNITS = frozenset({"degC", "°C"})
_ARCHIVE_TOP_LEVEL_KEYS = frozenset(
    {
        "schema",
        "availability_basis",
        "provider_source",
        "provider_origin",
        "index",
        "grib",
        "reference",
        "run_date",
        "cycle_hour",
        "step_hours",
        "index_row_offset",
        "message_offset",
        "message_length",
        "content_range",
        "object_total_bytes",
        "effective_archive_available_at_utc",
        "captured_at_utc",
        "decoded",
        "policy_hash",
        "method_hash",
        "evidence_hash",
        "limitations",
        "public_read_continuity_assumption",
        "availability_is_local_receipt",
        "availability_is_prospective",
        "etag_is_content_hash",
    }
)
_ARCHIVE_OBJECT_KEYS = frozenset(
    {
        "bucket",
        "key",
        "url",
        "etag",
        "version_id",
        "http_etag",
        "http_version_id",
        "size_bytes",
        "last_modified_utc",
        "s3_last_modified_utc",
        "http_last_modified_utc",
        "s3_captured_at_utc",
        "http_captured_at_utc",
        "sha256",
    }
)
_ARCHIVE_OBJECT_STABLE_KEYS = frozenset(
    {
        "bucket",
        "key",
        "url",
        "etag",
        "version_id",
        "http_etag",
        "http_version_id",
        "size_bytes",
        "last_modified_utc",
        "s3_last_modified_utc",
        "http_last_modified_utc",
        "sha256",
    }
)
_ARCHIVE_REFERENCE_KEYS = frozenset(
    {
        "source",
        "origin",
        "asset_url",
        "request_sha256",
        "grib_sha256",
        "index_sha256",
        "index_row_offset",
        "run_date",
        "cycle_hour",
        "step_hours",
        "valid_at_utc",
    }
)
_ARCHIVE_REFERENCE_STABLE_KEYS = _ARCHIVE_REFERENCE_KEYS - {"request_sha256"}
_ARCHIVE_DECODED_KEYS = frozenset(
    {
        "decoder_library",
        "decoder_version",
        "param_id",
        "units",
        "step_type",
        "grid_type",
        "grid_ni",
        "grid_nj",
        "data_date",
        "data_time_utc",
        "validity_at_utc",
        "forecast_step_hours",
        "request_sha256",
    }
)
_ARCHIVE_DECODED_STABLE_KEYS = _ARCHIVE_DECODED_KEYS - {"request_sha256"}
_ARCHIVE_BINDING_KEYS = frozenset(
    {
        "forecast_observation_id",
        "point_id",
        "series_id",
        "entity_id",
        "identity_mapping_id",
        "request_sha256",
        "grib_sha256",
        "index_sha256",
        "valid_at_utc",
    }
)
_ARCHIVE_BINDING_STABLE_KEYS = _ARCHIVE_BINDING_KEYS - {"request_sha256"}
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


class EcmwfForecastArchiveValidationError(EcmwfForecastPersistenceError):
    """The internal archive payload does not bind to the exact transport/decoded pair."""

    code = "ECMWF_ARCHIVE_EVIDENCE_INVALID"


class EcmwfForecastArchiveChanged(EcmwfForecastPersistenceError):
    """A persisted archive object binding has different stable object facts."""

    code = "ARCHIVE_OBJECT_CHANGED"


class EcmwfForecastArchiveEvidenceMissing(EcmwfForecastPersistenceError):
    """An existing canonical row predates archive evidence and is never backfilled."""

    code = "ECMWF_ARCHIVE_EVIDENCE_MISSING"


class EcmwfForecastArchivePendingWrites(EcmwfForecastPersistenceError):
    """Caller-pending ORM writes would be flushed by the existing repository path."""

    code = "ECMWF_ARCHIVE_PENDING_CALLER_WRITES"


class EcmwfForecastArchiveLookupLimit(EcmwfForecastPersistenceError):
    """The bounded archive-identity lookup found more rows than the reviewed limit."""

    code = "ECMWF_ARCHIVE_LOOKUP_LIMIT"


class EcmwfForecastArchiveBusy(EcmwfForecastPersistenceError):
    """The bounded archive-object lock wait expired; the caller may retry.

    Acquired keys are transaction-scoped and are never explicitly released by this
    helper.  This refusal never commits or rolls back the caller's outer
    transaction itself.
    """

    code = "ECMWF_ARCHIVE_BUSY"
    retryable: bool = True


def refuse_pending_archive_caller_writes(session: Session) -> None:
    """Refuse caller-pending ORM state before the archive path touches SQL.

    The existing default append keeps its historical autoflush behaviour.  The
    archive path cannot use it safely: opening the existing nested savepoint (or
    executing the first SELECT) would flush unrelated caller rows.  There is no
    silent flush and no no-autoflush rewrite of the legacy repository here.
    """

    if session.new or session.dirty or session.deleted:
        raise EcmwfForecastArchivePendingWrites(
            "caller-pending ORM writes are refused before the archive append"
        )


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
    archive_evidence: Mapping[str, Any] | None = None,
) -> EcmwfForecastInsertSummary:
    """Append one decoded field as one existing observation per bound point.

    Every decoded point must appear exactly once in ``bindings``.  Each binding
    names an existing series/entity pair and must resolve through exactly one
    approved, active ECMWF Open Data point mapping valid at the forecast validity
    instant.  The caller owns the outer transaction.  A nested savepoint makes a
    conflict discovered after earlier rows in this batch atomic, and the SQLite
    BEGIN helper ensures that savepoint is not silently the outermost transaction.

    ``archive_evidence`` is a deliberately optional, internal trusted payload seam
    for RFC-0007 S3.  It is not remote-origin authentication and not arbitrary JSON
    authorization: the application constructs it from a typed S2 capture validated
    through S1, and this repository revalidates every constituent transport/
    decoded/object-hash/clock binding, recomputes the exact S1 policy/method/
    evidence hashes and mandatory limitations, and checks stored bindings against
    the immutable v3 row before any archive replay.  The default ``None`` path is
    byte-compatible with the existing v3 append and never adds an archive block.
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

    archive_payload: dict[str, Any] | None = None
    if archive_evidence is not None:
        refuse_pending_archive_caller_writes(session)
        archive_payload = _validate_archive_evidence(
            archive_evidence,
            transport=transport,
            decoded=decoded,
            ingested_at_utc=ingested,
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
        archive_evidence=archive_payload,
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
            object_candidates: dict[str, tuple[ForecastObservationRecord, ...]] = {}
            if archive_payload is not None:
                # Serialize the object/binding append-or-verify decision before any
                # archive read.  PostgreSQL transaction-scoped advisory locks cover
                # both inserts and replays without a table lock or unique migration;
                # acquisition is non-blocking under one bounded monotonic budget and
                # keys are sorted so multi-row batches acquire in one global order.
                _lock_archive_object_bindings(session, rows)
                # Every archive check below is a bounded read.  Candidates are the
                # existing canonical rows for the fixed origin/exact object pair/
                # run/validity/binding, never the incoming id alone: a changed raw
                # hash creates a new id, and a non-archive row must not be backfilled.
                for row in rows:
                    object_candidates[row.forecast_observation_id] = (
                        _load_canonical_object_candidates(session, record=row)
                    )
                for row in rows:
                    current = _archive_block(row.provenance)
                    current_signature = _archive_stable_signature(current)
                    for old in object_candidates[row.forecast_observation_id]:
                        old_block = _archive_block(old.provenance)
                        _validate_stored_archive_evidence(old, old_block)
                        if _archive_stable_signature(old_block) != current_signature:
                            raise EcmwfForecastArchiveChanged(
                                "the same archive object/binding has different stable evidence"
                            )

            existing_by_id = _load_existing_by_id(session, tuple(expected))
            for row in rows:
                old = existing_by_id.get(row.forecast_observation_id)
                if old is None:
                    pending.append(row)
                    continue
                if archive_payload is not None:
                    old_block = _archive_block(old.provenance)
                    _validate_stored_archive_evidence(old, old_block)
                    if _archive_stable_signature(old_block) != _archive_stable_signature(
                        _archive_block(row.provenance)
                    ):
                        raise EcmwfForecastArchiveChanged(
                            "existing archive observation has different stable evidence"
                        )
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
    archive_evidence: Mapping[str, Any] | None = None,
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
        if archive_evidence is not None:
            provenance["archive_evidence"] = _archive_row_evidence(
                archive_evidence,
                record_id=record_id,
                resolved=resolved,
                transport=transport,
                point=point,
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


def _archive_row_evidence(
    archive_evidence: Mapping[str, Any],
    *,
    record_id: str,
    resolved: _ResolvedPointBinding,
    transport: EcmwfField,
    point: EcmwfPoint,
) -> dict[str, Any]:
    """Add the immutable v3 binding to one already-validated archive block."""

    block = copy.deepcopy(dict(archive_evidence))
    block["binding"] = {
        "forecast_observation_id": record_id,
        "point_id": point.point_id,
        "series_id": resolved.series.series_id,
        "entity_id": resolved.binding.entity_id,
        "identity_mapping_id": resolved.mapping.mapping_id,
        "request_sha256": transport.run.request_sha256,
        "grib_sha256": transport.grib_sha256,
        "index_sha256": transport.reference.index_sha256,
        "valid_at_utc": _iso(point.reference.valid_at_utc),
    }
    return block


def _validate_archive_evidence(
    archive_evidence: Mapping[str, Any],
    *,
    transport: EcmwfField,
    decoded: EcmwfDecodedField,
    ingested_at_utc: datetime,
) -> dict[str, Any]:
    """Revalidate the internal archive seam against the exact typed capture.

    This is deliberately not remote-origin authentication.  The caller is the
    trusted application boundary; this function only proves that the payload it
    was handed is the exact S1 evidence for this transport/decoded pair and cannot
    silently describe different bytes, validators, object keys, range or clock.
    """

    if not isinstance(archive_evidence, Mapping):
        raise EcmwfForecastArchiveValidationError(
            "archive evidence must be the internal typed mapping"
        )
    if set(archive_evidence) != _ARCHIVE_TOP_LEVEL_KEYS:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence has an unexpected top-level field set"
        )
    if _archive_text(archive_evidence["schema"], "archive schema", maximum=128) != (
        ARCHIVE_EVIDENCE_SCHEMA
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive evidence schema is not supported"
        )
    if _archive_text(
        archive_evidence["availability_basis"],
        "archive availability basis",
        maximum=128,
    ) != _ARCHIVE_AVAILABILITY_BASIS:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence is not the reviewed reconstruction basis"
        )

    request = transport.run.request
    reference = transport.reference
    metadata = decoded.metadata
    if decoded.reference != reference:
        raise EcmwfForecastArchiveValidationError(
            "archive decoded reference does not match transport"
        )
    if reference.source is not EcmwfSource.AWS or reference.origin != ARCHIVE_ORIGIN_LABEL:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence is not the reviewed AWS archive origin"
        )

    if _archive_text(archive_evidence["provider_source"], "provider source") != (
        reference.source.value
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive provider source does not match"
        )
    if _archive_text(archive_evidence["provider_origin"], "provider origin") != (
        reference.origin
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive provider origin does not match"
        )

    reference_payload = archive_evidence["reference"]
    if not isinstance(reference_payload, Mapping) or set(reference_payload) != (
        _ARCHIVE_REFERENCE_KEYS
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference binding has an unexpected field set"
        )
    if _archive_text(reference_payload["source"], "reference source") != (
        reference.source.value
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference source does not match"
        )
    if _archive_text(reference_payload["origin"], "reference origin") != reference.origin:
        raise EcmwfForecastArchiveValidationError(
            "archive reference origin does not match"
        )
    if _archive_text(reference_payload["asset_url"], "reference asset URL") != (
        reference.asset_url
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference asset URL does not match"
        )
    if _archive_hash(reference_payload["request_sha256"], "reference request hash") != (
        request.fingerprint()
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference request hash does not match"
        )
    if _archive_hash(reference_payload["grib_sha256"], "reference GRIB hash") != (
        transport.grib_sha256
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference GRIB hash does not match"
        )
    if _archive_hash(reference_payload["index_sha256"], "reference index hash") != (
        reference.index_sha256
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference index hash does not match"
        )
    offset = _archive_int(
        reference_payload["index_row_offset"], "reference row offset", 0, 10**12
    )
    if offset != reference.index_row_offset:
        raise EcmwfForecastArchiveValidationError(
            "archive reference row offset does not match"
        )
    if _archive_date(reference_payload["run_date"], "reference run date") != (
        request.run_date
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference run date does not match"
        )
    if _archive_int(reference_payload["cycle_hour"], "reference cycle", 0, 23) != (
        request.cycle_hour
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference cycle does not match"
        )
    if _archive_int(reference_payload["step_hours"], "reference step", 0, 10_000) != (
        request.step_hours
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference step does not match"
        )
    if _archive_utc(reference_payload["valid_at_utc"], "reference validity") != (
        reference.valid_at_utc
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive reference validity does not match"
        )

    decoded_payload = archive_evidence["decoded"]
    if not isinstance(decoded_payload, Mapping) or set(decoded_payload) != (
        _ARCHIVE_DECODED_KEYS
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive decoded binding has an unexpected field set"
        )
    decoded_text_fields = (
        "decoder_library",
        "decoder_version",
        "units",
        "step_type",
        "grid_type",
    )
    for name in decoded_text_fields:
        if _archive_text(decoded_payload[name], f"decoded {name}") != getattr(
            metadata, name
        ):
            raise EcmwfForecastArchiveValidationError(
                f"archive decoded {name} does not match"
            )
    if _archive_int(decoded_payload["param_id"], "decoded paramId", 0, 1_000_000) != (
        metadata.param_id
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive decoded paramId does not match"
        )
    if _archive_int(decoded_payload["grid_ni"], "decoded Ni", 1, 1_000_000) != (
        metadata.grid_ni
    ):
        raise EcmwfForecastArchiveValidationError("archive decoded Ni does not match")
    if _archive_int(decoded_payload["grid_nj"], "decoded Nj", 1, 1_000_000) != (
        metadata.grid_nj
    ):
        raise EcmwfForecastArchiveValidationError("archive decoded Nj does not match")
    if _archive_date(decoded_payload["data_date"], "decoded data date") != (
        metadata.data_date
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive decoded data date does not match"
        )
    if _archive_utc(decoded_payload["data_time_utc"], "decoded data time") != (
        metadata.data_time_utc
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive decoded data time does not match"
        )
    if _archive_utc(decoded_payload["validity_at_utc"], "decoded validity") != (
        metadata.validity_at_utc
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive decoded validity does not match"
        )
    decoded_step = _archive_int(
        decoded_payload["forecast_step_hours"], "decoded step", 0, 10_000
    )
    if decoded_step != metadata.forecast_step_hours:
        raise EcmwfForecastArchiveValidationError(
            "archive decoded step does not match"
        )
    if _archive_hash(decoded_payload["request_sha256"], "decoded request hash") != (
        request.fingerprint()
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive decoded request hash does not match"
        )

    index_key = request.s3_prefix + request.index_filename
    grib_key = request.s3_prefix + request.asset_filename
    index_object = _archive_object(
        archive_evidence["index"],
        "archive index",
        expected_key=index_key,
        expected_url=transport.run.index_url,
        expected_size=transport.index.raw_size_bytes,
        expected_hash=reference.index_sha256,
    )
    grib_object = _archive_object(
        archive_evidence["grib"],
        "archive GRIB",
        expected_key=grib_key,
        expected_url=reference.asset_url,
        expected_size=transport.asset_total_bytes,
        expected_hash=transport.grib_sha256,
    )
    if index_object["sha256"] != transport.index.raw_sha256:
        raise EcmwfForecastArchiveValidationError(
            "archive index hash does not match parsed index"
        )
    if grib_object["sha256"] != decoded.reference.grib_sha256:
        raise EcmwfForecastArchiveValidationError(
            "archive GRIB hash does not match decoded"
        )

    selected = transport.index.selected
    index_row_offset = _archive_int(
        archive_evidence["index_row_offset"], "archive index row offset", 0, 10**12
    )
    if index_row_offset != selected.row_offset:
        raise EcmwfForecastArchiveValidationError(
            "archive index row offset does not match"
        )
    message_offset = _archive_int(
        archive_evidence["message_offset"], "archive message offset", 0, 10**12
    )
    if message_offset != selected.byte_offset:
        raise EcmwfForecastArchiveValidationError(
            "archive message offset does not match"
        )
    message_length = _archive_int(
        archive_evidence["message_length"], "archive message length", 1, 10**9
    )
    if message_length != selected.byte_length:
        raise EcmwfForecastArchiveValidationError(
            "archive message length does not match"
        )
    if message_length != len(transport.grib_bytes):
        raise EcmwfForecastArchiveValidationError(
            "archive message length does not match bytes"
        )
    content_range = _archive_text(
        archive_evidence["content_range"], "archive Content-Range", maximum=128
    )
    if content_range != transport.content_range:
        raise EcmwfForecastArchiveValidationError(
            "archive Content-Range does not match"
        )
    object_total = _archive_int(
        archive_evidence["object_total_bytes"], "archive object total", 1, 10**9
    )
    if object_total != transport.asset_total_bytes:
        raise EcmwfForecastArchiveValidationError(
            "archive object total does not match"
        )
    if transport.asset_total_bytes < (selected.byte_offset + selected.byte_length):
        raise EcmwfForecastArchiveValidationError(
            "archive range escapes the transport object"
        )

    run_date = _archive_date(archive_evidence["run_date"], "archive run date")
    cycle_hour = _archive_int(archive_evidence["cycle_hour"], "archive cycle", 0, 23)
    step_hours = _archive_int(archive_evidence["step_hours"], "archive step", 0, 10_000)
    if (run_date, cycle_hour, step_hours) != (
        request.run_date,
        request.cycle_hour,
        request.step_hours,
    ):
        raise EcmwfForecastArchiveValidationError(
            "archive run/step identities do not match"
        )

    effective = _archive_utc(
        archive_evidence["effective_archive_available_at_utc"],
        "archive effective availability",
    )
    expected_effective = max(
        _archive_utc(index_object["last_modified_utc"], "index LastModified"),
        _archive_utc(grib_object["last_modified_utc"], "GRIB LastModified"),
    )
    if effective != expected_effective:
        raise EcmwfForecastArchiveValidationError(
            "archive effective availability is not the conservative max"
        )
    captured_at = _archive_utc(
        archive_evidence["captured_at_utc"], "archive captured_at"
    )
    receipt = _explicit_utc(
        transport.run.receipt_completed_at_utc, "receipt_completed_at_utc"
    )
    if captured_at != receipt:
        raise EcmwfForecastArchiveValidationError(
            "archive capture clock is not the transport receipt"
        )
    if captured_at > ingested_at_utc:
        raise EcmwfForecastArchiveValidationError(
            "archive capture clock is after the explicit ingestion clock"
        )
    if effective > captured_at:
        raise EcmwfForecastArchiveValidationError(
            "archive effective availability is after its capture"
        )
    for name, obj in (("index", index_object), ("GRIB", grib_object)):
        s3_captured = _archive_utc(obj["s3_captured_at_utc"], f"{name} S3 capture")
        http_captured = _archive_utc(
            obj["http_captured_at_utc"], f"{name} HTTP capture"
        )
        if s3_captured > captured_at:
            raise EcmwfForecastArchiveValidationError(
                f"{name} S3 capture is after the overall capture"
            )
        if http_captured > captured_at:
            raise EcmwfForecastArchiveValidationError(
                f"{name} HTTP capture is after the overall capture"
            )

    for name in ("policy_hash", "method_hash", "evidence_hash"):
        _archive_hash(archive_evidence[name], f"archive {name}")
    raw_limitations = archive_evidence["limitations"]
    if not isinstance(raw_limitations, (list, tuple)):
        raise EcmwfForecastArchiveValidationError(
            "archive limitations are missing or unbounded"
        )
    if not 1 <= len(raw_limitations) <= 8:
        raise EcmwfForecastArchiveValidationError(
            "archive limitations are missing or unbounded"
        )
    for item in raw_limitations:
        _archive_text(item, "archive limitation", maximum=1024)
    if archive_evidence["public_read_continuity_assumption"] is not True:
        raise EcmwfForecastArchiveValidationError(
            "archive public-read continuity assumption is not explicit"
        )
    for name in (
        "availability_is_local_receipt",
        "availability_is_prospective",
        "etag_is_content_hash",
    ):
        if archive_evidence[name] is not False:
            raise EcmwfForecastArchiveValidationError(f"archive {name} must be false")

    try:
        normalized = json.loads(
            json.dumps(
                dict(archive_evidence),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence is not a bounded JSON object"
        ) from exc

    # S1 hashes and limitations are recomputed from the validated typed facts.
    # Carrying a syntactically valid 64-hex value or arbitrary limitation text is
    # not evidence identity, and replay must detect a stored block whose carried
    # values no longer describe its own contents.
    expected_policy = archive_policy_hash()
    try:
        expected_method = archive_method_hash(decoded.metadata.decoder_version)
        expected_limitations = archive_limitations(
            normalized["index"]["version_id"],
            normalized["grib"]["version_id"],
        )
        expected_evidence = archive_evidence_hash(normalized)
    except (KeyError, TypeError, ValueError) as exc:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence schema cannot be recomputed"
        ) from exc
    if normalized["policy_hash"] != expected_policy:
        raise EcmwfForecastArchiveValidationError(
            "archive policy hash is not the exact reviewed S1 policy identity"
        )
    if normalized["method_hash"] != expected_method:
        raise EcmwfForecastArchiveValidationError(
            "archive method hash is not the exact typed decoder method identity"
        )
    if tuple(normalized["limitations"]) != expected_limitations:
        raise EcmwfForecastArchiveValidationError(
            "archive limitations are not the exact mandatory S1 limitation set"
        )
    if normalized["evidence_hash"] != expected_evidence:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence hash is not the exact S1 evidence hash"
        )
    return normalized


def _archive_object(
    value: object,
    name: str,
    *,
    expected_key: str,
    expected_url: str,
    expected_size: int,
    expected_hash: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ARCHIVE_OBJECT_KEYS:
        raise EcmwfForecastArchiveValidationError(
            f"{name} has an unexpected object-evidence field set"
        )
    bucket = _archive_text(value["bucket"], f"{name} bucket", maximum=255)
    if bucket != _ARCHIVE_BUCKET:
        raise EcmwfForecastArchiveValidationError(
            f"{name} bucket is not the reviewed bucket"
        )
    if _archive_text(value["key"], f"{name} key", maximum=512) != expected_key:
        raise EcmwfForecastArchiveValidationError(
            f"{name} key is not the exact object"
        )
    if _archive_text(value["url"], f"{name} URL", maximum=1024) != expected_url:
        raise EcmwfForecastArchiveValidationError(
            f"{name} URL is not the exact object"
        )
    etag = _archive_text(value["etag"], f"{name} ETag")
    http_etag = _archive_text(value["http_etag"], f"{name} HTTP ETag")
    if etag != http_etag:
        raise EcmwfForecastArchiveValidationError(f"{name} ETag metadata disagree")
    version = _archive_optional_text(value["version_id"], f"{name} versionId")
    http_version = _archive_optional_text(
        value["http_version_id"], f"{name} HTTP versionId"
    )
    if version != http_version:
        raise EcmwfForecastArchiveValidationError(
            f"{name} versionId metadata disagree"
        )
    size_bytes = _archive_int(value["size_bytes"], f"{name} size", 1, 10**9)
    if size_bytes != expected_size:
        raise EcmwfForecastArchiveValidationError(
            f"{name} size does not match the object"
        )
    last_modified = _archive_utc(value["last_modified_utc"], f"{name} LastModified")
    s3_last_modified = _archive_utc(
        value["s3_last_modified_utc"], f"{name} S3 LastModified"
    )
    http_last_modified = _archive_utc(
        value["http_last_modified_utc"], f"{name} HTTP LastModified"
    )
    if last_modified != s3_last_modified.replace(microsecond=0) or last_modified != (
        http_last_modified.replace(microsecond=0)
    ):
        raise EcmwfForecastArchiveValidationError(
            f"{name} LastModified metadata disagree"
        )
    s3_captured = _archive_utc(value["s3_captured_at_utc"], f"{name} S3 capture")
    http_captured = _archive_utc(
        value["http_captured_at_utc"], f"{name} HTTP capture"
    )
    if s3_captured > http_captured:
        raise EcmwfForecastArchiveValidationError(
            f"{name} capture clocks are not monotonic"
        )
    if last_modified > s3_captured or last_modified > http_captured:
        raise EcmwfForecastArchiveValidationError(
            f"{name} LastModified is after its receipt"
        )
    if _archive_hash(value["sha256"], f"{name} hash") != expected_hash:
        raise EcmwfForecastArchiveValidationError(
            f"{name} hash does not match raw bytes"
        )
    return value


def _archive_block(provenance: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(provenance, Mapping):
        raise EcmwfForecastArchiveEvidenceMissing(
            "existing forecast observation has no archive evidence"
        )
    block = provenance.get("archive_evidence")
    if not isinstance(block, Mapping):
        raise EcmwfForecastArchiveEvidenceMissing(
            "existing forecast observation predates archive evidence; it is not backfilled"
        )
    return block


def _validate_stored_archive_evidence(
    record: ForecastObservationRecord,
    block: Mapping[str, Any],
) -> None:
    """Revalidate a stored block against its own facts and immutable v3 row.

    Replay compares only stable object facts, but a stored block must first be
    self-consistent: its carried policy/method/evidence hashes and limitation text
    are recomputed, and its binding is checked against the original v3 provenance.
    The incoming query fingerprint is deliberately not part of that binding check.
    """

    try:
        if block["schema"] != ARCHIVE_EVIDENCE_SCHEMA:
            raise ValueError("stored archive schema")
        expected_policy = archive_policy_hash()
        expected_method = archive_method_hash(block["decoded"]["decoder_version"])
        expected_limitations = archive_limitations(
            block["index"]["version_id"],
            block["grib"]["version_id"],
        )
        expected_evidence = archive_evidence_hash(block)
    except (KeyError, TypeError, ValueError) as exc:
        raise EcmwfForecastArchiveChanged(
            "stored archive evidence is malformed or not the reviewed S1 schema"
        ) from exc
    stored_limitations = block.get("limitations")
    if (
        block.get("policy_hash") != expected_policy
        or block.get("method_hash") != expected_method
        or not isinstance(stored_limitations, (list, tuple))
        or tuple(stored_limitations) != expected_limitations
        or block.get("evidence_hash") != expected_evidence
    ):
        raise EcmwfForecastArchiveChanged(
            "stored archive hashes or mandatory limitations were altered"
        )
    _validate_archive_row_binding(record, block)


def _validate_archive_row_binding(
    record: ForecastObservationRecord,
    block: Mapping[str, Any],
) -> None:
    """Bind stored archive evidence to the immutable row's original v3 facts."""

    binding = block.get("binding")
    if not isinstance(binding, Mapping) or set(binding) != _ARCHIVE_BINDING_KEYS:
        raise EcmwfForecastArchiveChanged(
            "stored archive row binding is missing or malformed"
        )
    provenance = record.provenance
    if not isinstance(provenance, Mapping):
        raise EcmwfForecastArchiveChanged("stored forecast provenance is missing")
    row_binding = provenance.get("binding")
    request = provenance.get("request")
    reference = provenance.get("reference")
    run = provenance.get("run")
    block_reference = block.get("reference")
    block_index = block.get("index")
    block_grib = block.get("grib")
    block_decoded = block.get("decoded")
    identity_mappings = provenance.get("identity_mapping_ids")
    immutable_mappings = (
        row_binding,
        request,
        reference,
        run,
        block_reference,
        block_index,
        block_grib,
        block_decoded,
    )
    if not all(isinstance(item, Mapping) for item in immutable_mappings):
        raise EcmwfForecastArchiveChanged(
            "stored archive binding has no immutable v3 counterpart"
        )
    if not isinstance(identity_mappings, (list, tuple)):
        raise EcmwfForecastArchiveChanged(
            "stored archive binding has no immutable mapping identity"
        )

    expected_request = provenance.get("request_sha256")
    expected_grib = provenance.get("grib_sha256")
    expected_index = provenance.get("index_sha256")
    expected_valid_at = _iso(record.forecast_valid_start)
    checks = (
        (
            binding["forecast_observation_id"] == record.forecast_observation_id,
            "row id",
        ),
        (binding["point_id"] == row_binding.get("point_id"), "point id"),
        (
            binding["series_id"] == record.series_id
            and binding["series_id"] == row_binding.get("series_id"),
            "series id",
        ),
        (
            binding["entity_id"] == record.entity_id
            and binding["entity_id"] == row_binding.get("entity_id"),
            "entity id",
        ),
        (
            binding["identity_mapping_id"] == row_binding.get("identity_mapping_id")
            and binding["identity_mapping_id"] in identity_mappings,
            "identity mapping",
        ),
        (
            binding["request_sha256"] == expected_request
            and request.get("sha256") == expected_request
            and reference.get("request_sha256") == expected_request
            and block_reference.get("request_sha256") == expected_request
            and block_decoded.get("request_sha256") == expected_request,
            "original request",
        ),
        (
            binding["grib_sha256"] == expected_grib
            and reference.get("grib_sha256") == expected_grib
            and block_grib.get("sha256") == expected_grib,
            "GRIB reference",
        ),
        (
            binding["index_sha256"] == expected_index
            and reference.get("index_sha256") == expected_index
            and block_index.get("sha256") == expected_index,
            "index reference",
        ),
        (
            binding["valid_at_utc"] == expected_valid_at
            and reference.get("valid_at_utc") == expected_valid_at
            and run.get("forecast_valid_at_utc") == expected_valid_at
            and block_reference.get("valid_at_utc") == expected_valid_at,
            "validity",
        ),
        (
            block.get("captured_at_utc") == run.get("receipt_completed_at_utc"),
            "capture receipt",
        ),
    )
    for matched, name in checks:
        if not matched:
            raise EcmwfForecastArchiveChanged(
                f"stored archive binding does not match the immutable v3 {name}"
            )


def _archive_stable_signature(payload: Mapping[str, Any]) -> str:
    try:
        return _sha256_json(_archive_stable_payload(payload))
    except (KeyError, TypeError, ValueError) as exc:
        raise EcmwfForecastArchiveChanged(
            "stored archive evidence is malformed or not the same object binding"
        ) from exc


def _archive_stable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Stable object facts only; receipt clocks and whole-evidence hashes differ."""

    return {
        "schema": payload["schema"],
        "availability_basis": payload["availability_basis"],
        "provider_source": payload["provider_source"],
        "provider_origin": payload["provider_origin"],
        "index": {
            key: payload["index"][key] for key in _ARCHIVE_OBJECT_STABLE_KEYS
        },
        "grib": {
            key: payload["grib"][key] for key in _ARCHIVE_OBJECT_STABLE_KEYS
        },
        "reference": {
            key: payload["reference"][key] for key in _ARCHIVE_REFERENCE_STABLE_KEYS
        },
        "decoded": {
            key: payload["decoded"][key] for key in _ARCHIVE_DECODED_STABLE_KEYS
        },
        "binding": {
            key: payload["binding"][key] for key in _ARCHIVE_BINDING_STABLE_KEYS
        },
        "run_date": payload["run_date"],
        "cycle_hour": payload["cycle_hour"],
        "step_hours": payload["step_hours"],
        "index_row_offset": payload["index_row_offset"],
        "message_offset": payload["message_offset"],
        "message_length": payload["message_length"],
        "content_range": payload["content_range"],
        "object_total_bytes": payload["object_total_bytes"],
        "effective_archive_available_at_utc": payload[
            "effective_archive_available_at_utc"
        ],
        "policy_hash": payload["policy_hash"],
        "method_hash": payload["method_hash"],
        "limitations": payload["limitations"],
        "public_read_continuity_assumption": payload[
            "public_read_continuity_assumption"
        ],
        "availability_is_local_receipt": payload["availability_is_local_receipt"],
        "availability_is_prospective": payload["availability_is_prospective"],
        "etag_is_content_hash": payload["etag_is_content_hash"],
    }


def _load_canonical_object_candidates(
    session: Session, *, record: ForecastObservationRecord
) -> tuple[ForecastObservationRecord, ...]:
    """Find existing v3 rows for the fixed object/run/validity/binding, bounded.

    This deliberately does not require the existing row to have archive evidence.
    A non-archive row is then a typed refusal rather than an opportunity to append
    a new, apparently archive-backed identity beside it.  The v3 locators are the
    exact M2M object URLs, so a different request-location fingerprint is not a
    different object candidate.
    """

    block = _archive_block(record.provenance)
    binding = block.get("binding")
    if not isinstance(binding, Mapping):
        raise EcmwfForecastArchiveValidationError("archive row binding is missing")
    point_id = binding.get("point_id")
    if not isinstance(point_id, str) or not point_id:
        raise EcmwfForecastArchiveValidationError("archive row point binding is invalid")
    provenance = ForecastObservationRecord.provenance
    rows = session.scalars(
        select(ForecastObservationRecord)
        .where(
            ForecastObservationRecord.source_system == SOURCE_SYSTEM,
            ForecastObservationRecord.model_provider == MODEL_PROVIDER,
            ForecastObservationRecord.series_id == record.series_id,
            ForecastObservationRecord.entity_id == record.entity_id,
            ForecastObservationRecord.forecast_valid_start == record.forecast_valid_start,
            ForecastObservationRecord.horizon == record.horizon,
            provenance["provider_source"].as_string() == block["provider_source"],
            provenance["provider_origin"].as_string() == block["provider_origin"],
            provenance[("reference", "asset_url")].as_string() == block["grib"]["url"],
            provenance[("run", "index_url")].as_string() == block["index"]["url"],
            provenance[("request", "run_date")].as_string() == block["run_date"],
            provenance[("request", "cycle_hour")].as_string() == str(block["cycle_hour"]),
            provenance[("request", "step_hours")].as_string() == str(block["step_hours"]),
            provenance[("binding", "point_id")].as_string() == point_id,
        )
        .order_by(ForecastObservationRecord.forecast_observation_id)
        .limit(_ARCHIVE_LOOKUP_LIMIT + 1)
    )
    found = tuple(rows)
    if len(found) > _ARCHIVE_LOOKUP_LIMIT:
        raise EcmwfForecastArchiveLookupLimit(
            "canonical object/binding lookup exceeded its explicit bound"
        )
    return found


def _lock_archive_object_bindings(
    session: Session,
    rows: Sequence[ForecastObservationRecord],
) -> None:
    """Serialize archive object/binding decisions within one bounded wait.

    PostgreSQL transaction-scoped advisory locks are deterministic and released by
    the caller's transaction; this function never commits, rolls back, changes a
    session setting or takes a session/table lock.  It uses the non-blocking
    ``pg_try_advisory_xact_lock`` variant plus short sleeps so the wait cannot rely
    on a caller-configured ``lock_timeout``.  The monotonic deadline is shared by
    every key in the batch: the whole acquisition sequence is bounded by
    ``_ARCHIVE_LOCK_BUDGET_SECONDS`` and raises ``EcmwfForecastArchiveBusy`` when it
    expires.  Keys are sorted for a single acquisition order so a multi-row batch
    cannot deadlock against another sorted batch; a key already acquired is
    transaction-scoped and is never explicitly released by this helper.  SQLite is
    an auxiliary sequential fixture backend only and is not given a fake lock.
    """

    if session.get_bind().dialect.name != "postgresql":
        return
    keys = sorted({_archive_lock_key(row) for row in rows})
    deadline = time.monotonic() + _ARCHIVE_LOCK_BUDGET_SECONDS
    for key in keys:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EcmwfForecastArchiveBusy(
                    "timed out waiting for the archive object advisory lock"
                )
            acquired = session.execute(
                select(func.pg_try_advisory_xact_lock(literal(key, BigInteger)))
            ).scalar_one()
            if acquired:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EcmwfForecastArchiveBusy(
                    "timed out waiting for the archive object advisory lock"
                )
            time.sleep(min(_ARCHIVE_LOCK_POLL_SECONDS, remaining))


def _archive_lock_key(record: ForecastObservationRecord) -> int:
    block = _archive_block(record.provenance)
    try:
        reference = block["reference"]
        if not isinstance(reference, Mapping):
            raise TypeError("archive reference is not a mapping")
        payload = {
            "schema": block["schema"],
            "availability_basis": block["availability_basis"],
            "provider_source": block["provider_source"],
            "provider_origin": block["provider_origin"],
            "index_key": block["index"]["key"],
            "grib_key": block["grib"]["key"],
            "index_url": block["index"]["url"],
            "grib_url": block["grib"]["url"],
            "run_date": block["run_date"],
            "cycle_hour": block["cycle_hour"],
            "step_hours": block["step_hours"],
            "valid_at_utc": reference["valid_at_utc"],
        }
    except (KeyError, TypeError) as exc:
        raise EcmwfForecastArchiveValidationError(
            "archive evidence cannot form a deterministic object lock key"
        ) from exc
    value = int(_sha256_json(payload)[:16], 16)
    return value if value < 2**63 else value - 2**64


def _archive_text(value: object, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise EcmwfForecastArchiveValidationError(
            f"{name} must be non-empty bounded text"
        )
    if value != value.strip() or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in value
    ):
        raise EcmwfForecastArchiveValidationError(
            f"{name} contains forbidden bytes"
        )
    return value


def _archive_optional_text(
    value: object, name: str, *, maximum: int = 512
) -> str | None:
    if value is None:
        return None
    return _archive_text(value, name, maximum=maximum)


def _archive_int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise EcmwfForecastArchiveValidationError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise EcmwfForecastArchiveValidationError(
            f"{name} is outside its reviewed bound"
        )
    return value


def _archive_hash(value: object, name: str) -> str:
    text = _archive_text(value, name, maximum=64)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise EcmwfForecastArchiveValidationError(
            f"{name} must be a lowercase 64-character SHA-256"
        )
    return text


def _archive_date(value: object, name: str) -> date:
    text = _archive_text(value, name, maximum=10)
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise EcmwfForecastArchiveValidationError(
            f"{name} is not an ISO date"
        ) from exc
    if text != parsed.isoformat():
        raise EcmwfForecastArchiveValidationError(
            f"{name} is not a canonical date"
        )
    return parsed


def _archive_utc(value: object, name: str) -> datetime:
    text = _archive_text(value, name, maximum=64)
    try:
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise EcmwfForecastArchiveValidationError(
            f"{name} is not an ISO datetime"
        ) from exc
    if parsed.tzinfo is None:
        raise EcmwfForecastArchiveValidationError(f"{name} must not be naive")
    try:
        offset = parsed.utcoffset()
    except (OverflowError, ValueError) as exc:
        raise EcmwfForecastArchiveValidationError(
            f"{name} has an invalid UTC offset"
        ) from exc
    if offset is None or offset != timedelta(0):
        raise EcmwfForecastArchiveValidationError(f"{name} must be UTC")
    try:
        return parsed.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise EcmwfForecastArchiveValidationError(
            f"{name} cannot be normalized to UTC"
        ) from exc


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
