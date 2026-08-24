"""Audit event persistence tests (Gate 1)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.audit_service import record_audit_event
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord


def test_record_audit_event_persists_row_when_db_available(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "audit.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", f"sqlite+pysqlite:///{db_path.as_posix()}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    event_id = record_audit_event(
        event_type="governance.policy",
        action="entitlement.denied",
        resource="analysis_query",
        outcome="denied",
        severity="warning",
        detail="request_id=abc123; source=ICIS_Sim",
        source_system="analysis",
        request_id="abc123",
    )

    assert event_id is not None
    with Session(engine) as session:
        row = session.get(AuditEventRecord, event_id)
        assert row is not None
        assert row.action == "entitlement.denied"
        assert row.outcome == "denied"
        assert row.severity == "warning"
        assert "request_id=abc123" in row.detail
        assert row.human_review_required is True


def test_record_audit_event_noop_without_db(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    event_id = record_audit_event(
        event_type="governance.action",
        action="llm.invoke",
        resource="analysis_query",
        outcome="not_invoked",
    )

    assert event_id is None


def test_record_audit_event_never_raises_on_db_failure(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "RUNTIME_STORE_DATABASE_URL", "sqlite+pysqlite:///nonexistent-dir/x.sqlite"
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    event_id = record_audit_event(
        event_type="governance.action",
        action="report.generated",
        resource="generated_reports:r1",
        outcome="generated",
    )

    assert event_id is None
