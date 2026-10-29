"""Strict adapter for National Gas's keyless operational-data REST API.

The only supported operations are a fixed-origin POST to the published-time
endpoint and a pure parser for its JSON response.  The adapter deliberately
does not use the retired SOAP service, CSV timezone rules, a provider SDK, a
database, or credentials.

The provider reports three clocks: ``applicableAt``, ``generatedTimeStamp`` and
``createdDate``.  All three are preserved as exact raw text and normalized UTC
instants.  ``provider_timestamp_upper_bound_utc`` is the latest of those three
clocks and its evidence basis is explicitly
``PROVIDER_DECLARED_TIMESTAMP_UPPER_BOUND``.  It is a derived conservative upper
bound among reported provider clocks, not proof of the actual first public
availability of a row, so it is not an automatic admission to historical
training.  Local receipt is recorded separately and is the conservative default
for ``available_at_utc``; it is never backdated.  Values remain their exact
decimal text, quality and substitution flags are distinct, and an amendment or
late revision is never collapsed into an older row.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as clock_time
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from .national_gas_demand import NTS_DEMAND_D1, NTS_DEMAND_D6, DemandSeries

if TYPE_CHECKING:  # pragma: no cover - imported by the transport function only
    import httpx

SOURCE_SYSTEM: Final = "NATIONAL_GAS"
API_HOST: Final = "api.nationalgas.com"
API_PATH: Final = "/operationaldata/v1/publications/publishedtime"
API_URL: Final = f"https://{API_HOST}{API_PATH}"
UNIT: Final = "mscm"
REGION: Final = "GB_NTS"
SERIES_KEY: Final = "GB_NTS_ACTUAL_DEMAND"
HASH_SCHEMA: Final = "national_gas_rest_publication.v1"
EVIDENCE_BASIS: Final = "PROVIDER_DECLARED_TIMESTAMP_UPPER_BOUND"
MAX_WINDOW_DAYS: Final = 31
MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024
MAX_VALUE_CHARS: Final = 64
DEFAULT_TIMEOUT_SECONDS: Final = 10.0
DEFAULT_MAX_ATTEMPTS: Final = 3
MIN_TIMEOUT_SECONDS: Final = 1.0
MAX_TIMEOUT_SECONDS: Final = 30.0
MAX_ATTEMPTS: Final = 5

D1_PUBLICATION_ID: Final = NTS_DEMAND_D1.provider_item_id
D6_PUBLICATION_ID: Final = NTS_DEMAND_D6.provider_item_id
DEFAULT_PUBLICATION_IDS: Final = (D1_PUBLICATION_ID, D6_PUBLICATION_ID)
APPROVED_PUBLICATION_IDS: Final = frozenset(DEFAULT_PUBLICATION_IDS)

_PUBLICATIONS: Final = {
    NTS_DEMAND_D1.provider_item_id: NTS_DEMAND_D1,
    NTS_DEMAND_D6.provider_item_id: NTS_DEMAND_D6,
}

_DECIMAL_RE: Final = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_DATE_RE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_RFC3339_RE: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt]"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?"
    r"(?:[Zz]|[+-][0-9]{2}:[0-9]{2})\Z"
)
_UNIT_FIELDS: Final = ("unit", "publicationUnit", "unitOfMeasure")
_RECORD_FIELDS: Final = (
    "applicableAt",
    "applicableFor",
    "value",
    "generatedTimeStamp",
    "qualityIndicator",
    "substituted",
    "createdDate",
)
_SENSITIVE_REQUEST_HEADERS: Final = ("authorization", "cookie", "proxy-authorization")


class NationalGasRestError(ValueError):
    """A stable, operator-safe source, contract, or transport failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class QualityFlag(StrEnum):
    """The three quality states exposed by the approved REST contract."""

    UNKNOWN = "UNKNOWN"
    AMENDED = "AMENDED"
    SUBSTITUTED = "SUBSTITUTED"


@dataclass(frozen=True)
class NationalGasRestPublication:
    """One immutable, source-faithful provider publication revision."""

    record_id: str
    source_publication_id: str
    publication_id: str
    publication_name: str
    term: str
    provisional_status: str
    is_provisional: bool | None
    applicable_for: date
    applicable_for_raw: str
    applicable_at_utc: datetime
    applicable_at_raw: str
    generated_at_utc: datetime
    generated_at_raw: str
    created_at_utc: datetime
    created_at_raw: str
    provider_timestamp_upper_bound_utc: datetime
    value_text: str
    value_decimal: Decimal | None
    value_is_blank: bool
    unit: str
    quality_flag: QualityFlag
    quality_indicator_raw: str
    substituted_raw: str
    is_substituted: bool | None
    received_at_utc: datetime
    available_at_utc: datetime
    ingested_at_utc: datetime
    raw_sha256: str
    source_url: str
    evidence_basis: str
    hash_schema: str

    @property
    def current_received_at_utc(self) -> datetime:
        """Alias making the distinction from provider time explicit."""

        return self.received_at_utc


@dataclass(frozen=True)
class NationalGasRestDownload:
    """A bounded response together with independent raw bytes and receipt."""

    rows: tuple[NationalGasRestPublication, ...]
    raw_json: bytes
    raw_sha256: str
    request_body: bytes
    source_url: str
    received_at_utc: datetime


def validate_query_window(date_from: date, date_to: date) -> None:
    """Validate an explicit inclusive applicableAt query window.

    The window selects provider rows by ``applicableAt``.  It is not a gas-day
    (``applicableFor``) membership requirement.
    """

    if isinstance(date_from, datetime) or isinstance(date_to, datetime):
        raise NationalGasRestError("INVALID_WINDOW", "window endpoints must be dates")
    if not isinstance(date_from, date) or not isinstance(date_to, date):
        raise NationalGasRestError("INVALID_WINDOW", "window endpoints must be dates")
    if date_from > date_to:
        raise NationalGasRestError("INVALID_WINDOW", "fromDate must not be after toDate")
    if (date_to - date_from).days + 1 > MAX_WINDOW_DAYS:
        raise NationalGasRestError(
            "INVALID_WINDOW", f"window must not exceed {MAX_WINDOW_DAYS} days"
        )


def validate_publication_ids(publication_ids: Iterable[str]) -> tuple[str, ...]:
    """Return the requested IDs in order, refusing unknown or duplicate IDs."""

    if isinstance(publication_ids, (str, bytes)):
        raise NationalGasRestError(
            "INVALID_PUBLICATION_IDS", "publicationIds must be an explicit sequence"
        )
    try:
        requested = tuple(publication_ids)
    except TypeError as exc:
        raise NationalGasRestError(
            "INVALID_PUBLICATION_IDS", "publicationIds must be an explicit sequence"
        ) from exc
    if not requested:
        raise NationalGasRestError("INVALID_PUBLICATION_IDS", "publicationIds is empty")
    if any(not isinstance(item, str) for item in requested):
        raise NationalGasRestError("INVALID_PUBLICATION_IDS", "publication IDs must be text")
    if len(set(requested)) != len(requested):
        raise NationalGasRestError(
            "DUPLICATE_PUBLICATION_ID", "publicationIds must not contain duplicates"
        )
    for publication_id in requested:
        if publication_id not in APPROVED_PUBLICATION_IDS:
            raise NationalGasRestError(
                "UNKNOWN_PUBLICATION", "publication ID is not an approved NTS series"
            )
    return requested


def build_published_time_request(
    date_from: date,
    date_to: date,
    *,
    publication_ids: Iterable[str] = DEFAULT_PUBLICATION_IDS,
) -> dict[str, object]:
    """Build the only permitted request body with an applicableAt window.

    ``fromDate`` and ``toDate`` carry explicit RFC3339 offsets.  They select
    rows by ``applicableAt`` and do not require ``applicableFor`` to fall inside
    the query dates.
    """

    validate_query_window(date_from, date_to)
    requested = validate_publication_ids(publication_ids)
    start = datetime.combine(date_from, clock_time.min, tzinfo=UTC)
    end = datetime.combine(date_to, clock_time(23, 59, 59), tzinfo=UTC)
    return {
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
        "publicationIds": list(requested),
        "latestValue": "N",
    }


def parse_national_gas_rest(
    payload: bytes | str,
    *,
    date_from: date,
    date_to: date,
    received_at_utc: datetime,
    available_at_utc: datetime | None = None,
    publication_ids: Iterable[str] = DEFAULT_PUBLICATION_IDS,
) -> tuple[NationalGasRestPublication, ...]:
    """Parse an exact National Gas published-time response into revisions.

    The parser preserves the provider's three reported clocks and decimal
    spelling directly.  ``provider_timestamp_upper_bound_utc`` is the maximum of
    ``applicableAt``, ``generatedTimeStamp`` and ``createdDate``; it is a
    conservative declared-clock upper bound, not proof of first publication.
    The parser does not apply a gas-day timezone, require ``applicableFor`` to
    fall inside the query dates, or use the current receipt time in place of a
    provider clock.  Empty, duplicate, unknown, or contract-drifted identities
    are refused rather than skipped, so a blank value and a zero value remain
    visible revisions.
    """

    validate_query_window(date_from, date_to)
    requested = frozenset(validate_publication_ids(publication_ids))
    received = _require_aware_utc(received_at_utc, "received_at_utc")
    available = _require_aware_utc(available_at_utc or received, "available_at_utc")
    if available < received:
        raise NationalGasRestError(
            "INVALID_AVAILABILITY", "available_at_utc must not precede local receipt"
        )

    text, raw_bytes = _decode_payload(payload)
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if not text.strip():
        raise NationalGasRestError("EMPTY_RESPONSE", "REST response contained no JSON")

    try:
        root = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except NationalGasRestError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise NationalGasRestError("MALFORMED_JSON", "response is not valid JSON") from exc

    if not isinstance(root, list):
        raise NationalGasRestError("MALFORMED_JSON", "response root must be a JSON array")

    rows: list[NationalGasRestPublication] = []
    seen_publications: set[str] = set()
    for group in root:
        publication_id, series, records = _parse_group(
            group,
            requested=requested,
        )
        if publication_id in seen_publications:
            raise NationalGasRestError(
                "DUPLICATE_PUBLICATION", "response repeated an approved publication"
            )
        seen_publications.add(publication_id)
        for record in records:
            rows.append(
                _parse_record(
                    record,
                    series=series,
                    publication_id=publication_id,
                    received=received,
                    available=available,
                    raw_sha256=raw_sha256,
                )
            )

    if not rows:
        raise NationalGasRestError("NO_DATA", "response contained no publication rows")
    return tuple(rows)


def fetch_national_gas_rest(
    date_from: date,
    date_to: date,
    *,
    publication_ids: Iterable[str] = DEFAULT_PUBLICATION_IDS,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    received_at_utc: datetime | None = None,
    available_at_utc: datetime | None = None,
) -> NationalGasRestDownload:
    """POST the fixed official endpoint with bounded retries and response size.

    The client never follows redirects, inherits environment proxy/authentication
    settings, sends cookies, or accepts an arbitrary URL.  Supplying ``transport``
    allows tests to use ``httpx.MockTransport`` without weakening that boundary.
    Retries are bounded and limited to 429/server responses and transient
    transport failures.
    """

    request = build_published_time_request(
        date_from, date_to, publication_ids=publication_ids
    )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS
    ):
        raise NationalGasRestError(
            "INVALID_TIMEOUT",
            f"timeout must be {MIN_TIMEOUT_SECONDS:g}..{MAX_TIMEOUT_SECONDS:g} seconds",
        )
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or not 1 <= max_attempts <= MAX_ATTEMPTS
    ):
        raise NationalGasRestError(
            "INVALID_RETRY_POLICY", f"max_attempts must be 1..{MAX_ATTEMPTS}"
        )

    prepared_receipt = (
        _require_aware_utc(received_at_utc, "received_at_utc")
        if received_at_utc is not None
        else None
    )
    prepared_available = (
        _require_aware_utc(available_at_utc, "available_at_utc")
        if available_at_utc is not None
        else None
    )

    import httpx

    request_body = json.dumps(
        request, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")

    for attempt in range(1, max_attempts + 1):
        retry_delay: float | None = None
        try:
            # A fresh client per attempt prevents a provider Set-Cookie header
            # from leaking into the next request.  No cookie jar is supplied.
            with httpx.Client(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
                trust_env=False,
                auth=None,
                cookies=None,
                transport=transport,
            ) as client:
                with client.stream(
                    "POST",
                    API_URL,
                    content=request_body,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                ) as response:
                    _assert_trusted_response(response)
                    status = response.status_code
                    if status == 200:
                        raw_json = _read_bounded(response)
                        receipt = prepared_receipt or datetime.now(UTC)
                        rows = parse_national_gas_rest(
                            raw_json,
                            date_from=date_from,
                            date_to=date_to,
                            received_at_utc=receipt,
                            available_at_utc=prepared_available,
                            publication_ids=tuple(request["publicationIds"]),
                        )
                        return NationalGasRestDownload(
                            rows=rows,
                            raw_json=raw_json,
                            raw_sha256=hashlib.sha256(raw_json).hexdigest(),
                            request_body=request_body,
                            source_url=API_URL,
                            received_at_utc=receipt,
                        )
                    if _is_retryable_status(status) and attempt < max_attempts:
                        retry_delay = min(0.25 * (2 ** (attempt - 1)), 2.0)
                    elif status == 429:
                        raise NationalGasRestError(
                            "HTTP_RATE_LIMITED", "official endpoint rate-limited the request"
                        )
                    elif 500 <= status <= 599:
                        raise NationalGasRestError(
                            "HTTP_SERVER_ERROR", "official endpoint returned a server error"
                        )
                    elif 300 <= status <= 399:
                        raise NationalGasRestError(
                            "REDIRECT_REFUSED", "official endpoint attempted a redirect"
                        )
                    else:
                        raise NationalGasRestError(
                            "HTTP_STATUS", "official endpoint returned a non-200 response"
                        )
        except httpx.TimeoutException as exc:
            if attempt >= max_attempts:
                raise NationalGasRestError(
                    "HTTP_TIMEOUT", "official endpoint timed out"
                ) from exc
            retry_delay = min(0.25 * (2 ** (attempt - 1)), 2.0)
        except httpx.TransportError as exc:
            if attempt >= max_attempts:
                raise NationalGasRestError(
                    "HTTP_TRANSPORT_ERROR", "official endpoint transport failed"
                ) from exc
            retry_delay = min(0.25 * (2 ** (attempt - 1)), 2.0)
        except httpx.HTTPError as exc:
            if attempt >= max_attempts:
                raise NationalGasRestError(
                    "HTTP_TRANSPORT_ERROR", "official endpoint response stream failed"
                ) from exc
            retry_delay = min(0.25 * (2 ** (attempt - 1)), 2.0)

        if retry_delay is None:  # pragma: no cover - defensive loop invariant
            raise NationalGasRestError(
                "HTTP_RETRY_EXHAUSTED", "official endpoint attempts exhausted"
            )
        sleep(retry_delay)

    raise NationalGasRestError(
        "HTTP_RETRY_EXHAUSTED", "official endpoint attempts exhausted"
    )  # pragma: no cover - all loop paths return or raise


def _parse_group(
    group: object,
    *,
    requested: frozenset[str],
) -> tuple[str, DemandSeries, list[object]]:
    if not isinstance(group, dict):
        raise NationalGasRestError(
            "MALFORMED_PUBLICATION", "publication group must be a JSON object"
        )
    if any(field not in group for field in ("publicationId", "publicationName", "publications")):
        raise NationalGasRestError(
            "MALFORMED_PUBLICATION", "publication group is missing a required field"
        )

    publication_id = group["publicationId"]
    if not isinstance(publication_id, str) or publication_id not in _PUBLICATIONS:
        raise NationalGasRestError(
            "UNKNOWN_PUBLICATION", "publication ID is not an approved NTS series"
        )
    if publication_id not in requested:
        raise NationalGasRestError(
            "UNEXPECTED_PUBLICATION", "response contains a publication outside the request"
        )
    _validate_unit_fields(group)

    series = _PUBLICATIONS[publication_id]
    publication_name = group["publicationName"]
    if not isinstance(publication_name, str) or publication_name != series.label:
        raise NationalGasRestError(
            "PUBLICATION_NAME_MISMATCH", "publication name does not match the approved identity"
        )
    records = group["publications"]
    if not isinstance(records, list):
        raise NationalGasRestError(
            "MALFORMED_PUBLICATION", "publications must be a JSON array"
        )
    return publication_id, series, records


def _parse_record(
    record: object,
    *,
    series: DemandSeries,
    publication_id: str,
    received: datetime,
    available: datetime,
    raw_sha256: str,
) -> NationalGasRestPublication:
    if not isinstance(record, dict):
        raise NationalGasRestError("MALFORMED_RECORD", "publication row must be a JSON object")
    if any(field not in record for field in _RECORD_FIELDS):
        raise NationalGasRestError(
            "MALFORMED_RECORD", "publication row is missing a required field"
        )
    _validate_unit_fields(record)

    applicable_for_raw = _parse_applicable_for(record["applicableFor"])
    applicable_at_utc, applicable_at_raw = _parse_provider_timestamp(
        record["applicableAt"], "applicableAt"
    )
    generated_at_utc, generated_at_raw = _parse_provider_timestamp(
        record["generatedTimeStamp"], "generatedTimeStamp"
    )
    created_at_utc, created_at_raw = _parse_provider_timestamp(
        record["createdDate"], "createdDate"
    )
    value_text, value_decimal, value_is_blank = _parse_value(record["value"])
    quality_flag, quality_raw = _parse_quality(record["qualityIndicator"])
    substituted_raw, is_substituted = _parse_substituted(record["substituted"])

    # Conservative provider-declared bound; this is not a first-publication fact.
    provider_timestamp_upper_bound_utc = max(
        applicable_at_utc, generated_at_utc, created_at_utc
    )

    identity = [
        HASH_SCHEMA,
        SOURCE_SYSTEM,
        publication_id,
        str(series.label),
        str(series.term),
        str(series.provisional_status),
        applicable_for_raw,
        applicable_at_raw,
        generated_at_raw,
        created_at_raw,
        value_text,
        UNIT,
        quality_raw,
        substituted_raw,
    ]
    source_publication_id = _sha256_json(identity)
    record_id = _sha256_json(["RECORD", REGION, SERIES_KEY, *identity])

    return NationalGasRestPublication(
        record_id=record_id,
        source_publication_id=source_publication_id,
        publication_id=publication_id,
        publication_name=str(series.label),
        term=str(series.term),
        provisional_status=str(series.provisional_status),
        is_provisional=series.is_provisional,
        applicable_for=date.fromisoformat(applicable_for_raw),
        applicable_for_raw=applicable_for_raw,
        applicable_at_utc=applicable_at_utc,
        applicable_at_raw=applicable_at_raw,
        generated_at_utc=generated_at_utc,
        generated_at_raw=generated_at_raw,
        created_at_utc=created_at_utc,
        created_at_raw=created_at_raw,
        provider_timestamp_upper_bound_utc=provider_timestamp_upper_bound_utc,
        value_text=value_text,
        value_decimal=value_decimal,
        value_is_blank=value_is_blank,
        unit=UNIT,
        quality_flag=quality_flag,
        quality_indicator_raw=quality_raw,
        substituted_raw=substituted_raw,
        is_substituted=is_substituted,
        received_at_utc=received,
        available_at_utc=available,
        ingested_at_utc=received,
        raw_sha256=raw_sha256,
        source_url=API_URL,
        evidence_basis=EVIDENCE_BASIS,
        hash_schema=HASH_SCHEMA,
    )


def _parse_applicable_for(raw: object) -> str:
    if not isinstance(raw, str) or _DATE_RE.fullmatch(raw) is None:
        raise NationalGasRestError(
            "MALFORMED_APPLICABLE_FOR", "applicableFor must be a date in YYYY-MM-DD form"
        )
    try:
        date.fromisoformat(raw)
    except ValueError as exc:
        raise NationalGasRestError(
            "MALFORMED_APPLICABLE_FOR", "applicableFor is not a calendar date"
        ) from exc
    return raw


def _parse_provider_timestamp(raw: object, field: str) -> tuple[datetime, str]:
    if not isinstance(raw, str) or not raw:
        raise NationalGasRestError(
            "MALFORMED_TIMESTAMP", f"{field} must be an RFC3339 timestamp"
        )
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise NationalGasRestError(
            "MALFORMED_TIMESTAMP", f"{field} is not a supported RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise NationalGasRestError(
            "NAIVE_TIMESTAMP", f"{field} must include an explicit UTC offset"
        )
    if _RFC3339_RE.fullmatch(raw) is None:
        raise NationalGasRestError(
            "MALFORMED_TIMESTAMP", f"{field} is not an exact RFC3339 timestamp"
        )
    return parsed.astimezone(UTC), raw


def _parse_value(raw: object) -> tuple[str, Decimal | None, bool]:
    if not isinstance(raw, str):
        raise NationalGasRestError("INVALID_VALUE", "value must be an exact decimal string")
    if raw == "":
        return "", None, True
    if raw != raw.strip():
        raise NationalGasRestError(
            "INVALID_VALUE", "value must not have surrounding whitespace"
        )
    if len(raw) > MAX_VALUE_CHARS or _DECIMAL_RE.fullmatch(raw) is None:
        raise NationalGasRestError("INVALID_VALUE", "value is not a bounded decimal string")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:  # pragma: no cover - regex already excludes this
        raise NationalGasRestError("INVALID_VALUE", "value is not a decimal") from exc
    if not number.is_finite():  # pragma: no cover - regex already excludes this
        raise NationalGasRestError("INVALID_VALUE", "NaN and infinity are not accepted")
    return raw, number, False


def _parse_quality(raw: object) -> tuple[QualityFlag, str]:
    if not isinstance(raw, str):
        raise NationalGasRestError(
            "MALFORMED_QUALITY", "qualityIndicator must be text"
        )
    if raw == "":
        return QualityFlag.UNKNOWN, raw
    if raw == "A":
        return QualityFlag.AMENDED, raw
    if raw == "S":
        return QualityFlag.SUBSTITUTED, raw
    raise NationalGasRestError(
        "UNKNOWN_QUALITY", "qualityIndicator is not blank, A, or S"
    )


def _parse_substituted(raw: object) -> tuple[str, bool | None]:
    if not isinstance(raw, str):
        raise NationalGasRestError("MALFORMED_SUBSTITUTED", "substituted must be text")
    if raw == "":
        return raw, None
    if raw == "Y":
        return raw, True
    if raw == "N":
        return raw, False
    raise NationalGasRestError(
        "MALFORMED_SUBSTITUTED", "substituted must be blank, Y, or N"
    )


def _validate_unit_fields(container: dict[object, object]) -> None:
    for field in _UNIT_FIELDS:
        if field not in container:
            continue
        unit = container[field]
        if not isinstance(unit, str) or unit != UNIT:
            raise NationalGasRestError(
                "UNKNOWN_UNIT", "publication unit is not the approved mscm identity"
            )


def _decode_payload(payload: bytes | str) -> tuple[str, bytes]:
    if isinstance(payload, bytes):
        raw = payload
        if len(raw) > MAX_RESPONSE_BYTES:
            raise NationalGasRestError(
                "RESPONSE_TOO_LARGE", "REST response exceeds the 2 MiB limit"
            )
        try:
            return raw.decode("utf-8"), raw
        except UnicodeDecodeError as exc:
            raise NationalGasRestError(
                "MALFORMED_ENCODING", "REST response is not UTF-8"
            ) from exc
    if isinstance(payload, str):
        try:
            raw = payload.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise NationalGasRestError(
                "MALFORMED_ENCODING", "REST response is not UTF-8"
            ) from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise NationalGasRestError(
                "RESPONSE_TOO_LARGE", "REST response exceeds the 2 MiB limit"
            )
        return payload, raw
    raise NationalGasRestError("INVALID_PAYLOAD", "REST payload must be bytes or text")


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise NationalGasRestError("DUPLICATE_JSON_KEY", "JSON object repeated a key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise NationalGasRestError(
        "MALFORMED_JSON", f"JSON constant {value!r} is not accepted"
    )


def _require_aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise NationalGasRestError("INVALID_TIMESTAMP", f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise NationalGasRestError("NAIVE_TIMESTAMP", f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _is_retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _sha256_json(parts: list[str]) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_trusted_response(response: httpx.Response) -> None:
    if response.history:
        raise NationalGasRestError(
            "REDIRECT_REFUSED", "official endpoint attempted a redirect"
        )
    request_url = response.request.url
    if (
        response.request.method != "POST"
        or request_url.scheme != "https"
        or (request_url.host or "").lower() != API_HOST
        or request_url.port not in (None, 443)
        or request_url.path != API_PATH
        or str(request_url) != API_URL
        or str(response.url) != API_URL
    ):
        raise NationalGasRestError(
            "UNTRUSTED_RESPONSE_ORIGIN", "response did not come from the fixed official origin"
        )
    if any(header in response.request.headers for header in _SENSITIVE_REQUEST_HEADERS):
        raise NationalGasRestError(
            "UNTRUSTED_REQUEST_HEADERS", "request carried an authentication or cookie header"
        )


def _read_bounded(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError as exc:
            raise NationalGasRestError(
                "MALFORMED_CONTENT_LENGTH", "response Content-Length is not an integer"
            ) from exc
        if declared_size < 0:
            raise NationalGasRestError(
                "MALFORMED_CONTENT_LENGTH", "response Content-Length is negative"
            )
        if declared_size > MAX_RESPONSE_BYTES:
            raise NationalGasRestError(
                "RESPONSE_TOO_LARGE", "declared response size exceeds the 2 MiB limit"
            )

    body = bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) > MAX_RESPONSE_BYTES:
            raise NationalGasRestError(
                "RESPONSE_TOO_LARGE", "REST response exceeds the 2 MiB limit"
            )
    return bytes(body)
