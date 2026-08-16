"""Runtime data retention pruning (D6 defaults).

Retention: market quotes 30 days, market observations 90 days, intraday
opportunities 7 days. Purely additive deletion; no schema change.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

QUOTE_RETENTION_DAYS = 30
OBSERVATION_RETENTION_DAYS = 90
OPPORTUNITY_RETENTION_DAYS = 7


def prune_expired_rows(
    session: Session,
    *,
    now_utc: datetime | None = None,
    dry_run: bool = False,
) -> dict:
    """Delete (or count, when dry_run) expired runtime rows per the policy."""

    from eurogas_nexus.db.models import (
        IntradayOpportunityRecord,
        MarketObservationRecord,
        MarketQuoteRecord,
    )

    now = _as_utc(now_utc or datetime.now(UTC))
    targets = [
        (
            "market_quotes",
            MarketQuoteRecord,
            MarketQuoteRecord.observed_at_utc,
            now - timedelta(days=QUOTE_RETENTION_DAYS),
        ),
        (
            "market_observations",
            MarketObservationRecord,
            MarketObservationRecord.observed_at_utc,
            now - timedelta(days=OBSERVATION_RETENTION_DAYS),
        ),
        (
            "intraday_opportunities",
            IntradayOpportunityRecord,
            IntradayOpportunityRecord.detected_at_utc,
            now - timedelta(days=OPPORTUNITY_RETENTION_DAYS),
        ),
    ]

    summary: dict[str, object] = {"dry_run": dry_run, "pruned_at_utc": now.isoformat()}
    for key, model, column, cutoff in targets:
        query = session.query(model).filter(column < cutoff)
        summary[f"{key}_deleted"] = (
            query.count() if dry_run else query.delete(synchronize_session=False)
        )
    session.flush()
    return summary


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
