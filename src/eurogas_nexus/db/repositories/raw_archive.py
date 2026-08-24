"""Raw payload archive persistence (raw -> canonical lineage)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import RawPayloadArchiveRecord


def archive_raw_payload(
    session: Session,
    *,
    archive_id: str,
    source_system: str,
    dataset: str,
    source_reference: str,
    payload_text: str | None = None,
    payload_json: dict | None = None,
    payload_sha256: str,
    record_count: int,
    received_at_utc: datetime | None = None,
) -> RawPayloadArchiveRecord:
    """Append one immutable raw payload archive row."""

    record = RawPayloadArchiveRecord(
        archive_id=archive_id,
        source_system=source_system,
        dataset=dataset,
        source_reference=source_reference,
        payload_text=payload_text,
        payload_json=payload_json,
        payload_sha256=payload_sha256,
        record_count=record_count,
        received_at_utc=received_at_utc or datetime.now(UTC),
        research_only=True,
        human_review_required=True,
    )
    session.add(record)
    session.flush()
    return record
