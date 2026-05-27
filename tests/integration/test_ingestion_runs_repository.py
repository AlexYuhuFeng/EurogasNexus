"""Integration checks for ingestion-run repository mapping."""

from datetime import UTC, datetime

from sqlalchemy.engine import create_mock_engine

from eurogas_nexus.db.models import IngestionRunRecord
from eurogas_nexus.db.repositories import SqlAlchemyIngestionRunRepository
from eurogas_nexus.db.session import create_session_factory


class _SessionDouble:
    def __init__(self, row: IngestionRunRecord) -> None:
        self._row = row

    def get(self, model: type[IngestionRunRecord], run_id: str) -> IngestionRunRecord | None:
        if model is not IngestionRunRecord:
            return None
        return self._row if self._row.run_id == run_id else None


def test_session_factory_and_repository_contract_integration() -> None:
    engine = create_mock_engine("postgresql+psycopg://", executor=lambda *args, **kwargs: None)
    session_factory = create_session_factory(engine)

    assert session_factory is not None

    row = IngestionRunRecord(
        run_id="run-42",
        source_name="integration-source",
        status="running",
        started_at_utc=datetime(2026, 5, 27, tzinfo=UTC),
        finished_at_utc=None,
        notes="integration-check",
    )

    repo = SqlAlchemyIngestionRunRepository(_SessionDouble(row))
    result = repo.get_by_id("run-42")

    assert result is not None
    assert result.run_id == "run-42"
    assert result.source_name == "integration-source"
    assert result.status == "running"
