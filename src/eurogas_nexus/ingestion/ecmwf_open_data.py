"""Bounded, credentialless access to ECMWF's official open-data GRIB2 assets.

Phase A only: discover the official directory (or the ECMWF-managed AWS replica),
select the single indexed ``2t``/paramId 167 surface message for an IFS 0p25
``oper`` run/step, and fetch only that message with an HTTP byte range.

This module deliberately has no persistence, scheduler, source activation, or
provider-payload JSON weather model.  A successful result is either exact GRIB2
bytes plus their hashes/provenance, or a stable typed error.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import StrEnum
from html.parser import HTMLParser
from types import MappingProxyType
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

MODEL_NAME = "ifs"
GRID_NAME = "0p25"
PRODUCT_STREAM = "oper"
PARAM_ID = 167
PARAM_SHORT_NAME = "2t"
PARAM_UNITS = "K"

CYCLE_HOURS = frozenset({0, 6, 12, 18})
MIN_RUN_DATE = date(2023, 1, 18)
MAX_STEP_HOURS = 360
STEP_HOURS = frozenset(range(0, MAX_STEP_HOURS + 1, 3))
MAX_LOCATIONS = 64
MAX_FIELD_BYTES = 32 * 1024 * 1024
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_LISTING_BYTES = 1024 * 1024
MAX_LISTING_PAGES = 6
MAX_REDIRECTS = 3
MAX_HTTP_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 2.0
_STREAM_CHUNK_BYTES = 64 * 1024

ECMWF_FORECASTS_URL = "https://data.ecmwf.int/forecasts/"
AWS_FORECASTS_URL = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/"
ALLOWED_HOSTS = frozenset(
    {
        "data.ecmwf.int",
        "ecmwf-forecasts.s3.eu-central-1.amazonaws.com",
    }
)

_USER_AGENT = "eurogas-nexus/0.5 (ECMWF open-data phase A; credentialless)"
_CONTENT_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
_DATE_RE = re.compile(r"^\d{8}$")
_INT_RE = re.compile(r"^[+-]?\d+$")


class EcmwfOpenDataError(RuntimeError):
    """Base error with a stable machine-readable code."""

    code = "ecmwf_open_data_error"


class EcmwfInvalidRequestError(EcmwfOpenDataError):
    code = "ecmwf_request_invalid"


class EcmwfSourceError(EcmwfOpenDataError):
    code = "ecmwf_source_invalid"


class EcmwfOriginError(EcmwfOpenDataError):
    code = "ecmwf_origin_rejected"


class EcmwfHttpStatusError(EcmwfOpenDataError):
    code = "ecmwf_http_status"

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"unexpected HTTP status {status_code}")


class EcmwfRateLimitedError(EcmwfOpenDataError):
    code = "ecmwf_rate_limited"


class EcmwfResponseTooLargeError(EcmwfOpenDataError):
    code = "ecmwf_response_too_large"


class EcmwfProtocolError(EcmwfOpenDataError):
    code = "ecmwf_response_protocol"


class EcmwfListingError(EcmwfOpenDataError):
    code = "ecmwf_listing_invalid"


class EcmwfAssetNotFoundError(EcmwfOpenDataError):
    code = "ecmwf_asset_not_found"


class EcmwfIndexError(EcmwfOpenDataError):
    code = "ecmwf_index_invalid"


class EcmwfIndexAmbiguousError(EcmwfOpenDataError):
    code = "ecmwf_index_ambiguous"


class EcmwfIndexMismatchError(EcmwfOpenDataError):
    code = "ecmwf_index_mismatch"


class EcmwfRangeError(EcmwfOpenDataError):
    code = "ecmwf_range_invalid"


class EcmwfSource(StrEnum):
    ECMWF = "ecmwf"
    AWS = "aws"


class EcmwfAvailabilityBasis(StrEnum):
    PROVIDER_LAST_MODIFIED = "provider_last_modified"
    LOCAL_RECEIPT_ONLY = "local_receipt_only"


class EcmwfParamIdBasis(StrEnum):
    """How an index row's parameter id was established.

    Actual official index rows currently carry only the reviewed ``param`` short
    name.  A short name is never mapped to an arbitrary numeric id: only the
    reviewed ``2t`` -> 167 pair is derived.
    """

    INDEX_DECLARED = "index_declared"
    REVIEWED_SHORT_NAME = "reviewed_short_name"


@dataclass(frozen=True, slots=True)
class EcmwfOrigin:
    """A fixed, reviewed provider origin.  There is no arbitrary-host input."""

    source: EcmwfSource
    label: str
    base_url: str
    path_prefix: str
    bucket: str | None = None

    @property
    def host(self) -> str:
        host = urlsplit(self.base_url).hostname
        if host is None:
            raise EcmwfSourceError("origin has no host")
        return host


_ORIGINS: Mapping[EcmwfSource, EcmwfOrigin] = MappingProxyType(
    {
        EcmwfSource.ECMWF: EcmwfOrigin(
            source=EcmwfSource.ECMWF,
            label="ECMWF official open data",
            base_url=ECMWF_FORECASTS_URL,
            path_prefix="/forecasts/",
        ),
        EcmwfSource.AWS: EcmwfOrigin(
            source=EcmwfSource.AWS,
            label="ECMWF-managed AWS Open Data replica",
            base_url=AWS_FORECASTS_URL,
            path_prefix="/",
            bucket="ecmwf-forecasts",
        ),
    }
)


def resolve_origin(source: EcmwfSource | str) -> EcmwfOrigin:
    """Resolve only the two explicit source names; never a URL or mirror."""

    try:
        selected = source if isinstance(source, EcmwfSource) else EcmwfSource(source)
    except (TypeError, ValueError) as exc:
        raise EcmwfSourceError("source must be 'ecmwf' or 'aws'") from exc
    origin = _ORIGINS.get(selected)
    if origin is None or origin.host not in ALLOWED_HOSTS:
        raise EcmwfSourceError("source has no reviewed origin")
    return origin


def _utc(value: datetime) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset != timedelta(0):
        raise EcmwfInvalidRequestError("timestamps must be UTC")
    return value.astimezone(UTC)


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EcmwfInvalidRequestError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise EcmwfInvalidRequestError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class EcmwfLocation:
    """Explicit user location; never represented as an observing station."""

    point_id: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.point_id, str) or not self.point_id.strip():
            raise EcmwfInvalidRequestError("point_id must be non-empty")
        if len(self.point_id) > 64 or self.point_id != self.point_id.strip():
            raise EcmwfInvalidRequestError("point_id must be trimmed and at most 64 characters")
        latitude = _number(self.latitude, "latitude")
        longitude = _number(self.longitude, "longitude")
        if not -90.0 <= latitude <= 90.0:
            raise EcmwfInvalidRequestError("latitude outside [-90, 90]")
        if not -180.0 <= longitude <= 180.0:
            raise EcmwfInvalidRequestError("longitude outside [-180, 180]")


@dataclass(frozen=True, slots=True)
class EcmwfOpenDataRequest:
    """Immutable Phase A request: one IFS 0p25 oper 2t run/step and locations."""

    run_date: date
    cycle_hour: int
    step_hours: int
    locations: tuple[EcmwfLocation, ...]

    def __post_init__(self) -> None:
        if isinstance(self.run_date, datetime) or not isinstance(self.run_date, date):
            raise EcmwfInvalidRequestError("run_date must be a date")
        if self.run_date < MIN_RUN_DATE:
            raise EcmwfInvalidRequestError("run_date predates reviewed archive support")
        if self.run_date > datetime.now(UTC).date():
            raise EcmwfInvalidRequestError("run_date is in the future")
        if (
            isinstance(self.cycle_hour, bool)
            or not isinstance(self.cycle_hour, int)
            or self.cycle_hour not in CYCLE_HOURS
        ):
            raise EcmwfInvalidRequestError("cycle_hour must be 00/06/12/18")
        if (
            isinstance(self.step_hours, bool)
            or not isinstance(self.step_hours, int)
            or self.step_hours not in STEP_HOURS
        ):
            raise EcmwfInvalidRequestError("step_hours must be 0..360 in 3-hour increments")
        try:
            locations = tuple(self.locations)
        except TypeError as exc:
            raise EcmwfInvalidRequestError("locations must be an iterable") from exc
        if not 1 <= len(locations) <= MAX_LOCATIONS:
            raise EcmwfInvalidRequestError("one to 64 locations are required")
        if not all(isinstance(item, EcmwfLocation) for item in locations):
            raise EcmwfInvalidRequestError("locations must contain EcmwfLocation values")
        if len({item.point_id for item in locations}) != len(locations):
            raise EcmwfInvalidRequestError("point_id values must be unique")
        object.__setattr__(self, "locations", locations)

    @property
    def issued_at_utc(self) -> datetime:
        """Nominal model issue time; this is not a publication/receipt time."""

        return datetime(
            self.run_date.year,
            self.run_date.month,
            self.run_date.day,
            self.cycle_hour,
            tzinfo=UTC,
        )

    @property
    def valid_at_utc(self) -> datetime:
        return self.issued_at_utc + timedelta(hours=self.step_hours)

    @property
    def asset_filename(self) -> str:
        stamp = f"{self.run_date:%Y%m%d}{self.cycle_hour:02d}0000"
        return f"{stamp}-{self.step_hours}h-oper-fc.grib2"

    @property
    def index_filename(self) -> str:
        return f"{self.asset_filename.removesuffix('.grib2')}.index"

    @property
    def s3_prefix(self) -> str:
        return (
            f"{self.run_date:%Y%m%d}/{self.cycle_hour:02d}z/"
            f"{MODEL_NAME}/{GRID_NAME}/{PRODUCT_STREAM}/"
        )

    def fingerprint(self) -> str:
        canonical = json.dumps(
            {
                "schema": "ecmwf-open-data-phase-a-v1",
                "model": MODEL_NAME,
                "grid": GRID_NAME,
                "stream": PRODUCT_STREAM,
                "param_id": PARAM_ID,
                "param": PARAM_SHORT_NAME,
                "run_date": self.run_date.isoformat(),
                "cycle_hour": self.cycle_hour,
                "step_hours": self.step_hours,
                "locations": [
                    [item.point_id, item.latitude, item.longitude]
                    for item in self.locations
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EcmwfListingPage:
    url: str
    sha256: str


@dataclass(frozen=True, slots=True)
class EcmwfIndexRow:
    """One official JSONL index row; ``row_json`` preserves the raw row verbatim.

    ``param_id`` is the row's declared id when present and is derived only from the
    reviewed ``2t`` short name otherwise.  It is ``None`` for any other row that
    does not declare an id, so an unrecognized parameter is never relabelled 167.
    ``param_id_basis`` distinguishes a declared id from a reviewed derivation.
    """

    row_offset: int
    row_sha256: str
    row_json: str
    param_id: int | None
    short_name: str | None
    name: str | None
    units: str | None
    level_type: str | None
    level: str | None
    data_type: str | None
    stream: str | None
    run_date: date | None
    cycle_hour: int | None
    step_hours: int | None
    byte_offset: int
    byte_length: int
    param_id_basis: EcmwfParamIdBasis | None = None


@dataclass(frozen=True, slots=True)
class EcmwfIndex:
    raw_sha256: str
    raw_size_bytes: int
    row_count: int
    selected: EcmwfIndexRow


@dataclass(frozen=True, slots=True)
class EcmwfFieldReference:
    """Portable raw evidence reference checked again by the decoder."""

    source: EcmwfSource
    origin: str
    asset_url: str
    request_sha256: str
    grib_sha256: str
    index_sha256: str
    index_row_offset: int
    run_date: date
    cycle_hour: int
    step_hours: int
    valid_at_utc: datetime

    def __post_init__(self) -> None:
        if self.valid_at_utc.tzinfo is None or self.valid_at_utc.utcoffset() != timedelta(0):
            raise EcmwfInvalidRequestError("field reference validity must be UTC")


@dataclass(frozen=True, slots=True)
class EcmwfRun:
    """Immutable provenance for one selected field retrieval.

    ``issued_at_utc`` is the model's nominal issue time.  It is intentionally not
    populated from, or used to infer, a publication receipt.  ``receipt_completed_at_utc``
    is local receipt of these bytes.  ``provider_last_modified_utc`` is unreviewed
    provider evidence, retained separately and not a historical local receipt.
    """

    request: EcmwfOpenDataRequest
    request_sha256: str
    source: EcmwfSource
    origin: str
    directory_url: str
    asset_url: str
    index_url: str
    listing_pages: tuple[EcmwfListingPage, ...]
    issued_at_utc: datetime
    valid_at_utc: datetime
    request_started_at_utc: datetime
    receipt_completed_at_utc: datetime
    provider_last_modified_utc: datetime | None
    availability_basis: EcmwfAvailabilityBasis


@dataclass(frozen=True, slots=True)
class EcmwfField:
    """Exact selected GRIB2 message bytes and every immutable locator/hash."""

    run: EcmwfRun
    index: EcmwfIndex
    reference: EcmwfFieldReference
    grib_bytes: bytes = field(repr=False)
    grib_sha256: str
    content_range: str
    asset_total_bytes: int

    def __post_init__(self) -> None:
        actual = hashlib.sha256(self.grib_bytes).hexdigest()
        if actual != self.grib_sha256 or actual != self.reference.grib_sha256:
            raise EcmwfProtocolError("field hash does not match returned bytes")

    @property
    def byte_offset(self) -> int:
        return self.index.selected.byte_offset

    @property
    def byte_length(self) -> int:
        return self.index.selected.byte_length

    def decode(self):
        """Decode with ecCodes without making ecCodes a core dependency."""

        from eurogas_nexus.ingestion.ecmwf_grib import EcmwfGribDecoder

        return EcmwfGribDecoder().decode(self)


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value)
                break


def _anchor_hrefs(text: str) -> tuple[str, ...]:
    parser = _Anchors()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:
        raise EcmwfListingError("directory HTML could not be parsed") from exc
    return tuple(parser.hrefs)


def _index_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    raise EcmwfIndexError("index metadata has an unsupported type")


def _index_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise EcmwfIndexError(f"index {name} is not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INT_RE.fullmatch(value.strip()):
        return int(value.strip())
    raise EcmwfIndexError(f"index {name} is not an integer")


def _optional_index_int(value: object, name: str) -> int | None:
    return None if value is None else _index_int(value, name)


def _index_date(value: object) -> date | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not _DATE_RE.fullmatch(raw):
        raise EcmwfIndexError("index date is not YYYYMMDD")
    try:
        return date(int(raw[0:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError as exc:
        raise EcmwfIndexError("index date is not a real date") from exc


def _index_cycle(value: object) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw.isdigit() or len(raw) > 4:
        raise EcmwfIndexError("index time is not HHMM")
    number = int(raw)
    if len(raw) <= 2:
        hour, minute = number, 0
    else:
        hour, minute = number // 100, number % 100
    if hour not in CYCLE_HOURS or minute != 0:
        raise EcmwfIndexError("index time is not an ECMWF cycle")
    return hour


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key}")
        result[key] = value
    return result


def _reviewed_param_id(short_name: str | None) -> int | None:
    if short_name is not None and short_name.lower() == PARAM_SHORT_NAME:
        return PARAM_ID
    return None


def _build_index_row(
    obj: Mapping[str, object], *, row_offset: int, row_json: str, row_sha256: str
) -> EcmwfIndexRow:
    short_name_field = _index_text(obj.get("shortName"))
    param_field = _index_text(obj.get("param"))
    if (
        short_name_field is not None
        and param_field is not None
        and short_name_field.lower() != param_field.lower()
    ):
        raise EcmwfIndexError("index shortName and param disagree")
    short_name = short_name_field if short_name_field is not None else param_field

    if "paramId" in obj:
        param_id = _index_int(obj.get("paramId"), "paramId")
        param_id_basis: EcmwfParamIdBasis | None = EcmwfParamIdBasis.INDEX_DECLARED
        reviewed = _reviewed_param_id(short_name)
        if reviewed is not None and reviewed != param_id:
            raise EcmwfIndexError("index paramId conflicts with reviewed shortName")
        if param_id == PARAM_ID and short_name is not None and reviewed is None:
            raise EcmwfIndexError("index paramId 167 conflicts with shortName")
    else:
        param_id = _reviewed_param_id(short_name)
        param_id_basis = (
            EcmwfParamIdBasis.REVIEWED_SHORT_NAME if param_id is not None else None
        )
    units = _index_text(obj.get("units"))
    level_type = _index_text(obj.get("levtype"))
    level = _index_text(obj.get("levelist"))
    data_type = _index_text(obj.get("type"))
    stream = _index_text(obj.get("stream"))
    run_date = _index_date(obj.get("date"))
    cycle_hour = _index_cycle(obj.get("time"))
    step_hours = _optional_index_int(obj.get("step"), "step")

    if "_offset" in obj:
        byte_offset = _index_int(obj["_offset"], "_offset")
    elif "offset" in obj:
        byte_offset = _index_int(obj["offset"], "offset")
    else:
        raise EcmwfIndexError("index row has no message offset")
    if "_length" in obj:
        byte_length = _index_int(obj["_length"], "_length")
    elif "length" in obj:
        byte_length = _index_int(obj["length"], "length")
    else:
        raise EcmwfIndexError("index row has no message length")
    if byte_offset < 0:
        raise EcmwfIndexError("index offset must be non-negative")
    if byte_length < 1:
        raise EcmwfIndexError("index length must be positive")
    if byte_length > MAX_FIELD_BYTES:
        raise EcmwfResponseTooLargeError("indexed field exceeds the 32 MiB field bound")

    return EcmwfIndexRow(
        row_offset=row_offset,
        row_sha256=row_sha256,
        row_json=row_json,
        param_id=param_id,
        short_name=short_name,
        name=_index_text(obj.get("name")),
        units=units,
        level_type=level_type,
        level=level,
        data_type=data_type,
        stream=stream,
        run_date=run_date,
        cycle_hour=cycle_hour,
        step_hours=step_hours,
        byte_offset=byte_offset,
        byte_length=byte_length,
        param_id_basis=param_id_basis,
    )


def _is_this_2t_surface(row: EcmwfIndexRow) -> bool:
    if row.param_id != PARAM_ID:
        return False
    if row.short_name is not None and row.short_name.lower() != PARAM_SHORT_NAME:
        return False
    if row.level_type is not None and row.level_type.lower() != "sfc":
        return False
    if row.level is not None and row.level not in {"2", "2.0"}:
        return False
    return True


def parse_grib_index(raw_index: bytes, request: EcmwfOpenDataRequest) -> EcmwfIndex:
    """Select exactly one official-index 2t surface message.

    Official index dictionaries are read tolerantly (unknown keys are retained in
    ``row_json``) but the selection is strict: one surface row whose declared or
    reviewed-derived parameter id is 167, with present run/time/step/unit metadata
    agreeing with the request.  The actual index may omit units and name; the
    authentic GRIB decoder, not this index, proves paramId 167 and K.
    """

    if not isinstance(request, EcmwfOpenDataRequest):
        raise EcmwfInvalidRequestError("request must be EcmwfOpenDataRequest")
    if not isinstance(raw_index, bytes) or not raw_index:
        raise EcmwfIndexError("index body is empty or not bytes")
    if len(raw_index) > MAX_INDEX_BYTES:
        raise EcmwfResponseTooLargeError("index exceeds the 2 MiB index bound")

    rows: list[EcmwfIndexRow] = []
    offset = 0
    for line_with_newline in raw_index.splitlines(keepends=True):
        line = line_with_newline.rstrip(b"\r\n")
        if not line.strip():
            offset += len(line_with_newline)
            continue
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EcmwfIndexError("index row is not UTF-8") from exc
        try:
            obj = json.loads(
                text,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_unique_object,
            )
        except (TypeError, ValueError) as exc:
            raise EcmwfIndexError("index row is not valid JSON") from exc
        if not isinstance(obj, dict):
            raise EcmwfIndexError("index row is not a JSON object")
        rows.append(
            _build_index_row(
                obj,
                row_offset=offset,
                row_json=text,
                row_sha256=hashlib.sha256(line).hexdigest(),
            )
        )
        offset += len(line_with_newline)

    candidates = [row for row in rows if _is_this_2t_surface(row)]
    if not candidates:
        raise EcmwfAssetNotFoundError("index has no 2t/paramId 167 surface message")
    if len(candidates) != 1:
        raise EcmwfIndexAmbiguousError("index has more than one 2t surface message")
    selected = candidates[0]

    if selected.units is not None and selected.units != PARAM_UNITS:
        raise EcmwfIndexMismatchError("2t index metadata does not report kelvin")
    if selected.run_date is not None and selected.run_date != request.run_date:
        raise EcmwfIndexMismatchError("2t index run date does not match the request")
    if selected.cycle_hour is not None and selected.cycle_hour != request.cycle_hour:
        raise EcmwfIndexMismatchError("2t index cycle does not match the request")
    if selected.step_hours is not None and selected.step_hours != request.step_hours:
        raise EcmwfIndexMismatchError("2t index step does not match the request")
    if selected.stream is not None and selected.stream.lower() != PRODUCT_STREAM:
        raise EcmwfIndexMismatchError("2t index stream is not oper")
    if selected.data_type is not None and selected.data_type.lower() != "fc":
        raise EcmwfIndexMismatchError("2t index type is not deterministic forecast")

    return EcmwfIndex(
        raw_sha256=hashlib.sha256(raw_index).hexdigest(),
        raw_size_bytes=len(raw_index),
        row_count=len(rows),
        selected=selected,
    )


@dataclass(frozen=True, slots=True)
class _DiscoveredAsset:
    asset_url: str
    index_url: str
    directory_url: str
    listing_pages: tuple[EcmwfListingPage, ...]


class EcmwfOpenDataClient:
    """Synchronous, bounded transport for the two reviewed ECMWF origins."""

    def __init__(
        self,
        *,
        source: EcmwfSource | str = EcmwfSource.ECMWF,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 15.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise EcmwfInvalidRequestError("timeout_seconds must be positive and finite")
        self.origin = resolve_origin(source)
        self._source = self.origin.source
        self._sleep = sleep
        self._clock = clock
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(timeout_seconds, connect=min(5.0, timeout_seconds)),
            follow_redirects=False,
            trust_env=False,
            cookies=None,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept-Encoding": "identity",
            },
        )

    def __enter__(self) -> EcmwfOpenDataClient:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime):
            raise EcmwfProtocolError("clock did not return a datetime")
        try:
            return _utc(value)
        except EcmwfInvalidRequestError as exc:
            raise EcmwfProtocolError("clock must return an aware UTC datetime") from exc

    def _validate_url(self, url: str, *, allow_query: bool = False) -> None:
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise EcmwfOriginError("URL is malformed") from exc
        if parsed.scheme != "https":
            raise EcmwfOriginError("only HTTPS provider origins are allowed")
        if parsed.username is not None or parsed.password is not None:
            raise EcmwfOriginError("credential-bearing URLs are forbidden")
        host = (parsed.hostname or "").lower()
        if host not in ALLOWED_HOSTS or host != self.origin.host:
            raise EcmwfOriginError("host is outside the selected fixed origin")
        if port not in (None, 443):
            raise EcmwfOriginError("non-HTTPS port is forbidden")
        if not parsed.path.startswith(self.origin.path_prefix):
            raise EcmwfOriginError("path is outside the selected provider prefix")
        if parsed.fragment:
            raise EcmwfOriginError("URL fragments are forbidden")
        if parsed.query and not allow_query:
            raise EcmwfOriginError("query parameters are forbidden for this request")
        decoded = unquote(parsed.path)
        if (
            "\\" in decoded
            or "\x00" in decoded
            or any(segment in {".", ".."} for segment in decoded.split("/"))
        ):
            raise EcmwfOriginError("path traversal is forbidden")

    def _validate_redirect(self, current: str, target: str) -> None:
        self._validate_url(target, allow_query=True)
        current_parts = urlsplit(current)
        target_parts = urlsplit(target)
        if target_parts.path != current_parts.path:
            raise EcmwfOriginError("redirect must not change the selected object path")
        if target_parts.query != current_parts.query:
            raise EcmwfOriginError("redirect must not change the fixed request query")
        if target_parts.fragment:
            raise EcmwfOriginError("redirect fragments are forbidden")

    def _send_following_redirects(
        self, url: str, headers: Mapping[str, str]
    ) -> tuple[httpx.Response, str]:
        current = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            self._validate_url(current, allow_query=True)
            # httpx keeps a cookie jar by default.  Clear it on both sides of every
            # hop so a provider Set-Cookie can never become a credential on a retry.
            self._client.cookies.clear()
            request = self._client.build_request(
                "GET",
                current,
                headers=dict(headers),
            )
            response = self._client.send(request, stream=True)
            self._client.cookies.clear()
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if redirect_count >= MAX_REDIRECTS:
                    raise EcmwfOriginError("redirect limit exceeded")
                if not location:
                    raise EcmwfOriginError("redirect has no location")
                target = urljoin(current, location)
                self._validate_redirect(current, target)
                current = target
                continue
            return response, current
        raise EcmwfOriginError("redirect limit exceeded")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        raw = response.headers.get("retry-after")
        if raw is not None:
            raw = raw.strip()
            if raw.isdigit():
                try:
                    seconds = float(raw)
                except (OverflowError, ValueError):
                    return MAX_RETRY_AFTER_SECONDS
                if not math.isfinite(seconds):
                    return MAX_RETRY_AFTER_SECONDS
                return max(0.0, min(seconds, MAX_RETRY_AFTER_SECONDS))
            try:
                when = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                when = None
            if when is not None:
                if when.tzinfo is None:
                    return 0.0
                delta = (when.astimezone(UTC) - self._now()).total_seconds()
                return max(0.0, min(delta, MAX_RETRY_AFTER_SECONDS))
        return min(0.5 * (2**attempt), MAX_RETRY_AFTER_SECONDS)

    def _send_with_retries(
        self, url: str, headers: Mapping[str, str]
    ) -> tuple[httpx.Response, str]:
        for attempt in range(MAX_HTTP_ATTEMPTS):
            response, final_url = self._send_following_redirects(url, headers)
            if response.status_code not in {429, 503}:
                return response, final_url
            delay = self._retry_delay(response, attempt)
            response.close()
            if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                raise EcmwfRateLimitedError("provider remained rate limited")
            self._sleep(delay)
        raise EcmwfRateLimitedError("provider remained rate limited")

    @staticmethod
    def _check_identity_encoding(response: httpx.Response) -> None:
        encoding = response.headers.get("content-encoding")
        if encoding and encoding.strip().lower() != "identity":
            raise EcmwfProtocolError("content encoding is not identity")

    @staticmethod
    def _read_raw_limited(
        response: httpx.Response,
        limit: int,
        error_type: type[EcmwfOpenDataError],
        too_large_message: str,
    ) -> bytes:
        """Return exact raw bytes without exceeding ``limit``.

        Production responses are true streams: ``iter_raw`` keeps the transfer
        bounded and undecoded.  Some transports, notably ``httpx.MockTransport``
        with a preloaded ``content=`` response, have already consumed and
        buffered the body, so ``iter_raw`` would raise ``StreamConsumed``.  Those
        buffered bytes are still the exact identity-encoded body (the caller has
        already rejected non-identity encoding), so use them under the same bound.
        """

        if response.is_stream_consumed:
            body = response.content
            if len(body) > limit:
                raise error_type(too_large_message)
            return body
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_raw(chunk_size=_STREAM_CHUNK_BYTES):
            total += len(chunk)
            if total > limit:
                raise error_type(too_large_message)
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _read_limited(response: httpx.Response, limit: int) -> bytes:
        declared: int | None = None
        raw_length = response.headers.get("content-length")
        if raw_length is not None:
            try:
                declared = int(raw_length)
            except ValueError as exc:
                raise EcmwfProtocolError("invalid Content-Length") from exc
            if declared < 0:
                raise EcmwfProtocolError("invalid Content-Length")
            if declared > limit:
                raise EcmwfResponseTooLargeError("response exceeds the configured bound")
        body = EcmwfOpenDataClient._read_raw_limited(
            response,
            limit,
            EcmwfResponseTooLargeError,
            "response exceeds the configured bound",
        )
        if declared is not None and len(body) != declared:
            raise EcmwfProtocolError("response length does not match Content-Length")
        return body

    def _get_text(
        self, url: str, *, accept: str, limit: int = MAX_LISTING_BYTES
    ) -> tuple[str, str]:
        headers = {"Accept": accept, "Accept-Encoding": "identity", "User-Agent": _USER_AGENT}
        response, _final_url = self._send_with_retries(url, headers)
        try:
            if response.status_code != 200:
                raise EcmwfHttpStatusError(response.status_code)
            self._check_identity_encoding(response)
            body = self._read_limited(response, limit)
        finally:
            response.close()
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EcmwfProtocolError("listing/index body is not UTF-8") from exc
        return text, hashlib.sha256(body).hexdigest()

    def _get_index(self, url: str) -> bytes:
        headers = {
            "Accept": "application/json, application/x-ndjson, text/plain",
            "Accept-Encoding": "identity",
            "User-Agent": _USER_AGENT,
        }
        response, _final_url = self._send_with_retries(url, headers)
        try:
            if response.status_code != 200:
                raise EcmwfHttpStatusError(response.status_code)
            self._check_identity_encoding(response)
            return self._read_limited(response, MAX_INDEX_BYTES)
        finally:
            response.close()

    def _discover_official(self, request: EcmwfOpenDataRequest) -> _DiscoveredAsset:
        pages: list[EcmwfListingPage] = []
        current = self.origin.base_url
        date_path = f"/forecasts/{request.run_date:%Y%m%d}/"
        expected_paths = (
            date_path,
            f"{date_path}{request.cycle_hour:02d}z/",
            f"{date_path}{request.cycle_hour:02d}z/{MODEL_NAME}/",
            f"{date_path}{request.cycle_hour:02d}z/{MODEL_NAME}/{GRID_NAME}/",
            f"{date_path}{request.cycle_hour:02d}z/{MODEL_NAME}/{GRID_NAME}/{PRODUCT_STREAM}/",
        )
        for expected_path in expected_paths:
            text, digest = self._get_text(
                current,
                accept="text/html, application/xhtml+xml",
            )
            pages.append(EcmwfListingPage(url=current, sha256=digest))
            current = self._select_child_from_text(text, current, expected_path)
        if len(pages) > MAX_LISTING_PAGES:
            raise EcmwfListingError("official listing traversal exceeded its bound")
        final_text, final_digest = self._get_text(
            current,
            accept="text/html, application/xhtml+xml",
        )
        pages.append(EcmwfListingPage(url=current, sha256=final_digest))
        asset_url = self._member_url_from_text(final_text, current, request.asset_filename)
        index_url = self._member_url_from_text(final_text, current, request.index_filename)
        if len(pages) > MAX_LISTING_PAGES:
            raise EcmwfListingError("official listing traversal exceeded its bound")
        return _DiscoveredAsset(
            asset_url=asset_url,
            index_url=index_url,
            directory_url=current,
            listing_pages=tuple(pages),
        )

    def _select_child_from_text(self, text: str, base_url: str, expected_path: str) -> str:
        matches: set[str] = set()
        for href in _anchor_hrefs(text):
            try:
                target = urljoin(base_url, href)
                parsed = urlsplit(target)
                self._validate_url(target)
            except (EcmwfOriginError, ValueError):
                continue
            if parsed.path == expected_path:
                matches.add(urlunsplit(("https", parsed.netloc, parsed.path, "", "")))
        if not matches:
            raise EcmwfAssetNotFoundError("expected official directory link was not found")
        if len(matches) != 1:
            raise EcmwfListingError("expected official directory link is ambiguous")
        return matches.pop()

    def _member_url_from_text(self, text: str, directory_url: str, member: str) -> str:
        directory = urlsplit(directory_url)
        expected_path = f"{directory.path}{member}"
        matches: set[str] = set()
        for href in _anchor_hrefs(text):
            try:
                target = urljoin(directory_url, href)
                parsed = urlsplit(target)
                self._validate_url(target)
            except (EcmwfOriginError, ValueError):
                continue
            if parsed.path == expected_path:
                matches.add(urlunsplit(("https", parsed.netloc, parsed.path, "", "")))
        if not matches:
            raise EcmwfAssetNotFoundError(f"directly linked asset {member} was not found")
        if len(matches) != 1:
            raise EcmwfListingError(f"asset {member} is linked ambiguously")
        return matches.pop()

    def _discover_aws(self, request: EcmwfOpenDataRequest) -> _DiscoveredAsset:
        prefix = request.s3_prefix
        query = urlencode(
            {"list-type": "2", "prefix": prefix, "max-keys": "1000"},
            safe="/",
        )
        listing_url = f"{self.origin.base_url}?{query}"
        xml_text, digest = self._get_text(
            listing_url,
            accept="application/xml, text/xml",
            limit=MAX_LISTING_BYTES,
        )
        keys = _parse_s3_keys(xml_text, expected_bucket="ecmwf-forecasts", prefix=prefix)
        asset_key = f"{prefix}{request.asset_filename}"
        index_key = f"{prefix}{request.index_filename}"
        if asset_key not in keys or index_key not in keys:
            raise EcmwfAssetNotFoundError("S3 listing lacks the exact GRIB or index object")
        asset_url = self.origin.base_url + quote(asset_key, safe="/")
        index_url = self.origin.base_url + quote(index_key, safe="/")
        self._validate_url(asset_url)
        self._validate_url(index_url)
        return _DiscoveredAsset(
            asset_url=asset_url,
            index_url=index_url,
            directory_url=listing_url,
            listing_pages=(EcmwfListingPage(url=listing_url, sha256=digest),),
        )

    def _retrieve_bytes(
        self, asset_url: str, row: EcmwfIndexRow
    ) -> tuple[bytes, str, str, int, datetime | None]:
        start = row.byte_offset
        end = start + row.byte_length - 1
        range_header = f"bytes={start}-{end}"
        headers = {
            "Accept": "application/octet-stream",
            "Accept-Encoding": "identity",
            "Range": range_header,
            "User-Agent": _USER_AGENT,
        }
        response, _final_url = self._send_with_retries(asset_url, headers)
        try:
            if response.status_code != 206:
                raise EcmwfRangeError("provider did not return HTTP 206")
            self._check_identity_encoding(response)
            content_range = response.headers.get("content-range", "")
            match = _CONTENT_RANGE_RE.fullmatch(content_range.strip())
            if match is None:
                raise EcmwfRangeError("missing or malformed Content-Range")
            returned_start, returned_end, total = (int(item) for item in match.groups())
            if returned_start != start or returned_end != end:
                raise EcmwfRangeError("Content-Range does not match the selected message")
            if total < end + 1:
                raise EcmwfRangeError("Content-Range total is smaller than the selected message")
            raw_length = response.headers.get("content-length")
            if raw_length is None or not raw_length.isdigit():
                raise EcmwfRangeError("Content-Length is required for an exact range")
            if int(raw_length) != row.byte_length:
                raise EcmwfRangeError("Content-Length does not match the indexed message")
            body = self._read_raw_limited(
                response,
                row.byte_length,
                EcmwfRangeError,
                "range response exceeded the indexed message",
            )
            if len(body) != row.byte_length:
                raise EcmwfRangeError("range response was shorter than the indexed message")
            last_modified = _parse_http_date(response.headers.get("last-modified"))
            return body, content_range, range_header, total, last_modified
        finally:
            response.close()

    def retrieve(self, request: EcmwfOpenDataRequest) -> EcmwfField:
        """Discover, select, verify, and return one exact GRIB2 message."""

        if not isinstance(request, EcmwfOpenDataRequest):
            raise EcmwfInvalidRequestError("request must be EcmwfOpenDataRequest")
        started = self._now()
        discovered = (
            self._discover_official(request)
            if self._source is EcmwfSource.ECMWF
            else self._discover_aws(request)
        )
        raw_index = self._get_index(discovered.index_url)
        index = parse_grib_index(raw_index, request)
        grib_bytes, content_range, _range_header, total, last_modified = (
            self._retrieve_bytes(discovered.asset_url, index.selected)
        )
        completed = self._now()
        if completed < started:
            raise EcmwfProtocolError("clock moved backwards during retrieval")
        grib_sha256 = hashlib.sha256(grib_bytes).hexdigest()
        request_sha256 = request.fingerprint()
        reference = EcmwfFieldReference(
            source=self._source,
            origin=self.origin.label,
            asset_url=discovered.asset_url,
            request_sha256=request_sha256,
            grib_sha256=grib_sha256,
            index_sha256=index.raw_sha256,
            index_row_offset=index.selected.row_offset,
            run_date=request.run_date,
            cycle_hour=request.cycle_hour,
            step_hours=request.step_hours,
            valid_at_utc=request.valid_at_utc,
        )
        run = EcmwfRun(
            request=request,
            request_sha256=request_sha256,
            source=self._source,
            origin=self.origin.label,
            directory_url=discovered.directory_url,
            asset_url=discovered.asset_url,
            index_url=discovered.index_url,
            listing_pages=discovered.listing_pages,
            issued_at_utc=request.issued_at_utc,
            valid_at_utc=request.valid_at_utc,
            request_started_at_utc=started,
            receipt_completed_at_utc=completed,
            provider_last_modified_utc=last_modified,
            availability_basis=(
                EcmwfAvailabilityBasis.PROVIDER_LAST_MODIFIED
                if last_modified is not None
                else EcmwfAvailabilityBasis.LOCAL_RECEIPT_ONLY
            ),
        )
        return EcmwfField(
            run=run,
            index=index,
            reference=reference,
            grib_bytes=grib_bytes,
            grib_sha256=grib_sha256,
            content_range=content_range,
            asset_total_bytes=total,
        )


def _parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None or parsed.tzinfo is None:
        return None
    try:
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_s3_keys(xml_text: str, *, expected_bucket: str, prefix: str) -> frozenset[str]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise EcmwfListingError("S3 listing is not well-formed XML") from exc
    if _local_name(root.tag) != "ListBucketResult":
        raise EcmwfListingError("S3 listing has an unexpected root element")
    bucket = None
    listing_prefix = None
    truncated = None
    keys: set[str] = set()
    for child in root:
        name = _local_name(child.tag)
        if name == "Name":
            bucket = (child.text or "").strip()
        elif name == "Prefix":
            listing_prefix = (child.text or "").strip()
        elif name == "IsTruncated":
            truncated = (child.text or "").strip().lower()
        elif name == "Contents":
            key = None
            for part in child:
                if _local_name(part.tag) == "Key":
                    key = part.text
                    break
            if key is None:
                raise EcmwfListingError("S3 Contents entry has no Key")
            if not key.startswith(prefix):
                raise EcmwfListingError("S3 key escapes the fixed prefix")
            if key in keys:
                raise EcmwfListingError("S3 listing repeats a key")
            keys.add(key)
    if bucket != expected_bucket:
        raise EcmwfListingError("S3 listing bucket is not the reviewed ECMWF bucket")
    if listing_prefix != prefix:
        raise EcmwfListingError("S3 listing prefix does not match the fixed request")
    if truncated != "false":
        raise EcmwfListingError("S3 listing is truncated or has no completeness flag")
    return frozenset(keys)
