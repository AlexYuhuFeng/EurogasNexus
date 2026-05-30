"""Runtime DB health checks (read-only, operator-invoked only)."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine, text

from eurogas_nexus.db.registry import REQUIRED_TABLES
from eurogas_nexus.db.session import get_engine, redact_database_url, resolve_database_url


@dataclass(frozen=True)
class DbConnectivityStatus:
    """Result of an explicit DB connectivity check."""

    ok: bool
    database_url_present: bool
    redacted_database_url: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class DbRuntimeStatus:
    """Snapshot of DB runtime health — never contains a full DSN."""

    reachable: bool
    redacted_dsn: str
    current_revision: str | None = None
    missing_tables: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _redact_dsn(dsn: str) -> str:
    """Return a safe-for-logging DSN with password replaced."""
    if "@" not in dsn:
        return dsn
    if "://" in dsn:
        scheme, _, rest = dsn.partition("://")
        _, _, host_db = rest.partition("@")
        return f"{scheme}://****@{host_db}"
    prefix, _, rest = dsn.partition("@")
    return f"{prefix.split(':')[0]}:****@{rest}"


def _safe_error_message(exc: Exception, database_url: str, redacted_url: str | None) -> str:
    message = f"{exc.__class__.__name__}: {exc}"
    if redacted_url:
        message = message.replace(database_url, redacted_url)
    return message


def check_db_connectivity(database_url: str | None = None) -> DbConnectivityStatus:
    """Run a read-only `SELECT 1` check when a DB URL is explicitly available."""

    resolved_url = database_url.strip() if database_url else resolve_database_url()
    if not resolved_url:
        return DbConnectivityStatus(
            ok=False,
            database_url_present=False,
            error="Database URL is missing.",
        )

    redacted_url = redact_database_url(resolved_url)
    engine = None
    try:
        engine = get_engine(resolved_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        return DbConnectivityStatus(
            ok=True,
            database_url_present=True,
            redacted_database_url=redacted_url,
        )
    except Exception as exc:
        return DbConnectivityStatus(
            ok=False,
            database_url_present=True,
            redacted_database_url=redacted_url,
            error=_safe_error_message(exc, resolved_url, redacted_url),
        )
    finally:
        if engine is not None:
            engine.dispose()


def get_alembic_revision(database_url: str | None = None) -> str | None:
    """Read the Alembic revision if the version table exists."""

    resolved_url = database_url.strip() if database_url else resolve_database_url()
    if not resolved_url:
        return None

    engine = None
    try:
        engine = get_engine(resolved_url)
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none()
        return str(revision) if revision else None
    except Exception:
        return None
    finally:
        if engine is not None:
            engine.dispose()


def check_db_health(engine: Engine) -> DbRuntimeStatus:
    """Read-only DB health check. Never writes, never prints the full DSN."""
    redacted = _redact_dsn(str(engine.url))
    errors: list[str] = []
    revision: str | None = None
    missing: list[str] = []
    reachable = False

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        reachable = True
    except Exception as exc:
        errors.append(f"connectivity check failed: {exc}")
        return DbRuntimeStatus(reachable=False, redacted_dsn=redacted, errors=errors)

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            ).first()
            if row is not None:
                revision = row[0]
    except Exception as exc:
        errors.append(f"alembic_version query failed: {exc}")

    try:
        with engine.connect() as conn:
            existing = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public'"
                    )
                )
            }
        missing = [t.name for t in REQUIRED_TABLES if t.name not in existing]
    except Exception as exc:
        errors.append(f"table inspection failed: {exc}")

    return DbRuntimeStatus(
        reachable=reachable,
        redacted_dsn=redacted,
        current_revision=revision,
        missing_tables=missing,
        errors=errors,
    )
