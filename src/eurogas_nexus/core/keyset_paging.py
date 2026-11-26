"""One pagination style for list reads: keyset pages with a visible limit (backend audit A4c/A5).

The style is the audit retrieval's (``application/audit_paging.py``, #59), made general:

- rows are ordered newest first by ``(timestamp, id)``, so tied timestamps have a stable order;
- the walk is anchored to a high-water mark fixed on the first page (``to_utc``, else the
  newest row of the first page: a stored row may carry a future timestamp, so "now" would
  hide it), so rows written while a caller pages never shift it;
- the continuation cursor carries the anchor, the last ``(timestamp, id)`` returned and a
  digest of the filters it was issued for; a cursor used with other filters is refused;
- every page states ``meta.continuation = {anchor_utc, limit, returned, has_more, cursor}``:
  a list is never cut short without saying so.

A caller that needs every row of a range asks for the range (``from_utc``/``to_utc``) and
follows ``cursor`` until ``has_more`` is false. The cursor is position, not authority: every
page re-applies the caller's entitlement.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

CURSOR_VERSION = 1
DEFAULT_PAGE_SIZE = 1000
MAX_PAGE_SIZE = 10_000


class PageCursorError(ValueError):
    """A cursor or window bound the server refuses, with a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class KeysetPosition:
    anchor: datetime
    last_ts: datetime
    last_id: str


def _utc(value: datetime) -> datetime:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC)


def filters_digest(filters: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {key: "" if value is None else str(value) for key, value in filters.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def parse_bound(value: str | None, name: str) -> datetime | None:
    """A UTC window bound from an ISO-8601 instant with an explicit offset, or None."""

    if value is None or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise PageCursorError("page_window_invalid", f"{name} is not an ISO-8601 instant") from exc
    if parsed.tzinfo is None:
        raise PageCursorError(
            "page_window_timezone_required", f"{name} needs an explicit UTC offset"
        )
    return parsed.astimezone(UTC)


def encode_cursor(
    *, anchor: datetime, last_ts: datetime, last_id: str, filters: Mapping[str, Any]
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "a": _utc(anchor).isoformat(),
        "t": _utc(last_ts).isoformat(),
        "i": last_id,
        "f": filters_digest(filters),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, filters: Mapping[str, Any]) -> KeysetPosition:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("v") != CURSOR_VERSION:
            raise ValueError("version")
        position = KeysetPosition(
            anchor=_utc(datetime.fromisoformat(payload["a"])),
            last_ts=_utc(datetime.fromisoformat(payload["t"])),
            last_id=str(payload["i"]),
        )
        digest = str(payload["f"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PageCursorError(
            "page_cursor_invalid", "the continuation cursor is not valid"
        ) from exc
    if digest != filters_digest(filters):
        raise PageCursorError(
            "page_cursor_filter_mismatch",
            "the continuation cursor was issued for other filters; start from the first page",
        )
    return position


@dataclass(frozen=True)
class PageRequest:
    """What one page asks for: its window, its position and its size."""

    limit: int
    #: None on a first page without ``to_utc``: no upper bound; the cursor fixes one.
    anchor: datetime | None
    from_utc: datetime | None
    position: KeysetPosition | None
    filters: Mapping[str, Any]


def page_request(
    *,
    limit: int,
    cursor: str | None,
    from_utc: str | None,
    to_utc: str | None,
    filters: Mapping[str, Any],
) -> PageRequest:
    """Parse a page's parameters; :class:`PageCursorError` on a bad bound or cursor."""

    every = {**filters, "from_utc": from_utc or "", "to_utc": to_utc or ""}
    start = parse_bound(from_utc, "from_utc")
    end = parse_bound(to_utc, "to_utc")
    position = decode_cursor(cursor, every) if cursor else None
    anchor = position.anchor if position else end
    return PageRequest(
        limit=max(1, min(int(limit), MAX_PAGE_SIZE)),
        anchor=anchor,
        from_utc=start,
        position=position,
        filters=every,
    )


def continuation(
    request: PageRequest,
    *,
    returned: int,
    has_more: bool,
    last: tuple[datetime, str] | None,
    first: datetime | None = None,
) -> dict[str, Any]:
    """``meta.continuation`` for a page (``first``: the page's newest timestamp)."""

    anchor = request.anchor or (_utc(first) if first is not None else None)
    cursor = (
        encode_cursor(
            anchor=anchor or _utc(last[0]), last_ts=last[0], last_id=last[1],
            filters=request.filters,
        )
        if has_more and last is not None
        else None
    )
    return {
        "anchor_utc": anchor.isoformat() if anchor else None,
        "limit": request.limit,
        "returned": returned,
        "has_more": has_more,
        "cursor": cursor,
    }


def keyset_query(query: Any, request: PageRequest, *, ts_column: Any, id_column: Any) -> Any:
    """Apply the window, the position and the order to a SQLAlchemy query (one past the page)."""

    from sqlalchemy import and_, or_

    bind = query.session.get_bind() if getattr(query, "session", None) is not None else None
    naive = bind is not None and bind.dialect.name == "sqlite"

    def bound(moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if naive else moment

    if request.anchor is not None:
        query = query.filter(ts_column <= bound(request.anchor))
    if request.from_utc is not None:
        query = query.filter(ts_column >= bound(request.from_utc))
    if request.position is not None:
        last_ts = bound(request.position.last_ts)
        last_id = request.position.last_id
        query = query.filter(
            or_(ts_column < last_ts, and_(ts_column == last_ts, id_column < last_id))
        )
    return query.order_by(ts_column.desc(), id_column.desc()).limit(request.limit + 1)


def page_rows(
    rows: Sequence[Mapping[str, Any]],
    request: PageRequest,
    *,
    ts_of: Callable[[Mapping[str, Any]], datetime | None],
    id_of: Callable[[Mapping[str, Any]], str],
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """The same page over rows already read (an as-of reconstruction); returns rows, meta."""

    def key(row: Mapping[str, Any]) -> tuple[datetime, str]:
        moment = ts_of(row)
        return (_utc(moment) if moment else datetime.min.replace(tzinfo=UTC), id_of(row))

    kept = []
    for row in rows:
        moment, ident = key(row)
        if request.anchor is not None and moment > request.anchor:
            continue
        if request.from_utc is not None and moment < request.from_utc:
            continue
        if request.position is not None and (moment, ident) >= (
            request.position.last_ts,
            request.position.last_id,
        ):
            continue
        kept.append(row)
    kept.sort(key=key, reverse=True)
    page = kept[: request.limit]
    has_more = len(kept) > request.limit
    meta = continuation(
        request, returned=len(page), has_more=has_more,
        last=key(page[-1]) if page else None, first=key(page[0])[0] if page else None,
    )
    return page, meta


def iso_ts(row: Mapping[str, Any], key: str = "observed_at_utc") -> datetime | None:
    value = row.get(key)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
