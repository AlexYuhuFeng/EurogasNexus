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
- ``upsert_revision_safe_observation_rows`` is the GIE-scoped append-or-verify
  path: a new natural key is inserted, a semantically unchanged existing row is
  left untouched, and a semantically revised existing row is refused with
  :class:`GieRevisionRequiresHistoryError` instead of overwriting it. The
  generic upsert above keeps its documented in-place-revision limitation for the
  other sources and is deliberately not changed here.
- ``replace_reference_snapshot`` replaces only the rows of one source system
  and only when the new payload is non-empty. An empty payload is treated as
  provider failure, not as evidence that the reference data became empty.

Both helpers run inside the caller's transaction and never commit.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

OBSERVATION_PRESERVED_COLUMNS = ("observed_at_utc",)
REFERENCE_PRESERVED_COLUMNS = ("created_at_utc",)

#: Canonical GIE observation column families. ``source_system`` is also compared
#: so a row that has drifted to another source identity is treated as changed
#: content rather than silently kept. ``observed_at_utc`` and every poll-owned
#: receipt/run/archive field are deliberately **excluded**: an unchanged poll
#: keeps the stored first-seen instant and original lineage, so a fresh receipt is
#: never mistaken for a revised measurement.
GIE_SEMANTIC_FIELDS: dict[str, tuple[str, ...]] = {
    "storage_observations": (
        "source_system",
        "source_dataset",
        "facility_id",
        "facility_name",
        "country",
        "inventory_twh",
        "working_capacity_twh",
        "fill_pct",
        "injection_twh_d",
        "withdrawal_twh_d",
        "period_start_utc",
        "period_end_utc",
    ),
    "lng_observations": (
        "source_system",
        "source_dataset",
        "terminal_id",
        "terminal_name",
        "country",
        "inventory_twh",
        "send_out_twh_d",
        "dtmi_twh",
        "period_start_utc",
        "period_end_utc",
    ),
}


class GieRevisionRequiresHistoryError(RuntimeError):
    """A GIE natural key already exists with different semantic content.

    Until append-only revision history and revision-aware selectors exist, a
    revised provider measurement must never overwrite the original row: doing so
    projects the new value back to the original first-seen observation instant
    (lookahead). The batch is refused as a whole; the error message carries only
    the source, dataset, counts and observation ids, never provider payload text.
    """

    code = "gie_revision_requires_history"


class GieRevisionRaceError(RuntimeError):
    """A concurrent write could not be confirmed as ours or as an existing row.

    The helper saw an ``ON CONFLICT DO NOTHING`` that neither inserted the row nor
    resolved to a readable existing row. Counting that as an insert would report a
    phantom row, so the batch fails closed instead of booking an unconfirmed
    write.
    """

    code = "gie_revision_race_unresolved"


def upsert_observation_rows(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
) -> int:
    """Upsert observation rows by natural primary key with first-seen timestamps."""

    return _upsert_rows(session, model, rows, preserve_columns=OBSERVATION_PRESERVED_COLUMNS)


def upsert_revision_safe_observation_rows(
    session: Session,
    model: Any,
    rows: list[dict[str, Any]],
    *,
    semantic_fields: Iterable[str] | None = None,
) -> dict[str, int]:
    """Append-or-verify GIE observation rows without revising existing content.

    For every incoming row, keyed by the table's natural primary key:

    * key absent -> the row is inserted with its own first-seen instant and its
      own exact archive/receipt lineage;
    * key present and every semantic column equal -> the existing row is left
      **byte-for-byte unchanged** (original ``observed_at_utc``, original
      ``source_reference``, original ``metadata_json``); the caller's newer
      poll metadata is not merged into it, so unchanged probes never churn the
      stored row;
    * key present with any semantic column different -> the whole batch is
      refused with :class:`GieRevisionRequiresHistoryError`, and because the
      caller runs this inside a savepoint the original rows survive untouched.

    Concurrency: the insert is ``ON CONFLICT DO NOTHING`` and the comparison
    reads the row ``FOR UPDATE``, so two concurrent ingests of the same natural
    key serialize on the row lock. The loser either sees the winner's committed
    row (unchanged -> verified, changed -> refused) or re-inserts it if the
    winner rolled back; no lost update is possible and no external lock service
    is required.

    Args:
        session: Caller-owned session; the caller owns the transaction/savepoint.
        model: Observation ORM model (``StorageObservationRecord`` /
            ``LngObservationRecord``).
        rows: Normalized row dicts already carrying their exact archive lineage.
        semantic_fields: Override of the compared semantic columns; defaults to
            :data:`GIE_SEMANTIC_FIELDS` for the model's table.

    Returns:
        ``{"inserted": n, "unchanged": m}`` counts for the batch.

    Raises:
        GieRevisionRequiresHistoryError: An existing natural key carries
            different semantic content.
        ValueError: ``rows`` is empty, repeats a natural key, or the model has
            no declarable semantic field set.
    """

    if not rows:
        raise ValueError("rows must not be empty")

    table = model.__table__
    key_columns = [column.name for column in table.primary_key.columns]
    fields = _resolve_semantic_fields(table, semantic_fields)

    seen_keys: set[tuple[Any, ...]] = set()
    inserted = 0
    unchanged = 0
    for row in rows:
        key = tuple(_key_value(row, name, table) for name in key_columns)
        if key in seen_keys:
            raise ValueError(
                f"{table.name} batch repeats natural key {key!r}; refusing a batch "
                "that is not a set of distinct observations."
            )
        seen_keys.add(key)

        existing = _select_existing_for_update(session, table, key_columns, key)
        if existing is None:
            # ``ON CONFLICT DO NOTHING`` reports whether the row was actually
            # inserted. A conflict means a concurrent ingest committed the same
            # natural key between our read and this insert; that row must be
            # re-read (now locked) and compared, never counted as a fresh insert.
            if _insert_if_absent(session, table, row):
                inserted += 1
                continue
            existing = _select_existing_for_update(session, table, key_columns, key)
            if existing is None:
                # The conflicting transaction rolled back after all, so retry the
                # write once. The retry must be *confirmed*: a second unconfirmed
                # DO NOTHING is never counted as an insert, because that would
                # report a phantom row.
                if _insert_if_absent(session, table, row):
                    inserted += 1
                    continue
                existing = _select_existing_for_update(session, table, key_columns, key)
                if existing is None:
                    raise GieRevisionRaceError(
                        f"{table.name} natural key {_display_key(key)} could not be "
                        "confirmed as inserted or as an existing row; refusing to report "
                        "a phantom insert."
                    )

        mismatched = [
            name
            for name in fields
            if _semantic_value(existing.get(name)) != _semantic_value(row.get(name))
        ]
        if mismatched:
            raise GieRevisionRequiresHistoryError(
                "GIE revision requires append-only history: refusing to overwrite "
                f"{table.name} key={_display_key(key)} for dataset "
                f"{row.get('source_dataset')!r}; the existing row differs on "
                f"{len(mismatched)} semantic field(s) [{', '.join(sorted(mismatched))}]. "
                "No revision history exists, so the original measurement is kept and the "
                "batch is refused as a whole."
            )
        unchanged += 1

    return {"inserted": inserted, "unchanged": unchanged}


def _resolve_semantic_fields(
    table: Any, override: Iterable[str] | None
) -> tuple[str, ...]:
    if override is not None:
        fields = tuple(str(name) for name in override)
    else:
        fields = GIE_SEMANTIC_FIELDS.get(table.name)
    if not fields:
        raise ValueError(
            f"{table.name} has no declared semantic field set; revision-safe "
            "persistence is only defined for the GIE observation tables."
        )
    missing = [name for name in fields if name not in table.columns]
    if missing:
        raise ValueError(
            f"{table.name} is missing declared semantic column(s): {', '.join(missing)}"
        )
    return fields


def _insert_if_absent(session: Session, table: Any, row: Mapping[str, Any]) -> bool:
    """Insert one row with ``ON CONFLICT DO NOTHING``; True only if it was written.

    ``rowcount == 1`` is the sole evidence that this call actually created the
    row. A conflict (``0``) is never counted as an insert.
    """

    result = session.execute(pg_insert(table).values(row).on_conflict_do_nothing())
    return result.rowcount == 1


def _key_value(row: Mapping[str, Any], name: str, table: Any) -> Any:
    if name in row:
        return row[name]
    raise ValueError(f"{table.name} row is missing natural key column {name!r}")


def _select_existing_for_update(
    session: Session,
    table: Any,
    key_columns: list[str],
    key: tuple[Any, ...],
) -> dict[str, Any] | None:
    statement = (
        select(table)
        .where(
            *(
                table.columns[name] == value
                for name, value in zip(key_columns, key, strict=True)
            )
        )
        .with_for_update()
    )
    found = session.execute(statement).mappings().first()
    return dict(found) if found is not None else None


def _display_key(key: tuple[Any, ...]) -> str:
    """Render the natural key without ever quoting provider payload values."""

    return "|".join(str(part) for part in key)


def _semantic_value(value: Any) -> Any:
    """Canonicalize one column value for semantic equality.

    A naive and a UTC-aware timestamp for the same instant are equal; an integer
    and a float for the same number are equal; ``None`` stays distinct from a
    value. Provider payload text is never involved.
    """

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    return value


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
