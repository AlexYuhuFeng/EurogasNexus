"""Reads behind ``GET /api/news`` and ``GET /api/news/{item_id}`` (NEWS-1).

Items are public-source data, so every caller with read access sees every item. What an item
means for the book is not: matches to contracts, cargoes and nominations are computed only for
a caller who may read the portfolio, and only in the books that caller may see
(``security.portfolio_scope``). The list puts the items that touch the caller's book first
(``order=relevance``, the default), then the newest; ``order=time`` is newest first.

新闻读取：条目为公开来源数据；与账簿的关联仅对有组合读取权限的调用者、在其可见账簿内计算。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.news_relevance import firm_exposures, matches, relevance_score
from eurogas_nexus.domain.news.sources import NEWS_SOURCES_BY_ID, registry_rows
from eurogas_nexus.domain.news.tagging import EVENT_TYPES

MAX_LIMIT = 200
ORDERS = ("relevance", "time")
#: How many stored items a list read considers before filtering by relevance.
SCAN = 2_000


class NewsQueryError(ValueError):
    """A filter that cannot be applied (``code`` and ``message`` for a 422)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NewsFilters:
    hub: str | None = None
    country: str | None = None
    event_type: str | None = None
    source_id: str | None = None
    since: datetime | None = None
    mine: bool = False
    order: str = "relevance"
    limit: int = 50


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    moment = _aware(value)
    return moment.isoformat() if moment else None


def parse_filters(*, hub: str | None, country: str | None, event_type: str | None,
                  source: str | None, since: str | None, mine: bool, order: str,
                  limit: int) -> NewsFilters:
    """Validated filters, or :class:`NewsQueryError`."""

    if event_type and event_type not in EVENT_TYPES:
        raise NewsQueryError("type_unknown", f"type must be one of {', '.join(EVENT_TYPES)}")
    if source and source not in NEWS_SOURCES_BY_ID:
        raise NewsQueryError("source_unknown", f"source {source!r} is not in the registry")
    if order not in ORDERS:
        raise NewsQueryError("order_unknown", "order must be relevance or time")
    moment = None
    if since:
        try:
            moment = _aware(datetime.fromisoformat(since.replace("Z", "+00:00")))
        except ValueError as exc:
            raise NewsQueryError("since_invalid", "since must be an ISO 8601 instant") from exc
    return NewsFilters(
        hub=hub.strip().upper() if hub else None,
        country=country.strip().upper() if country else None,
        event_type=event_type or None,
        source_id=source or None,
        since=moment,
        mine=mine,
        order=order,
        limit=max(1, min(MAX_LIMIT, limit)),
    )


def item_dict(row) -> dict[str, Any]:
    """A stored item as the API returns it."""

    source = NEWS_SOURCES_BY_ID.get(row.source_id)
    return {
        "item_id": row.item_id,
        "source_id": row.source_id,
        "source_title": source.title if source else row.source_id,
        "publisher": row.publisher,
        "url": row.url,
        "title": row.title,
        "summary": row.summary or "",
        "language": row.language,
        "published_at_utc": _iso(row.published_at_utc),
        "retrieved_at_utc": _iso(row.retrieved_at_utc),
        "content_sha256": row.content_sha256,
        "licence_note": row.licence_note,
        "event_types": list(row.event_types or []),
        "entities": list(row.entities or []),
        "hubs": list(row.hubs or []),
        "countries": list(row.countries or []),
        "capacity_change": bool(row.capacity_change),
        "linked_event_key": row.linked_event_key,
        "revision": int(row.revision or 1),
        "first_seen_at_utc": _iso(row.first_seen_at_utc),
    }


def _summarise_matches(found: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "score": relevance_score(found),
        "matches": len(found),
        "roles": sorted({m["role"] for m in found}),
        "reasons": [m["reason"] for m in found[:3]],
    }


def list_items(session, filters: NewsFilters, *, book_allowed: bool,
               visible_books: set[str] | None, now: datetime) -> list[dict[str, Any]]:
    """The items the filters select, each with what it touches in the caller's book."""

    from eurogas_nexus.db.models import NewsItemRecord

    query = session.query(NewsItemRecord)
    if filters.source_id:
        query = query.filter(NewsItemRecord.source_id == filters.source_id)
    if filters.since is not None:
        naive = session.get_bind().dialect.name == "sqlite"
        since = filters.since.replace(tzinfo=None) if naive else filters.since
        query = query.filter(NewsItemRecord.first_seen_at_utc >= since)
    rows = query.order_by(NewsItemRecord.first_seen_at_utc.desc()).limit(SCAN).all()
    exposures = firm_exposures(session, now=now) if book_allowed else []
    out = []
    for row in rows:
        if filters.hub and filters.hub not in (row.hubs or []):
            continue
        if filters.country and filters.country not in (row.countries or []):
            continue
        if filters.event_type and filters.event_type not in (row.event_types or []):
            continue
        item = item_dict(row)
        found = matches(item, exposures, visible_books) if book_allowed else []
        if filters.mine and not found:
            continue
        item["relevance"] = _summarise_matches(found)
        item["book_hidden"] = not book_allowed
        out.append(item)

    def newest(item: dict[str, Any]) -> str:
        return item["published_at_utc"] or item["first_seen_at_utc"] or ""

    out.sort(key=newest, reverse=True)
    if filters.order == "relevance":
        out.sort(key=lambda item: -item["relevance"]["score"])
    return out[: filters.limit]


def item_detail(session, item_id: str, *, book_allowed: bool,
                visible_books: set[str] | None, now: datetime) -> dict[str, Any] | None:
    """One item with its source and terms, the book it touches, related items and the rule
    note with its citations; ``None`` when there is no such item."""

    from eurogas_nexus.application.news_note import assemble, build_evidence, related_items
    from eurogas_nexus.db.models import NewsItemRecord

    row = session.get(NewsItemRecord, item_id)
    if row is None:
        return None
    item = item_dict(row)
    exposures = firm_exposures(session, now=now) if book_allowed else []
    found = matches(item, exposures, visible_books) if book_allowed else []
    evidence = build_evidence(session, item, found, row)
    source = next((r for r in registry_rows() if r["source_id"] == row.source_id), None)
    item.update(
        {
            "source": source,
            "relevance": _summarise_matches(found),
            "linked_exposures": found,
            "book_hidden": not book_allowed,
            "related": [
                {"item_id": other.item_id, "title": other.title, "publisher": other.publisher,
                 "published_at_utc": _iso(other.published_at_utc), "url": other.url}
                for other in related_items(session, row)
            ],
            "note": assemble(item, found, evidence, ai=None, prompt_version="",
                             language="en"),
        }
    )
    return item


def sources_state(session) -> list[dict[str, Any]]:
    """The registry rows with each source's last poll."""

    from eurogas_nexus.db.models import NewsSourcePollRecord

    polls = {row.source_id: row for row in session.query(NewsSourcePollRecord).all()}
    out = []
    for row in registry_rows():
        poll = polls.get(str(row["source_id"]))
        row = dict(row)
        row["last_poll"] = None if poll is None else {
            "at_utc": _iso(poll.last_polled_at_utc),
            "status": poll.last_status,
            "detail": poll.last_detail,
            "last_success_at_utc": _iso(poll.last_success_at_utc),
            "items_seen": poll.items_seen,
            "items_new": poll.items_new,
        }
        out.append(row)
    return out


__all__ = [
    "MAX_LIMIT",
    "NewsFilters",
    "NewsQueryError",
    "item_detail",
    "item_dict",
    "list_items",
    "parse_filters",
    "sources_state",
]
