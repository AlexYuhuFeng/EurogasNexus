"""Pipeline health aggregation tests."""

from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.pipeline_health import (
    empty_pipeline_health,
    pipeline_health,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IngestionRunRecord


def test_empty_pipeline_health_shape() -> None:
    data = empty_pipeline_health()
    assert data["sources"] == []
    assert data["quote_freshness"] == {}
    assert data["open_alerts"] == 0
    assert data["latest_opportunity_detected_at_utc"] is None


def test_pipeline_health_aggregates_empty_db() -> None:
    session = MagicMock()
    query = MagicMock()
    session.query.return_value = query
    query.order_by.return_value.limit.return_value.all.return_value = []
    query.order_by.return_value.first.return_value = None
    query.filter.return_value.all.return_value = []
    query.filter.return_value.count.return_value = 0

    data = pipeline_health(session)

    assert data["sources"] == []
    assert data["quote_freshness"] == {}
    assert data["open_alerts"] == 0
    assert data["latest_opportunity_detected_at_utc"] is None
    assert data["generated_at_utc"]


def test_pipeline_health_counts_mixed_status_spellings_and_keeps_raw_status() -> None:
    """``FAILED`` and legacy ``failed`` count identically; raw status stays raw."""

    from datetime import UTC, datetime, timedelta

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    base = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
    runs = [
        ("ECB", "run-ecb-3", "FAILED", 3),
        ("ECB", "run-ecb-2", "failed", 2),
        ("ECB", "run-ecb-1", "SUCCEEDED", 1),
        ("ENTSOG", "run-entsog-3", "failed", 3),
        ("ENTSOG", "run-entsog-2", "FAILED", 2),
        ("ENTSOG", "run-entsog-1", "FAILED", 1),
        ("GIE", "run-gie-2", "SUCCEEDED_WITH_WARNINGS", 2),
        ("GIE", "run-gie-1", "FAILED", 1),
        ("BBL", "run-bbl-2", "MYSTERY", 2),
        ("BBL", "run-bbl-1", "failed", 1),
        ("IUK", "run-iuk-2", "CANCELLED", 2),
        ("IUK", "run-iuk-1", "FAILED", 1),
    ]

    with Session(engine) as session:
        for source_name, run_id, status, minute in runs:
            started = base + timedelta(minutes=minute)
            session.add(
                IngestionRunRecord(
                    run_id=run_id,
                    source_name=source_name,
                    status=status,
                    started_at_utc=started,
                    finished_at_utc=started,
                    notes="probe",
                )
            )
        session.commit()
        data = pipeline_health(session, now_utc=base + timedelta(minutes=10))

    by_source = {entry["source_name"]: entry for entry in data["sources"]}
    assert by_source["ECB"]["consecutive_failures"] == 2
    assert by_source["ECB"]["status"] == "FAILED"
    assert by_source["ENTSOG"]["consecutive_failures"] == 3
    assert by_source["ENTSOG"]["status"] == "failed"
    # Success, warning-qualified success, unknown and cancelled are not
    # failures; each interrupts the streak behind it.
    assert by_source["GIE"]["consecutive_failures"] == 0
    assert by_source["GIE"]["status"] == "SUCCEEDED_WITH_WARNINGS"
    assert by_source["BBL"]["consecutive_failures"] == 0
    assert by_source["BBL"]["status"] == "MYSTERY"
    assert by_source["IUK"]["consecutive_failures"] == 0
    assert by_source["IUK"]["status"] == "CANCELLED"
