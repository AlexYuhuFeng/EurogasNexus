"""Database package exports (import-safe)."""

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.engine import create_db_engine
from eurogas_nexus.db.health import (
    DbConnectivityStatus,
    DbRuntimeStatus,
    check_db_connectivity,
    check_db_health,
    get_alembic_revision,
)
from eurogas_nexus.db.models import IngestionRunRecord
from eurogas_nexus.db.registry import (
    REQUIRED_TABLES,
    RequiredTable,
    get_metadata,
    list_missing_required_tables,
    list_required_tables,
    required_table_names,
)
from eurogas_nexus.db.repositories import (
    IngestionRun,
    IngestionRunRepository,
    SqlAlchemyIngestionRunRepository,
)
from eurogas_nexus.db.session import (
    create_session_factory,
    get_engine,
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.db.settings import DatabaseSettings

__all__ = [
    "Base",
    "DatabaseSettings",
    "DbConnectivityStatus",
    "DbRuntimeStatus",
    "REQUIRED_TABLES",
    "RequiredTable",
    "check_db_connectivity",
    "check_db_health",
    "create_db_engine",
    "create_session_factory",
    "get_alembic_revision",
    "get_engine",
    "get_metadata",
    "get_session_factory",
    "IngestionRun",
    "IngestionRunRecord",
    "IngestionRunRepository",
    "list_missing_required_tables",
    "list_required_tables",
    "redact_database_url",
    "required_table_names",
    "resolve_database_url",
    "SqlAlchemyIngestionRunRepository",
]
