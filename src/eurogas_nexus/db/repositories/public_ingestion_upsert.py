"""Idempotent persistence helpers for the public-source ingestion path.

Re-running public-source ingestion must converge to the same stored state:
the same natural-key rows, no duplicates, and no destructive wipes when a
provider payload is partial or empty.

Semantics:

- ``upsert_observation_rows`` performs a PostgreSQL ``INSERT ... ON CONFLICT
  (natural primary key) DO UPDATE`` and preserves ``observed_at_utc``, so a
  re-run records the first time the record was observed instead of drifting
  timestamps. Pipeline activity time stays in ``ingestion_runs`` (one row per
  run).
- ``replace_reference_snapshot`` replaces only the rows of one source system
  and only when the new payload is non-empty. An empty payload is treated as
  provider failure, not as evidence that the reference data became empty.

Both helpers run inside the caller's transaction and never commit.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

OBSERVATION_PRESERVED_COLUMNS = ("observed_at_utc",)
REFERENCE_PRESERVED_COLUMNS = ("created_at_utc",)


def upsert_observation_rows(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
) -> int:
    """Upsert observation rows by natural primary key with first-seen timestamps."""

    return _upsert_rows(session, model, rows, preserve_columns=OBSERVATION_PRESERVED_COLUMNS)


def replace_reference_snapshot(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
    *,
    source_system: str,
) -> int:
    """Replace one source system's snapshot of a reference table.

    An empty payload leaves existing rows untouched. Deletion is scoped to the
    given source system so operator-maintained rows are never wiped.
    """

    if not rows:
        return 0
    table = model.__table__
    source_column = table.columns.get("source_system")
    if source_column is None:
        raise ValueError(
            f"{table.name} has no source_system column; cannot scope the replace."
        )
    session.execute(
        delete(model).where(source_column == source_system),
        execution_options={"synchronize_session": False},
    )
    return _upsert_rows(session, model, rows, preserve_columns=REFERENCE_PRESERVED_COLUMNS)


def _upsert_rows(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
    *,
    preserve_columns: Collection[str],
) -> int:
    if not rows:
        return 0
    table = model.__table__
    primary_keys = [column.name for column in table.primary_key.columns]
    statement = pg_insert(table).values(rows)
    update_columns = {
        column.name: getattr(statement.excluded, column.name)
        for column in table.columns
        if column.name not in preserve_columns
    }
    statement = statement.on_conflict_do_update(
        index_elements=primary_keys,
        set_=update_columns,
    )
    session.execute(statement)
    return len(rows)
