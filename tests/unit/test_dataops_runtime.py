"""CR-09 scheduler/runtime/retry/quality persistence tests (SQLite)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.dataops_runtime import (
    IngestionAttemptResult,
    execute_claimed_runs,
    scan_scheduler,
    set_source_enabled,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IngestionRunRecord, SourceRuntimeStateRecord
from eurogas_nexus.db.repositories import dataops as dataops_repository
from eurogas_nexus.domain.dataops.contracts import (
    AccessMode,
    CircuitPolicy,
    CircuitState,
    FailureCategory,
    FreshnessPolicy,
    FreshnessState,
    IngestionRunStatus,
    QualityIssue,
    QualitySeverity,
    RetryPolicy,
    ScheduleType,
    SourceCalendar,
    SourceClass,
    SourceDefinition,
    SourceScheduleSpec,
)
from eurogas_nexus.domain.dataops.quality import summarize_quality
from eurogas_nexus.domain.dataops.registry import source_definitions

NOW = datetime(2026, 7, 6, 10, 0, tzinfo=UTC)  # Monday


def _test_definition(
    *,
    source_id: str = "src-test",
    interval_seconds: int = 3600,
    enabled_default: bool = True,
    retry_max: int = 3,
) -> SourceDefinition:
    return SourceDefinition(
        source_id=source_id,
        provider="TEST",
        dataset="test",
        datasets=("test",),
        source_class=SourceClass.PUBLIC,
        access_mode=AccessMode.PUBLIC_HTTP,
        schedulable=True,
        enabled_default=enabled_default,
        schedule=SourceScheduleSpec(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=interval_seconds,
        ),
        freshness_policy=FreshnessPolicy(60, 120, 360),
        retry_policy=RetryPolicy(retry_max=retry_max, backoff_seconds=0.001),
        circuit_policy=CircuitPolicy(
            degraded_after_failures=3,
            open_after_failures=6,
            recovery_probe_after_seconds=900,
        ),
        calendar=SourceCalendar.ALWAYS_OPEN,
        adapter_version="test-adapter/1",
    )


@pytest.fixture()
def engine(tmp_path):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'dataops.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    return engine


def _queue_run(
    session: Session,
    definition: SourceDefinition,
    when: datetime,
) -> IngestionRunRecord:
    state = dataops_repository.ensure_source_runtime_state(
        session, definition, now_utc=when
    )
    state.enabled = True
    state.next_run_at_utc = when
    session.flush()
    claims = dataops_repository.claim_due_sources(
        session, (definition,), now_utc=when, limit=10
    )
    assert len(claims) == 1
    return claims[0][1]


def test_source_is_scheduled_once_and_not_duplicated(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        initialized = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW,
        )
        assert initialized["claimed_runs"] == []
        session.commit()

    with Session(engine) as session:
        first = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW + timedelta(minutes=61),
        )
        assert len(first["claimed_runs"]) == 1
        session.commit()

    with Session(engine) as session:
        second = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW + timedelta(minutes=61, seconds=1),
        )
        assert second["claimed_runs"] == []
        session.commit()


def test_future_source_is_not_run_early(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        result = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW,
        )
        assert result["claimed_runs"] == []


def test_disabled_source_is_not_run(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        dataops_repository.ensure_source_runtime_state(
            session, definition, now_utc=NOW
        )
        set_source_enabled(
            session,
            source_id=definition.source_id,
            enabled=False,
            now_utc=NOW,
            definitions=(definition,),
        )
        session.commit()
    with Session(engine) as session:
        result = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW + timedelta(hours=2),
        )
        assert result["claimed_runs"] == []


def test_restart_recovery_marks_stale_run_failed_and_claims_again(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        run = _queue_run(session, definition, NOW)
        run_id = run.run_id
        run.status = IngestionRunStatus.RUNNING.value
        run.started_at_utc = NOW - timedelta(hours=1)
        state = session.get(SourceRuntimeStateRecord, definition.source_id)
        state.next_run_at_utc = NOW + timedelta(minutes=61)
        session.commit()
    with Session(engine) as session:
        result = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW + timedelta(minutes=90),
        )
        assert result["recovered_stale_runs"] == 1
        assert len(result["claimed_runs"]) == 1
        stale = session.get(IngestionRunRecord, run_id)
        assert stale.status == IngestionRunStatus.FAILED.value
        assert stale.error_code == "STALE_RUN"


def test_retryable_failure_retries_then_succeeds(engine) -> None:
    definition = _test_definition()
    calls: list[int] = []

    def runner(payload: dict, attempt: int) -> IngestionAttemptResult:
        calls.append(attempt)
        if attempt < 2:
            return IngestionAttemptResult(
                succeeded=False,
                classification=FailureCategory.NETWORK_TRANSIENT,
                error_message="timeout",
            )
        return IngestionAttemptResult(
            succeeded=True,
            rows_received=3,
            rows_accepted=3,
            rows_inserted=3,
            lineage_refs=["test-run:lineage"],
        )

    with Session(engine) as session:
        run = _queue_run(session, definition, NOW)
        run_id = run.run_id
        session.commit()
    with Session(engine) as session:
        result = execute_claimed_runs(
            session,
            runner=runner,
            definitions=(definition,),
            now_utc=NOW + timedelta(seconds=1),
            sleeper=lambda _seconds: None,
        )
        session.commit()

    assert calls == [1, 2]
    outcome = result["outcomes"][0]
    assert outcome["attempts"] == 2
    with Session(engine) as session:
        row = session.get(IngestionRunRecord, run_id)
        assert row.status == IngestionRunStatus.SUCCEEDED.value
        assert row.lineage_refs == ["test-run:lineage"]


def test_authentication_failure_does_not_retry_endlessly(engine) -> None:
    definition = _test_definition()
    calls: list[int] = []

    def runner(payload: dict, attempt: int) -> IngestionAttemptResult:
        calls.append(attempt)
        return IngestionAttemptResult(
            succeeded=False,
            classification=FailureCategory.AUTHENTICATION,
            error_message="invalid credential",
        )

    with Session(engine) as session:
        run = _queue_run(session, definition, NOW)
        run_id = run.run_id
        session.commit()
    with Session(engine) as session:
        execute_claimed_runs(
            session,
            runner=runner,
            definitions=(definition,),
            now_utc=NOW + timedelta(seconds=1),
            sleeper=lambda _seconds: None,
        )
        session.commit()

    assert calls == [1]
    with Session(engine) as session:
        row = session.get(IngestionRunRecord, run_id)
        assert row.status == IngestionRunStatus.FAILED.value
        assert row.error_category == FailureCategory.AUTHENTICATION.value


def test_schema_change_stops_correctly(engine) -> None:
    definition = _test_definition()
    calls: list[int] = []

    def runner(payload: dict, attempt: int) -> IngestionAttemptResult:
        calls.append(attempt)
        return IngestionAttemptResult(
            succeeded=False,
            classification=FailureCategory.SCHEMA_CHANGED,
            error_message="unknown field",
        )

    with Session(engine) as session:
        run = _queue_run(session, definition, NOW)
        run_id = run.run_id
        session.commit()
    with Session(engine) as session:
        execute_claimed_runs(
            session,
            runner=runner,
            definitions=(definition,),
            now_utc=NOW + timedelta(seconds=1),
            sleeper=lambda _seconds: None,
        )
        session.commit()

    assert calls == [1]
    with Session(engine) as session:
        row = session.get(IngestionRunRecord, run_id)
        assert row.error_category == FailureCategory.SCHEMA_CHANGED.value


def test_circuit_opens_then_recovery_probe_uses_recovery_trigger(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        state = dataops_repository.ensure_source_runtime_state(
            session, definition, now_utc=NOW
        )
        state.enabled = True
        state.next_run_at_utc = NOW
        session.commit()

    for index in range(6):
        with Session(engine) as session:
            state = session.get(SourceRuntimeStateRecord, definition.source_id)
            state.next_run_at_utc = NOW + timedelta(minutes=index)
            session.flush()
            claims = dataops_repository.claim_due_sources(
                session, (definition,), now_utc=NOW + timedelta(minutes=index), limit=10
            )
            assert len(claims) == 1
            _state, run = claims[0]
            dataops_repository.finalize_run(
                session,
                run,
                definition,
                classification=__import__(
                    "eurogas_nexus.domain.dataops.retry", fromlist=["classify_failure"]
                ).classify_failure(error=None, status_code=503),
                now_utc=NOW + timedelta(minutes=index),
                succeeded=False,
            )
            session.commit()

    with Session(engine) as session:
        state = session.get(SourceRuntimeStateRecord, definition.source_id)
        assert state.circuit_state == CircuitState.OPEN_CIRCUIT.value
        assert state.consecutive_failures == 6
        state.next_run_at_utc = NOW + timedelta(hours=1)
        session.commit()

    with Session(engine) as session:
        before_probe = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW + timedelta(minutes=10),
        )
        assert before_probe["claimed_runs"] == []

    with Session(engine) as session:
        after_probe = scan_scheduler(
            session,
            definitions=(definition,),
            now_utc=NOW + timedelta(minutes=21),
        )
        assert len(after_probe["claimed_runs"]) == 1
        run = session.get(IngestionRunRecord, after_probe["claimed_runs"][0])
        assert run.trigger_type == "RECOVERY"


def test_success_resets_consecutive_failures(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        state = dataops_repository.ensure_source_runtime_state(
            session, definition, now_utc=NOW
        )
        state.enabled = True
        state.consecutive_failures = 4
        state.circuit_state = CircuitState.DEGRADED.value
        state.next_run_at_utc = NOW
        session.commit()
    with Session(engine) as session:
        claims = dataops_repository.claim_due_sources(
            session, (definition,), now_utc=NOW, limit=10
        )
        _state, run = claims[0]
        dataops_repository.finalize_run(
            session,
            run,
            definition,
            succeeded=True,
            now_utc=NOW,
        )
        state = session.get(SourceRuntimeStateRecord, definition.source_id)
        assert state.circuit_state == CircuitState.HEALTHY.value
        assert state.consecutive_failures == 0
        assert state.last_success_at_utc is not None


def test_quality_issues_and_lineage_are_persisted(engine) -> None:
    definition = _test_definition()
    issue = QualityIssue(
        quality_code="OUTLIER",
        severity=QualitySeverity.WARNING,
        field="price",
        observation_reference="obs-1",
        message="WARNING/REVIEW only",
    )
    with Session(engine) as session:
        run = _queue_run(session, definition, NOW)
        dataops_repository.record_quality_issues(session, run.run_id, (issue,))
        dataops_repository.finalize_run(
            session,
            run,
            definition,
            quality_result=summarize_quality((issue,)).result,
            quality_warning_count=1,
            rows_received=1,
            rows_accepted=1,
            rows_inserted=1,
            lineage_refs=["raw:test-payload", "run:test"],
            now_utc=NOW,
        )
        session.commit()
        run_id = run.run_id
    with Session(engine) as session:
        row = session.get(IngestionRunRecord, run_id)
        issues = dataops_repository.list_run_issues(session, run_id)
        assert row.status == IngestionRunStatus.SUCCEEDED_WITH_WARNINGS.value
        assert row.lineage_refs == ["raw:test-payload", "run:test"]
        assert issues[0]["quality_code"] == "OUTLIER"


def test_registered_schedulable_sources_reconcile_without_network(engine) -> None:
    with Session(engine) as session:
        result = scan_scheduler(
            session,
            definitions=source_definitions(),
            now_utc=NOW,
        )
        assert result["heartbeat"]["sources_scheduled"] >= 2
        states = session.query(SourceRuntimeStateRecord).all()
        assert {state.source_id for state in states} >= {"src-ecb", "src-entsog"}


def test_freshness_state_is_persisted_from_backend_evidence(engine) -> None:
    definition = _test_definition()
    with Session(engine) as session:
        run = _queue_run(session, definition, NOW - timedelta(hours=2))
        dataops_repository.finalize_run(
            session,
            run,
            definition,
            succeeded=True,
            now_utc=NOW - timedelta(hours=2),
        )
        state = session.get(SourceRuntimeStateRecord, definition.source_id)
        assert state.freshness_state == FreshnessState.FRESH.value
        session.commit()
    with Session(engine) as session:
        state = session.get(SourceRuntimeStateRecord, definition.source_id)
        # Re-evaluation happens in source_health; persisted state is not rewritten
        # historically, which is the documented invalidation boundary.
        from eurogas_nexus.domain.dataops.contracts import as_utc

        assert as_utc(state.last_success_at_utc) == NOW - timedelta(hours=2)
