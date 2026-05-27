"""Contract tests for milestone 3 persistence slice."""

from datetime import UTC, datetime

from eurogas_nexus.db.models import IngestionRunRecord
from eurogas_nexus.db.repositories import (
    IngestionRun,
    IngestionRunRepository,
    SqlAlchemyIngestionRunRepository,
)


class _FakeSession:
    def __init__(self, row: IngestionRunRecord | None) -> None:
        self._row = row

    def get(self, model: type[IngestionRunRecord], run_id: str) -> IngestionRunRecord | None:
        if self._row is None:
            return None
        if model is not IngestionRunRecord:
            return None
        return self._row if self._row.run_id == run_id else None


def test_ingestion_run_record_tablename_contract() -> None:
    assert IngestionRunRecord.__tablename__ == "ingestion_runs"


def test_sqlalchemy_repository_maps_row_to_domain_payload() -> None:
    row = IngestionRunRecord(
        run_id="run-1",
        source_name="fixture-source",
        status="queued",
        started_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at_utc=None,
        notes="bootstrap",
    )
    repo = SqlAlchemyIngestionRunRepository(_FakeSession(row))

    result = repo.get_by_id("run-1")

    assert isinstance(result, IngestionRun)
    assert result is not None
    assert result.run_id == "run-1"
    assert result.source_name == "fixture-source"


def test_repository_protocol_shape() -> None:
    assert hasattr(IngestionRunRepository, "get_by_id")
