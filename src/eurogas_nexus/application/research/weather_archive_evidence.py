"""Pure RFC-0007 S1 ECMWF archive availability evidence.

Validates server-captured, typed S3/HTTP metadata for the exact official
ECMWF-managed AWS ``.index``/``.grib2`` pair and reconstructs

``max(index LastModified, selected GRIB LastModified)``

under the explicit, research-only ``ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION``
basis.  This module performs no network, database, ecCodes, CLI/API, registry,
source-activation or eligibility work.  It does not authenticate arbitrary caller
JSON, grant entitlement, write rows, or prove first publication, continuous public
readability, a genuine forecast vintage or forecast accuracy.  S2 owns transport
trust; S4 owns opt-in archive reads.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Final

from eurogas_nexus.ingestion.ecmwf_grib import (
    DECODER_LIBRARY,
    MIN_ECCODES_VERSION,
    EcmwfDecoderMetadata,
)
from eurogas_nexus.ingestion.ecmwf_open_data import (
    GRID_NAME,
    MAX_FIELD_BYTES,
    MAX_INDEX_BYTES,
    MODEL_NAME,
    PARAM_ID,
    PARAM_UNITS,
    PRODUCT_STREAM,
    STEP_HOURS,
    EcmwfFieldReference,
    EcmwfIndexAmbiguousError,
    EcmwfOpenDataError,
    EcmwfOpenDataRequest,
    EcmwfResponseTooLargeError,
    EcmwfSource,
    parse_grib_index,
)

ARCHIVE_AVAILABILITY_BASIS: Final = "ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION"
ARCHIVE_BUCKET: Final = "ecmwf-forecasts"
ARCHIVE_HOST: Final = "ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
ARCHIVE_ORIGIN_LABEL: Final = "ECMWF-managed AWS Open Data replica"
ARCHIVE_CYCLE_HOUR: Final = 0
ARCHIVE_GRID_TYPE: Final = "regular_ll"
ARCHIVE_GRID_NI: Final = 1440
ARCHIVE_GRID_NJ: Final = 721
ARCHIVE_TIME_PRECISION: Final = "utc_seconds"
MAX_ARCHIVE_OBJECT_BYTES: Final = 256 * 1024 * 1024
_CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
_VERSION_RE = re.compile(r"^\s*(\d+)\.(\d+)(?:\.(\d+))?")


class WeatherArchiveEvidenceError(RuntimeError):
    """Base typed refusal with a stable machine-readable code."""

    code = "weather_archive_evidence_invalid"


class WeatherArchiveMetadataError(WeatherArchiveEvidenceError):
    code = "weather_archive_metadata_invalid"


class WeatherArchiveTimeError(WeatherArchiveEvidenceError):
    code = "weather_archive_time_invalid"


class WeatherArchiveIdentityError(WeatherArchiveEvidenceError):
    code = "weather_archive_identity_mismatch"


class WeatherArchiveRangeError(WeatherArchiveEvidenceError):
    code = "weather_archive_range_invalid"


class WeatherArchiveHashError(WeatherArchiveEvidenceError):
    code = "weather_archive_hash_mismatch"


class WeatherArchivePolicyError(WeatherArchiveEvidenceError):
    code = "weather_archive_policy_rejected"


class WeatherArchiveAssumptionError(WeatherArchiveEvidenceError):
    code = "weather_archive_assumption_required"


class ArchiveObjectChangedError(WeatherArchiveEvidenceError):
    code = "ARCHIVE_OBJECT_CHANGED"


@dataclass(frozen=True, slots=True)
class ArchiveS3ObjectMetadata:
    """Server-captured S3 listing or HEAD metadata for one exact object."""

    bucket: str
    key: str
    etag: str
    version_id: str | None
    last_modified_utc: datetime
    size_bytes: int
    captured_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ArchiveHttpObjectMetadata:
    """Server-captured HTTP response validators for the same exact object."""

    url: str
    status_code: int
    etag: str
    version_id: str | None
    last_modified_utc: datetime
    content_range: str | None
    content_length: int
    captured_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ArchiveIndexObject:
    metadata: ArchiveS3ObjectMetadata
    http: ArchiveHttpObjectMetadata
    raw_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class ArchiveGribObject:
    metadata: ArchiveS3ObjectMetadata
    http: ArchiveHttpObjectMetadata
    raw_bytes: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class ArchiveSelectedMessage:
    """Existing exact core reference plus decoded identity for one message."""

    reference: EcmwfFieldReference
    decoded: EcmwfDecoderMetadata


@dataclass(frozen=True, slots=True)
class ArchiveObjectEvidence:
    """Validated evidence for one object; ETag remains opaque."""

    bucket: str
    key: str
    url: str
    etag: str
    version_id: str | None
    http_etag: str
    http_version_id: str | None
    size_bytes: int
    last_modified_utc: datetime
    s3_last_modified_utc: datetime
    http_last_modified_utc: datetime
    s3_captured_at_utc: datetime
    http_captured_at_utc: datetime
    sha256: str

    def replay_key(self) -> tuple[object, ...]:
        return (
            self.bucket,
            self.key,
            self.url,
            self.etag,
            self.version_id,
            self.http_etag,
            self.http_version_id,
            self.size_bytes,
            self.last_modified_utc,
            self.s3_last_modified_utc,
            self.http_last_modified_utc,
            self.sha256,
        )


@dataclass(frozen=True, slots=True)
class ArchiveEvidence:
    """Read-only reconstruction; never a local receipt or eligibility grant."""

    availability_basis: str
    index: ArchiveObjectEvidence
    grib: ArchiveObjectEvidence
    run_date: date
    cycle_hour: int
    step_hours: int
    index_row_offset: int
    message_offset: int
    message_length: int
    content_range: str
    object_total_bytes: int
    effective_archive_available_at_utc: datetime
    captured_at_utc: datetime
    decoded: EcmwfDecoderMetadata
    policy_hash: str
    method_hash: str
    evidence_hash: str
    limitations: tuple[str, ...]
    public_read_continuity_assumption: bool

    @property
    def availability_is_local_receipt(self) -> bool:
        return False

    @property
    def availability_is_prospective(self) -> bool:
        return False

    @property
    def etag_is_content_hash(self) -> bool:
        return False


_POLICY_PAYLOAD: Final[dict[str, object]] = {
    "schema": "ecmwf-archive-availability-policy-v1",
    "availability_basis": ARCHIVE_AVAILABILITY_BASIS,
    "bucket": ARCHIVE_BUCKET,
    "host": ARCHIVE_HOST,
    "model": MODEL_NAME,
    "grid": GRID_NAME,
    "stream": PRODUCT_STREAM,
    "key_layout": "YYYYMMDD/00z/ifs/0p25/oper/YYYYMMDD000000-{step}h-oper-fc",
    "index_suffix": ".index",
    "grib_suffix": ".grib2",
    "cycle_hours": [ARCHIVE_CYCLE_HOUR],
    "step": {"min_hours": 0, "max_hours": 360, "increment_hours": 3},
    "param_id": PARAM_ID,
    "param_units": PARAM_UNITS,
    "step_type": "instant",
    "grid_type": ARCHIVE_GRID_TYPE,
    "grid_ni": ARCHIVE_GRID_NI,
    "grid_nj": ARCHIVE_GRID_NJ,
    "last_modified_precision": ARCHIVE_TIME_PRECISION,
    "effective_rule": "max(index_last_modified,grib_last_modified)",
    "public_read_continuity_assumption": True,
    "max_index_bytes": MAX_INDEX_BYTES,
    "max_message_bytes": MAX_FIELD_BYTES,
    "max_object_bytes": MAX_ARCHIVE_OBJECT_BYTES,
}
_WORK_BOUNDS: Final[dict[str, object]] = {
    "max_index_bytes": MAX_INDEX_BYTES,
    "max_message_bytes": MAX_FIELD_BYTES,
    "max_object_bytes": MAX_ARCHIVE_OBJECT_BYTES,
    "time_precision": ARCHIVE_TIME_PRECISION,
}


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_ARCHIVE_POLICY_HASH: Final = _canonical_hash(_POLICY_PAYLOAD)


def _text(value: object, name: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WeatherArchiveMetadataError(f"{name} must be non-empty bounded text")
    if value != value.strip() or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in value
    ):
        raise WeatherArchiveMetadataError(f"{name} contains forbidden whitespace/control bytes")
    return value


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise WeatherArchiveMetadataError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise WeatherArchiveRangeError(f"{name} is outside its reviewed bound")
    return value


def _utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise WeatherArchiveTimeError(f"{name} must be an aware UTC datetime")
    if value.tzinfo is None:
        raise WeatherArchiveTimeError(f"{name} must not be naive")
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


def _utc_seconds(value: object, name: str) -> datetime:
    return _utc(value, name).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return _utc(value, "evidence timestamp").isoformat()


def _not_future(value: object, captured_at: object, name: str) -> None:
    if _utc_seconds(value, f"{name} LastModified") > _utc_seconds(
        captured_at, f"{name} captured_at"
    ):
        raise WeatherArchiveTimeError(f"{name} LastModified is after its capture time")


def _expected_keys(request: EcmwfOpenDataRequest) -> tuple[str, str]:
    return request.s3_prefix + request.index_filename, request.s3_prefix + request.asset_filename


def _object_url(key: str) -> str:
    return f"https://{ARCHIVE_HOST}/{key}"


def _check_object(
    obj: object,
    *,
    name: str,
    expected_key: str,
    expected_url: str,
    expected_status: int,
    ranged: bool,
    max_content_length: int,
) -> ArchiveObjectEvidence:
    if not isinstance(obj, (ArchiveIndexObject, ArchiveGribObject)):
        raise WeatherArchiveMetadataError(f"{name} object has the wrong type")
    meta, http = obj.metadata, obj.http
    if not isinstance(meta, ArchiveS3ObjectMetadata) or not isinstance(
        http, ArchiveHttpObjectMetadata
    ):
        raise WeatherArchiveMetadataError(f"{name} metadata has the wrong type")
    raw = obj.raw_bytes
    if type(raw) is not bytes or not raw:
        raise WeatherArchiveMetadataError(f"{name} raw bytes must be non-empty bytes")
    if _text(meta.bucket, f"{name} bucket", maximum=255) != ARCHIVE_BUCKET:
        raise WeatherArchiveIdentityError(f"{name} bucket is not the reviewed ECMWF bucket")
    if _text(meta.key, f"{name} key", maximum=512) != expected_key:
        raise WeatherArchiveIdentityError(f"{name} key is not the exact official object")
    if _text(http.url, f"{name} URL") != expected_url:
        raise WeatherArchiveIdentityError(f"{name} HTTP URL is not the exact official object")
    if type(http.status_code) is not int or http.status_code != expected_status:
        raise WeatherArchiveMetadataError(f"{name} HTTP status is not {expected_status}")
    s3_etag = _text(meta.etag, f"{name} ETag", maximum=512)
    http_etag = _text(http.etag, f"{name} HTTP ETag", maximum=512)
    if s3_etag != http_etag:
        raise WeatherArchiveMetadataError(f"{name} S3/HEAD and HTTP ETag disagree")
    if meta.version_id != http.version_id:
        raise WeatherArchiveMetadataError(f"{name} S3/HEAD and HTTP versionId disagree")
    if meta.version_id is not None:
        _text(meta.version_id, f"{name} versionId")
        _text(http.version_id, f"{name} HTTP versionId")
    size = _integer(meta.size_bytes, f"{name} size", 1, MAX_ARCHIVE_OBJECT_BYTES)
    content_length = _integer(http.content_length, f"{name} Content-Length", 1, max_content_length)
    if content_length != len(raw):
        raise WeatherArchiveRangeError(f"{name} Content-Length does not match the body bytes")
    if ranged:
        if not isinstance(http.content_range, str):
            raise WeatherArchiveRangeError(f"{name} Content-Range is required")
        if len(raw) > MAX_FIELD_BYTES:
            raise WeatherArchiveRangeError(f"{name} body exceeds the selected-message bound")
    else:
        if http.content_range is not None:
            raise WeatherArchiveRangeError(f"{name} full-object response has Content-Range")
        if size != len(raw):
            raise WeatherArchiveRangeError(f"{name} full-object size does not match the body")
    s3_lm = _utc_seconds(meta.last_modified_utc, f"{name} S3 LastModified")
    http_lm = _utc_seconds(http.last_modified_utc, f"{name} HTTP LastModified")
    if s3_lm != http_lm:
        raise WeatherArchiveMetadataError(
            f"{name} S3/HEAD and HTTP LastModified disagree at UTC seconds precision"
        )
    _not_future(meta.last_modified_utc, meta.captured_at_utc, f"{name} S3")
    _not_future(http.last_modified_utc, http.captured_at_utc, f"{name} HTTP")
    return ArchiveObjectEvidence(
        bucket=meta.bucket,
        key=meta.key,
        url=http.url,
        etag=s3_etag,
        version_id=meta.version_id,
        http_etag=http_etag,
        http_version_id=http.version_id,
        size_bytes=size,
        last_modified_utc=s3_lm,
        s3_last_modified_utc=_utc(meta.last_modified_utc, f"{name} S3 LastModified"),
        http_last_modified_utc=_utc(http.last_modified_utc, f"{name} HTTP LastModified"),
        s3_captured_at_utc=_utc(meta.captured_at_utc, f"{name} S3 captured_at"),
        http_captured_at_utc=_utc(http.captured_at_utc, f"{name} HTTP captured_at"),
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def _parse_content_range(
    raw_content_range: str,
    *,
    expected_start: int,
    expected_length: int,
    expected_total: int,
) -> tuple[str, int]:
    if len(raw_content_range) > 128:
        raise WeatherArchiveRangeError("Content-Range is not bounded")
    match = _CONTENT_RANGE_RE.fullmatch(raw_content_range)
    if match is None:
        raise WeatherArchiveRangeError("Content-Range is missing or malformed")
    start, end, total = (int(part) for part in match.groups())
    if f"bytes {start}-{end}/{total}" != raw_content_range:
        raise WeatherArchiveRangeError("Content-Range is not in canonical byte-range form")
    if start != expected_start:
        raise WeatherArchiveRangeError("Content-Range start does not match the selected row")
    if end != expected_start + expected_length - 1:
        raise WeatherArchiveRangeError("Content-Range end does not match the selected message")
    if total != expected_total:
        raise WeatherArchiveRangeError("Content-Range total does not match the S3 object size")
    if total < end + 1:
        raise WeatherArchiveRangeError("Content-Range total is smaller than the selected message")
    _integer(total, "archive object total bytes", 1, MAX_ARCHIVE_OBJECT_BYTES)
    return raw_content_range, total


def _decoder_version(value: object) -> str:
    text = _text(value, "decoder_version", maximum=64)
    match = _VERSION_RE.match(text)
    if match is None:
        raise WeatherArchiveIdentityError("decoder version is not parseable")
    if tuple(int(part or 0) for part in match.groups()) < MIN_ECCODES_VERSION:
        raise WeatherArchiveIdentityError("decoder version is below the reviewed minimum")
    return text


def _check_decoded(
    decoded: object,
    *,
    request: EcmwfOpenDataRequest,
    expected_request_sha256: str,
) -> tuple[EcmwfDecoderMetadata, str]:
    if not isinstance(decoded, EcmwfDecoderMetadata):
        raise WeatherArchiveMetadataError("decoded identity has the wrong type")
    if _text(decoded.decoder_library, "decoder_library", maximum=64) != DECODER_LIBRARY:
        raise WeatherArchiveIdentityError("decoder library is not ecCodes")
    version = _decoder_version(decoded.decoder_version)
    if _integer(decoded.param_id, "decoded paramId", 0, 1_000_000) != PARAM_ID:
        raise WeatherArchiveIdentityError("decoded parameter is not 167")
    if _text(decoded.units, "decoded units", maximum=32) != PARAM_UNITS:
        raise WeatherArchiveIdentityError("decoded units are not K")
    if _text(decoded.step_type, "decoded stepType", maximum=32).lower() != "instant":
        raise WeatherArchiveIdentityError("decoded step type is not instant")
    if _text(decoded.grid_type, "decoded gridType", maximum=64) != ARCHIVE_GRID_TYPE:
        raise WeatherArchiveIdentityError("decoded grid type is not regular_ll")
    if _integer(decoded.grid_ni, "decoded Ni", 1, 1_000_000) != ARCHIVE_GRID_NI:
        raise WeatherArchiveIdentityError("decoded grid Ni is not 1440")
    if _integer(decoded.grid_nj, "decoded Nj", 1, 1_000_000) != ARCHIVE_GRID_NJ:
        raise WeatherArchiveIdentityError("decoded grid Nj is not 721")
    if not isinstance(decoded.data_date, date) or isinstance(decoded.data_date, datetime):
        raise WeatherArchiveMetadataError("decoded dataDate is not a date")
    if (
        decoded.data_date,
        _utc(decoded.data_time_utc, "decoded dataTime"),
        _utc(decoded.validity_at_utc, "decoded validity"),
        _integer(decoded.forecast_step_hours, "decoded step", 0, 10_000),
    ) != (
        request.run_date,
        _utc(request.issued_at_utc, "request issued_at"),
        _utc(request.valid_at_utc, "request validity"),
        request.step_hours,
    ):
        raise WeatherArchiveIdentityError("decoded run/step/validity does not match the request")
    if _text(decoded.request_sha256, "decoded request hash", maximum=64) != (
        expected_request_sha256
    ):
        raise WeatherArchiveIdentityError("decoded request hash does not match the request")
    return decoded, version


def _check_reference(
    reference: object,
    *,
    request: EcmwfOpenDataRequest,
    index_sha256: str,
    grib_sha256: str,
    grib_url: str,
    selected_row_offset: int,
) -> None:
    if not isinstance(reference, EcmwfFieldReference):
        raise WeatherArchiveMetadataError("selected-message reference has the wrong type")
    if reference.source is not EcmwfSource.AWS:
        raise WeatherArchiveIdentityError("selected-message reference is not the AWS origin")
    if _text(reference.origin, "reference origin", maximum=128) != ARCHIVE_ORIGIN_LABEL:
        raise WeatherArchiveIdentityError("selected-message origin is not the reviewed origin")
    if _text(reference.asset_url, "reference asset URL") != grib_url:
        raise WeatherArchiveIdentityError("selected-message asset URL is not the GRIB object")
    if _text(reference.request_sha256, "reference request hash", maximum=64) != (
        request.fingerprint()
    ):
        raise WeatherArchiveIdentityError("selected-message request hash does not match")
    if _text(reference.index_sha256, "reference index hash", maximum=64) != index_sha256:
        raise WeatherArchiveHashError("selected-message index hash does not match raw bytes")
    if _text(reference.grib_sha256, "reference GRIB hash", maximum=64) != grib_sha256:
        raise WeatherArchiveHashError("selected-message GRIB hash does not match raw bytes")
    if (
        reference.index_row_offset,
        reference.run_date,
        reference.cycle_hour,
        reference.step_hours,
        _utc(reference.valid_at_utc, "reference validity"),
    ) != (
        selected_row_offset,
        request.run_date,
        request.cycle_hour,
        request.step_hours,
        _utc(request.valid_at_utc, "request validity"),
    ):
        raise WeatherArchiveIdentityError("selected-message identity does not match the request")


def _object_payload(obj: ArchiveObjectEvidence) -> dict[str, object]:
    return {
        "bucket": obj.bucket,
        "key": obj.key,
        "url": obj.url,
        "etag": obj.etag,
        "version_id": obj.version_id,
        "http_etag": obj.http_etag,
        "http_version_id": obj.http_version_id,
        "size_bytes": obj.size_bytes,
        "last_modified_utc": _iso(obj.last_modified_utc),
        "s3_last_modified_utc": _iso(obj.s3_last_modified_utc),
        "http_last_modified_utc": _iso(obj.http_last_modified_utc),
        "s3_captured_at_utc": _iso(obj.s3_captured_at_utc),
        "http_captured_at_utc": _iso(obj.http_captured_at_utc),
        "sha256": obj.sha256,
    }


def reconstruct_archive_evidence(
    *,
    request: EcmwfOpenDataRequest,
    index_object: ArchiveIndexObject,
    grib_object: ArchiveGribObject,
    selected_message: ArchiveSelectedMessage,
    captured_at_utc: datetime,
    public_read_continuity_assumption: bool,
) -> ArchiveEvidence:
    """Validate exact object/message evidence and reconstruct archive availability."""

    if public_read_continuity_assumption is not True:
        raise WeatherArchiveAssumptionError(
            "public-read continuity must be explicitly accepted as a research assumption"
        )
    if not isinstance(request, EcmwfOpenDataRequest):
        raise WeatherArchiveMetadataError("request must be EcmwfOpenDataRequest")
    if request.cycle_hour != ARCHIVE_CYCLE_HOUR:
        raise WeatherArchivePolicyError("archive policy allows only the 00z cycle")
    if request.step_hours not in STEP_HOURS:
        raise WeatherArchivePolicyError("archive policy allows only 0..360 in 3-hour steps")
    if not isinstance(index_object, ArchiveIndexObject) or not isinstance(
        grib_object, ArchiveGribObject
    ):
        raise WeatherArchiveMetadataError("index and GRIB must be typed archive objects")
    if not isinstance(selected_message, ArchiveSelectedMessage):
        raise WeatherArchiveMetadataError("selected_message must be ArchiveSelectedMessage")

    captured_at = _utc(captured_at_utc, "captured_at_utc")
    index_key, grib_key = _expected_keys(request)
    index_ev = _check_object(
        index_object,
        name="index",
        expected_key=index_key,
        expected_url=_object_url(index_key),
        expected_status=200,
        ranged=False,
        max_content_length=MAX_INDEX_BYTES,
    )
    grib_ev = _check_object(
        grib_object,
        name="GRIB",
        expected_key=grib_key,
        expected_url=_object_url(grib_key),
        expected_status=206,
        ranged=True,
        max_content_length=MAX_FIELD_BYTES,
    )
    if any(
        item > captured_at
        for item in (
            index_ev.s3_captured_at_utc,
            index_ev.http_captured_at_utc,
            grib_ev.s3_captured_at_utc,
            grib_ev.http_captured_at_utc,
        )
    ):
        raise WeatherArchiveTimeError("object capture time is after the overall capture time")

    raw_index = index_object.raw_bytes
    try:
        parsed = parse_grib_index(raw_index, request)
    except EcmwfIndexAmbiguousError as exc:
        raise WeatherArchiveIdentityError("index selects more than one 2t surface message") from exc
    except EcmwfResponseTooLargeError as exc:
        raise WeatherArchiveRangeError("index exceeds the existing pure index bound") from exc
    except EcmwfOpenDataError as exc:
        raise WeatherArchiveMetadataError("index failed existing pure validation") from exc
    if parsed.raw_sha256 != index_ev.sha256 or parsed.raw_size_bytes != len(raw_index):
        raise WeatherArchiveHashError("index hash/size does not match the parsed raw index")
    selected = parsed.selected
    row_bytes = selected.row_json.encode("utf-8")
    if selected.row_offset < 0 or selected.row_offset + len(row_bytes) > len(raw_index):
        raise WeatherArchiveMetadataError("selected index row is outside the index bytes")
    if raw_index[selected.row_offset : selected.row_offset + len(row_bytes)] != row_bytes:
        raise WeatherArchiveHashError("selected index row bytes do not match the raw index")
    if selected.row_offset and raw_index[selected.row_offset - 1 : selected.row_offset] not in {
        b"\n",
        b"\r",
    }:
        raise WeatherArchiveMetadataError("selected index row offset is not a line start")

    raw_grib = grib_object.raw_bytes
    if selected.byte_offset < 0 or not 1 <= selected.byte_length <= MAX_FIELD_BYTES:
        raise WeatherArchiveMetadataError("selected index row has an invalid GRIB range")
    if len(raw_grib) != selected.byte_length:
        raise WeatherArchiveRangeError("GRIB body length does not match the selected index row")
    if selected.byte_offset + selected.byte_length > grib_ev.size_bytes:
        raise WeatherArchiveRangeError("selected message escapes the S3 object size")
    raw_range = grib_object.http.content_range
    if not isinstance(raw_range, str):
        raise WeatherArchiveRangeError("GRIB response has no Content-Range")
    content_range, object_total = _parse_content_range(
        raw_range,
        expected_start=selected.byte_offset,
        expected_length=len(raw_grib),
        expected_total=grib_ev.size_bytes,
    )

    _check_reference(
        selected_message.reference,
        request=request,
        index_sha256=index_ev.sha256,
        grib_sha256=grib_ev.sha256,
        grib_url=grib_ev.url,
        selected_row_offset=selected.row_offset,
    )
    decoded, decoder_version = _check_decoded(
        selected_message.decoded,
        request=request,
        expected_request_sha256=request.fingerprint(),
    )
    method_hash = _canonical_hash(
        {
            "schema": "ecmwf-archive-evidence-method-v1",
            "policy_hash": _ARCHIVE_POLICY_HASH,
            "index_parser": "eurogas_nexus.ingestion.ecmwf_open_data.parse_grib_index",
            "selection": "single reviewed 2t surface row",
            "range_reader": "exact single Content-Range with no full-body fallback",
            "decoder_library": DECODER_LIBRARY,
            "decoder_version": decoder_version,
            "work_bounds": _WORK_BOUNDS,
        }
    )
    effective = max(index_ev.last_modified_utc, grib_ev.last_modified_utc)
    limitations = [
        (
            "Availability is reconstructed from current S3 object LastModified; it is not a "
            "local capture receipt."
        ),
        (
            "Public-read continuity is an accepted research assumption, not proof of historical "
            "public readability, rights, or entitlement."
        ),
        (
            "Object LastModified does not prove first publication, continuous availability, or "
            "prospective OOS availability."
        ),
        "ETag is retained as an opaque validator and is not a content hash or MD5.",
        "This evidence is not a genuine forecast vintage and is not forecast-accuracy evidence.",
    ]
    if index_ev.version_id in (None, "null"):
        limitations.append(
            "Index versionId is null/unversioned; the index object is not version-pinned."
        )
    if grib_ev.version_id in (None, "null"):
        limitations.append(
            "GRIB versionId is null/unversioned; the GRIB object is not version-pinned."
        )
    evidence_payload: dict[str, object] = {
        "schema": "ecmwf-archive-evidence-v1",
        "availability_basis": ARCHIVE_AVAILABILITY_BASIS,
        "index": _object_payload(index_ev),
        "grib": _object_payload(grib_ev),
        "run_date": request.run_date.isoformat(),
        "cycle_hour": request.cycle_hour,
        "step_hours": request.step_hours,
        "index_row_offset": selected.row_offset,
        "message_offset": selected.byte_offset,
        "message_length": selected.byte_length,
        "content_range": content_range,
        "object_total_bytes": object_total,
        "effective_archive_available_at_utc": _iso(effective),
        "captured_at_utc": _iso(captured_at),
        "decoder_library": decoded.decoder_library,
        "decoder_version": decoder_version,
        "param_id": decoded.param_id,
        "units": decoded.units,
        "step_type": decoded.step_type,
        "grid_type": decoded.grid_type,
        "grid_ni": decoded.grid_ni,
        "grid_nj": decoded.grid_nj,
        "decoded_data_date": decoded.data_date.isoformat(),
        "decoded_data_time_utc": _iso(decoded.data_time_utc),
        "decoded_validity_at_utc": _iso(decoded.validity_at_utc),
        "decoded_forecast_step_hours": decoded.forecast_step_hours,
        "decoded_request_sha256": decoded.request_sha256,
        "policy_hash": _ARCHIVE_POLICY_HASH,
        "method_hash": method_hash,
        "work_bounds": _WORK_BOUNDS,
        "public_read_continuity_assumption": True,
        "availability_is_local_receipt": False,
        "availability_is_prospective": False,
        "limitations": limitations,
    }
    return ArchiveEvidence(
        availability_basis=ARCHIVE_AVAILABILITY_BASIS,
        index=index_ev,
        grib=grib_ev,
        run_date=request.run_date,
        cycle_hour=request.cycle_hour,
        step_hours=request.step_hours,
        index_row_offset=selected.row_offset,
        message_offset=selected.byte_offset,
        message_length=selected.byte_length,
        content_range=content_range,
        object_total_bytes=object_total,
        effective_archive_available_at_utc=effective,
        captured_at_utc=captured_at,
        decoded=decoded,
        policy_hash=_ARCHIVE_POLICY_HASH,
        method_hash=method_hash,
        evidence_hash=_canonical_hash(evidence_payload),
        limitations=tuple(limitations),
        public_read_continuity_assumption=True,
    )


def assert_archive_replay(
    previous: ArchiveEvidence,
    current: ArchiveEvidence,
) -> ArchiveEvidence:
    """Compare the same request/decoder selection; changed facts are refused.

    This is query-specific evidence replay, not a cross-location object-cache
    comparison: decoded request identity deliberately participates in equality.
    """

    if not isinstance(previous, ArchiveEvidence) or not isinstance(current, ArchiveEvidence):
        raise WeatherArchiveMetadataError("replay comparison requires ArchiveEvidence values")
    if previous.index.replay_key() != current.index.replay_key():
        raise ArchiveObjectChangedError("the index object or its validators changed")
    if previous.grib.replay_key() != current.grib.replay_key():
        raise ArchiveObjectChangedError("the GRIB object or its validators changed")
    if previous.decoded != current.decoded:
        raise ArchiveObjectChangedError("the selected archive decoded identity changed")
    return current
