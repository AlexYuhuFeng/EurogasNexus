"""Storage of power observations, with the history of every revised value.

ENTSO-E and Elexon re-state actual load and generation for days after first publication
(live: 44 ENTSO-E values replaced in two scheduler runs on 14 November 2026). A later
publication with a different value replaces the current row, and the version it replaces
is appended to ``observation_revisions`` in the same transaction, as for the gas tables
(docs/operations/DATA_REVISIONS.md):

- the row keeps its first version's ``published_at_utc`` (availability of the first value)
  and ``ingested_at_utc`` (first receipt); ``revised_at_utc`` is when the current value was
  received;
- a revision is available from its receipt by this store, never earlier. The parser caps
  ``published_at_utc`` at the regulatory publication deadline, which is the same for the
  first and the revised publication of an actual, so that time cannot order versions.

The source system, zone, metric, process type, period and unit identify the observation; a
different value of any of them under a stored id is refused
(:class:`PowerRevisionIdentityConflictError`) and the caller's transaction should be rolled
back, so nothing of the batch is kept.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.db.repositories.public_ingestion_upsert import _append_revision
from eurogas_nexus.ingestion.entsoe_transparency import PowerObservation

#: Columns that identify a power observation: a change in any of them is not a revision.
POWER_IDENTITY_FIELDS = (
    "source_system",
    "zone",
    "metric",
    "process_type",
    "period_start_utc",
    "period_end_utc",
    "unit",
)


class PowerRevisionIdentityConflictError(RuntimeError):
    """A stored power observation id arrived with a different identity: not a revision."""

    code = "power_revision_identity_conflict"


class PowerStaleRevisionError(RuntimeError):
    """A changed value whose receipt is not after the stored version's."""

    code = "power_revision_not_newer"


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _row_values(row: PowerObservationRecord) -> dict[str, object]:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def upsert_power_observations(
    session: Session,
    observations: Iterable[PowerObservation],
    *,
    source_system: str = "ENTSOE",
    now: datetime | None = None,
) -> dict[str, int]:
    """Insert new values, keep revised ones with history; returns the counts.

    Counts: ``inserted``, ``updated`` (current rows replaced, each with one history
    record), ``unchanged`` and ``revised`` (the updated rows: for power every replacement
    is a changed value).

    Raises:
        PowerRevisionIdentityConflictError: a stored id with a different identity.
        PowerStaleRevisionError: a changed value at or before the stored version's receipt
            (only possible with an explicit ``now`` earlier than a stored receipt).
    """

    stamp = _utc(now) or datetime.now(UTC)
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "revised": 0}
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
            continue
        incoming = {
            "source_system": source_system,
            "zone": item.zone,
            "metric": item.metric,
            "process_type": item.process_type,
            "period_start_utc": _utc(item.period_start_utc),
            "period_end_utc": _utc(item.period_end_utc),
            "unit": item.unit,
        }
        differing = [
            name
            for name in POWER_IDENTITY_FIELDS
            if (_utc(getattr(row, name)) if name.endswith("_utc") else getattr(row, name))
            != incoming[name]
        ]
        if differing:
            raise PowerRevisionIdentityConflictError(
                f"Refusing power observation {item.observation_id}: the stored row differs "
                f"on identity field(s) [{', '.join(differing)}], which a revision may not "
                "change."
            )
        if row.value == item.value:
            counts["unchanged"] += 1
            continue
        prior_received = _utc(row.revised_at_utc) or _utc(row.published_at_utc)
        if prior_received is not None and stamp <= prior_received:
            raise PowerStaleRevisionError(
                f"Refusing power observation {item.observation_id}: a changed value received "
                "no later than the stored version cannot supersede it."
            )
        _append_revision(
            session,
            PowerObservationRecord.__table__,
            _row_values(row),
            {"source_reference": item.source_reference},
            reason="value_changed",
            changed_fields=["value"],
            prior_received=prior_received or stamp,
            superseded_at=stamp,
        )
        row.value = item.value
        row.source_reference = item.source_reference[:160]
        row.revised_at_utc = stamp
        counts["updated"] += 1
        counts["revised"] += 1
    return counts
