"""RFC-0007 S3 bounded append-or-verify for validated ECMWF archive captures.

The application accepts only the typed server-owned S2 capture.  It validates that
capture through the existing lazy decoder and pure S1 evidence path, then hands the
exact resulting evidence to the existing forecast repository as one optional,
internal trusted archive block.  The caller owns the transaction; this module never
commits or rolls back and never rewrites an existing canonical receipt.

The repository revalidates every constituent transport/decoded/object-hash/range/
clock binding, recomputes the exact S1 policy/method/evidence hashes and mandatory
limitations, and validates stored row bindings before any archive write.  This is
controlled-writer storage trust at the application/DB boundary, not remote-origin
authentication, cryptographic provenance, a rights grant, source activation, an
API, or a future S4 archive read. A caller-supplied JSON block is never accepted
as proof here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy.orm import Session

from eurogas_nexus.application.research.weather_archive_capture import (
    WeatherArchiveCaptureEvidence,
    validate_archive_capture,
)
from eurogas_nexus.application.research.weather_archive_evidence import (
    ArchiveEvidence,
    ArchiveObjectEvidence,
    WeatherArchiveMetadataError,
)
from eurogas_nexus.db.repositories.ecmwf_forecasts import (
    ARCHIVE_EVIDENCE_SCHEMA,
    EcmwfForecastInsertSummary,
    EcmwfForecastPointBinding,
    append_ecmwf_forecast,
    refuse_pending_archive_caller_writes,
)
from eurogas_nexus.ingestion.ecmwf_archive_capture import EcmwfArchiveCapture
from eurogas_nexus.ingestion.ecmwf_grib import EcmwfGribDecoder
from eurogas_nexus.ingestion.ecmwf_open_data import EcmwfFieldReference

PERSISTENCE_EVIDENCE_SCHEMA: Final = ARCHIVE_EVIDENCE_SCHEMA


class WeatherArchivePersistenceError(RuntimeError):
    """Stable application refusal before any archive database write."""

    code = "ECMWF_ARCHIVE_PERSISTENCE_INVALID"


@dataclass(frozen=True, slots=True)
class WeatherArchivePersistenceSummary:
    """Deterministic append accounting for one validated S2 capture.

    ``capture_completed_at_utc`` is this fetch's receipt clock.  It is deliberately
    not called the row's availability: a replay preserves the first actual receipt,
    and the stable object evidence is what makes the replay idempotent.
    """

    rows_seen: int
    inserted: int
    duplicates: int
    batch_identity: str
    forecast_observation_ids: tuple[str, ...]
    availability_basis: str
    archive_policy_hash: str
    archive_method_hash: str
    archive_evidence_hash: str
    effective_archive_available_at_utc: datetime
    capture_completed_at_utc: datetime


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise WeatherArchivePersistenceError(f"{name} must be an aware UTC datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError) as exc:
        raise WeatherArchivePersistenceError(f"{name} has an invalid UTC offset") from exc
    if offset is None or offset != timedelta(0):
        raise WeatherArchivePersistenceError(f"{name} must be an aware UTC datetime")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise WeatherArchivePersistenceError(f"{name} cannot be normalized to UTC") from exc


def _iso(value: object, name: str) -> str:
    return _utc(value, name).isoformat()


def _object_payload(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, ArchiveObjectEvidence):
        raise WeatherArchiveMetadataError(f"{name} object evidence has the wrong type")
    return {
        "bucket": value.bucket,
        "key": value.key,
        "url": value.url,
        "etag": value.etag,
        "version_id": value.version_id,
        "http_etag": value.http_etag,
        "http_version_id": value.http_version_id,
        "size_bytes": value.size_bytes,
        "last_modified_utc": _iso(value.last_modified_utc, f"{name} LastModified"),
        "s3_last_modified_utc": _iso(
            value.s3_last_modified_utc, f"{name} S3 LastModified"
        ),
        "http_last_modified_utc": _iso(
            value.http_last_modified_utc, f"{name} HTTP LastModified"
        ),
        "s3_captured_at_utc": _iso(value.s3_captured_at_utc, f"{name} S3 capture"),
        "http_captured_at_utc": _iso(value.http_captured_at_utc, f"{name} HTTP capture"),
        "sha256": value.sha256,
    }


def build_archive_persistence_payload(
    evidence: ArchiveEvidence,
    *,
    reference: EcmwfFieldReference,
) -> dict[str, object]:
    """Serialize validated S1 evidence without any raw index/GRIB bytes.

    The caller is the internal application boundary.  This builder only preserves
    the already-validated S1 facts; the repository independently verifies that the
    result binds to the exact transport/decoded pair before using it.
    """

    if not isinstance(evidence, ArchiveEvidence):
        raise WeatherArchiveMetadataError("evidence must be ArchiveEvidence")
    if not isinstance(reference, EcmwfFieldReference):
        raise WeatherArchiveMetadataError("reference must be EcmwfFieldReference")
    if evidence.public_read_continuity_assumption is not True:
        raise WeatherArchivePersistenceError(
            "public-read continuity must remain an explicit research assumption"
        )
    if evidence.availability_is_local_receipt is not False:
        raise WeatherArchivePersistenceError(
            "archive evidence must not be represented as a local receipt"
        )
    if evidence.availability_is_prospective is not False:
        raise WeatherArchivePersistenceError(
            "archive evidence must not be represented as prospective availability"
        )
    if evidence.etag_is_content_hash is not False:
        raise WeatherArchivePersistenceError("ETag must remain an opaque validator")

    decoded = evidence.decoded
    return {
        "schema": PERSISTENCE_EVIDENCE_SCHEMA,
        "availability_basis": evidence.availability_basis,
        "provider_source": reference.source.value,
        "provider_origin": reference.origin,
        "index": _object_payload(evidence.index, "index"),
        "grib": _object_payload(evidence.grib, "GRIB"),
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
            "valid_at_utc": _iso(reference.valid_at_utc, "reference validity"),
        },
        "run_date": evidence.run_date.isoformat(),
        "cycle_hour": evidence.cycle_hour,
        "step_hours": evidence.step_hours,
        "index_row_offset": evidence.index_row_offset,
        "message_offset": evidence.message_offset,
        "message_length": evidence.message_length,
        "content_range": evidence.content_range,
        "object_total_bytes": evidence.object_total_bytes,
        "effective_archive_available_at_utc": _iso(
            evidence.effective_archive_available_at_utc,
            "effective archive availability",
        ),
        "captured_at_utc": _iso(evidence.captured_at_utc, "archive capture"),
        "decoded": {
            "decoder_library": decoded.decoder_library,
            "decoder_version": decoded.decoder_version,
            "param_id": decoded.param_id,
            "units": decoded.units,
            "step_type": decoded.step_type,
            "grid_type": decoded.grid_type,
            "grid_ni": decoded.grid_ni,
            "grid_nj": decoded.grid_nj,
            "data_date": decoded.data_date.isoformat(),
            "data_time_utc": _iso(decoded.data_time_utc, "decoded data time"),
            "validity_at_utc": _iso(decoded.validity_at_utc, "decoded validity"),
            "forecast_step_hours": decoded.forecast_step_hours,
            "request_sha256": decoded.request_sha256,
        },
        "policy_hash": evidence.policy_hash,
        "method_hash": evidence.method_hash,
        "evidence_hash": evidence.evidence_hash,
        "limitations": list(evidence.limitations),
        "public_read_continuity_assumption": True,
        "availability_is_local_receipt": False,
        "availability_is_prospective": False,
        "etag_is_content_hash": False,
    }


def persist_weather_archive_capture(
    session: Session,
    capture: EcmwfArchiveCapture,
    *,
    bindings: Sequence[EcmwfForecastPointBinding],
    ingested_at_utc: datetime,
    public_read_continuity_assumption: bool,
    decoder: EcmwfGribDecoder | None = None,
) -> WeatherArchivePersistenceSummary:
    """Validate one typed S2 capture and append-or-verify it through the repository.

    Existing point bindings, series, entities and active mappings are supplied
    explicitly by the caller.  The capture is decoded and S1-validated here, never
    trusted from caller JSON.  No commit, rollback, source activation, default-read
    change or API is introduced.
    """

    if not isinstance(session, Session):
        raise WeatherArchivePersistenceError("session must be a SQLAlchemy Session")
    refuse_pending_archive_caller_writes(session)

    validated: WeatherArchiveCaptureEvidence = validate_archive_capture(
        capture,
        public_read_continuity_assumption=public_read_continuity_assumption,
        decoder=decoder,
    )
    payload = build_archive_persistence_payload(
        validated.evidence,
        reference=validated.field.reference,
    )
    appended: EcmwfForecastInsertSummary = append_ecmwf_forecast(
        session,
        bindings=bindings,
        transport=validated.field,
        decoded=validated.decoded,
        ingested_at_utc=ingested_at_utc,
        archive_evidence=payload,
    )
    evidence = validated.evidence
    return WeatherArchivePersistenceSummary(
        rows_seen=appended.rows_seen,
        inserted=appended.inserted,
        duplicates=appended.duplicates,
        batch_identity=appended.batch_identity,
        forecast_observation_ids=appended.forecast_observation_ids,
        availability_basis=evidence.availability_basis,
        archive_policy_hash=evidence.policy_hash,
        archive_method_hash=evidence.method_hash,
        archive_evidence_hash=evidence.evidence_hash,
        effective_archive_available_at_utc=evidence.effective_archive_available_at_utc,
        capture_completed_at_utc=evidence.captured_at_utc,
    )
