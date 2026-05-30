"""Repository boundary for DB-backed runtime metadata."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import IngestionRunRecord


@dataclass(frozen=True)
class IngestionRun:
    """Domain-safe ingestion run metadata payload."""

    run_id: str
    source_name: str
    status: str
    started_at_utc: datetime
    finished_at_utc: datetime | None = None
    notes: str | None = None


class IngestionRunRepository(Protocol):
    """Repository abstraction for ingestion run metadata."""

    def get_by_id(self, run_id: str) -> IngestionRun | None: ...


class SqlAlchemyIngestionRunRepository:
    """SQLAlchemy adapter implementing ingestion run repository contract."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, run_id: str) -> IngestionRun | None:
        row = self._session.get(IngestionRunRecord, run_id)
        if row is None:
            return None

        return IngestionRun(
            run_id=row.run_id,
            source_name=row.source_name,
            status=row.status,
            started_at_utc=row.started_at_utc,
            finished_at_utc=row.finished_at_utc,
            notes=row.notes,
        )


__all__ = [
    "IngestionRun",
    "IngestionRunRepository",
    "SqlAlchemyIngestionRunRepository",
]
