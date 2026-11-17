"""Per-process memory of which tables (and their columns) exist in a runtime store.

Reads such as ``GET /api/sources`` asked the database catalogue whether each table exists
and which columns it has on every request: 60 of its 138 statements (2026-11-17). The schema
of a running store only grows, and only through a migration, which restarts the service; so
a table found once is remembered with its columns for the life of the process, per engine.
A table not found is never remembered, so a store migrated later is seen at the next read.
"""

from __future__ import annotations

import threading
import weakref
from typing import Any

_LOCK = threading.Lock()
#: (engine id, url, table) -> (the engine, weakly, so a reused id is never mistaken; columns)
_KNOWN: dict[tuple[int, str, str], tuple[Any, frozenset[str]]] = {}


def _engine(session_or_connection: Any):
    bind = session_or_connection.get_bind() if hasattr(session_or_connection, "get_bind") else (
        session_or_connection.engine
    )
    return getattr(bind, "engine", bind)


def table_columns(session, table: str) -> frozenset[str] | None:
    """The table's column names, or ``None`` when the table does not exist (not cached)."""

    from sqlalchemy import inspect

    engine = _engine(session)
    key = (id(engine), str(engine.url), table)
    with _LOCK:
        known = _KNOWN.get(key)
    if known is not None and known[0]() is engine:
        return known[1]
    connection = session.connection() if hasattr(session, "connection") else session
    inspector = inspect(connection)
    if not inspector.has_table(table):
        return None
    columns = frozenset(column["name"] for column in inspector.get_columns(table))
    with _LOCK:
        _KNOWN[key] = (weakref.ref(engine), columns)
    return columns


def has_table(session, table: str) -> bool:
    return table_columns(session, table) is not None


def forget() -> None:
    """Drop every remembered table (tests that change a schema under a live engine)."""

    with _LOCK:
        _KNOWN.clear()
