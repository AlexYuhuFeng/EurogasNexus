"""Periodic cost-source refresh application service.

This service fetches a machine-readable cost-observation feed and upserts the
normalized rows into PostgreSQL. It is scheduler-friendly: the caller provides
the HTTP function and session factory.
"""

from __future__ import annotations

from datetime import UTC, datetime

from eurogas_nexus.db.repositories.cost_observation import upsert_cost_observation
from eurogas_nexus.ingestion.connectors.cost_source import (
    JsonCostObservationConnector,
)


def refresh_cost_source(
    session_factory,
    *,
    url: str,
    http_get=None,
    source_system: str = "TSO_TARIFFS",
    now_utc: datetime | None = None,
) -> int:
    """Fetch and upsert cost observations from the configured JSON URL.

    Returns the number of observations refreshed.
    """

    if not url:
        return 0
    connector = JsonCostObservationConnector(
        source_system=source_system,
        datasets=("published_tariffs",),
        url=url,
        http_get=http_get or _default_http_get,
    )
    observations = connector.fetch_cost_observations()
    if not observations:
        return 0

    now = now_utc or datetime.now(UTC)
    with session_factory() as session:
        for observation in observations:
            if not observation.created_at_utc:
                object.__setattr__(observation, "created_at_utc", now.isoformat())
            upsert_cost_observation(session, observation, now_utc=now)
        session.commit()
    return len(observations)


def _default_http_get(url: str):
    import httpx

    return httpx.get(url, timeout=10)
