"""Audit-event retention (R32; security review H5).

* Retention is configured (``EUROGAS_NEXUS_AUDIT_RETENTION_DAYS``, default five years, at least
  one year): nothing younger is ever pruned, whatever a caller asks for.
* Pruning is dual-controlled: a dry run counts, and a deletion runs only for a privileged
  change (kind ``audit_prune``) another administrator approved (``api/dual_control.py``), or
  from the command line with that change's id.
* Pruning keeps the hash chain verifiable: only a contiguous oldest part of the chain is
  removed, and the last removed link is recorded as an anchor the verification starts from.
* Pruning is itself audited, in the same transaction.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

#: Five years: the usual record-keeping horizon for trading decisions and their evidence
#: (MiFID II Art. 16(6)-(7), MAR, REMIT record-keeping).
DEFAULT_AUDIT_RETENTION_DAYS = 1827
#: The shortest retention a deployment may configure (on legal advice only).
MIN_AUDIT_RETENTION_DAYS = 365
MAX_AUDIT_RETENTION_DAYS = 3650
RETENTION_ENV = "EUROGAS_NEXUS_AUDIT_RETENTION_DAYS"


class AuditPruneRefused(ValueError):
    """A prune the policy does not allow."""


def configured_retention_days() -> int:
    raw = (os.environ.get(RETENTION_ENV) or "").strip()
    value = int(raw) if raw.isdigit() else DEFAULT_AUDIT_RETENTION_DAYS
    return min(max(value, MIN_AUDIT_RETENTION_DAYS), MAX_AUDIT_RETENTION_DAYS)


def prune_expired_audit_events(
    session: Session,
    *,
    retention_days: int | None = None,
    now_utc: datetime | None = None,
    dry_run: bool = True,
    approved_change_id: str | None = None,
    by: str = "operator",
) -> dict:
    """Delete (or count, when dry-run) the oldest audit rows beyond retention.

    Raises:
        AuditPruneRefused: a window below the configured retention, or a deletion without an
            approved privileged change.
    """

    from eurogas_nexus.db import audit_chain
    from eurogas_nexus.db.models import AuditChainRecord, AuditEventRecord
    from eurogas_nexus.db.repositories.audit import record_governed_audit

    floor = configured_retention_days()
    days = floor if retention_days is None else retention_days
    if not floor <= days <= MAX_AUDIT_RETENTION_DAYS:
        raise AuditPruneRefused(
            f"retention_days must be between {floor} (the configured retention, "
            f"{RETENTION_ENV}) and {MAX_AUDIT_RETENTION_DAYS}"
        )
    if not dry_run and not approved_change_id:
        raise AuditPruneRefused(
            "deleting audit rows needs a second administrator's approval (an approved "
            "audit_prune change)"
        )
    now = _as_utc(now_utc or datetime.now(UTC))
    cutoff = now - timedelta(days=days)
    audit_chain.seal_pending(session)
    # The chain is pruned from its start only: up to the first link whose row is younger.
    first_kept = (
        session.query(func.min(AuditChainRecord.chain_seq))
        .join(AuditEventRecord, AuditEventRecord.event_id == AuditChainRecord.event_id)
        .filter(AuditEventRecord.event_ts_utc >= cutoff)
        .scalar()
    )
    links = session.query(AuditChainRecord)
    if first_kept is not None:
        links = links.filter(AuditChainRecord.chain_seq < first_kept)
    last = links.order_by(AuditChainRecord.chain_seq.desc()).first()
    event_ids = [event_id for (event_id,) in links.with_entities(AuditChainRecord.event_id)]
    deleted = len(event_ids)
    if not dry_run and last is not None:
        audit_chain.record_anchor(
            session, kind="prune", seq=last.chain_seq, digest=last.row_hash, by=by,
            detail=f"change={approved_change_id}; retention_days={days}; rows={deleted}",
        )
        if session.get_bind().dialect.name == "postgresql":
            # The database guard (migration 0095) lets an approved prune through only.
            session.execute(text("SET LOCAL eurogas.audit_prune = 'approved'"))
        for start in range(0, len(event_ids), 1000):
            chunk = event_ids[start : start + 1000]
            session.query(AuditChainRecord).filter(
                AuditChainRecord.event_id.in_(chunk)
            ).delete(synchronize_session=False)
            session.query(AuditEventRecord).filter(
                AuditEventRecord.event_id.in_(chunk)
            ).delete(synchronize_session=False)
    record_governed_audit(
        session,
        event_type="governance.audit",
        principal=by[:64],
        action="audit.retention.prune",
        resource="audit_events",
        outcome="dry_run" if dry_run else "pruned",
        severity="info" if dry_run else "warning",
        detail=(
            f"retention_days={days}; cutoff={cutoff.isoformat()}; rows={deleted}; "
            f"change={approved_change_id or '-'}"
        ),
        source_system="audit-retention",
    )
    session.flush()
    return {
        "dry_run": dry_run,
        "retention_days": days,
        "cutoff_utc": cutoff.isoformat(),
        "audit_events_deleted": deleted,
        "anchor_seq": last.chain_seq if (last is not None and not dry_run) else None,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
