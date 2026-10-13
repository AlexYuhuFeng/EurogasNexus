"""Bounded ENTSOG public API reads; no database writes or source authority.

Official TP API manual v3.0 (2025-10-01) describes limit and sorting, and
shows offset/count/total metadata. Bounded public probes on 2026-10-12 verified
offset traversal for these three endpoints. They also found that the documented
``sorting=id`` is ignored, whereas ``sort=id`` is echoed as ``meta.sort=id``.
``total`` equalled the page count even when further pages existed. Consequently
this transport never uses total as a grand total and requires the sort echo.

Only a short/empty page establishes traversal exhaustion. ``complete`` means
that this query's offset traversal exhausted, not that a consistent snapshot or
complete history was obtained: ENTSOG supplies no snapshot token. Inserts or
deletions during traversal can still cause undetectable omissions. Overlapping
provider IDs are refused. Provider IDs remain distinct even if a downstream
normalizer maps several of them to the same canonical key.

Each page retains exact decompressed response bytes, their SHA256 and a receipt
captured after the body arrived. Archive helpers return values for the existing
raw archive repository; they do not archive anything themselves. The shared
public ingestor consumes these pages through the separate persistence module.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx

ENTSOG_BASE_URL = "https://transparency.entsog.eu/api/v1"
ENTSOG_DATASETS = frozenset({"operationaldatas", "connectionpoints", "operatorpointdirections"})
# Application safety ceilings, not claimed provider maxima.
ENTSOG_MAX_PAGE_SIZE = 1000
ENTSOG_HARD_MAX_PAGES = 50
ENTSOG_HARD_MAX_RECORDS = 50_000
ENTSOG_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_FILTERS = frozenset(
    {
        "indicator",
        "from",
        "to",
        "periodType",
        "pointDirection",
        "operatorKey",
        "pointKey",
        "directionKey",
        "timeZone",
        "extended",
        "hasData",
    }
)


class EntsogTransportError(RuntimeError):
    """Stable classification; never interpolate an untrusted provider body."""

    code = "entsog_transport_error"

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        # Successfully validated earlier pages remain auditable on a later failure.
        # This is never a usable successful query or a complete snapshot.
        self.validated_prefix_result: EntsogFetchResult | None = None


class EntsogHttpError(EntsogTransportError):
    code = "entsog_http_error"


class EntsogRateLimitedError(EntsogTransportError):
    code = "entsog_rate_limited"


class EntsogTimeoutError(EntsogTransportError):
    code = "entsog_timeout"


class EntsogRedirectRefusedError(EntsogTransportError):
    code = "entsog_redirect_refused"


class EntsogMalformedResponseError(EntsogTransportError):
    code = "entsog_malformed_response"


class EntsogPaginationError(EntsogTransportError):
    code = "entsog_pagination_error"


class EntsogProductMismatchError(EntsogTransportError):
    code = "entsog_product_mismatch"


class EntsogResponseTooLargeError(EntsogTransportError):
    code = "entsog_response_too_large"


class EntsogTruncationError(EntsogTransportError):
    code = "entsog_truncated"


class EntsogWindowError(EntsogTransportError):
    code = "entsog_window_invalid"


class EntsogWindowRequiredError(EntsogWindowError):
    code = "entsog_window_required"


def validate_entsog_window(from_date: str | None, to_date: str | None) -> dict[str, str]:
    """Require an operator-chosen date window of at most 31 days.

    The month-sized ceiling is an application bound, not a provider restriction.
    Dates are provider query dates, not a claim of UTC gas-day boundaries.
    """
    if not from_date or not to_date:
        raise EntsogWindowRequiredError("ENTSOG observations require explicit from/to dates.")
    try:
        start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
        if start.isoformat() != from_date or end.isoformat() != to_date:
            raise ValueError
        if not 0 < (end - start).days <= 31:
            raise ValueError
    except (TypeError, ValueError):
        raise EntsogWindowError(
            "ENTSOG requires YYYY-MM-DD dates with 0 < window <= 31 days."
        ) from None
    return {"from": from_date, "to": to_date}


def _decode_json(raw_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise EntsogMalformedResponseError("ENTSOG response is not valid UTF-8 JSON.") from None
    if not isinstance(payload, dict):
        raise EntsogMalformedResponseError("ENTSOG response envelope must be an object.")
    return payload


@dataclass(frozen=True)
class EntsogPage:
    dataset: str
    offset: int
    requested_limit: int
    record_count: int
    provider_total: int
    request_url: str
    received_at_utc: datetime
    raw_body: bytes = field(repr=False)

    @property
    def payload(self) -> dict[str, Any]:
        """Fresh decoded copy: normalization cannot mutate the archive bytes."""
        return _decode_json(self.raw_body)

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.raw_body).hexdigest()

    @property
    def source_reference(self) -> str:
        query_hash = hashlib.sha256(self.request_url.encode("utf-8")).hexdigest()
        return (
            f"entsog-{self.dataset};offset={self.offset};limit={self.requested_limit};"
            f"request={query_hash}"
        )

    def raw_archive_values(self) -> dict[str, Any]:
        """Arguments for raw_archive.archive_raw_payload, except session/id.

        The digest covers payload_text encoded as UTF-8, including the original
        spacing. Do not reserialize payload_json and claim that digest matches it.
        """
        return {
            "source_system": "ENTSOG",
            "dataset": self.dataset,
            "source_reference": self.source_reference,
            "payload_text": self.raw_body.decode("utf-8"),
            "payload_json": self.payload,
            "payload_sha256": self.payload_sha256,
            "record_count": self.record_count,
            "received_at_utc": self.received_at_utc,
        }

    def lineage_metadata(self, *, archive_id: str) -> dict[str, Any]:
        """Stamp only after the caller successfully archives this exact page."""
        if not isinstance(archive_id, str) or not archive_id.strip():
            raise ValueError("A persisted raw archive identity is required.")
        return {
            "archive_id": archive_id,
            "payload_sha256": self.payload_sha256,
            "source_dataset": self.dataset,
            "source_reference": self.source_reference,
            "source_offset": self.offset,
            "source_limit": self.requested_limit,
            "source_request_url": self.request_url,
            "source_receipt_at_utc": self.received_at_utc.isoformat(),
        }


@dataclass(frozen=True)
class EntsogFetchResult:
    dataset: str
    pages: tuple[EntsogPage, ...]
    complete: bool
    stop_reason: str
    budget_records: int
    budget_pages: int
    # An exhausted offset sequence is not evidence of an atomic provider snapshot.
    snapshot_consistent: bool = False
    completeness_basis: str = "offset_exhaustion_not_snapshot"

    @property
    def record_count(self) -> int:
        return sum(page.record_count for page in self.pages)

    @property
    def received_at_utc(self) -> datetime:
        """Conservative aggregate receipt: the latest response, never run start."""
        return max(page.received_at_utc for page in self.pages)

    @property
    def source_reference(self) -> str:
        return (
            f"entsog-{self.dataset};pages={len(self.pages)};records={self.record_count};"
            f"complete={str(self.complete).lower()};stop={self.stop_reason};snapshot=false"
        )

    def require_complete(self) -> None:
        if not self.complete:
            raise EntsogTruncationError("ENTSOG query did not exhaust within the fetch budget.")


def _positive_integer(value: int, maximum: int, name: str) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}.")


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    # Numeric Retry-After only; malformed/date/non-finite values use bounded backoff.
    try:
        delay = float(response.headers.get("Retry-After", ""))
    except ValueError:
        delay = float(2**attempt)
    if not math.isfinite(delay) or delay < 0:
        delay = float(2**attempt)
    return min(delay, 30.0)


def _read_response(
    client: httpx.Client,
    url: str,
    params: Mapping[str, str],
    *,
    attempts: int,
    timeout_seconds: float,
    sleep: Callable[[float], None],
    clock: Callable[[], datetime],
) -> tuple[bytes, datetime, str]:
    for attempt in range(attempts):
        retry_delay = float(2**attempt)
        try:
            request = client.build_request("GET", url, params=params, timeout=timeout_seconds)
            response = client.send(request, stream=True, follow_redirects=False)
            try:
                status = response.status_code
                if 300 <= status < 400:
                    raise EntsogRedirectRefusedError(
                        "ENTSOG redirects are refused.", status_code=status
                    )
                if status != 200:
                    error_type = EntsogRateLimitedError if status == 429 else EntsogHttpError
                    if status not in _RETRY_STATUS or attempt == attempts - 1:
                        raise error_type(
                            "ENTSOG returned an unsuccessful HTTP status.", status_code=status
                        )
                    retry_delay = _retry_delay(response, attempt)
                else:
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > ENTSOG_MAX_RESPONSE_BYTES:
                            raise EntsogResponseTooLargeError(
                                "ENTSOG response exceeds the application byte ceiling."
                            )
                        chunks.append(chunk)
                    received_at = clock()
                    if received_at.tzinfo is None or received_at.utcoffset() is None:
                        raise ValueError("The receipt clock must return a timezone-aware instant.")
                    return b"".join(chunks), received_at.astimezone(UTC), str(request.url)
            finally:
                response.close()
        except httpx.TimeoutException:
            if attempt == attempts - 1:
                raise EntsogTimeoutError("ENTSOG request timed out.") from None
        except httpx.HTTPError:
            if attempt == attempts - 1:
                raise EntsogTransportError("ENTSOG HTTP transport failed.") from None
        sleep(min(retry_delay, 30.0))
    raise AssertionError("Unreachable retry state.")


def _parse_page(
    dataset: str,
    raw_body: bytes,
    received_at: datetime,
    request_url: str,
    *,
    offset: int,
    limit: int,
    seen_ids: set[str],
    expected_indicators: frozenset[str],
) -> EntsogPage:
    payload = _decode_json(raw_body)
    meta = payload.get("meta")
    rows = payload.get(dataset)
    if "error" in payload or "message" in payload:
        raise EntsogMalformedResponseError("ENTSOG returned a provider error envelope.")
    if not isinstance(meta, dict) or not isinstance(rows, list):
        raise EntsogMalformedResponseError("ENTSOG metadata and dataset array are required.")
    for key in ("limit", "offset", "count", "total"):
        value = meta.get(key)
        if type(value) is not int or value < 0:
            raise EntsogMalformedResponseError(
                "ENTSOG pagination metadata must be nonnegative integers."
            )
    if meta["limit"] != limit or meta["offset"] != offset:
        raise EntsogPaginationError("ENTSOG did not echo the requested limit and offset.")
    if meta["count"] != len(rows) or len(rows) > limit:
        raise EntsogPaginationError("ENTSOG record count disagrees with the response or request.")
    if meta.get("sort") != "id":
        raise EntsogPaginationError("ENTSOG did not acknowledge ascending provider-id sorting.")
    page_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise EntsogMalformedResponseError("ENTSOG records require a nonempty provider id.")
        if expected_indicators and (
            not isinstance(row.get("indicator"), str) or row["indicator"] not in expected_indicators
        ):
            raise EntsogProductMismatchError(
                "ENTSOG returned an indicator outside the requested set."
            )
        if row["id"] in page_ids or row["id"] in seen_ids:
            raise EntsogPaginationError("ENTSOG provider ids overlap within or across pages.")
        page_ids.add(row["id"])
    seen_ids.update(page_ids)
    return EntsogPage(
        dataset, offset, limit, len(rows), meta["total"], request_url, received_at, raw_body
    )


def fetch_entsog_dataset(
    client: httpx.Client,
    dataset: str,
    *,
    filters: Mapping[str, str] | None = None,
    page_size: int = 100,
    max_records: int = 1000,
    max_pages: int = 10,
    attempts: int = 3,
    timeout_seconds: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EntsogFetchResult:
    """Read one bounded query, preserving filters and exact raw page receipts.

    No limit=-1 and no lookahead outside the record/page budget. At a full budget
    boundary, exhaustion is unknown even if that happened to be the last record.
    Positive offset is always explicit; changing the final limit is safe because
    offsets address records, unlike page-number protocols.
    """
    if dataset not in ENTSOG_DATASETS:
        raise ValueError("Unsupported ENTSOG dataset.")
    _positive_integer(page_size, ENTSOG_MAX_PAGE_SIZE, "page_size")
    _positive_integer(max_records, ENTSOG_HARD_MAX_RECORDS, "max_records")
    _positive_integer(max_pages, ENTSOG_HARD_MAX_PAGES, "max_pages")
    _positive_integer(attempts, 3, "attempts")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 60
    ):
        raise ValueError("timeout_seconds must be finite and between 0 and 60 seconds.")
    query = dict(filters or {})
    if any(
        key not in _FILTERS or not isinstance(value, str) or not value
        for key, value in query.items()
    ):
        raise ValueError("Unsupported ENTSOG filter or nonempty-string filter value required.")
    expected_indicators = (
        frozenset(query["indicator"].split(",")) if "indicator" in query else frozenset()
    )
    if "" in expected_indicators:
        raise ValueError("ENTSOG indicator filters must contain nonempty comma-separated values.")
    pages: list[EntsogPage] = []
    seen_ids: set[str] = set()
    offset = 0
    complete = False
    stop_reason = "operator_page_budget"
    for _ in range(max_pages):
        limit = min(page_size, max_records - offset)
        params = {**query, "limit": str(limit), "offset": str(offset), "sort": "id"}
        try:
            raw_body, received_at, request_url = _read_response(
                client,
                f"{ENTSOG_BASE_URL}/{dataset}",
                params,
                attempts=attempts,
                timeout_seconds=timeout_seconds,
                sleep=sleep,
                clock=clock,
            )
            page = _parse_page(
                dataset,
                raw_body,
                received_at,
                request_url,
                offset=offset,
                limit=limit,
                seen_ids=seen_ids,
                expected_indicators=expected_indicators,
            )
        except EntsogTransportError as exc:
            if pages:
                exc.validated_prefix_result = EntsogFetchResult(
                    dataset, tuple(pages), False, "transport_failed", max_records, max_pages
                )
            raise
        pages.append(page)
        offset += page.record_count
        if page.record_count < limit:
            complete = True
            stop_reason = "provider_offset_exhausted"
            break
        if offset == max_records:
            stop_reason = "operator_record_budget"
            break
    return EntsogFetchResult(dataset, tuple(pages), complete, stop_reason, max_records, max_pages)
