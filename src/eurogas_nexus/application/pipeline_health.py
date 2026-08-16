"""Pipeline health aggregation for runtime observability.

Read-only aggregation over PostgreSQL: per-source ingestion state, quote
freshness, latest opportunity, and open alert count. This is the operations
view (freshness / errors / latency) that turns near-real-time into a
measurable SLA surface.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session


def pipeline_health(session: Session, *, now_utc: datetime | None = None) -> dict:
    """Aggregate pipeline health from runtime tables (read-only)."""

    from eurogas_nexus.db.models import (
        IngestionRunRecord,
        IntradayOpportunityRecord,
        MarketQuoteRecord,
        MonitoringAlertRecord,
    )

    now = _as_utc(now_utc or datetime.now(UTC))
    recent_cutoff = now - timedelta(minutes=5)

    ingestion_rows = (
        session.query(IngestionRunRecord)
        .order_by(IngestionRunRecord.started_at_utc.desc())
        .limit(500)
        .all()
    )
    by_source: dict[str, list[IngestionRunRecord]] = {}
    for row in ingestion_rows:
        by_source.setdefault(row.source_name, []).append(row)

    sources: list[dict] = []
    for source_name, rows in sorted(by_source.items()):
        latest = rows[0]
        consecutive_failures = 0
        for row in rows:
            if row.status != "failed":
                break
            consecutive_failures += 1
        sources.append(
            {
                "source_name": source_name,
                "status": latest.status,
                "started_at_utc": _as_utc(latest.started_at_utc).isoformat(),
                "finished_at_utc": (
                    _as_utc(latest.finished_at_utc).isoformat()
                    if latest.finished_at_utc
                    else None
                ),
                "consecutive_failures": consecutive_failures,
            }
        )

    quote_rows = (
        session.query(MarketQuoteRecord)
        .filter(MarketQuoteRecord.observed_at_utc >= recent_cutoff)
        .all()
    )
    quote_freshness: dict[str, dict] = {}
    for row in quote_rows:
        entry = quote_freshness.setdefault(
            row.source_system, {"count_recent_5m": 0, "latest_observed_at_utc": None}
        )
        entry["count_recent_5m"] += 1
        observed = _as_utc(row.observed_at_utc)
        if entry["latest_observed_at_utc"] is None or observed > entry["latest_observed_at_utc"]:
            entry["latest_observed_at_utc"] = observed

    latest_opportunity = (
        session.query(IntradayOpportunityRecord)
        .order_by(IntradayOpportunityRecord.detected_at_utc.desc())
        .first()
    )
    open_alerts = (
        session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.status == "open")
        .count()
    )

    return {
        "generated_at_utc": now.isoformat(),
        "sources": sources,
        "quote_freshness": {
            source: {
                "count_recent_5m": entry["count_recent_5m"],
                "latest_observed_at_utc": (
                    entry["latest_observed_at_utc"].isoformat()
                    if entry["latest_observed_at_utc"]
                    else None
                ),
            }
            for source, entry in sorted(quote_freshness.items())
        },
        "latest_opportunity_detected_at_utc": (
            _as_utc(latest_opportunity.detected_at_utc).isoformat()
            if latest_opportunity is not None
            else None
        ),
        "open_alerts": open_alerts,
    }


def empty_pipeline_health(now_utc: datetime | None = None) -> dict:
    """DB-unavailable fallback payload (explicitly marked, not silent)."""

    return {
        "generated_at_utc": _as_utc(now_utc or datetime.now(UTC)).isoformat(),
        "sources": [],
        "quote_freshness": {},
        "latest_opportunity_detected_at_utc": None,
        "open_alerts": 0,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
