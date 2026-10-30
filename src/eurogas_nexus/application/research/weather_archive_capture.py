"""RFC-0007 S2 application bridge from server-owned capture to S1 evidence.

The ingestion capture is raw and typed.  This module converts it into the existing
S1 archive DTOs, lets the existing lazy ecCodes decoder validate the exact GRIB
message, and then calls the pure S1 reconstructor.  It does not persist rows,
grant archive eligibility, widen a default read or expose an API/CLI.

Unit tests inject a fake decoder to isolate transport mechanics.  Only an actual
ecCodes installation can establish authentic provider decoding.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from eurogas_nexus.application.research.weather_archive_evidence import (
    ARCHIVE_ORIGIN_LABEL,
    ArchiveEvidence,
    ArchiveGribObject,
    ArchiveHttpObjectMetadata,
    ArchiveIndexObject,
    ArchiveS3ObjectMetadata,
    ArchiveSelectedMessage,
    WeatherArchiveAssumptionError,
    WeatherArchiveHashError,
    WeatherArchiveIdentityError,
    WeatherArchiveMetadataError,
    WeatherArchivePolicyError,
    WeatherArchiveRangeError,
    WeatherArchiveTimeError,
    reconstruct_archive_evidence,
)
from eurogas_nexus.ingestion.ecmwf_archive_capture import (
    EcmwfArchiveCapture,
    EcmwfArchiveHead,
    EcmwfArchiveHttp,
    EcmwfArchiveIndexCapture,
    EcmwfArchiveMessageCapture,
)
from eurogas_nexus.ingestion.ecmwf_grib import EcmwfDecodedField, EcmwfGribDecoder
from eurogas_nexus.ingestion.ecmwf_open_data import (
    STEP_HOURS,
    EcmwfAvailabilityBasis,
    EcmwfField,
    EcmwfFieldReference,
    EcmwfIndex,
    EcmwfIndexAmbiguousError,
    EcmwfOpenDataError,
    EcmwfOpenDataRequest,
    EcmwfResponseTooLargeError,
    EcmwfRun,
    EcmwfSource,
    parse_grib_index,
)

ARCHIVE_CYCLE_HOUR: Final = 0


@dataclass(frozen=True, slots=True)
class WeatherArchiveCaptureEvidence:
    """Validated S1 evidence plus the decoded field; no persistence or grant."""

    evidence: ArchiveEvidence
    field: EcmwfField
    decoded: EcmwfDecodedField
    index_head_date_utc: datetime | None
    index_get_date_utc: datetime | None
    grib_head_date_utc: datetime | None
    grib_get_date_utc: datetime | None

    @property
    def availability_basis(self) -> str:
        return self.evidence.availability_basis


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise WeatherArchiveTimeError(f"{name} must be an aware UTC datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError) as exc:
        raise WeatherArchiveTimeError(f"{name} has an invalid UTC offset") from exc
    if offset is None or offset != timedelta(0):
        raise WeatherArchiveTimeError(f"{name} must be an aware UTC datetime")
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise WeatherArchiveTimeError(f"{name} cannot be normalized to UTC") from exc


def _check_capture_clock(capture: EcmwfArchiveCapture) -> None:
    started = _utc(capture.started_at_utc, "capture start")
    completed = _utc(capture.completed_at_utc, "capture completion")
    if completed < started:
        raise WeatherArchiveTimeError("capture timestamps are not monotonic")
    for head, http in (
        (capture.index.head, capture.index.http),
        (capture.grib.head, capture.grib.http),
    ):
        head_at = _utc(head.captured_at_utc, "HEAD receipt")
        http_at = _utc(http.captured_at_utc, "GET receipt")
        if head_at < started or http_at < head_at or completed < http_at:
            raise WeatherArchiveTimeError("capture timestamps are not monotonic")


def _s3_metadata(head: EcmwfArchiveHead) -> ArchiveS3ObjectMetadata:
    if not isinstance(head, EcmwfArchiveHead):
        raise WeatherArchiveMetadataError("capture HEAD metadata has the wrong type")
    return ArchiveS3ObjectMetadata(
        bucket=head.bucket,
        key=head.key,
        etag=head.etag,
        version_id=head.version_id,
        last_modified_utc=head.last_modified_utc,
        size_bytes=head.content_length,
        captured_at_utc=head.captured_at_utc,
    )


def _http_metadata(http: EcmwfArchiveHttp) -> ArchiveHttpObjectMetadata:
    if not isinstance(http, EcmwfArchiveHttp):
        raise WeatherArchiveMetadataError("capture HTTP metadata has the wrong type")
    return ArchiveHttpObjectMetadata(
        url=http.url,
        status_code=http.status_code,
        etag=http.etag,
        version_id=http.version_id,
        last_modified_utc=http.last_modified_utc,
        content_range=http.content_range,
        content_length=http.content_length,
        captured_at_utc=http.captured_at_utc,
    )


def _parse_capture_index(
    capture: EcmwfArchiveCapture, request: EcmwfOpenDataRequest
) -> EcmwfIndex:
    try:
        return parse_grib_index(capture.index.raw_bytes, request)
    except EcmwfIndexAmbiguousError as exc:
        raise WeatherArchiveIdentityError(
            "index selects more than one 2t surface message"
        ) from exc
    except EcmwfResponseTooLargeError as exc:
        raise WeatherArchiveRangeError(
            "index exceeds the existing pure index bound"
        ) from exc
    except EcmwfOpenDataError as exc:
        raise WeatherArchiveMetadataError(
            "index failed existing pure validation"
        ) from exc


def _run(capture: EcmwfArchiveCapture) -> EcmwfRun:
    request = capture.request
    return EcmwfRun(
        request=request,
        request_sha256=capture.request_sha256,
        source=EcmwfSource.AWS,
        origin=ARCHIVE_ORIGIN_LABEL,
        directory_url=capture.index.head.url.rsplit("/", 1)[0] + "/",
        asset_url=capture.grib.head.url,
        index_url=capture.index.head.url,
        # S2 performs direct HEAD capture, not directory-listing discovery.
        listing_pages=(),
        issued_at_utc=request.issued_at_utc,
        valid_at_utc=request.valid_at_utc,
        request_started_at_utc=capture.started_at_utc,
        receipt_completed_at_utc=capture.completed_at_utc,
        provider_last_modified_utc=None,
        availability_basis=EcmwfAvailabilityBasis.LOCAL_RECEIPT_ONLY,
    )


def validate_archive_capture(
    capture: EcmwfArchiveCapture,
    *,
    public_read_continuity_assumption: bool,
    decoder: EcmwfGribDecoder | None = None,
) -> WeatherArchiveCaptureEvidence:
    """Decode and validate one S2 capture, returning immutable evidence only."""

    if public_read_continuity_assumption is not True:
        raise WeatherArchiveAssumptionError(
            "public-read continuity must be explicitly accepted as a research assumption"
        )
    if not isinstance(capture, EcmwfArchiveCapture):
        raise WeatherArchiveMetadataError("capture must be EcmwfArchiveCapture")
    if not isinstance(capture.index, EcmwfArchiveIndexCapture) or not isinstance(
        capture.grib, EcmwfArchiveMessageCapture
    ):
        raise WeatherArchiveMetadataError("capture objects have the wrong type")
    if not isinstance(capture.index.raw_bytes, bytes) or not isinstance(
        capture.grib.raw_bytes, bytes
    ):
        raise WeatherArchiveMetadataError("capture raw bytes must be bytes")
    if not isinstance(capture.reference, EcmwfFieldReference):
        raise WeatherArchiveMetadataError("capture reference has the wrong type")
    if not isinstance(capture.index.head.url, str) or not isinstance(
        capture.grib.head.url, str
    ):
        raise WeatherArchiveMetadataError("capture object URLs must be text")
    if not all(
        isinstance(item, EcmwfArchiveHead | EcmwfArchiveHttp)
        for item in (
            capture.index.head,
            capture.index.http,
            capture.grib.head,
            capture.grib.http,
        )
    ):
        raise WeatherArchiveMetadataError("capture metadata has the wrong type")
    request = capture.request
    if not isinstance(request, EcmwfOpenDataRequest):
        raise WeatherArchiveMetadataError("capture request must be EcmwfOpenDataRequest")
    if request.cycle_hour != ARCHIVE_CYCLE_HOUR:
        raise WeatherArchivePolicyError("archive policy allows only the 00z cycle")
    if request.step_hours not in STEP_HOURS:
        raise WeatherArchivePolicyError("archive policy allows only 0..360 in 3-hour steps")
    if capture.source is not EcmwfSource.AWS or capture.origin != ARCHIVE_ORIGIN_LABEL:
        raise WeatherArchiveIdentityError("capture is not the reviewed AWS origin")
    if capture.request_sha256 != request.fingerprint():
        raise WeatherArchiveIdentityError("capture request hash does not match the request")
    _check_capture_clock(capture)

    parsed = _parse_capture_index(capture, request)
    index_object = ArchiveIndexObject(
        metadata=_s3_metadata(capture.index.head),
        http=_http_metadata(capture.index.http),
        raw_bytes=capture.index.raw_bytes,
    )
    grib_object = ArchiveGribObject(
        metadata=_s3_metadata(capture.grib.head),
        http=_http_metadata(capture.grib.http),
        raw_bytes=capture.grib.raw_bytes,
    )
    content_range = capture.grib.http.content_range
    if content_range is None:
        raise WeatherArchiveRangeError("captured GRIB response has no Content-Range")
    try:
        field = EcmwfField(
            run=_run(capture),
            index=parsed,
            reference=capture.reference,
            grib_bytes=capture.grib.raw_bytes,
            grib_sha256=hashlib.sha256(capture.grib.raw_bytes).hexdigest(),
            content_range=content_range,
            asset_total_bytes=capture.grib.head.content_length,
        )
    except EcmwfOpenDataError as exc:
        raise WeatherArchiveHashError(
            "captured GRIB bytes do not match the capture reference"
        ) from exc

    selected_decoder = decoder if decoder is not None else EcmwfGribDecoder()
    decoded = selected_decoder.decode(field)
    if not isinstance(decoded, EcmwfDecodedField):
        raise WeatherArchiveMetadataError("decoder did not return EcmwfDecodedField")
    if decoded.reference != capture.reference:
        raise WeatherArchiveIdentityError("decoded reference does not match the capture")
    evidence = reconstruct_archive_evidence(
        request=request,
        index_object=index_object,
        grib_object=grib_object,
        selected_message=ArchiveSelectedMessage(
            reference=capture.reference, decoded=decoded.metadata
        ),
        captured_at_utc=capture.completed_at_utc,
        public_read_continuity_assumption=True,
    )
    return WeatherArchiveCaptureEvidence(
        evidence=evidence,
        field=field,
        decoded=decoded,
        index_head_date_utc=capture.index.head.date_header_utc,
        index_get_date_utc=capture.index.http.date_header_utc,
        grib_head_date_utc=capture.grib.head.date_header_utc,
        grib_get_date_utc=capture.grib.http.date_header_utc,
    )
