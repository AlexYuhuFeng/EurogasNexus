"""Server-sent event streams for near-real-time decision feeds.

Design: PostgreSQL IS the event log. These endpoints are faster READERS: each
connection holds its own cursor (~1.5s cadence) and receives only deltas. No
in-memory truth, no new dependencies; clients keep HTTP polling as a fallback.

Serving: a connection does not query the database itself. The process's one poller
(``api.stream_hub``) reads every source once per interval in a thread, off the event loop,
and hands each connection its own events (its cursor, its caller's entitlement) through an
in-memory queue. The stream states below (:class:`_RowStream`, :class:`_LiveStream`) are what
that poller runs for each connection.

Entitlement: a stream outlives the request that opened it, so every poll passes its rows
through a guard built from the caller: quotes by licensed data scope (as the REST read
does), spread opportunities by the scopes of both quotes behind them, and alerts by book
scope. The guard re-reads the principal every ``REAUTH_SECONDS``; a disabled identity or a
withdrawn scope takes effect on the open connection, and a disabled identity ends it.

Resumability: every event carries an ``id:`` line encoding the row position as
``<timestamp ISO 8601>|<primary key>``. A client that reconnects sends
``Last-Event-ID`` and the stream resumes exactly after that row — including
when more than 200 rows share the same timestamp (the old timestamp-only
watermark could permanently skip rows).
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

router = APIRouter(tags=["streaming"])

POLL_SECONDS = 1.5
#: How often an open stream re-reads its principal (status and data scopes).
REAUTH_SECONDS = 30.0
HEARTBEAT_SECONDS = 15.0
PAGE_SIZE = 200

# (observed_at_utc as UTC datetime, primary key) — the stream cursor.
Cursor = tuple[datetime, str] | None

FetchRows = Callable[[object, Cursor], list[dict]]
#: Rows the caller may receive, or ``None`` when the caller may no longer stream at all.
RowGuard = Callable[[object, list[dict]], list[dict] | None]


def _sse(payload: object, *, event: str | None = None, event_id: str | None = None) -> str:
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(payload, default=_iso)}")
    return "\n".join(lines) + "\n\n"


def _iso(value: object) -> str:
    if isinstance(value, datetime):
        return _as_utc(value).isoformat()
    return str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_cursor(value: str | None) -> Cursor:
    """Parse a ``Last-Event-ID`` value into a (timestamp, pk) cursor."""

    if not value:
        return None
    ts_part, _, pk = value.partition("|")
    if not ts_part or not pk:
        return None
    try:
        since_ts = datetime.fromisoformat(ts_part)
    except ValueError:
        return None
    return _as_utc(since_ts), pk


def _event_id(ts_field_value: object, pk: object) -> str:
    return f"{_iso(ts_field_value)}|{pk}"


def refused_event() -> str:
    """What a stream sends when the caller already holds the most streams allowed; it ends."""

    return _sse({"type": "refused", "message": "STREAM_LIMIT_REACHED"}, event="refused")


def warning_event() -> str:
    """What a stream sends while the database is unavailable (it keeps trying)."""

    return _sse({"type": "warning", "message": "RUNTIME_POSTGRESQL_UNAVAILABLE"}, event="warning")


def _reads_keys(fetch_notices) -> tuple[str, ...]:
    return tuple(getattr(fetch_notices, "reads_keys", ()))


class _RowStream:
    """One row stream's cursor, guard and notice cursors; run by the poller thread.

    Each poll sends the rows after the cursor that the guard lets through; the cursor still
    moves past the others, so a withheld row is never retried, and a caller who may no longer
    stream gets one ``revoked`` event and the stream ends. Database unavailability sends an
    explicit warning event (never a silent fallback) and the stream keeps trying.
    """

    def __init__(
        self,
        topic: str,
        fetch: FetchRows,
        ts_field: str,
        pk_field: str,
        initial_cursor: Cursor,
        guard: RowGuard | None,
        notices: tuple[tuple[str, FetchNotices], ...],
    ) -> None:
        self.topic = topic
        self.fetch = fetch
        self.ts_field = ts_field
        self.pk_field = pk_field
        self.cursor: Cursor = initial_cursor
        self.guard = guard
        self.notices = notices
        # Change notices ride on the same connection (a browser holds few per host): each from
        # now, without an id (a reconnecting client re-reads what they announce anyway).
        self.notice_cursors: dict[str, Cursor] = {
            name: (datetime.now(UTC), "") for name, _ in notices
        }
        self.last_heartbeat = datetime.now(UTC)
        self.started = False

    def _cursor_of(self, row: dict) -> Cursor:
        return _row_cursor(row, self.ts_field, self.pk_field)

    def want(self, reads) -> None:
        reads.want(("rows", self.fetch), self.cursor)
        for name, fetch_notices in self.notices:
            cursor = self.notice_cursors[name]
            for key in _reads_keys(fetch_notices):
                reads.want(key, _notice_since(key, cursor, reads))

    def poll(self, reads) -> tuple[list[str], bool]:
        self.started = True
        out: list[str] = []
        rows: list[dict] = []
        allowed: list[dict] | None = []
        announced: list[tuple[str, dict]] = []
        try:
            rows = reads.ascending(
                ("rows", self.fetch), self.fetch, self.cursor, self._cursor_of, PAGE_SIZE
            )
            guard = self.guard
            if guard is None:
                allowed = rows
            else:
                allowed = guard(reads if isinstance(guard, StreamGuard) else reads.session, rows)
            caller = getattr(guard, "principal", None)
            for name, fetch_notices in self.notices:
                for notice in fetch_notices(reads, self.notice_cursors[name], caller):
                    moved = notice.get("cursor") or notice.get("changed_at")
                    if isinstance(moved, datetime):
                        current = self.notice_cursors[name]
                        if current is None or _as_utc(moved) > current[0]:
                            self.notice_cursors[name] = (_as_utc(moved), "")
                    # What the caller may not see moves the cursor and is not announced.
                    if notice.get("visible", True):
                        announced.append(
                            (
                                name,
                                {
                                    **(notice.get("detail") or {}),
                                    "group": notice["group"],
                                    "changed_at": notice["changed_at"],
                                },
                            )
                        )
        except Exception:
            reads.recover()
            rows, allowed, announced = [], [], []
            out.append(warning_event())
        if allowed is None:
            out.append(_sse({"type": "revoked", "message": "ACCESS_REVOKED"}, event="revoked"))
            return out, True
        for row in allowed:
            out.append(
                _sse(
                    row,
                    event=self.topic,
                    event_id=_event_id(row.get(self.ts_field), row.get(self.pk_field)),
                )
            )
        for name, notice in announced:
            out.append(_sse(notice, event=name))
        for row in rows:
            self.cursor = self._cursor_of(row) or self.cursor
        now = datetime.now(UTC)
        if (now - self.last_heartbeat).total_seconds() >= HEARTBEAT_SECONDS:
            out.append(": ping\n\n")
            self.last_heartbeat = now
        return out, False


def _notice_since(key: str, cursor: Cursor, reads):
    """The cursor a notice source reads ``key`` from (see each source's ``reads_keys``)."""

    if key == "expiries":
        return (cursor[0] if cursor is not None else reads.now, "")
    if key == "evaluations":
        return None if cursor is None else (cursor[0], "")
    return cursor[0] if cursor is not None else None


async def _event_stream(
    topic: str,
    fetch: FetchRows,
    ts_field: str,
    pk_field: str,
    initial_cursor: Cursor,
    guard: RowGuard | None = None,
    notices: tuple[tuple[str, FetchNotices], ...] = (),
    principal_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """The connection's events: rows after the cursor and notices, from the process's poller.

    Database unavailability emits an explicit warning event (never a silent
    fallback) and the stream keeps retrying. With a ``guard``, only the rows the caller
    may receive are sent; the cursor still moves past the others, so a withheld row is
    never retried, and a caller who may no longer stream gets one ``revoked`` event and
    the stream ends.
    """

    from eurogas_nexus.api.stream_hub import get_hub

    state = _RowStream(topic, fetch, ts_field, pk_field, initial_cursor, guard, notices)
    async for chunk in get_hub().stream(state, principal_id):
        yield chunk


def _row_cursor(row: dict, ts_field: str, pk_field: str) -> Cursor:
    ts_value = row.get(ts_field)
    pk = row.get(pk_field)
    if not isinstance(ts_value, datetime) or not isinstance(pk, str) or not pk:
        return None
    return _as_utc(ts_value), pk


# --- Read-only fetchers (cursor-based) --------------------------------------


def _fetch_new_quotes(session: Session, cursor: Cursor) -> list[dict]:
    from sqlalchemy import and_, or_

    from eurogas_nexus.db.models import MarketQuoteRecord

    query = session.query(MarketQuoteRecord)
    if cursor is not None:
        since_ts, since_pk = cursor
        query = query.filter(
            or_(
                MarketQuoteRecord.observed_at_utc > since_ts,
                and_(
                    MarketQuoteRecord.observed_at_utc == since_ts,
                    MarketQuoteRecord.quote_id > since_pk,
                ),
            )
        )
    rows = (
        query.order_by(
            MarketQuoteRecord.observed_at_utc.asc(),
            MarketQuoteRecord.quote_id.asc(),
        )
        .limit(PAGE_SIZE)
        .all()
    )
    return [_columns_payload(row) for row in rows]


#: Opportunity states the Opportunities page lists; any other state is a withdrawal.
LISTED_OPPORTUNITY_STATES = frozenset({"actionable", "indicative"})


def _opportunity_change(row, *, withdrawn_reason: str | None = None) -> dict:
    """One opportunity's transition as the stream sends it: ``open`` while the page lists it,
    ``withdrawn`` (with the reason) once it stops being viable. No figure: the page re-reads
    its list, which carries the arithmetic and is filtered the same way."""

    if withdrawn_reason is None and _as_utc(row.expires_at_utc) <= datetime.now(UTC):
        withdrawn_reason = "expired"  # past its validity, before the engine records it
    listed = (
        withdrawn_reason is None and row.state in LISTED_OPPORTUNITY_STATES and bool(row.surfaced)
    )
    return {
        "opportunity_id": row.opportunity_id,
        "type": row.type,
        "lane": row.lane,
        "state": row.state,
        "version": row.version,
        "status": "open" if listed else "withdrawn",
        "reason": None if listed else (withdrawn_reason or row.ended_reason or row.state),
        "changed_at_utc": _as_utc(row.last_changed_utc),
        "expires_at_utc": _as_utc(row.expires_at_utc),
        "deadline_utc": _as_utc(row.deadline_utc) if row.deadline_utc else None,
        "evaluation_id": row.evaluation_id,
        "book_ids": list(row.book_ids or []),
        "source_families": list(row.source_families or []),
    }


def _fetch_new_opportunities(session: Session, cursor: Cursor) -> list[dict]:
    """Opportunities of the opportunity engine whose state or version moved after the cursor
    (M7; the legacy intraday table is no longer streamed). A record not yet surfaced (state
    ``new``) moves the cursor and is not sent: the page never showed it."""

    from sqlalchemy import and_, or_

    from eurogas_nexus.db.models import OpportunityRecord

    query = session.query(OpportunityRecord)
    if cursor is not None:
        since_ts, since_pk = cursor
        query = query.filter(
            or_(
                OpportunityRecord.last_changed_utc > since_ts,
                and_(
                    OpportunityRecord.last_changed_utc == since_ts,
                    OpportunityRecord.opportunity_id > since_pk,
                ),
            )
        )
    rows = (
        query.order_by(
            OpportunityRecord.last_changed_utc.asc(),
            OpportunityRecord.opportunity_id.asc(),
        )
        .limit(PAGE_SIZE)
        .all()
    )
    out = []
    for row in rows:
        change = _opportunity_change(row)
        change["sent"] = row.state != "new"
        out.append(change)
    return out


def _opportunity_visible(session, principal):
    """The opportunity read rule for one caller (``listing.visible_to``), as a dict predicate.

    ``session`` is a session or the poll's shared reads (the caller's books once per poll)."""

    from types import SimpleNamespace

    from eurogas_nexus.application.live_topics import as_reads
    from eurogas_nexus.application.opportunities.listing import visible_to
    from eurogas_nexus.application.projections.market_reads import row_allowed

    if principal is None:
        return lambda change: True
    books = as_reads(session).books(principal)

    def visible(change: dict) -> bool:
        row = SimpleNamespace(
            lane=change.get("lane"),
            book_ids=change.get("book_ids") or [],
            source_families=change.get("source_families") or [],
        )
        return visible_to(row, books, lambda family: row_allowed(principal, family))

    return visible


def _fetch_opportunity_expiries(session: Session, cursor: Cursor, principal=None) -> list[dict]:
    """Listed opportunities whose validity ended after the cursor: withdrawn at their expiry,
    not at the engine's next run (which records ``expired`` and sends it again, harmlessly).

    ``session`` is a session or the poll's shared reads."""

    from eurogas_nexus.application.live_topics import as_reads
    from eurogas_nexus.db.models import OpportunityRecord

    reads = as_reads(session)
    now = reads.now
    since = cursor[0] if cursor is not None else now

    def fetch(db, at):
        return (
            db.query(OpportunityRecord)
            .filter(OpportunityRecord.state.in_(sorted(LISTED_OPPORTUNITY_STATES)))
            .filter(OpportunityRecord.surfaced.is_(True))
            .filter(OpportunityRecord.expires_at_utc > at[0])
            .filter(OpportunityRecord.expires_at_utc <= now)
            .order_by(OpportunityRecord.expires_at_utc.asc())
            .limit(NOTICE_PAGE)
            .all()
        )

    rows = reads.ascending(
        "expiries",
        fetch,
        (since, ""),
        lambda row: (_as_utc(row.expires_at_utc), ""),
        NOTICE_PAGE,
    )
    visible = _opportunity_visible(reads, principal)
    out = []
    for row in rows:
        change = _opportunity_change(row, withdrawn_reason="expired")
        change["changed_at_utc"] = _as_utc(row.expires_at_utc)
        out.append(
            {
                "group": "expiry",
                "changed_at": _as_utc(row.expires_at_utc),
                "visible": visible(change),
                "cursor": _as_utc(row.expires_at_utc),
                "detail": change,
            }
        )
    # Time itself moves the cursor: what expires later is found by a later poll.
    out.append({"group": "expiry", "changed_at": now, "visible": False, "cursor": now})
    return out


_fetch_opportunity_expiries.reads_keys = ("expiries",)  # type: ignore[attr-defined]


def _fetch_evaluations(session: Session, cursor: Cursor, principal=None) -> list[dict]:
    """Opportunity evaluations finished after the cursor: the page's "as of" moves and it
    re-reads (a re-evaluation can change figures without changing a state). The run is
    firm-wide; the notice names when and why it ran, not what it found.

    ``session`` is a session or the poll's shared reads."""

    from eurogas_nexus.application.live_topics import as_reads
    from eurogas_nexus.db.models import OpportunityEvaluationRecord

    def fetch(db, at):
        query = db.query(OpportunityEvaluationRecord).filter(
            OpportunityEvaluationRecord.finished_at_utc.is_not(None)
        )
        if at is not None:
            query = query.filter(OpportunityEvaluationRecord.finished_at_utc > at[0])
        return (
            query.order_by(OpportunityEvaluationRecord.finished_at_utc.asc())
            .limit(NOTICE_PAGE)
            .all()
        )

    rows = as_reads(session).ascending(
        "evaluations",
        fetch,
        None if cursor is None else (cursor[0], ""),
        lambda row: (_as_utc(row.finished_at_utc), ""),
        NOTICE_PAGE,
    )
    return [
        {
            "group": "evaluation",
            "changed_at": _as_utc(row.finished_at_utc),
            "visible": True,
            "cursor": _as_utc(row.finished_at_utc),
            "detail": {
                "evaluation_id": row.evaluation_id,
                "trigger": row.trigger,
                "as_of_utc": _as_utc(row.as_of_utc),
            },
        }
        for row in rows
    ]


_fetch_evaluations.reads_keys = ("evaluations",)  # type: ignore[attr-defined]


def _fetch_new_alerts(session: Session, cursor: Cursor) -> list[dict]:
    from sqlalchemy import and_, or_

    from eurogas_nexus.db.models import MonitoringAlertRecord

    query = session.query(MonitoringAlertRecord)
    if cursor is not None:
        since_ts, since_pk = cursor
        query = query.filter(
            or_(
                MonitoringAlertRecord.updated_at_utc > since_ts,
                and_(
                    MonitoringAlertRecord.updated_at_utc == since_ts,
                    MonitoringAlertRecord.alert_id > since_pk,
                ),
            )
        )
    rows = (
        query.order_by(
            MonitoringAlertRecord.updated_at_utc.asc(),
            MonitoringAlertRecord.alert_id.asc(),
        )
        .limit(PAGE_SIZE)
        .all()
    )
    return [_columns_payload(row) for row in rows]


#: The map's fast inputs, each with the column that says when a row last changed: the map
#: re-reads (conditionally) when one of them moves. Group names only, never a row.
MAP_CHANGE_GROUPS = ("outages", "flows", "cargoes", "slots", "opportunities")

#: Rows looked at per group and poll (the newest first): enough to find one the caller sees.
NOTICE_PAGE = 200

#: A change notice source: the session, the group cursor and the caller -> changes, each
#: ``{"group", "changed_at", "visible"}``; only the visible ones are announced, every one
#: moves the cursor.
FetchNotices = Callable[[object, Cursor, object], list[dict]]


def _fetch_map_changes(session: Session, cursor: Cursor, principal=None) -> list[dict]:
    """The map's fast inputs that changed after the cursor, as the caller may see them.

    A notice names a group and a time, no row; the client answers it with a conditional read
    of the map situation. Still, a notice must not reveal that something changed in data the
    caller may not read: each group's changed rows pass the same rules as the map's own read
    before they count. Flows are read under the identity rule (``identity_clause``: a
    withheld row is not news); flows and outages by the caller's data scopes on their source;
    the firm's cargoes and slots by its books (an unbooked slot is head office's); market
    cargoes by the vessel feed's entitlement; opportunities by the opportunity core's own
    visibility. Without a principal (an internal caller) every change counts.
    """

    from eurogas_nexus.application.live_topics import as_reads
    from eurogas_nexus.application.opportunities.listing import visible_to
    from eurogas_nexus.application.projections.market_reads import (
        filter_entitled_rows,
        row_allowed,
    )
    from eurogas_nexus.domain.opportunities.model import OpportunityState

    reads = as_reads(session)
    since = cursor[0] if cursor is not None else None

    def entitled(rows: list[dict]) -> list[dict]:
        if principal is None:
            return rows
        return filter_entitled_rows(principal, rows, source_key="source_system")

    books = reads.books(principal)

    def own_book(book_id) -> bool:
        return books is None or (book_id is not None and book_id in books)

    found: dict[str, list[tuple[datetime, bool]]] = {group: [] for group in MAP_CHANGE_GROUPS}
    flows = [
        {"changed_at": row.observed_at_utc, "source_system": row.source_system}
        for row in reads.newest("map_flows", since)
    ]
    seen = {id(row) for row in entitled(flows)}
    found["flows"] = [(row["changed_at"], id(row) in seen) for row in flows]
    outages = [
        {"changed_at": row.ingested_at_utc, "source_system": row.source_system}
        for row in reads.newest("map_outages", since)
    ]
    seen = {id(row) for row in entitled(outages)}
    found["outages"] = [(row["changed_at"], id(row) in seen) for row in outages]
    cargoes = [
        {
            "changed_at": row.updated_at_utc,
            "book_id": row.book_id,
            "source_system": row.source_system,
        }
        for row in reads.newest("map_cargoes", since)
    ]
    market = {id(row) for row in entitled([row for row in cargoes if row["book_id"] is None])}
    found["cargoes"] = [
        (row["changed_at"], own_book(row["book_id"]) if row["book_id"] else id(row) in market)
        for row in cargoes
    ]
    found["slots"] = [
        (row.updated_at_utc, own_book(row.book_id) if row.book_id else books is None)
        for row in reads.newest("map_slots", since)
    ]
    # An opportunity counts for a caller who may read it while it is live (``listing.
    # visible_records``: book scope and entitlement), decided per changed row.
    ended = {OpportunityState.EXPIRED.value, OpportunityState.CONVERTED.value}

    def mine(row) -> bool:
        if principal is None:
            return True
        if row.state in ended:
            return False
        return visible_to(row, books, lambda family: row_allowed(principal, family))

    found["opportunities"] = [
        (row.last_changed_utc, mine(row)) for row in reads.newest("map_opportunities", since)
    ]

    out: list[dict] = []
    for group, rows in found.items():
        if not rows:
            continue
        latest = max(_as_utc(at) for at, _ in rows)
        visible = [_as_utc(at) for at, ok in rows if ok]
        out.append(
            {
                "group": group,
                "changed_at": max(visible) if visible else latest,
                "visible": bool(visible),
                "cursor": latest,
            }
        )
    return sorted(out, key=lambda item: (item["changed_at"], item["group"]))


_fetch_map_changes.reads_keys = (  # type: ignore[attr-defined]
    "map_flows",
    "map_outages",
    "map_cargoes",
    "map_slots",
    "map_opportunities",
)


def _columns_payload(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _stream_response(
    topic: str,
    fetch: FetchRows,
    ts_field: str,
    pk_field: str,
    request: Request,
    notices: tuple[tuple[str, FetchNotices], ...] = (),
) -> StreamingResponse:
    initial_cursor = _initial_cursor(request)
    guard = _guard_for(topic, request)
    return StreamingResponse(
        _event_stream(
            topic,
            fetch,
            ts_field,
            pk_field,
            initial_cursor,
            guard=guard,
            notices=notices,
            principal_id=_admit(guard),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _admit(guard: StreamGuard) -> str | None:
    """The caller's id for the per-caller stream cap, or 429 when the cap is reached.

    A browser opens one stream per tab; the cap (``EUROGAS_NEXUS_STREAMS_PER_PRINCIPAL`` per
    process) stops one caller from holding the process's poller with hundreds. The shared
    deployment token has no identity of its own and is not capped here.
    """

    from fastapi import HTTPException

    from eurogas_nexus.api.stream_hub import get_hub, streams_per_principal

    principal = guard.principal
    if principal is None or principal.auth_method == "legacy_public_token":
        return None
    if get_hub().streams_of(principal.principal_id) >= streams_per_principal():
        raise HTTPException(
            status_code=429,
            detail={
                "code": "stream_limit_reached",
                "message": "Too many live-update connections for this identity.",
            },
        )
    return principal.principal_id


def _guard_for(topic: str, request: Request) -> RowGuard:
    """The entitlement guard for one open stream, bound to the caller who opened it."""

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal

    return StreamGuard(topic, current_principal(request))


class StreamGuard:
    """Filters each poll's rows for one caller and keeps that caller's access current."""

    def __init__(self, topic: str, principal) -> None:
        self.topic = topic
        self.principal = principal
        self._checked_at = datetime.now(UTC)

    def __call__(self, session, rows: list[dict]) -> list[dict] | None:
        """``session`` is a session or the poll's shared reads (books read once per caller)."""

        from eurogas_nexus.application.live_topics import Reads

        db = session.session if isinstance(session, Reads) else session
        if not self._still_authorised(db):
            return None
        if not rows:
            return rows
        if self.topic == "quotes":
            from eurogas_nexus.application.projections.market_reads import filter_entitled_rows

            return filter_entitled_rows(self.principal, rows, source_key="source_system")
        if self.topic == "opportunity":
            visible = _opportunity_visible(session, self.principal)
            return [row for row in rows if row.get("sent", True) and visible(row)]
        if self.topic == "alerts":
            from eurogas_nexus.application.live_topics import alert_predicate, as_reads

            visible = alert_predicate(as_reads(session), self.principal)
            return [row for row in rows if visible(row)]
        return []  # an unknown topic sends nothing

    def _still_authorised(self, session) -> bool:
        """Re-read the stored identity every ``REAUTH_SECONDS``; the static token has none."""

        if self.principal.auth_method == "legacy_public_token":
            return True
        now = datetime.now(UTC)
        if (now - self._checked_at).total_seconds() < REAUTH_SECONDS:
            return True
        self._checked_at = now
        from dataclasses import replace

        from eurogas_nexus.db.models import IdentityPrincipalRecord

        record = session.get(IdentityPrincipalRecord, self.principal.principal_id)
        if record is None or str(record.status).upper() != "ACTIVE":
            return False
        self.principal = replace(self.principal, data_scopes=tuple(record.data_scopes or ()))
        return True


def _initial_cursor(request: Request) -> Cursor:
    """Resume from Last-Event-ID or start a new connection at the current time."""

    # Without Last-Event-ID, start from "now" rather than replaying the entire
    # PostgreSQL table. The client already reconciles recent rows through the
    # regular REST polling path, so an initial full-table replay would flood the
    # EventSource and freeze low-memory browser contexts without adding data.
    return _parse_cursor(request.headers.get("last-event-id")) or (
        datetime.now(UTC),
        "",
    )


@router.get("/api/stream/quotes")
async def stream_quotes(request: Request) -> StreamingResponse:
    """Push newly persisted market quotes as they land in PostgreSQL."""

    return _stream_response("quotes", _fetch_new_quotes, "observed_at_utc", "quote_id", request)


@router.get("/api/stream/opportunities")
async def stream_opportunities(request: Request) -> StreamingResponse:
    """Push the opportunity engine's changes as they happen (M7).

    Events: ``opportunity`` when one opens (``status: open``) or stops being viable
    (``status: withdrawn`` with ``reason``: expired, converted, blocked, watch), resumable by
    ``Last-Event-ID``, including a withdrawal at the moment its validity ends; and
    ``evaluated`` when an evaluation finishes (``as_of_utc``, ``trigger``). A notice carries no
    figure: the page re-reads ``GET /api/opportunities``. Each is filtered by the
    opportunity's own read rule (book scope and source entitlement). Until M7 this stream
    sent the legacy intraday spread table, which ``GET /api/market/opportunities`` still
    serves.
    """

    return _stream_response(
        "opportunity",
        _fetch_new_opportunities,
        "changed_at_utc",
        "opportunity_id",
        request,
        notices=(("opportunity", _fetch_opportunity_expiries), ("evaluated", _fetch_evaluations)),
    )


@router.get("/api/stream/alerts")
async def stream_alerts(request: Request) -> StreamingResponse:
    """Push newly created or updated monitoring alerts, and the map's change notices.

    The ``map`` notices (outages, flows, cargoes, slots, opportunities changed; a group and a
    time, no row) ride on this connection rather than a stream of their own: a browser holds
    few connections per host and every session already has this one open.
    """

    return _stream_response(
        "alerts",
        _fetch_new_alerts,
        "updated_at_utc",
        "alert_id",
        request,
        notices=(("map", _fetch_map_changes),),
    )


# --- The live stream: per-topic change notices and job progress ---------------------------

#: How often the live stream sends a ``heartbeat`` event (a named event, so a browser sees it
#: and can tell a quiet feed from a dead connection).
LIVE_HEARTBEAT_SECONDS = 5.0
#: How far back a resumed live stream looks at most: older gaps are re-read by the page anyway.
LIVE_RESUME_LIMIT_SECONDS = 15 * 60.0
LIVE_ID_PREFIX = "live|"


def _live_event_id(at: datetime, outbox: str | None = None) -> str:
    base = f"{LIVE_ID_PREFIX}{_as_utc(at).isoformat()}"
    return f"{base}|{outbox}" if outbox else base


def _parse_live_id(value: str | None, now: datetime) -> tuple[datetime, str | None] | None:
    """The time and outbox cursor a ``Last-Event-ID`` of the live stream names.

    The time is kept within the resume limit; the outbox cursor (``c1-<writer>-<seq>``) is
    exact, so a resumed client hears of every market event recorded while it was away.
    """

    if not value or not value.startswith(LIVE_ID_PREFIX):
        return None
    stamp, _, outbox = value[len(LIVE_ID_PREFIX) :].partition("|")
    try:
        at = _as_utc(datetime.fromisoformat(stamp))
    except ValueError:
        return None
    if outbox:
        from eurogas_nexus.application.change_feed import ChangeFeedError, parse_cursor

        try:
            parsed = parse_cursor(outbox)
        except ChangeFeedError:
            outbox = ""
        else:
            outbox = outbox if not isinstance(parsed, str) else ""
    earliest = now.timestamp() - LIVE_RESUME_LIMIT_SECONDS
    if at.timestamp() < earliest:
        at = datetime.fromtimestamp(earliest, UTC)
    return min(at, now), outbox or None


class _LiveStream:
    """One live stream's topics, cursors, outbox position and guard; run by the poller."""

    def __init__(
        self,
        topics: tuple[str, ...],
        start: datetime,
        resumed: bool,
        guard: StreamGuard | None,
        outbox_after: str | None,
    ) -> None:
        self.topics = topics
        self.start = start
        self.resumed = resumed
        self.guard = guard
        self.notice_topics = tuple(topic for topic in topics if topic != "jobs")
        self.cursors: dict = dict.fromkeys(self.notice_topics, start)
        self.outbox = outbox_after
        self.jobs_seen: dict[str, tuple] = {}
        self.jobs_since = start
        self.last_heartbeat = datetime.now(UTC)
        self.started = False

    def _principal(self):
        return None if self.guard is None else self.guard.principal

    def event_id(self) -> str:
        return _live_event_id(min(self.cursors.values(), default=datetime.now(UTC)), self.outbox)

    def want(self, reads) -> None:
        from eurogas_nexus.application.live_topics import OUTBOX_TOPICS, want_topics

        want_topics(reads, self.notice_topics, self.cursors)
        kinds = [kind for kind, topic in OUTBOX_TOPICS.items() if topic in self.notice_topics]
        if kinds:
            reads.want_outbox(self.outbox, kinds)
        if "jobs" in self.topics:
            reads.want_jobs(getattr(self._principal(), "principal_id", None), self.jobs_since)

    def poll(self, reads) -> tuple[list[str], bool]:
        from eurogas_nexus.application.live_topics import (
            job_events,
            outbox_changes,
            topic_changes,
        )

        out: list[str] = []
        if not self.started:
            self.started = True
            if self.outbox is None and self.notice_topics:
                try:
                    self.outbox = reads.outbox_latest()
                except Exception:
                    reads.recover()
                    self.outbox = None  # the first poll that reaches the store starts it
            ready_id = self.event_id()
            out.append(
                _sse(
                    {
                        "topics": list(self.topics),
                        "resumed_from": self.start if self.resumed else None,
                        "poll_seconds": POLL_SECONDS,
                        "heartbeat_seconds": LIVE_HEARTBEAT_SECONDS,
                        # In the payload too (as every live event): a browser's EventSource
                        # keeps the id to itself, and the client resumes from the last one.
                        "event_id": ready_id,
                    },
                    event="ready",
                    event_id=ready_id,
                )
            )
            self.last_heartbeat = datetime.now(UTC)
        announced: dict[str, dict] = {}
        jobs: list[dict] = []
        try:
            if self.guard is not None and not self.guard._still_authorised(reads.session):
                out.append(_sse({"type": "revoked", "message": "ACCESS_REVOKED"}, event="revoked"))
                return out, True
            principal = self._principal()
            found = topic_changes(
                reads, self.notice_topics, self.cursors, principal, _fetch_map_changes
            )
            if self.outbox is None:
                self.outbox = reads.outbox_latest()
            else:
                events, self.outbox = outbox_changes(
                    reads, self.notice_topics, self.outbox, principal
                )
                found.extend(events)
            for notice in found:
                topic = notice["topic"]
                moved = notice.get("cursor")
                if isinstance(moved, datetime) and _as_utc(moved) > self.cursors[topic]:
                    self.cursors[topic] = _as_utc(moved)
                if not notice.get("visible", True):
                    continue
                held = announced.get(topic)
                if held is None or _as_utc(notice["changed_at"]) > _as_utc(held["changed_at"]):
                    announced[topic] = notice
            if "jobs" in self.topics:
                jobs = job_events(reads, principal, self.jobs_since, self.jobs_seen)
        except Exception:
            reads.recover()
            announced, jobs = {}, []
            out.append(warning_event())
        current = self.event_id()
        for notice in announced.values():
            out.append(
                _sse(
                    {
                        "topic": notice["topic"],
                        "changed_at": notice["changed_at"],
                        "event_id": current,
                    },
                    event="change",
                    event_id=current,
                )
            )
        for job in jobs:
            out.append(_sse({**job, "event_id": current}, event="jobs", event_id=current))
        now = datetime.now(UTC)
        if (now - self.last_heartbeat).total_seconds() >= LIVE_HEARTBEAT_SECONDS:
            out.append(
                _sse({"at": now, "event_id": current}, event="heartbeat", event_id=current)
            )
            self.last_heartbeat = now
        return out, False


async def _live_stream(
    topics: tuple[str, ...],
    start: datetime,
    resumed: bool,
    guard: StreamGuard | None,
    outbox_after: str | None = None,
    principal_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """The subscribed topics' ``change`` notices, from the process's poller.

    Market events come from the outbox (``market_events``, through ``change_feed``); what the
    outbox does not carry (screen quotes, booked trades, nominations, alerts, the map's fast
    inputs) from its own table (``application.live_topics``).

    Events (each ``data`` is JSON):

    * ``ready`` once: ``{topics, resumed_from, poll_seconds, heartbeat_seconds}``;
    * ``change``: ``{topic, changed_at, event_id}``, at most one per topic per poll (bursts are
      coalesced here: a page re-reads once however many rows landed);
    * ``jobs``: ``{job_id, kind, status, progress, step, error_code, created_at, started_at,
      finished_at, event_id}`` when one of the caller's jobs moves;
    * ``heartbeat``: ``{at, event_id}`` every ``LIVE_HEARTBEAT_SECONDS``;
    * ``warning`` (the database is unavailable; the stream keeps trying) and ``revoked`` (the
      caller may no longer stream; the stream ends).

    Every event but ``warning`` carries an ``id:`` (``live|<time>|<outbox cursor>``: the
    earliest table cursor and the outbox position). A client that reconnects with it as
    ``Last-Event-ID`` (or ``last_event_id``) is told about every topic that changed while it
    was away.
    """

    from eurogas_nexus.api.stream_hub import get_hub

    state = _LiveStream(topics, start, resumed, guard, outbox_after)
    async for chunk in get_hub().stream(state, principal_id):
        yield chunk


@router.get("/api/stream/live")
async def stream_live(request: Request, topics: str = "") -> StreamingResponse:
    """Push a change notice per subscribed topic, and the caller's job progress.

    ``topics`` is a comma-separated subset of ``prices, trades, alerts, nominations, tariffs,
    outages, flows, cargoes, slots, opportunities, book, capacity, sources, news, jobs``;
    unknown names are ignored. Market events are read from the outbox (``market_events``). A notice
    names a topic and a time, never a row: the page answers it with its own (conditional) read,
    so the notice never carries data the page would have to entitle, and nothing the caller may
    not read produces one. Resumes from ``Last-Event-ID`` or the ``last_event_id`` parameter
    (a browser that opens a new connection cannot set the header).
    """

    from eurogas_nexus.application.live_topics import parse_topics

    now = datetime.now(UTC)
    resume = request.headers.get("last-event-id") or request.query_params.get("last_event_id")
    resumed = _parse_live_id(resume, now)
    guard = _guard_for("live", request)
    return StreamingResponse(
        _live_stream(
            parse_topics(topics),
            resumed[0] if resumed else now,
            resumed is not None,
            guard,
            outbox_after=resumed[1] if resumed else None,
            principal_id=_admit(guard),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
