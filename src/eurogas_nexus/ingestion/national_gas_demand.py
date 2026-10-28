"""Strict source adapter for National Gas NTS actual-demand CSV downloads.

The public download endpoint is keyless.  This module deliberately knows only
the two approved actual-demand catalogue items (D+1 and D+6), a fixed official
origin, and the exact CSV header.  It never changes a source value: the native
decimal spelling is retained as text, and blank/zero/quality states remain
distinct.

The parser is pure (no database or HTTP client import).  The download function
is a bounded transport wrapper around that parser.  ``available_at_utc`` is the
conservative local receipt time until the provider's CSV wall-clock timezone is
independently proven.  Published timestamps are therefore left unresolved
(``None``) even though the source's generated wall clock is retained.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

if TYPE_CHECKING:  # pragma: no cover - import used only by static type checkers
    import httpx

SOURCE_SYSTEM: Final = "NATIONAL_GAS"
DOWNLOAD_HOST: Final = "data.nationalgas.com"
DOWNLOAD_PATH: Final = "/api/find-gas-data-download"
DOWNLOAD_URL: Final = f"https://{DOWNLOAD_HOST}{DOWNLOAD_PATH}"
EXPECTED_HEADER: Final = (
    "Applicable At",
    "Applicable For",
    "Data Item",
    "Value",
    "Generated Time",
    "Quality Indicator",
)
UNIT: Final = "mscm"
REGION: Final = "GB_NTS"
HASH_SCHEMA: Final = "national_gas_actual_demand.v1"
CALENDAR: Final = "EU_CAM_UTC_CALENDAR"
MAX_WINDOW_DAYS: Final = 31
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024
MAX_VALUE_CHARS: Final = 64
DEFAULT_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_MAX_ATTEMPTS: Final = 3
RETRYABLE_STATUSES: Final = frozenset({429, 500, 502, 503, 504})
QUALITY_LABELS: Final = {
    "L": "LATE",
    "A": "AMENDED",
    "C": "CORRECTED",
    "E": "EXPIRED",
    "S": "SUBSTITUTED",
}

_GB_LOCAL = ZoneInfo("Europe/London")
_DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_NAIVE_FORMATS: Final = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")


class NationalGasDemandError(ValueError):
    """A stable, operator-safe source or contract failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class DemandSeries:
    """One allowlisted actual-demand catalogue item."""

    provider_item_id: str
    label: str
    term: str
    provisional_status: str
    is_provisional: bool | None


NTS_DEMAND_D6 = DemandSeries(
    provider_item_id="PUBOB652",
    label="Demand Actual, NTS, D+6",
    term="D+6",
    provisional_status="UNRESOLVED_D_PLUS_6",
    is_provisional=None,
)
NTS_DEMAND_D1 = DemandSeries(
    provider_item_id="PUBOB637",
    label="Demand Actual, NTS, D+1",
    term="D+1",
    provisional_status="PROVISIONAL_INITIAL",
    is_provisional=True,
)
SERIES_BY_ITEM: Final = {
    NTS_DEMAND_D1.provider_item_id: NTS_DEMAND_D1,
    NTS_DEMAND_D6.provider_item_id: NTS_DEMAND_D6,
}
ALLOWED_PROVIDER_ITEM_IDS: Final = frozenset(SERIES_BY_ITEM)


@dataclass(frozen=True)
class NationalGasActualDemand:
    """One immutable, source-faithful actual-demand publication revision."""

    record_id: str
    source_publication_id: str
    provider_item_id: str
    series_key: str
    region: str
    term: str
    label: str
    gas_day: date
    period_start_utc: datetime
    period_end_utc: datetime
    value_text: str
    unit: str
    received_at_utc: datetime
    available_at_utc: datetime
    ingested_at_utc: datetime
    published_at_utc: datetime | None
    applicable_at_raw: str
    generated_at_raw: str
    applicable_at_naive: datetime
    generated_at_naive: datetime
    quality_indicator: str | None
    provisional_status: str
    is_provisional: bool | None
    raw_sha256: str
    source_url: str
    hash_schema: str


@dataclass(frozen=True)
class DemandDownload:
    """A bounded download plus its parsed revisions."""

    rows: tuple[NationalGasActualDemand, ...]
    raw_csv: bytes
    raw_sha256: str
    source_url: str
    received_at_utc: datetime


def validate_query_window(date_from: date, date_to: date) -> None:
    """Validate an explicit, inclusive gas-day download window."""

    if isinstance(date_from, datetime) or isinstance(date_to, datetime):
        raise NationalGasDemandError("INVALID_WINDOW", "dates must be calendar dates")
    if date_from > date_to:
        raise NationalGasDemandError("INVALID_WINDOW", "dateFrom must not be after dateTo")
    if (date_to - date_from).days + 1 > MAX_WINDOW_DAYS:
        raise NationalGasDemandError(
            "INVALID_WINDOW", f"window must not exceed {MAX_WINDOW_DAYS} days"
        )


def validate_provider_item_id(provider_item_id: str) -> DemandSeries:
    """Return the allowlisted series or refuse an unknown publication item."""

    try:
        return SERIES_BY_ITEM[provider_item_id]
    except KeyError as exc:
        raise NationalGasDemandError(
            "UNKNOWN_SERIES", "publication item is not an approved NTS actual-demand series"
        ) from exc


def build_download_url(provider_item_id: str, date_from: date, date_to: date) -> str:
    """Build the only permitted official download URL."""

    item = validate_provider_item_id(provider_item_id)
    validate_query_window(date_from, date_to)
    query = urlencode(
        {
            "applicableFor": "Y",
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "dateType": "GASDAY",
            "latestFlag": "N",
            "ids": item.provider_item_id,
            "type": "CSV",
        }
    )
    return f"{DOWNLOAD_URL}?{query}"


def gas_day_period_utc(gas_day: date) -> tuple[datetime, datetime]:
    """Return the EU CAM gas-day physical period as timezone-aware UTC instants.

    The accepted calendar is the EU CAM gas day expressed as 05:00 GB local
    time (Europe/London), including DST.  The legacy UK 06:00 gas day is not
    used for new data.
    """

    start_local = datetime.combine(gas_day, clock_time(5), tzinfo=_GB_LOCAL)
    end_local = datetime.combine(gas_day + timedelta(days=1), clock_time(5), tzinfo=_GB_LOCAL)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def parse_national_gas_csv(
    payload: bytes | str,
    *,
    provider_item_id: str,
    date_from: date,
    date_to: date,
    received_at_utc: datetime,
    available_at_utc: datetime | None = None,
) -> list[NationalGasActualDemand]:
    """Parse the exact National Gas actual-demand CSV into immutable DTOs.

    Empty payloads, header drift, malformed values, unknown series, and rows
    outside the explicit window are refused.  Duplicate rows are retained here
    for the repository to classify idempotently; revisions are never collapsed.
    """

    series = validate_provider_item_id(provider_item_id)
    validate_query_window(date_from, date_to)
    received = _require_aware_utc(received_at_utc, "received_at_utc")
    available = _require_aware_utc(available_at_utc or received, "available_at_utc")
    if series.provider_item_id not in ALLOWED_PROVIDER_ITEM_IDS:
        raise NationalGasDemandError("UNKNOWN_SERIES", "publication item is not approved")

    text, raw_bytes = _decode_payload(payload)
    if not text.strip():
        raise NationalGasDemandError("EMPTY_RESPONSE", "download contained no CSV data")

    source_url = build_download_url(series.provider_item_id, date_from, date_to)
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = tuple(next(reader))
    except StopIteration as exc:
        raise NationalGasDemandError("EMPTY_RESPONSE", "download contained no CSV header") from exc
    except csv.Error as exc:
        raise NationalGasDemandError("MALFORMED_CSV", "CSV header is malformed") from exc
    if header != EXPECTED_HEADER:
        raise NationalGasDemandError("HEADER_DRIFT", "CSV header does not match the contract")

    rows: list[NationalGasActualDemand] = []
    try:
        for fields in reader:
            if not fields:
                continue
            if len(fields) != len(EXPECTED_HEADER):
                raise NationalGasDemandError(
                    "MALFORMED_CSV", "row does not have the contracted column count"
                )
            rows.append(
                _parse_row(
                    fields,
                    series=series,
                    date_from=date_from,
                    date_to=date_to,
                    received=received,
                    available=available,
                    raw_sha256=raw_sha256,
                    source_url=source_url,
                )
            )
    except csv.Error as exc:
        raise NationalGasDemandError("MALFORMED_CSV", "CSV row is malformed") from exc

    if not rows:
        raise NationalGasDemandError("NO_DATA_ROWS", "download contained no data rows")
    return rows


def download_national_gas_csv(
    provider_item_id: str,
    *,
    date_from: date,
    date_to: date,
    client: httpx.Client | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    received_at_utc: datetime | None = None,
) -> DemandDownload:
    """Download one allowlisted item from the fixed official origin.

    Redirects are not followed, cross-origin responses are refused, and retries
    are limited to 429/5xx and transport timeouts.  No credentials, arbitrary
    URL, provider status body, or operator-supplied host is accepted.
    """

    series = validate_provider_item_id(provider_item_id)
    validate_query_window(date_from, date_to)
    if not 1 <= max_attempts <= 5:
        raise NationalGasDemandError("INVALID_RETRY_POLICY", "max_attempts must be 1..5")
    if not 1.0 <= timeout_seconds <= 30.0:
        raise NationalGasDemandError("INVALID_TIMEOUT", "timeout must be 1..30 seconds")
    target_url = build_download_url(series.provider_item_id, date_from, date_to)

    import httpx

    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(timeout_seconds),
        follow_redirects=False,
        trust_env=False,
    )
    try:
        for attempt in range(1, max_attempts + 1):
            retry = False
            try:
                with active_client.stream(
                    "GET", target_url, headers={"Accept": "text/csv"}
                ) as response:
                    _assert_trusted_response(response, target_url)
                    if response.status_code == 200:
                        body = _read_bounded(response)
                    elif response.status_code in RETRYABLE_STATUSES and attempt < max_attempts:
                        retry = True
                        body = b""
                    elif response.status_code == 429:
                        raise NationalGasDemandError(
                            "HTTP_RATE_LIMITED", "official endpoint rate-limited the request"
                        )
                    elif response.status_code >= 500:
                        raise NationalGasDemandError(
                            "HTTP_SERVER_ERROR", "official endpoint returned a server error"
                        )
                    elif 300 <= response.status_code < 400:
                        raise NationalGasDemandError(
                            "REDIRECT_REFUSED", "official endpoint attempted a redirect"
                        )
                    else:
                        raise NationalGasDemandError(
                            "HTTP_CLIENT_ERROR", "official endpoint refused the request"
                        )
            except httpx.TimeoutException as exc:
                if attempt >= max_attempts:
                    raise NationalGasDemandError(
                        "HTTP_TIMEOUT", "official endpoint timed out"
                    ) from exc
                retry = True
                body = b""
            except httpx.TransportError as exc:
                if attempt >= max_attempts:
                    raise NationalGasDemandError(
                        "HTTP_TRANSPORT_ERROR", "official endpoint transport failed"
                    ) from exc
                retry = True
                body = b""

            if retry:
                sleep(min(0.25 * (2 ** (attempt - 1)), 2.0))
                continue

            receipt = _require_aware_utc(
                received_at_utc or datetime.now(UTC), "received_at_utc"
            )
            rows = tuple(
                parse_national_gas_csv(
                    body,
                    provider_item_id=series.provider_item_id,
                    date_from=date_from,
                    date_to=date_to,
                    received_at_utc=receipt,
                    available_at_utc=receipt,
                )
            )
            return DemandDownload(
                rows=rows,
                raw_csv=body,
                raw_sha256=hashlib.sha256(body).hexdigest(),
                source_url=target_url,
                received_at_utc=receipt,
            )
    finally:
        if owns_client:
            active_client.close()

    raise NationalGasDemandError("HTTP_RETRY_EXHAUSTED", "download attempts exhausted")


def _parse_row(
    fields: list[str],
    *,
    series: DemandSeries,
    date_from: date,
    date_to: date,
    received: datetime,
    available: datetime,
    raw_sha256: str,
    source_url: str,
) -> NationalGasActualDemand:
    applicable_raw = fields[0].strip()
    gas_day_raw = fields[1].strip()
    label = fields[2]
    value_text = fields[3]
    generated_raw = fields[4].strip()
    quality = _parse_quality(fields[5])

    if label != series.label:
        raise NationalGasDemandError(
            "UNKNOWN_SERIES", "data item label is not the expected NTS actual-demand label"
        )
    try:
        gas_day = datetime.strptime(gas_day_raw, "%d/%m/%Y").date()
    except ValueError as exc:
        raise NationalGasDemandError(
            "MALFORMED_GAS_DAY", "Applicable For is not a date"
        ) from exc
    if not date_from <= gas_day <= date_to:
        raise NationalGasDemandError(
            "ROW_OUTSIDE_WINDOW", "row gas day is outside the explicit query window"
        )

    applicable_naive = _parse_naive(applicable_raw, "Applicable At")
    generated_naive = _parse_naive(generated_raw, "Generated Time")
    _validate_value(value_text)
    period_start, period_end = gas_day_period_utc(gas_day)

    identity = [
        HASH_SCHEMA,
        SOURCE_SYSTEM,
        series.provider_item_id,
        series.label,
        series.term,
        gas_day.isoformat(),
        applicable_raw,
        generated_raw,
    ]
    source_publication_id = _sha256_json(identity)
    record_id = _sha256_json(
        [*identity, value_text, UNIT, quality or "", series.provisional_status]
    )
    return NationalGasActualDemand(
        record_id=record_id,
        source_publication_id=source_publication_id,
        provider_item_id=series.provider_item_id,
        series_key="GB_NTS_ACTUAL_DEMAND",
        region=REGION,
        term=series.term,
        label=series.label,
        gas_day=gas_day,
        period_start_utc=period_start,
        period_end_utc=period_end,
        value_text=value_text,
        unit=UNIT,
        received_at_utc=received,
        available_at_utc=available,
        ingested_at_utc=received,
        published_at_utc=None,
        applicable_at_raw=applicable_raw,
        generated_at_raw=generated_raw,
        applicable_at_naive=applicable_naive,
        generated_at_naive=generated_naive,
        quality_indicator=quality,
        provisional_status=series.provisional_status,
        is_provisional=series.is_provisional,
        raw_sha256=raw_sha256,
        source_url=source_url,
        hash_schema=HASH_SCHEMA,
    )


def _decode_payload(payload: bytes | str) -> tuple[str, bytes]:
    if isinstance(payload, bytes):
        raw = payload
        if len(raw) > MAX_RESPONSE_BYTES:
            raise NationalGasDemandError("RESPONSE_TOO_LARGE", "CSV exceeds the 2 MiB limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NationalGasDemandError("MALFORMED_ENCODING", "CSV is not UTF-8") from exc
        return text, raw
    if isinstance(payload, str):
        try:
            raw = payload.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise NationalGasDemandError("MALFORMED_ENCODING", "CSV is not UTF-8") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise NationalGasDemandError("RESPONSE_TOO_LARGE", "CSV exceeds the 2 MiB limit")
        return payload, raw
    raise NationalGasDemandError("INVALID_PAYLOAD", "CSV payload must be bytes or text")


def _parse_naive(raw: str, field: str) -> datetime:
    if not raw or len(raw) > 32:
        raise NationalGasDemandError("MALFORMED_TIMESTAMP", f"{field} is blank or too long")
    for fmt in _NAIVE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise NationalGasDemandError("MALFORMED_TIMESTAMP", f"{field} is not a supported timestamp")


def _parse_quality(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if len(value) > 8 or not value.isascii() or not value.isprintable():
        raise NationalGasDemandError("MALFORMED_QUALITY", "quality indicator is malformed")
    return value


def _validate_value(value_text: str) -> None:
    if not value_text or value_text != value_text.strip():
        raise NationalGasDemandError(
            "INVALID_VALUE", "value is blank or has surrounding whitespace"
        )
    if len(value_text) > MAX_VALUE_CHARS or not _DECIMAL_RE.fullmatch(value_text):
        raise NationalGasDemandError("INVALID_VALUE", "value is not a bounded decimal string")
    try:
        number = Decimal(value_text)
    except InvalidOperation as exc:
        raise NationalGasDemandError("INVALID_VALUE", "value is not a decimal") from exc
    if not number.is_finite():
        raise NationalGasDemandError("INVALID_VALUE", "NaN and infinity are not accepted")


def _sha256_json(parts: list[str]) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise NationalGasDemandError("NAIVE_TIMESTAMP", f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _assert_trusted_response(response: httpx.Response, expected_url: str) -> None:
    if response.history:
        raise NationalGasDemandError(
            "REDIRECT_REFUSED", "official endpoint response followed a redirect"
        )
    final = response.url
    if (
        final.scheme != "https"
        or (final.host or "").lower() != DOWNLOAD_HOST
        or final.port not in (None, 443)
        or final.path != DOWNLOAD_PATH
        or str(final) != expected_url
    ):
        raise NationalGasDemandError(
            "UNTRUSTED_RESPONSE_ORIGIN",
            "response did not come from the fixed official origin",
        )


def _read_bounded(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > MAX_RESPONSE_BYTES:
            raise NationalGasDemandError(
                "RESPONSE_TOO_LARGE", "declared CSV size exceeds the 2 MiB limit"
            )
    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise NationalGasDemandError("RESPONSE_TOO_LARGE", "CSV exceeds the 2 MiB limit")
    return bytes(body)
