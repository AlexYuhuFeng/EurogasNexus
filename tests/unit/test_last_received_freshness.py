"""Freshness reads "last received": a provider revision is a delivery (DATA_REVISIONS.md)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import StorageObservationRecord
from eurogas_nexus.db.repositories.observation_revisions import last_received_column

FIRST = datetime(2026, 11, 1, 6, tzinfo=UTC)
REVISED = datetime(2026, 11, 13, 9, tzinfo=UTC)


def _storage(observation_id, *, revised_at=None):
    return StorageObservationRecord(
        observation_id=observation_id,
        source_dataset="AGSI",
        facility_id="DE",
        facility_name="Germany",
        country="DE",
        inventory_twh=150.0,
        period_start_utc=FIRST - timedelta(days=1),
        period_end_utc=FIRST,
        observed_at_utc=FIRST,
        revised_at_utc=revised_at,
        source_system="GIE",
        source_reference="ref",
        freshness="daily",
        research_only=False,
    )


def _store(path):
    url = f"sqlite+pysqlite:///{path.as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([_storage("a"), _storage("b", revised_at=REVISED)])
        session.commit()
    return url, engine


def _utc(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def test_dataops_freshness_counts_a_revision_as_the_latest_delivery(tmp_path) -> None:
    from eurogas_nexus.application.dataops_runtime import _latest_observation_for

    _, engine = _store(tmp_path / "f.sqlite")
    with Session(engine) as session:
        assert _utc(_latest_observation_for(session, "GIE")) == REVISED


def test_sources_page_freshness_counts_a_revision(tmp_path, monkeypatch) -> None:
    from eurogas_nexus.api.routes.public.sources import _runtime_source_latest_observed

    url, _ = _store(tmp_path / "s.sqlite")
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    assert _utc(_runtime_source_latest_observed()["GIE"]) == REVISED


def test_provenance_summary_reports_last_received(tmp_path) -> None:
    from eurogas_nexus.db.repositories.data_platform import table_provenance_summary

    _, engine = _store(tmp_path / "p.sqlite")
    with Session(engine) as session:
        summary = table_provenance_summary(session, ["storage_observations"])
    assert _utc(summary["storage_observations"]["last_observed_at_utc"]) == REVISED


def test_first_seen_column_is_unchanged_for_point_in_time_reads(tmp_path) -> None:
    from sqlalchemy import func, select

    _, engine = _store(tmp_path / "x.sqlite")
    with Session(engine) as session:
        first_seen = session.execute(
            select(func.max(StorageObservationRecord.observed_at_utc))
        ).scalar()
        received = session.execute(
            select(func.max(last_received_column(StorageObservationRecord)))
        ).scalar()
    assert _utc(first_seen) == FIRST and _utc(received) == REVISED
