"""Provider certification persistence (operator-recorded evidence)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import ProviderCertificationRecord
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.domain.ingestion.certification import validate_certification_payload


def upsert_provider_certification(
    session: Session,
    *,
    source_system: str,
    stage: str,
    checks: list[str],
    evidence: dict[str, Any],
    evaluated_by: str,
    note: str | None = None,
    now_utc: datetime | None = None,
) -> dict:
    """Validate and record (or replace) certification evidence for a source.

    Does not commit the caller's transaction.
    """

    validate_certification_payload(
        source_system=source_system,
        stage=stage,
        checks=checks,
        evidence=evidence,
        evaluated_by=evaluated_by,
    )
    evaluated_at = now_utc or datetime.now(UTC)
    existing = (
        session.query(ProviderCertificationRecord)
        .filter(ProviderCertificationRecord.source_system == source_system)
        .first()
    )
    record = existing or ProviderCertificationRecord(
        certification_id=f"cert-{uuid4().hex[:24]}",
        source_system=source_system,
    )
    record.stage = str(stage).strip().lower()
    record.checks = list(dict.fromkeys(str(check).strip().lower() for check in checks))
    record.evidence = evidence
    record.evaluated_by = evaluated_by
    record.note = note
    record.evaluated_at_utc = evaluated_at
    if existing is None:
        session.add(record)
    record_audit_event(
        session,
        event_type="certification.upsert",
        principal=evaluated_by,
        action="upsert_provider_certification",
        resource=f"provider_certification:{source_system}",
        outcome=record.stage,
        severity="warning",
        detail=f"{source_system} certified as {record.stage}.",
        source_system="certification",
        now_utc=evaluated_at,
    )
    session.flush()
    return certification_payload(record)


def latest_certification(session: Session, source_system: str) -> dict | None:
    """Return the current certification row for a source system, if any."""

    row = (
        session.query(ProviderCertificationRecord)
        .filter(ProviderCertificationRecord.source_system == source_system)
        .first()
    )
    return certification_payload(row) if row is not None else None


def list_certifications(session: Session) -> list[dict]:
    """Return all certification rows ordered by source system."""

    rows = (
        session.query(ProviderCertificationRecord)
        .order_by(ProviderCertificationRecord.source_system)
        .all()
    )
    return [certification_payload(row) for row in rows]


def certification_payload(row: ProviderCertificationRecord) -> dict:
    """Serialize a certification row to its API payload shape.

    把认证记录序列化为 API 载荷（时间戳转 ISO）。

    Args:
        row: The certification record.

    Returns:
        Dict with all payload fields.
    """

    return {
        "certification_id": row.certification_id,
        "source_system": row.source_system,
        "stage": row.stage,
        "checks": list(row.checks or []),
        "evidence": dict(row.evidence or {}),
        "evaluated_by": row.evaluated_by,
        "note": row.note,
        "evaluated_at_utc": row.evaluated_at_utc.isoformat(),
    }
