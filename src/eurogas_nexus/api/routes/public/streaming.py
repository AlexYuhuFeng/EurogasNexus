"""Server-sent event streams for near-real-time decision feeds.

Design: PostgreSQL IS the event log. These endpoints are faster READERS — each
polls for rows newer than a per-connection cursor (~1.5s cadence) and pushes
only deltas. No in-memory truth, no new dependencies; clients keep HTTP polling
as a fallback.

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
HEARTBEAT_SECONDS = 15.0
PAGE_SIZE = 200

# (observed_at_utc as UTC datetime, primary key) — the stream cursor.
Cursor = tuple[datetime, str] | None

FetchRows = Callable[[object, Cursor], list[dict]]


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
) -> AsyncGenerator[str, None]:
    """Poll PostgreSQL for rows after the cursor and yield them as SSE events.

    Database unavailability emits an explicit warning event (never a silent
    fallback) and the stream keeps retrying.
    """

    cursor: Cursor = initial_cursor
    last_heartbeat = datetime.now(UTC)
    while True:
        rows: list[dict] = []
        try:
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                rows = fetch(session, cursor)
        except Exception:
            yield _sse(
                {"type": "warning", "message": "RUNTIME_POSTGRESQL_UNAVAILABLE"},
                event="warning",
            )
        for row in rows:
            yield _sse(row, event=topic, event_id=_event_id(row.get(ts_field), row.get(pk_field)))
            cursor = _row_cursor(row, ts_field, pk_field)
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


def _columns_payload(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _stream_response(
    topic: str,
    fetch: FetchRows,
    ts_field: str,
    pk_field: str,
    request: Request,
) -> StreamingResponse:
    initial_cursor = _parse_cursor(request.headers.get("last-event-id"))
    return StreamingResponse(
        _event_stream(topic, fetch, ts_field, pk_field, initial_cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/stream/quotes")
async def stream_quotes(request: Request) -> StreamingResponse:
    """Push newly persisted market quotes as they land in PostgreSQL."""

    return _stream_response(
        "quotes", _fetch_new_quotes, "observed_at_utc", "quote_id", request
    )


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
    """Push newly created or updated monitoring alerts."""

    return _stream_response(
        "alerts", _fetch_new_alerts, "updated_at_utc", "alert_id", request
    )
