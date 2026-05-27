"""Database package exports (import-safe)."""

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.engine import create_db_engine
from eurogas_nexus.db.models import IngestionRunRecord
from eurogas_nexus.db.repositories import (
    IngestionRun,
    IngestionRunRepository,
    SqlAlchemyIngestionRunRepository,
)
from eurogas_nexus.db.session import create_session_factory
from eurogas_nexus.db.settings import DatabaseSettings

__all__ = [
    "Base",
    "DatabaseSettings",
    "create_db_engine",
    "create_session_factory",
    "IngestionRun",
    "IngestionRunRecord",
    "IngestionRunRepository",
    "SqlAlchemyIngestionRunRepository",
]
