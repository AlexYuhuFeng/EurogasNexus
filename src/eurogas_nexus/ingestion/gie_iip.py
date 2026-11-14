"""GIE Inside Information Platform (IIP): gas UMMs from the platform's API.

GIE runs IIP for storage (SSO) and LNG (LSO) operators. Its API
(``https://iip.gie.eu/api``, documented to registered users) returns the REMIT urgent market
messages as JSON, newest submissions first, 50 per page, each message with its earlier
versions under ``prev``. Registration is mandatory and the personal key goes in the ``x-key``
header; GIE's AGSI/ALSI key is accepted (checked live 2026-11-14). Terms (iip.gie.eu,
"API data usage"): the data may be used or repackaged in any way provided GIE is clearly
indicated as the source (the register in ``domain/observations/remit_platforms``).

Only unavailability reports are collected (``unavailabilityOfGasFacilitiesReport``: storage,
injection, withdrawal, compressor, regasification); "other market information" carries no
capacity. Transmission operators do not publish on IIP.

The API's ``messageId`` ends in ``_<version>`` (``25041521X000000001120V182_035``, earlier
versions ``..._034``...), so the message is the part before it and the version the number.
``published``, ``from`` and ``to`` are UTC without an offset: each equals the
``publicationDateTime``, ``eventStart`` and ``eventStop`` (with ``Z``) of the ACER XML the
record embeds (150 of 150 checked). Records are mapped to ACER field names and read by the
importer's own normaliser (``domain/observations/remit_umm.parse_umm_export``).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

IIP_API_URL = "https://iip.gie.eu/api"
#: Message types with capacity; other market information is not an outage.
UNAVAILABILITY_REPORT = "unavailabilityOfGasFacilitiesReport"
#: Reporting entity type to the REMIT model's asset type.
ASSET_TYPE_BY_ENTITY = {"SSO": "storage", "LSO": "lng", "TSO": "transmission"}
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class IipError(RuntimeError):
    """A stable, operator-safe failure (never carries the key or a response body)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class IipRead:
    """The records read and how the read ended."""

    records: list[dict[str, Any]] = field(default_factory=list)
    pages: int = 0
    total: int | None = None
    stop: str = ""


def _submitted(record: Mapping[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(record.get("submitted") or "")).replace(tzinfo=UTC)
    except ValueError:
        return None


def fetch_iip_messages(
    get_page: Callable[[int], Mapping[str, Any]],
    *,
    since: datetime,
    max_pages: int,
    pause_seconds: float = 3.0,
    sleep: Callable[[float], None] = time.sleep,
) -> IipRead:
    """Pages from the newest until a page holds nothing submitted at or after ``since``.

    The API orders by submission only roughly (live: not strictly), so a page counts as
    past the window only when its newest submission is older than ``since``. Raises
    ``IipError('iip_read_bound_reached')`` when ``max_pages`` pages were read and the
    window was not exhausted: a partial read is not passed off as complete.
    """

    read = IipRead()
    for page in range(1, max_pages + 1):
        if page > 1:
            sleep(pause_seconds)
        payload = get_page(page)
        data = payload.get("data")
        meta = payload.get("meta") or {}
        if not isinstance(data, list):
            raise IipError("iip_malformed_response", "the response has no data list")
        read.pages = page
        read.total = meta.get("total") if isinstance(meta.get("total"), int) else read.total
        stamps = [stamp for stamp in map(_submitted, data) if stamp is not None]
        read.records.extend(record for record in data if isinstance(record, Mapping))
        if not data or (stamps and max(stamps) < since):
            read.stop = "window_exhausted"
            return read
        last_page = meta.get("last_page")
        if isinstance(last_page, int) and page >= last_page:
            read.stop = "last_page"
            return read
    raise IipError(
        "iip_read_bound_reached",
        f"{max_pages} pages read and the window is not exhausted; raise --max-pages",
    )


def _split_message_id(message_id: str) -> tuple[str, int]:
    base, separator, suffix = message_id.rpartition("_")
    if separator and suffix.isdigit() and base:
        return base, int(suffix)
    return message_id, 1


def _codes(items: Any) -> str:
    if isinstance(items, list):
        return ",".join(
            str(item.get("code") or item.get("name") or "")
            for item in items
            if isinstance(item, Mapping)
        )
    return str(items or "")


def _capacity(record: Mapping[str, Any], name: str) -> tuple[Any, str]:
    value = record.get(name)
    if isinstance(value, Mapping):
        return value.get("capacity"), str(value.get("unit") or "")
    return None, ""


def acer_fields(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """One IIP record as the ACER field names the importer reads; None if not an outage."""

    message = record.get("message") or {}
    if not isinstance(message, Mapping) or message.get("reportType") != UNAVAILABILITY_REPORT:
        return None
    message_id, version = _split_message_id(str(message.get("messageId") or "").strip())
    if not message_id:
        return None
    unavailable, unit = _capacity(record, "unavailable")
    available, available_unit = _capacity(record, "available")
    technical, technical_unit = _capacity(record, "technical")
    entity = record.get("reportingEntity") or {}
    entity_type = str(entity.get("type") or "") if isinstance(entity, Mapping) else ""
    asset = record.get("asset") or {}
    participants = record.get("marketParticipant") or []
    return {
        "messageId": message_id,
        "version": version,
        "publicationDateTime": record.get("published"),
        "eventStatus": record.get("status"),
        "unavailabilityType": message.get("unavailabilityType"),
        "eventStart": record.get("from"),
        "eventStop": record.get("to"),
        "affectedAssetName": asset.get("name") if isinstance(asset, Mapping) else None,
        "affectedAssetEic": asset.get("code") if isinstance(asset, Mapping) else None,
        "affectedAssetType": ASSET_TYPE_BY_ENTITY.get(entity_type, entity_type or "other"),
        "balancingZone": _codes(record.get("balancingZone")),
        "direction": record.get("direction"),
        "unitMeasure": unit or available_unit or technical_unit,
        "technicalCapacity": technical,
        "availableCapacity": available,
        "unavailableCapacity": unavailable,
        "unavailabilityReason": record.get("unavailabilityReason") or message.get("messageType"),
        "marketParticipant": ", ".join(
            str(item.get("name") or item.get("code") or "")
            for item in participants
            if isinstance(item, Mapping)
        ),
        "remarks": record.get("remarks"),
    }


def acer_messages(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every version of every unavailability message in the records (``prev`` included),
    once per message and version."""

    found: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        for version in (record, *(record.get("prev") or [])):
            if not isinstance(version, Mapping):
                continue
            fields = acer_fields(version)
            if fields is not None:
                found.setdefault((fields["messageId"], fields["version"]), fields)
    return list(found.values())


def http_page_getter(api_key: str, *, timeout: float = 30.0, max_attempts: int = 3,
                     sleep: Callable[[float], None] = time.sleep):
    """A bounded page reader for the fixed official URL; the key goes only in ``x-key``."""

    import httpx

    from eurogas_nexus.core.outbound_http import client_options

    client = httpx.Client(
        timeout=timeout, follow_redirects=False, trust_env=False, **client_options(IIP_API_URL)
    )

    def get_page(page: int) -> Mapping[str, Any]:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.get(
                    IIP_API_URL,
                    params={"page": str(page)},
                    headers={"x-key": api_key, "Accept": "application/json"},
                )
            except httpx.TimeoutException:
                if attempt == max_attempts:
                    raise IipError("iip_timeout", "the platform did not answer in time") from None
                sleep(10.0 * attempt)
                continue
            if response.status_code in RETRYABLE_STATUSES and attempt < max_attempts:
                retry_after = response.headers.get("retry-after", "")
                sleep(float(retry_after) if retry_after.isdigit() else 30.0 * attempt)
                continue
            if response.status_code != 200:
                raise IipError("iip_http_status", f"HTTP {response.status_code}")
            if len(response.content) > MAX_RESPONSE_BYTES:
                raise IipError("iip_response_too_large", "page larger than the bound")
            try:
                payload = json.loads(response.content)
            except ValueError:
                raise IipError("iip_malformed_response", "the response is not JSON") from None
            if not isinstance(payload, Mapping):
                raise IipError("iip_malformed_response", "the response is not an object")
            if "data" not in payload and payload.get("statusCode"):
                # The platform relays an upstream refusal (live: a 429 rate limit) as a 200
                # with an error envelope; wait and retry like a 429.
                if attempt < max_attempts:
                    sleep(60.0 * attempt)
                    continue
                raise IipError("iip_upstream_refused", f"upstream {payload.get('statusCode')}")
            return payload
        raise IipError("iip_unreachable", "no answer after retries")

    get_page.close = client.close  # type: ignore[attr-defined]
    return get_page
