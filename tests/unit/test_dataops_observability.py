"""Prometheus exporter tests for the shared ingestion-run status vocabulary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.dataops_observability import prometheus_metrics
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IngestionRunRecord


def _sample_value(text: str, metric: str) -> str:
    """Return the unlabelled sample value of ``metric`` from the exposition."""

    prefix = f"{metric} "
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    raise AssertionError(f"{metric} not found in exposition:\n{text}")


def test_failure_metric_counts_canonical_and_legacy_failures_once_each() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    base = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    statuses = [
        "FAILED",
        "failed",
        "SUCCEEDED",
        "succeeded",
        "SUCCEEDED_WITH_WARNINGS",
        "RUNNING",
        "CANCELLED",
        "BLOCKED",
    ]

    with Session(engine) as session:
        for index, status in enumerate(statuses):
            started = base + timedelta(minutes=index)
            session.add(
                IngestionRunRecord(
                    run_id=f"run-{index}",
                    source_name="ECB",
                    status=status,
                    started_at_utc=started,
                    finished_at_utc=started,
                    notes="probe",
                )
            )
        session.commit()
        text = prometheus_metrics(session, now_utc=base + timedelta(minutes=10))

    assert _sample_value(text, "eurogas_ingestion_runs_total") == "8"
    # Canonical FAILED and legacy failed are the same failure outcome; pending,
    # cancelled, warning-qualified success and unknown stored values are not.
    assert _sample_value(text, "eurogas_ingestion_failures_total") == "2"
    assert (
        "# HELP eurogas_ingestion_failures_total Persisted ingestion runs "
        "classified as failed." in text
    )
