"""Read repositories for R34A storage/nomination master data."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.storage_nomination import (
    NominationWindowMasterRecord,
    StorageFacilityMasterRecord,
    StorageInventoryObservationRecord,
)


def active_storage_facility(
    session: Session,
    facility_id: str,
    *,
    at_utc: datetime,
) -> StorageFacilityMasterRecord | None:
    """Return an active facility whose validity window covers ``at_utc``."""

    row = session.get(StorageFacilityMasterRecord, facility_id)
    if row is None or not row.active:
        return None
    if _as_utc(row.valid_from_utc) > at_utc:
        return None
    if row.valid_to_utc is not None and _as_utc(row.valid_to_utc) < at_utc:
        return None
    return row


def latest_storage_inventory(
    session: Session,
    facility_id: str,
    *,
    asof_utc: datetime,
) -> StorageInventoryObservationRecord | None:
    """Return the latest inventory observation not later than ``asof_utc``."""

    rows = (
        session.query(StorageInventoryObservationRecord)
        .filter(StorageInventoryObservationRecord.facility_id == facility_id)
        .filter(StorageInventoryObservationRecord.observed_at_utc <= asof_utc)
        .order_by(StorageInventoryObservationRecord.observed_at_utc.desc())
        .limit(1)
        .all()
    )
    return rows[0] if rows else None


def active_nomination_windows(
    session: Session,
    *,
    at_utc: datetime,
) -> list[NominationWindowMasterRecord]:
    """Return active nomination window masters valid at ``at_utc``."""

    rows = (
        session.query(NominationWindowMasterRecord)
        .filter(NominationWindowMasterRecord.active.is_(True))
        .all()
    )
    return [
        row
        for row in rows
        if _as_utc(row.valid_from_utc) <= at_utc
        and (row.valid_to_utc is None or _as_utc(row.valid_to_utc) >= at_utc)
    ]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
