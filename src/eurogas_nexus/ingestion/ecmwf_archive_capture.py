"""RFC-0007 S2 server-owned, bounded capture of the exact AWS archive pair.

The transport is the existing fixed-origin :class:`EcmwfOpenDataClient`: no
caller URL, source, proxy or header map is accepted.  This module issues one HEAD
per exact official object, then a conditional index GET and a conditional exact
byte-range GET.  It returns raw typed capture DTOs only; it does not decode,
persist, activate a source, grant archive eligibility or expose an API/CLI.

HEAD metadata is the S3 object evidence.  HTTP ``Date`` values and receipt times
are retained separately and never substituted for the object ``LastModified``.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Final
from urllib.parse import quote

import httpx

from eurogas_nexus.ingestion.ecmwf_open_data import (
    MAX_FIELD_BYTES,
    MAX_INDEX_BYTES,
    STEP_HOURS,
    EcmwfArchiveOperation,
    EcmwfFieldReference,
    EcmwfIndex,
    EcmwfIndexRow,
    EcmwfOpenDataClient,
    EcmwfOpenDataError,
    EcmwfOpenDataRequest,
    EcmwfResponseTooLargeError,
    EcmwfSource,
    parse_grib_index,
    resolve_origin,
)

ARCHIVE_CYCLE_HOUR: Final = 0
MAX_ARCHIVE_OBJECT_BYTES: Final = 256 * 1024 * 1024
_CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")


class EcmwfArchiveCaptureError(RuntimeError):
    """Base typed archive-capture refusal with a stable code."""

    code = "ecmwf_archive_capture_error"


class EcmwfArchivePolicyError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_policy_rejected"


class EcmwfArchiveMetadataError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_metadata_invalid"


class EcmwfArchiveChangedError(EcmwfArchiveCaptureError):
    code = "ARCHIVE_OBJECT_CHANGED"


class EcmwfArchiveRangeError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_range_invalid"


class EcmwfArchiveProtocolError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_protocol"


class EcmwfArchiveTransportError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_transport_failed"


class EcmwfArchiveResponseTooLargeError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_response_too_large"


class EcmwfArchiveClockError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_clock_invalid"


class EcmwfArchiveHttpStatusError(EcmwfArchiveCaptureError):
    code = "ecmwf_archive_http_status"

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"unexpected archive HTTP status {status_code}")


@dataclass(frozen=True, slots=True)
class EcmwfArchiveHead:
    """Validated S3 HEAD metadata for one exact official object."""

    bucket: str
    key: str
    url: str
    status_code: int
    etag: str
    version_id: str | None
    last_modified_utc: datetime
    content_length: int
    date_header_utc: datetime | None
    captured_at_utc: datetime


@dataclass(frozen=True, slots=True)
class EcmwfArchiveHttp:
    """Validated HTTP GET metadata; receipt time is separate from Date."""

    url: str
    status_code: int
    etag: str
    version_id: str | None
    last_modified_utc: datetime
    content_range: str | None
    content_length: int
    date_header_utc: datetime | None
    captured_at_utc: datetime


@dataclass(frozen=True, slots=True)
class EcmwfArchiveIndexCapture:
    head: EcmwfArchiveHead
    http: EcmwfArchiveHttp
    raw_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class EcmwfArchiveMessageCapture:
    head: EcmwfArchiveHead
    http: EcmwfArchiveHttp
    raw_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class EcmwfArchiveCapture:
    """Raw typed S2 capture; application owns validation/decoding."""

    request: EcmwfOpenDataRequest
    request_sha256: str
    source: EcmwfSource
    origin: str
    index: EcmwfArchiveIndexCapture
    grib: EcmwfArchiveMessageCapture
    reference: EcmwfFieldReference
    started_at_utc: datetime
    completed_at_utc: datetime


def _safe_http_date(value: str | None) -> datetime | None:
    if not value or len(value) > 128:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None or parsed.tzinfo is None:
        return None
    try:
        return parsed.astimezone(UTC).replace(microsecond=0)
    except (OverflowError, ValueError):
        return None


def _header_text(value: str | None, name: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise EcmwfArchiveMetadataError(f"{name} is missing or not bounded text")
    if value != value.strip() or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in value
    ):
        raise EcmwfArchiveMetadataError(f"{name} contains forbidden bytes")
    return value


def _etag(response: httpx.Response) -> str:
    return _header_text(response.headers.get("etag"), "ETag")


def _version_id(response: httpx.Response) -> str | None:
    raw = response.headers.get("x-amz-version-id")
    if raw is None:
        return None
    value = _header_text(raw, "versionId")
    # S3's literal null-version sentinel is recorded as an explicit absence.
    return None if value.lower() == "null" else value


def _last_modified(response: httpx.Response) -> datetime:
    parsed = _safe_http_date(response.headers.get("last-modified"))
    if parsed is None:
        raise EcmwfArchiveMetadataError("Last-Modified is missing or malformed")
    return parsed


def _content_length(response: httpx.Response, *, maximum: int) -> int:
    raw = response.headers.get("content-length")
    if (
        raw is None
        or len(raw) > 32
        or not raw.isascii()
        or not raw.isdigit()
    ):
        raise EcmwfArchiveMetadataError("Content-Length is missing or malformed")
    value = int(raw)
    if not 1 <= value <= maximum:
        raise EcmwfArchiveMetadataError("Content-Length is outside the reviewed bound")
    return value


def _require_status(
    response: httpx.Response, expected: int, operation: str
) -> None:
    if response.status_code == 412:
        raise EcmwfArchiveChangedError(f"{operation} refused because the object changed")
    if response.status_code != expected:
        raise EcmwfArchiveHttpStatusError(response.status_code)


def _require_identity(response: httpx.Response) -> None:
    encoding = response.headers.get("content-encoding")
    if encoding and encoding.strip().lower() != "identity":
        raise EcmwfArchiveProtocolError("archive content encoding is not identity")


def _clock_now(
    clock: Callable[[], datetime], previous: datetime | None = None
) -> datetime:
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise EcmwfArchiveClockError("capture clock must return an aware UTC datetime")
    try:
        offset = value.utcoffset()
    except (OverflowError, ValueError) as exc:
        raise EcmwfArchiveClockError("capture clock has an invalid UTC offset") from exc
    if offset is None or offset != timedelta(0):
        raise EcmwfArchiveClockError("capture clock must return an aware UTC datetime")
    try:
        normalized = value.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise EcmwfArchiveClockError("capture clock value cannot be normalized") from exc
    if previous is not None and normalized < previous:
        raise EcmwfArchiveClockError("capture clock moved backwards")
    return normalized


def _validate_request(request: object) -> EcmwfOpenDataRequest:
    if not isinstance(request, EcmwfOpenDataRequest):
        raise EcmwfArchivePolicyError("request must be EcmwfOpenDataRequest")
    if request.cycle_hour != ARCHIVE_CYCLE_HOUR:
        raise EcmwfArchivePolicyError("archive capture allows only the 00z cycle")
    if request.step_hours not in STEP_HOURS:
        raise EcmwfArchivePolicyError("archive step must be 0..360 in 3-hour increments")
    return request


def _capture_head(
    client: EcmwfOpenDataClient,
    request: EcmwfOpenDataRequest,
    *,
    operation: EcmwfArchiveOperation,
    bucket: str,
    key: str,
    url: str,
    maximum: int,
    receipt_time: Callable[[], datetime],
) -> EcmwfArchiveHead:
    response, _final_url = client.archive_http(request, operation)
    try:
        _require_status(response, 200, operation.value)
        _require_identity(response)
        captured = receipt_time()
        etag = _etag(response)
        version_id = _version_id(response)
        last_modified = _last_modified(response)
        if last_modified > captured:
            raise EcmwfArchiveMetadataError("HEAD Last-Modified is after its receipt")
        return EcmwfArchiveHead(
            bucket=bucket,
            key=key,
            url=url,
            status_code=response.status_code,
            etag=etag,
            version_id=version_id,
            last_modified_utc=last_modified,
            content_length=_content_length(response, maximum=maximum),
            date_header_utc=_safe_http_date(response.headers.get("date")),
            captured_at_utc=captured,
        )
    finally:
        # HEAD bodies are never read; the response is always released.
        response.close()


def _capture_index(
    client: EcmwfOpenDataClient,
    request: EcmwfOpenDataRequest,
    head: EcmwfArchiveHead,
    *,
    receipt_time: Callable[[], datetime],
) -> EcmwfArchiveIndexCapture:
    response, _final_url = client.archive_http(
        request, EcmwfArchiveOperation.GET_INDEX, if_match=head.etag
    )
    try:
        _require_status(response, 200, "index GET")
        _require_identity(response)
        etag = _etag(response)
        if etag != head.etag:
            raise EcmwfArchiveChangedError("index ETag changed between HEAD and GET")
        if _version_id(response) != head.version_id:
            raise EcmwfArchiveChangedError("index versionId changed between HEAD and GET")
        last_modified = _last_modified(response)
        if last_modified != head.last_modified_utc:
            raise EcmwfArchiveChangedError("index Last-Modified changed between HEAD and GET")
        if response.headers.get("content-range") is not None:
            raise EcmwfArchiveRangeError("full index response has Content-Range")
        content_length = _content_length(response, maximum=MAX_INDEX_BYTES)
        if content_length != head.content_length:
            raise EcmwfArchiveChangedError("index Content-Length changed between HEAD and GET")
        body = EcmwfOpenDataClient._read_raw_limited(
            response,
            MAX_INDEX_BYTES,
            EcmwfArchiveResponseTooLargeError,
            "index body exceeds the reviewed bound",
        )
        if len(body) != content_length:
            raise EcmwfArchiveProtocolError("index body length does not match Content-Length")
        if not body:
            raise EcmwfArchiveMetadataError("index body is empty")
        captured = receipt_time()
        if last_modified > captured:
            raise EcmwfArchiveMetadataError("index Last-Modified is after its receipt")
        return EcmwfArchiveIndexCapture(
            head=head,
            http=EcmwfArchiveHttp(
                url=head.url,
                status_code=response.status_code,
                etag=etag,
                version_id=head.version_id,
                last_modified_utc=last_modified,
                content_range=None,
                content_length=content_length,
                date_header_utc=_safe_http_date(response.headers.get("date")),
                captured_at_utc=captured,
            ),
            raw_bytes=body,
        )
    finally:
        response.close()


def _require_content_range(
    response: httpx.Response, *, start: int, length: int, total: int
) -> str:
    raw = response.headers.get("content-range")
    if raw is None:
        raise EcmwfArchiveRangeError("Content-Range is missing")
    raw = raw.strip()
    if len(raw) > 128:
        raise EcmwfArchiveRangeError("Content-Range is not bounded")
    match = _CONTENT_RANGE_RE.fullmatch(raw)
    if match is None:
        raise EcmwfArchiveRangeError("Content-Range is malformed")
    returned_start, returned_end, returned_total = (int(part) for part in match.groups())
    canonical = f"bytes {returned_start}-{returned_end}/{returned_total}"
    if canonical != raw:
        raise EcmwfArchiveRangeError("Content-Range is not canonical")
    if returned_start != start or returned_end != start + length - 1:
        raise EcmwfArchiveRangeError("Content-Range does not match the selected message")
    if returned_total != total:
        raise EcmwfArchiveChangedError("GRIB object size changed between HEAD and range GET")
    if returned_total < returned_end + 1 or returned_total > MAX_ARCHIVE_OBJECT_BYTES:
        raise EcmwfArchiveRangeError("Content-Range total is outside the reviewed bound")
    return raw


def _parse_index(raw_index: bytes, request: EcmwfOpenDataRequest) -> EcmwfIndex:
    try:
        return parse_grib_index(raw_index, request)
    except EcmwfResponseTooLargeError as exc:
        raise EcmwfArchiveResponseTooLargeError(
            "index exceeds the existing index bound"
        ) from exc
    except EcmwfOpenDataError as exc:
        raise EcmwfArchiveMetadataError(
            "index failed the existing strict index selection"
        ) from exc


def _capture_message(
    client: EcmwfOpenDataClient,
    request: EcmwfOpenDataRequest,
    head: EcmwfArchiveHead,
    selected: EcmwfIndexRow,
    *,
    receipt_time: Callable[[], datetime],
) -> EcmwfArchiveMessageCapture:
    start = selected.byte_offset
    length = selected.byte_length
    if start < 0 or not 1 <= length <= MAX_FIELD_BYTES:
        raise EcmwfArchiveRangeError("selected index range is invalid")
    if start + length > head.content_length:
        raise EcmwfArchiveRangeError("selected message escapes the GRIB object size")
    response, _final_url = client.archive_http(
        request,
        EcmwfArchiveOperation.GET_GRIB_RANGE,
        if_match=head.etag,
        byte_range=(start, length),
    )
    try:
        if response.status_code == 412:
            raise EcmwfArchiveChangedError(
                "GRIB range GET refused because the object changed"
            )
        if response.status_code != 206:
            raise EcmwfArchiveRangeError("provider did not return HTTP 206")
        _require_identity(response)
        etag = _etag(response)
        if etag != head.etag:
            raise EcmwfArchiveChangedError("GRIB ETag changed between HEAD and range GET")
        if _version_id(response) != head.version_id:
            raise EcmwfArchiveChangedError("GRIB versionId changed between HEAD and range GET")
        last_modified = _last_modified(response)
        if last_modified != head.last_modified_utc:
            raise EcmwfArchiveChangedError(
                "GRIB Last-Modified changed between HEAD and range GET"
            )
        content_range = _require_content_range(
            response, start=start, length=length, total=head.content_length
        )
        content_length = _content_length(response, maximum=MAX_FIELD_BYTES)
        if content_length != length:
            raise EcmwfArchiveRangeError(
                "Content-Length does not match the selected message"
            )
        body = EcmwfOpenDataClient._read_raw_limited(
            response,
            length,
            EcmwfArchiveRangeError,
            "range response exceeded the selected message",
        )
        if len(body) != length:
            raise EcmwfArchiveRangeError(
                "range response was shorter than the selected message"
            )
        captured = receipt_time()
        if last_modified > captured:
            raise EcmwfArchiveMetadataError("GRIB Last-Modified is after its receipt")
        return EcmwfArchiveMessageCapture(
            head=head,
            http=EcmwfArchiveHttp(
                url=head.url,
                status_code=response.status_code,
                etag=etag,
                version_id=head.version_id,
                last_modified_utc=last_modified,
                content_range=content_range,
                content_length=content_length,
                date_header_utc=_safe_http_date(response.headers.get("date")),
                captured_at_utc=captured,
            ),
            raw_bytes=body,
        )
    finally:
        response.close()


def capture_archive_sources(
    request: EcmwfOpenDataRequest,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 15.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EcmwfArchiveCapture:
    """Capture the exact AWS index/GRIB pair after server-side HEAD validation.

    Only an :class:`EcmwfOpenDataRequest` is accepted.  The fixed AWS origin,
    official keys, bounded redirects/retries, identity encoding and cookie
    clearing come from the existing client.  No decoded or persisted evidence is
    produced here.
    """

    request = _validate_request(request)
    origin = resolve_origin(EcmwfSource.AWS)
    if origin.bucket is None:
        raise EcmwfArchivePolicyError("reviewed AWS origin has no bucket")
    started = _clock_now(clock)
    previous = started

    def receipt_time() -> datetime:
        nonlocal previous
        previous = _clock_now(clock, previous)
        return previous

    index_key = request.s3_prefix + request.index_filename
    grib_key = request.s3_prefix + request.asset_filename
    index_url = origin.base_url + quote(index_key, safe="/")
    grib_url = origin.base_url + quote(grib_key, safe="/")
    try:
        with EcmwfOpenDataClient(
            source=EcmwfSource.AWS,
            transport=transport,
            timeout_seconds=timeout_seconds,
            sleep=sleep,
            clock=clock,
        ) as client:
            index_head = _capture_head(
                client,
                request,
                operation=EcmwfArchiveOperation.HEAD_INDEX,
                bucket=origin.bucket,
                key=index_key,
                url=index_url,
                maximum=MAX_INDEX_BYTES,
                receipt_time=receipt_time,
            )
            grib_head = _capture_head(
                client,
                request,
                operation=EcmwfArchiveOperation.HEAD_GRIB,
                bucket=origin.bucket,
                key=grib_key,
                url=grib_url,
                maximum=MAX_ARCHIVE_OBJECT_BYTES,
                receipt_time=receipt_time,
            )
            index = _capture_index(client, request, index_head, receipt_time=receipt_time)
            parsed = _parse_index(index.raw_bytes, request)
            grib = _capture_message(
                client,
                request,
                grib_head,
                parsed.selected,
                receipt_time=receipt_time,
            )
            completed = _clock_now(clock, previous)
    except httpx.HTTPError:
        raise EcmwfArchiveTransportError(
            "archive transport failed; no capture evidence was produced"
        ) from None
    reference = EcmwfFieldReference(
        source=EcmwfSource.AWS,
        origin=origin.label,
        asset_url=grib_url,
        request_sha256=request.fingerprint(),
        grib_sha256=hashlib.sha256(grib.raw_bytes).hexdigest(),
        index_sha256=hashlib.sha256(index.raw_bytes).hexdigest(),
        index_row_offset=parsed.selected.row_offset,
        run_date=request.run_date,
        cycle_hour=request.cycle_hour,
        step_hours=request.step_hours,
        valid_at_utc=request.valid_at_utc,
    )
    return EcmwfArchiveCapture(
        request=request,
        request_sha256=request.fingerprint(),
        source=EcmwfSource.AWS,
        origin=origin.label,
        index=index,
        grib=grib,
        reference=reference,
        started_at_utc=started,
        completed_at_utc=completed,
    )
