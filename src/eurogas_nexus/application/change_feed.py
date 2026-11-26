"""What changed since a client last looked: a cursor feed over market events (DATA-1, P2).

An ETRM, a BI tool or a script that keeps its own copy asks ``GET /api/market/changes``
with the cursor it was last given and receives every market event recorded since, oldest
first, with a new cursor. It never has to re-read everything to find what moved.

What a change says
------------------
A digest only: the event's key, type, subject (``hub:TTF:2027-01``, ``fx:EURGBP``,
``cargo:<id>``), revision and whether it is the first (``insert``) or a later one
(``update``), the times (market, published, ingested), its source and the snapshot keys it
touches. Never the value: a client reads the figure through the entitled read it already uses
(``GET /api/market/observations?as_of=<ingested_at_utc>``, the price strip, the cargo plan),
so licensed values and desk figures keep their own controls and the feed cannot become a way
round them (the firm's marks and contract terms already publish digests only).

Who sees what
-------------
A market event (price, FX, rate, outage, capacity, tariff, fundamentals, weather, ingestion)
is shown when the caller may read its source family, by the market reads' own rule
(``market_reads.row_allowed``), which also meters licensed families (GOV-1). A desk event
(contract, cargo, mark, assumption, limit, freight) is shown only to a caller who may read
the portfolio (``portfolio.read``) and sees every book (isolation off, or ``BOOKS:*``): its
digest names a contract or cargo, and the feed does not resolve each one's book. Withheld
events still move the cursor, so a client never asks for them again.

Order and the cursor
--------------------
Events are served in (writer transaction, ``seq``) order, and only those whose writing
transaction is older than the oldest transaction still open on PostgreSQL
(``pg_snapshot_xmin``): each of those is committed or rolled back for good, so no later read
can find a new event before a cursor already handed out. Serving by ``seq`` alone would skip
an event whose transaction drew its ``seq`` first and committed last. The price is latency:
an event waits until every write transaction that began before it has ended (a long import
holds the feed back for its length; see doc 15). Rows written before migration 0082 have no
writer id and come first, by ``seq``. On SQLite (tests, one writer) the order is ``seq``.

A cursor is opaque text (``c1-<writer>-<seq>``); it belongs to the filter it was read with.
``after=latest`` answers no events and the cursor of the newest one served, for a client
that wants only what happens from now on.

Retention: ``market_events`` is append-only and nothing prunes it, so any cursor stays
valid for as long as the store is kept. If a retention policy is ever introduced, a cursor
older than the oldest event held must answer 410 ``cursor_expired`` (this module states the
rule; there is nothing to expire today).

DATA-1：市场事件的增量变更流（游标分页、只读、按调用者授权过滤、只返回摘要不返回数值）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: Desk events: the firm's own book, terms and figures (book-wide visibility required).
DESK_EVENT_TYPES = frozenset(
    {
        "contract.changed",
        "cargo.changed",
        "mark.changed",
        "assumption.changed",
        "limit.changed",
        "freight.changed",
    }
)
DESK_SOURCE_PREFIXES = ("desk-", "firm-marks")

CURSOR_PREFIX = "c1"
LATEST = "latest"
DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
#: Rows examined per request at most (withheld rows included), so a caller who may see few
#: events still gets an answer quickly and moves on with the cursor.
MAX_SCANNED = 5000

#: Stable column order of a change (additions go at the end).
CHANGE_COLUMNS: tuple[str, ...] = (
    "cursor",
    "event_id",
    "event_key",
    "event_type",
    "operation",
    "revision",
    "supersedes_event_id",
    "subject_key",
    "source_id",
    "input_class",
    "dependency_keys",
    "content_hash",
    "market_time_utc",
    "published_at_utc",
    "ingested_at_utc",
)


class ChangeFeedError(ValueError):
    """A feed request that cannot be answered; ``code`` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, order=True)
class Cursor:
    """A position in the feed: after the event written by ``writer`` with ``seq``."""

    writer: int
    seq: int

    def text(self) -> str:
        return f"{CURSOR_PREFIX}-{self.writer}-{self.seq}"


START = Cursor(0, 0)


def parse_cursor(text: str | None) -> Cursor | str:
    """The cursor ``text`` names, :data:`START` when none, or :data:`LATEST`."""

    if text is None or not str(text).strip():
        return START
    raw = str(text).strip()
    if raw == LATEST:
        return LATEST
    parts = raw.split("-")
    if len(parts) != 3 or parts[0] != CURSOR_PREFIX:
        raise ChangeFeedError("cursor_invalid", "after must be a cursor this feed gave, or latest")
    try:
        writer, seq = int(parts[1]), int(parts[2])
    except ValueError:
        raise ChangeFeedError(
            "cursor_invalid", "after must be a cursor this feed gave, or latest"
        ) from None
    if writer < 0 or seq < 0:
        raise ChangeFeedError("cursor_invalid", "after must be a cursor this feed gave, or latest")
    return Cursor(writer, seq)


def parse_kinds(values: Iterable[str]) -> tuple[str, ...]:
    """Event types asked for (repeated or comma-separated); refuses an unknown one."""

    from eurogas_nexus.domain.market_events.model import EVENT_TYPES

    kinds = sorted(
        {part.strip() for value in values for part in str(value).split(",") if part.strip()}
    )
    unknown = [kind for kind in kinds if kind not in EVENT_TYPES]
    if unknown:
        raise ChangeFeedError(
            "kind_unknown",
            f"unknown event type(s) {', '.join(unknown)}; known: {', '.join(sorted(EVENT_TYPES))}",
        )
    return tuple(kinds)


@dataclass
class ChangePage:
    """One page of the feed."""

    changes: list[dict[str, Any]] = field(default_factory=list)
    next_cursor: str = START.text()
    has_more: bool = False
    scanned: int = 0
    withheld: int = 0
    #: The oldest open writer transaction; events from it on are held back (PostgreSQL only).
    horizon: int | None = None


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.isoformat()


def horizon(session) -> int | None:
    """The oldest writer transaction still open (PostgreSQL), or ``None`` (no horizon)."""

    if session.get_bind().dialect.name != "postgresql":
        return None
    from sqlalchemy import text

    return int(
        session.execute(text("SELECT pg_snapshot_xmin(pg_current_snapshot())::text::bigint"))
        .scalar_one()
    )


def is_desk_event(event_type: str, source_id: str) -> bool:
    return event_type in DESK_EVENT_TYPES or str(source_id).startswith(DESK_SOURCE_PREFIXES)


def _desk_visible(principal) -> bool:
    from eurogas_nexus.security.authorization import Permission, permissions_for_principal
    from eurogas_nexus.security.portfolio_scope import firm_level_visible

    if principal is None or principal.auth_method == "legacy_public_token":
        return True
    return firm_level_visible() and Permission.PORTFOLIO_READ in permissions_for_principal(
        principal
    )


def change_allowed(principal, event_type: str, source_id: str) -> bool:
    """Whether an explicit caller (a long-lived stream, not the current request) may see an
    event: the rule :func:`read_changes` applies, with the firm-level test taken from the
    caller's own data scopes rather than the request in flight."""

    from eurogas_nexus.application.projections.market_reads import row_allowed

    if principal is None or principal.auth_method == "legacy_public_token":
        return True
    if is_desk_event(event_type, source_id):
        from eurogas_nexus.security.authorization import Permission, permissions_for_principal
        from eurogas_nexus.security.portfolio_scope import scope_for_principal

        scope = scope_for_principal(principal.data_scopes)
        firm_level = scope is None or scope.all_books
        return firm_level and Permission.PORTFOLIO_READ in permissions_for_principal(principal)
    return row_allowed(principal, source_id)


def change_row(record, cursor: Cursor) -> dict[str, Any]:
    """One event as a change digest (never its payload)."""

    return {
        "cursor": cursor.text(),
        "event_id": record.event_id,
        "event_key": record.event_key,
        "event_type": record.event_type,
        "operation": "insert" if int(record.revision) == 1 else "update",
        "revision": int(record.revision),
        "supersedes_event_id": record.supersedes_event_id,
        "subject_key": record.subject_key,
        "source_id": record.source_id,
        "input_class": record.input_class,
        "dependency_keys": list(record.dependency_keys or []),
        "content_hash": record.content_hash,
        "market_time_utc": _iso(record.market_time_utc),
        "published_at_utc": _iso(record.published_at_utc),
        "ingested_at_utc": _iso(record.ingested_at_utc),
    }


def _position(record) -> Cursor:
    return Cursor(int(record.writer_txid or 0), int(record.seq))


def _filtered(query, e, kinds: Sequence[str], subject_prefix: str | None, ceiling: int | None):
    from sqlalchemy import or_

    if ceiling is not None:
        query = query.filter(or_(e.writer_txid.is_(None), e.writer_txid < ceiling))
    if kinds:
        query = query.filter(e.event_type.in_(list(kinds)))
    if subject_prefix:
        escaped = (
            subject_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        query = query.filter(e.subject_key.like(f"{escaped}%", escape="\\"))
    return query


def _query(
    session,
    after: Cursor,
    kinds: Sequence[str],
    subject_prefix: str | None,
    limit: int,
    ceiling: int | None,
):
    from sqlalchemy import and_, or_

    from eurogas_nexus.db.models import MarketEventRecord

    e = MarketEventRecord
    query = session.query(e)
    if after.writer == 0:
        query = query.filter(
            or_(and_(e.writer_txid.is_(None), e.seq > after.seq), e.writer_txid.isnot(None))
        )
    else:
        query = query.filter(
            or_(
                e.writer_txid > after.writer,
                and_(e.writer_txid == after.writer, e.seq > after.seq),
            )
        )
    query = _filtered(query, e, kinds, subject_prefix, ceiling)
    return query.order_by(e.writer_txid.asc().nulls_first(), e.seq.asc()).limit(limit)


def read_changes(
    session,
    principal,
    *,
    after: Cursor | str = START,
    kinds: Sequence[str] = (),
    subject_prefix: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ChangePage:
    """The next page of changes the caller may see after ``after``, oldest first."""

    from eurogas_nexus.application.projections.market_reads import row_allowed

    if not 1 <= limit <= MAX_LIMIT:
        raise ChangeFeedError("limit_out_of_range", f"limit must be 1 to {MAX_LIMIT}")
    ceiling = horizon(session)
    page = ChangePage(horizon=ceiling)
    if after == LATEST:
        newest = _newest(session, kinds, subject_prefix, ceiling)
        page.next_cursor = (newest or START).text()
        return page
    assert isinstance(after, Cursor)
    position = after
    desk = None
    batch_size = min(MAX_LIMIT, limit * 2)
    while len(page.changes) < limit and page.scanned < MAX_SCANNED:
        batch = _query(session, position, kinds, subject_prefix, batch_size, ceiling).all()
        for record in batch:
            page.scanned += 1
            position = _position(record)
            if is_desk_event(record.event_type, record.source_id):
                if desk is None:
                    desk = _desk_visible(principal)
                allowed = desk
            else:
                allowed = principal is None or row_allowed(principal, record.source_id)
            if allowed:
                page.changes.append(change_row(record, position))
            else:
                page.withheld += 1
            if len(page.changes) >= limit or page.scanned >= MAX_SCANNED:
                break
        if len(batch) < batch_size:
            break
    page.has_more = (
        _query(session, position, kinds, subject_prefix, 1, ceiling).first() is not None
    )
    page.next_cursor = position.text()
    return page


def _newest(session, kinds, subject_prefix, ceiling) -> Cursor | None:
    from eurogas_nexus.db.models import MarketEventRecord

    e = MarketEventRecord
    query = _filtered(session.query(e.writer_txid, e.seq), e, kinds, subject_prefix, ceiling)
    row = query.order_by(e.writer_txid.desc().nulls_last(), e.seq.desc()).first()
    return None if row is None else Cursor(int(row.writer_txid or 0), int(row.seq))


__all__ = [
    "CHANGE_COLUMNS",
    "DEFAULT_LIMIT",
    "DESK_EVENT_TYPES",
    "LATEST",
    "MAX_LIMIT",
    "START",
    "ChangeFeedError",
    "ChangePage",
    "Cursor",
    "change_allowed",
    "change_row",
    "horizon",
    "is_desk_event",
    "parse_cursor",
    "parse_kinds",
    "read_changes",
]
