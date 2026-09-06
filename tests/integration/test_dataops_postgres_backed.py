"""Data-operations PostgreSQL integration tests.

Run via ``scripts/ci/run_postgres_ci.sh`` (``RUNTIME_STORE_DATABASE_URL`` set).
These tests exercise real PostgreSQL scheduler claims, the partial unique
scheduled-run index, run finalization and issue persistence.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.dataops_runtime import scan_scheduler
from eurogas_nexus.db.models import (
    IngestionRunIssueRecord,
    IngestionRunRecord,
    SourceRuntimeStateRecord,
)
from eurogas_nexus.db.repositories import dataops as dataops_repository
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    FreshnessPolicy,
    IngestionRunStatus,
    QualityIssue,
    QualitySeverity,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceDefinition,
    SourceScheduleSpec,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL"),
    reason="RUNTIME_STORE_DATABASE_URL not configured; run via scripts/ci/run_postgres_ci.sh",
)


def _definition(source_id: str) -> SourceDefinition:
    return SourceDefinition(
        source_id=source_id,
        provider="PG_TEST",
        dataset="test",
        datasets=("test",),
        source_class=SourceClass.PUBLIC,
        access_mode=AccessMode.PUBLIC_HTTP,
        schedulable=True,
        enabled_default=True,
        schedule=SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=3600,
        ),
        freshness_policy=FreshnessPolicy(60, 120, 360),
        calendar=SourceCalendar.ALWAYS_OPEN,
        adapter_version="pg-test/1",
    )


def test_scheduler_claim_finalize_and_unique_index() -> None:
    source_id = "src-pg-dataops"
    definition = _definition(source_id)
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC).replace(microsecond=0)

    with Session(engine) as session:
        state = dataops_repository.ensure_source_runtime_state(
            session, definition, now_utc=now
        )
        state.enabled = True
        state.next_run_at_utc = now
        session.commit()

    with Session(engine) as session:
        claims = dataops_repository.claim_due_sources(
            session, (definition,), now_utc=now + timedelta(seconds=1), limit=10
        )
        assert len(claims) == 1
        _state, run = claims[0]
        assert run.trigger_type == "SCHEDULED"
        run_id = run.run_id
        dataops_repository.finalize_run(
            session,
            run,
            definition,
            succeeded=True,
            rows_received=2,
            rows_accepted=2,
            rows_inserted=2,
            lineage_refs=["pg-test:lineage"],
            now_utc=now + timedelta(seconds=2),
        )
        session.commit()

    with Session(engine) as session:
        row = session.get(IngestionRunRecord, run_id)
        assert row.status == IngestionRunStatus.SUCCEEDED.value
        assert row.lineage_refs == ["pg-test:lineage"]
        state = session.get(SourceRuntimeStateRecord, source_id)
        assert state.circuit_state == "HEALTHY"
        assert state.last_success_at_utc is not None
        session.commit()

    # Clean the fixture rows so repeat CI runs remain deterministic.
    with Session(engine) as session:
        session.query(IngestionRunRecord).filter(
            IngestionRunRecord.source_id == source_id
        ).delete()
        session.get(SourceRuntimeStateRecord, source_id)
        session.query(SourceRuntimeStateRecord).filter(
            SourceRuntimeStateRecord.source_id == source_id
        ).delete()
        session.commit()


def test_issue_persistence_against_postgresql() -> None:
    source_id = "src-pg-dataops-issues"
    definition = _definition(source_id)
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC).replace(microsecond=0)

    with Session(engine) as session:
        state = dataops_repository.ensure_source_runtime_state(
            session, definition, now_utc=now
        )
        state.enabled = True
        state.next_run_at_utc = now
        session.flush()
        claims = dataops_repository.claim_due_sources(
            session, (definition,), now_utc=now, limit=10
        )
        _state, run = claims[0]
        issue = QualityIssue(
            quality_code="OUTLIER",
            severity=QualitySeverity.WARNING,
            field="price",
            observation_reference="pg-obs-1",
            message="WARNING/REVIEW only",
        )
        dataops_repository.record_quality_issues(session, run.run_id, (issue,))
        run_id = run.run_id
        session.commit()

    with Session(engine) as session:
        issues = dataops_repository.list_run_issues(session, run_id)
        assert issues[0]["quality_code"] == "OUTLIER"
        run_ids = [
            row.run_id
            for row in session.query(IngestionRunRecord.run_id)
            .filter(IngestionRunRecord.source_id == source_id)
            .all()
        ]
        if run_ids:
            session.query(IngestionRunIssueRecord).filter(
                IngestionRunIssueRecord.run_id.in_(run_ids)
            ).delete(synchronize_session=False)
        session.query(IngestionRunRecord).filter(
            IngestionRunRecord.source_id == source_id
        ).delete(synchronize_session=False)
        session.query(SourceRuntimeStateRecord).filter(
            SourceRuntimeStateRecord.source_id == source_id
        ).delete()
        session.commit()


def test_scan_scheduler_heartbeat_against_postgresql() -> None:
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    with Session(engine) as session:
        result = scan_scheduler(session, now_utc=datetime.now(UTC))
        assert result["heartbeat"]["last_heartbeat_at_utc"] is not None
        session.commit()
