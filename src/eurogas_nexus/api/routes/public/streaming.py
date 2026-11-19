"""Server-sent event streams for near-real-time decision feeds.

Design: PostgreSQL IS the event log. These endpoints are faster READERS — each
polls for rows newer than a per-connection cursor (~1.5s cadence) and pushes
only deltas. No in-memory truth, no new dependencies; clients keep HTTP polling
as a fallback.

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

import asyncio
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


async def _event_stream(
    topic: str,
    fetch: FetchRows,
    ts_field: str,
    pk_field: str,
    initial_cursor: Cursor,
    guard: RowGuard | None = None,
    notices: tuple[tuple[str, FetchNotices], ...] = (),
) -> AsyncGenerator[str, None]:
    """Poll PostgreSQL for rows after the cursor and yield them as SSE events.

    Database unavailability emits an explicit warning event (never a silent
    fallback) and the stream keeps retrying. With a ``guard``, only the rows the caller
    may receive are sent; the cursor still moves past the others, so a withheld row is
    never retried, and a caller who may no longer stream gets one ``revoked`` event and
    the stream ends.
    """

    cursor: Cursor = initial_cursor
    # Change notices ride on the same connection (a browser holds few per host): each from
    # now, without an id (a reconnecting client re-reads what they announce anyway).
    notice_cursors: dict[str, Cursor] = {name: (datetime.now(UTC), "") for name, _ in notices}
    last_heartbeat = datetime.now(UTC)
    while True:
        rows: list[dict] = []
        allowed: list[dict] | None = []
        announced: list[tuple[str, dict]] = []
        try:
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                rows = fetch(session, cursor)
                allowed = rows if guard is None else guard(session, rows)
                caller = getattr(guard, "principal", None)
                for name, fetch_notices in notices:
                    for notice in fetch_notices(session, notice_cursors[name], caller):
                        moved = notice.get("cursor") or notice.get("changed_at")
                        if isinstance(moved, datetime):
                            current = notice_cursors[name]
                            if current is None or _as_utc(moved) > current[0]:
                                notice_cursors[name] = (_as_utc(moved), "")
                        # What the caller may not see moves the cursor and is not announced.
                        if notice.get("visible", True):
                            announced.append(
                                (
                                    name,
                                    {"group": notice["group"], "changed_at": notice["changed_at"]},
                                )
                            )
        except Exception:
            rows, allowed = [], []
            yield _sse(
                {"type": "warning", "message": "RUNTIME_POSTGRESQL_UNAVAILABLE"},
                event="warning",
            )
        if allowed is None:
            yield _sse({"type": "revoked", "message": "ACCESS_REVOKED"}, event="revoked")
            return
        for row in allowed:
            yield _sse(row, event=topic, event_id=_event_id(row.get(ts_field), row.get(pk_field)))
        for name, notice in announced:
            yield _sse(notice, event=name)
        for row in rows:
            cursor = _row_cursor(row, ts_field, pk_field) or cursor
        now = datetime.now(UTC)
        if (now - last_heartbeat).total_seconds() >= HEARTBEAT_SECONDS:
            yield ": ping\n\n"
            last_heartbeat = now
        await asyncio.sleep(POLL_SECONDS)


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


def _fetch_new_opportunities(session: Session, cursor: Cursor) -> list[dict]:
    from sqlalchemy import and_, or_

    from eurogas_nexus.db.models import IntradayOpportunityRecord

    query = session.query(IntradayOpportunityRecord)
    if cursor is not None:
        since_ts, since_pk = cursor
        query = query.filter(
            or_(
                IntradayOpportunityRecord.detected_at_utc > since_ts,
                and_(
                    IntradayOpportunityRecord.detected_at_utc == since_ts,
                    IntradayOpportunityRecord.opportunity_id > since_pk,
                ),
            )
        )
    rows = (
        query.order_by(
            IntradayOpportunityRecord.detected_at_utc.asc(),
            IntradayOpportunityRecord.opportunity_id.asc(),
        )
        .limit(PAGE_SIZE)
        .all()
    )
    return [_columns_payload(row) for row in rows]


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

    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows
    from eurogas_nexus.db.models import (
        FlowObservationRecord,
        LngCargoRecord,
        OpportunityRecord,
        RegasSlotRecord,
        RemitUmmRecord,
    )
    from eurogas_nexus.security.portfolio_scope import scope_for_principal, visible_book_ids

    since = cursor[0] if cursor is not None else None

    def changed(query, stamp):
        if since is not None:
            query = query.filter(stamp > since)
        return query.order_by(stamp.desc()).limit(NOTICE_PAGE).all()

    def entitled(rows: list[dict]) -> list[dict]:
        if principal is None:
            return rows
        return filter_entitled_rows(principal, rows, source_key="source_system")

    books = (
        None
        if principal is None
        else visible_book_ids(session, scope_for_principal(principal.data_scopes))
    )

    def own_book(book_id) -> bool:
        return books is None or (book_id is not None and book_id in books)

    found: dict[str, list[tuple[datetime, bool]]] = {group: [] for group in MAP_CHANGE_GROUPS}
    flows = [
        {"changed_at": at, "source_system": source}
        for at, source in changed(
            session.query(
                FlowObservationRecord.observed_at_utc, FlowObservationRecord.source_system
            ).filter(identity_clause(session, FlowObservationRecord)),
            FlowObservationRecord.observed_at_utc,
        )
    ]
    seen = {id(row) for row in entitled(flows)}
    found["flows"] = [(row["changed_at"], id(row) in seen) for row in flows]
    outages = [
        {"changed_at": at, "source_system": source}
        for at, source in changed(
            session.query(RemitUmmRecord.ingested_at_utc, RemitUmmRecord.source_system),
            RemitUmmRecord.ingested_at_utc,
        )
    ]
    seen = {id(row) for row in entitled(outages)}
    found["outages"] = [(row["changed_at"], id(row) in seen) for row in outages]
    cargoes = [
        {"changed_at": at, "book_id": book, "source_system": source}
        for at, book, source in changed(
            session.query(
                LngCargoRecord.updated_at_utc, LngCargoRecord.book_id, LngCargoRecord.source_system
            ),
            LngCargoRecord.updated_at_utc,
        )
    ]
    market = {id(row) for row in entitled([row for row in cargoes if row["book_id"] is None])}
    found["cargoes"] = [
        (row["changed_at"], own_book(row["book_id"]) if row["book_id"] else id(row) in market)
        for row in cargoes
    ]
    found["slots"] = [
        (at, own_book(book) if book else books is None)
        for at, book in changed(
            session.query(RegasSlotRecord.updated_at_utc, RegasSlotRecord.book_id),
            RegasSlotRecord.updated_at_utc,
        )
    ]
    opportunities = changed(
        session.query(OpportunityRecord.last_changed_utc, OpportunityRecord.opportunity_id),
        OpportunityRecord.last_changed_utc,
    )
    if opportunities and principal is not None:
        from eurogas_nexus.application.opportunities.listing import visible_records

        mine = {row.opportunity_id for row in visible_records(session, principal)}
    else:
        mine = None
    found["opportunities"] = [
        (at, mine is None or opportunity_id in mine) for at, opportunity_id in opportunities
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
    return StreamingResponse(
        _event_stream(
            topic,
            fetch,
            ts_field,
            pk_field,
            initial_cursor,
            guard=_guard_for(topic, request),
            notices=notices,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        if not self._still_authorised(session):
            return None
        if not rows:
            return rows
        if self.topic == "quotes":
            from eurogas_nexus.application.projections.market_reads import filter_entitled_rows

            return filter_entitled_rows(self.principal, rows, source_key="source_system")
        if self.topic == "opportunities":
            from eurogas_nexus.application.projections.market_reads import (
                filter_entitled_opportunities,
            )

            return filter_entitled_opportunities(session, self.principal, rows)
        if self.topic == "alerts":
            from eurogas_nexus.application.alert_scope import alert_visibility
            from eurogas_nexus.security.portfolio_scope import scope_for_principal

            visible = alert_visibility(
                session,
                scope=scope_for_principal(self.principal.data_scopes),
                principal=self.principal,
            )
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
    """Push newly persisted intraday opportunities."""

    return _stream_response(
        "opportunities",
        _fetch_new_opportunities,
        "detected_at_utc",
        "opportunity_id",
        request,
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
