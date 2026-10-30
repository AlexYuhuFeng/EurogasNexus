"""Idempotent storage of power observations."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.ingestion.entsoe_transparency import PowerObservation


def upsert_power_observations(
    session: Session,
    observations: Iterable[PowerObservation],
    *,
    source_system: str = "ENTSOE",
    now: datetime | None = None,
) -> dict[str, int]:
    """Insert new values and replace revised ones; returns inserted/updated/unchanged counts.

    A value republished in a later document (a revision) replaces the stored one and moves its
    ``published_at_utc`` forward, so a dataset built as of an earlier time does not see it.
    """

    stamp = now or datetime.now(UTC)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    for item in observations:
        row = session.get(PowerObservationRecord, item.observation_id)
        if row is None:
            session.add(
                PowerObservationRecord(
                    observation_id=item.observation_id,
                    zone=item.zone,
                    metric=item.metric,
                    process_type=item.process_type,
                    period_start_utc=item.period_start_utc,
                    period_end_utc=item.period_end_utc,
                    value=item.value,
                    unit=item.unit,
                    source_system=source_system,
                    source_reference=item.source_reference[:160],
                    published_at_utc=item.published_at_utc,
                    ingested_at_utc=stamp,
                )
            )
            counts["inserted"] += 1
        elif row.value != item.value:
            row.value = item.value
            row.published_at_utc = item.published_at_utc
            row.source_reference = item.source_reference[:160]
            row.ingested_at_utc = stamp
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    return counts
