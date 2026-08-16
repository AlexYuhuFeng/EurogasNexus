"""Server-sent event streams for near-real-time decision feeds.

Design: PostgreSQL IS the event log. These endpoints are faster READERS — each
polls for rows newer than a per-connection watermark (~1.5s cadence) and pushes
only deltas. No in-memory truth, no new dependencies; clients keep HTTP polling
as a fallback.
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

FetchRows = Callable[[object, datetime | None], list[dict]]


def _sse(payload: object, *, event: str | None = None) -> str:
    lines = [f"event: {event}"] if event else []
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


async def _event_stream(
    topic: str,
    fetch: FetchRows,
    watermark_field: str,
) -> AsyncGenerator[str, None]:
    """Poll PostgreSQL for new rows and yield them as SSE events.

    The watermark is the max seen value of ``watermark_field``; only rows newer
    than it are pushed. Database unavailability emits an explicit warning event
    (never a silent fallback) and the stream keeps retrying.
    """

    watermark: datetime | None = None
    last_heartbeat = datetime.now(UTC)
    while True:
        rows: list[dict] = []
        try:
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                rows = fetch(session, watermark)
        except Exception:
            yield _sse(
                {"type": "warning", "message": "RUNTIME_POSTGRESQL_UNAVAILABLE"},
                event="warning",
            )
        for row in rows:
            yield _sse(row, event=topic)
            candidate = row.get(watermark_field)
            if isinstance(candidate, datetime):
                candidate = _as_utc(candidate)
                if watermark is None or candidate > watermark:
                    watermark = candidate
        now = datetime.now(UTC)
        if (now - last_heartbeat).total_seconds() >= HEARTBEAT_SECONDS:
            yield ": ping\n\n"
            last_heartbeat = now
        await asyncio.sleep(POLL_SECONDS)


# --- Read-only fetchers (watermark-based) -----------------------------------


def _fetch_new_quotes(session: Session, since: datetime | None) -> list[dict]:
    from eurogas_nexus.db.models import MarketQuoteRecord

    query = session.query(MarketQuoteRecord)
    if since is not None:
        query = query.filter(MarketQuoteRecord.observed_at_utc > since)
    rows = query.order_by(MarketQuoteRecord.observed_at_utc.asc()).limit(200).all()
    return [_columns_payload(row) for row in rows]


def _fetch_new_opportunities(session: Session, since: datetime | None) -> list[dict]:
    from eurogas_nexus.db.models import IntradayOpportunityRecord

    query = session.query(IntradayOpportunityRecord)
    if since is not None:
        query = query.filter(IntradayOpportunityRecord.detected_at_utc > since)
    rows = query.order_by(IntradayOpportunityRecord.detected_at_utc.asc()).limit(200).all()
    return [_columns_payload(row) for row in rows]


def _fetch_new_alerts(session: Session, since: datetime | None) -> list[dict]:
    from eurogas_nexus.db.models import MonitoringAlertRecord

    query = session.query(MonitoringAlertRecord)
    if since is not None:
        query = query.filter(MonitoringAlertRecord.updated_at_utc > since)
    rows = query.order_by(MonitoringAlertRecord.updated_at_utc.asc()).limit(200).all()
    return [_columns_payload(row) for row in rows]


def _columns_payload(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _stream_response(
    topic: str,
    fetch: FetchRows,
    watermark_field: str,
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(topic, fetch, watermark_field),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/stream/quotes")
async def stream_quotes(request: Request) -> StreamingResponse:
    """Push newly persisted market quotes as they land in PostgreSQL."""

    return _stream_response("quotes", _fetch_new_quotes, "observed_at_utc")


@router.get("/api/stream/opportunities")
async def stream_opportunities(request: Request) -> StreamingResponse:
    """Push newly persisted intraday opportunities."""

    return _stream_response("opportunities", _fetch_new_opportunities, "detected_at_utc")


@router.get("/api/stream/alerts")
async def stream_alerts(request: Request) -> StreamingResponse:
    """Push newly created or updated monitoring alerts."""

    return _stream_response("alerts", _fetch_new_alerts, "updated_at_utc")
