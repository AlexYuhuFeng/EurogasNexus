"""Audit retention and prune script tests (R32)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.audit_retention import (
    DEFAULT_AUDIT_RETENTION_DAYS,
    prune_expired_audit_events,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord


def _row(age_days: int) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=f"audit-age-{age_days}",
        event_type="test",
        severity="info",
        principal="operator",
        action="test",
        resource="test",
        outcome="recorded",
        detail="",
        event_ts_utc=datetime.now(UTC) - timedelta(days=age_days),
        source_system="test",
        human_review_required=True,
    )


def test_prune_audit_events_dry_run_counts_only(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path.as_posix()}/audit.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_row(2600))
        session.add(_row(10))
        session.commit()

        summary = prune_expired_audit_events(session, dry_run=True)
        assert summary["dry_run"] is True
        assert summary["audit_events_deleted"] == 1

        # Nothing deleted; the dry run is itself audited.
        assert session.query(AuditEventRecord).filter_by(action="test").count() == 2


def test_prune_audit_events_commit_deletes_only_expired(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path.as_posix()}/audit.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_row(2700))
        session.add(_row(5))
        session.commit()

        # A deletion needs an approved privileged change (security review H5/H7).
        summary = prune_expired_audit_events(
            session, dry_run=False, approved_change_id="pc-approved"
        )
        assert summary["audit_events_deleted"] == 1

        # The young row stays, and the prune is itself audited.
        remaining = {row.event_id: row.action for row in session.query(AuditEventRecord).all()}
        assert "audit-age-5" in remaining and "audit-age-2700" not in remaining
        assert "audit.retention.prune" in remaining.values()


def test_prune_rejects_unsafe_retention_window(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path.as_posix()}/audit.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        try:
            prune_expired_audit_events(session, retention_days=1)
            raise AssertionError("expected ValueError")
        except ValueError as exc:
            # Never below the configured retention, which is never below seven years.
            assert "between 2557" in str(exc) and "configured retention" in str(exc)
        # Nothing a regulation requires may be deleted by a setting: five years is refused.
        try:
            prune_expired_audit_events(session, retention_days=1827)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_the_setting_cannot_lower_audit_retention_below_seven_years(monkeypatch) -> None:
    from eurogas_nexus.application.audit_retention import RETENTION_ENV, configured_retention_days

    for value in ("30", "365", "1827"):
        monkeypatch.setenv(RETENTION_ENV, value)
        assert configured_retention_days() == 2557
    monkeypatch.setenv(RETENTION_ENV, "3000")
    assert configured_retention_days() == 3000


def test_prune_script_without_db_url_returns_2(monkeypatch) -> None:
    import scripts.ops.prune_audit_events as script

    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    assert script.main([]) == 2
    assert DEFAULT_AUDIT_RETENTION_DAYS == 2557  # seven years
