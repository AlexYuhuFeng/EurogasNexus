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
- ``upsert_revision_safe_observation_rows`` is the append-or-verify path: a new
  natural key is inserted and a semantically unchanged existing row is left
  untouched. A semantically revised existing row is refused with
  :class:`GieRevisionRequiresHistoryError` unless the caller passes a
  :class:`RevisionPolicy` (ENTSOG and GIE do; EEX does not). Under a policy a
  change confined to the policy's revisable value fields replaces the current
  row and writes the version it replaces to ``observation_revisions`` in the same
  transaction (append-only history, see ``docs/operations/DATA_REVISIONS.md``);
  a change to any other compared field (source, identity, period) is still
  refused. An optional metadata allowlist extends the comparison without treating
  receipt, archive, run or hash churn as a revision. The generic upsert above
  keeps its documented in-place-revision limitation for the other sources and is
  deliberately not changed here.
- ``replace_reference_snapshot`` replaces only the rows of one source system
  and only when the new payload is non-empty. An empty payload is treated as
  provider failure, not as evidence that the reference data became empty.

Both helpers run inside the caller's transaction and never commit.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select, update
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


#: The GIE fields a provider revision may change: the measured quantities and the
#: descriptive name. Source, dataset, facility/terminal, country and period are identity.
GIE_REVISABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "storage_observations": (
        "facility_name",
        "inventory_twh",
        "working_capacity_twh",
        "fill_pct",
        "injection_twh_d",
        "withdrawal_twh_d",
    ),
    "lng_observations": ("terminal_name", "inventory_twh", "send_out_twh_d", "dtmi_twh"),
}


class GieRevisionRequiresHistoryError(RuntimeError):
    """A GIE natural key already exists with different semantic content.

    Raised when no :class:`RevisionPolicy` applies (or, through its subclasses,
    when a policy refuses the change). Overwriting without history would project
    the new value back to the original first-seen observation instant
    (lookahead). The batch is refused as a whole; the error message carries only
    the source, dataset, counts, observation ids and safe field names, never
    provider payload or metadata values.
    """

    code = "gie_revision_requires_history"

    def __init__(self, message: str, *, changed_fields: Iterable[str] = ()) -> None:
        self.changed_fields = tuple(changed_fields)
        super().__init__(message)


class GieRevisionIdentityConflictError(GieRevisionRequiresHistoryError):
    """A key exists with a different source, identity or period: never a revision.

    Under a :class:`RevisionPolicy` only the policy's value fields may change; any
    other compared field differing means the incoming row is not a later version of
    the stored one, so the batch is refused as a whole.
    """

    code = "gie_revision_identity_conflict"


class GieStaleRevisionError(GieRevisionRequiresHistoryError):
    """A changed value whose receipt is not later than the stored version's.

    Replaying an older capture must never rewind the current value, so a change
    that does not arrive after the version it would replace is refused.
    """

    code = "gie_revision_not_newer"


@dataclass(frozen=True)
class RevisionPolicy:
    """Which compared fields a provider may revise under an unchanged natural key.

    ``revisable_fields`` are value columns (quantities, descriptive names);
    ``revisable_metadata_keys`` are allowlisted metadata keys that are quality
    flags rather than identity (ENTSOG ``flowStatus``). Every other compared field
    is identity and a difference in it is refused. ``close_open_periods``: a row
    received before its period ended is replaced by one received after it, even
    with an equal value (reason ``period_closed``), so a snapshot of an open gas
    day is never left standing as the closed day's figure.
    """

    revisable_fields: tuple[str, ...]
    revisable_metadata_keys: tuple[str, ...] = ()
    close_open_periods: bool = False

    def revisable(self, name: str) -> bool:
        if name.startswith("metadata_json."):
            return name.removeprefix("metadata_json.") in self.revisable_metadata_keys
        return name in self.revisable_fields


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
    semantic_metadata_keys: Iterable[str] = (),
    revisions: RevisionPolicy | None = None,
) -> dict[str, int]:
    """Append-or-verify observation rows; revise them only under a policy.

    For every incoming row, keyed by the table's natural primary key:

    * key absent -> the row is inserted with its own first-seen instant and its
      own exact archive/receipt lineage;
    * key present and every semantic column equal -> the existing row is left
      **byte-for-byte unchanged** (original ``observed_at_utc``, original
      ``source_reference``, original ``metadata_json``); the caller's newer
      poll metadata is not merged into it, so unchanged probes never churn the
      stored row;
    * key present with any semantic column different, and no ``revisions``
      policy -> the whole batch is refused with
      :class:`GieRevisionRequiresHistoryError`, and because the caller runs this
      inside a savepoint the original rows survive untouched;
    * with a ``revisions`` policy, a difference confined to its revisable fields
      and received after the stored version -> the stored version is appended to
      ``observation_revisions`` and the current row takes the incoming content,
      keeping its first-seen ``observed_at_utc`` and setting ``revised_at_utc``
      to the incoming receipt. A difference in any other compared field is
      refused with :class:`GieRevisionIdentityConflictError`, a change received
      no later than the stored version with :class:`GieStaleRevisionError`.

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
        semantic_metadata_keys: Optional allowlist of ``metadata_json`` keys whose
            presence and exact value are also compared. The default is empty, so
            GIE rows keep their existing whole-metadata-ignoring behaviour.
            Provider receipt/archive/run/hash and other unlisted metadata churn is
            never compared. An absent key, an explicit JSON ``null`` and a value
            are three distinct states.
        revisions: Optional :class:`RevisionPolicy`; without one every revision
            is refused (the EEX path).

    Returns:
        ``{"inserted": n, "unchanged": m}`` counts for the batch; under a policy
        also ``updated`` (current rows replaced, each with one history record)
        and ``revised`` (those of them whose value changed; the rest closed an
        open period).

    Raises:
        GieRevisionRequiresHistoryError: An existing natural key carries
            different semantic content or an allowlisted metadata change.
        ValueError: ``rows`` is empty, repeats a natural key, or the model has
            no declarable semantic field set.
    """

    if not rows:
        raise ValueError("rows must not be empty")

    table = model.__table__
    key_columns = [column.name for column in table.primary_key.columns]
    fields = _resolve_semantic_fields(table, semantic_fields)
    metadata_keys = tuple(dict.fromkeys(str(name) for name in semantic_metadata_keys))

    seen_keys: set[tuple[Any, ...]] = set()
    inserted = 0
    unchanged = 0
    updated = 0
    revised = 0
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
        mismatched.extend(_metadata_semantic_mismatches(existing, row, metadata_keys))
        ordered = sorted(mismatched)
        if revisions is None:
            if ordered:
                raise GieRevisionRequiresHistoryError(
                    "GIE revision requires append-only history: refusing to overwrite "
                    f"{table.name} key={_display_key(key)} for dataset "
                    f"{row.get('source_dataset')!r}; the existing row differs on "
                    f"{len(ordered)} semantic field(s) [{', '.join(ordered)}]. "
                    "This path keeps no revision history, so the original measurement is "
                    "kept and the batch is refused as a whole.",
                    changed_fields=ordered,
                )
            unchanged += 1
            continue

        fixed = [name for name in ordered if not revisions.revisable(name)]
        if fixed:
            raise GieRevisionIdentityConflictError(
                f"Refusing {table.name} key={_display_key(key)}: the existing row differs on "
                f"{len(fixed)} identity field(s) [{', '.join(fixed)}], which a provider "
                "revision may not change. The original row is kept and the batch is refused "
                "as a whole.",
                changed_fields=ordered,
            )
        prior_received = received_at(existing)
        incoming_received = _utc_instant(row.get("observed_at_utc"))
        if incoming_received is None or prior_received is None:
            raise ValueError(f"{table.name} rows must carry observed_at_utc to be revised")
        period_end = _utc_instant(existing.get("period_end_utc"))
        if ordered:
            if incoming_received <= prior_received:
                raise GieStaleRevisionError(
                    f"Refusing {table.name} key={_display_key(key)}: a changed value "
                    f"[{', '.join(ordered)}] was received no later than the stored version, "
                    "so it cannot supersede it. The original row is kept.",
                    changed_fields=ordered,
                )
            reason = "value_changed"
        elif (
            revisions.close_open_periods
            and period_end is not None
            and prior_received < period_end <= incoming_received
        ):
            reason = "period_closed"
        else:
            unchanged += 1
            continue
        _append_revision(
            session,
            table,
            existing,
            row,
            reason=reason,
            changed_fields=ordered,
            prior_received=prior_received,
            superseded_at=incoming_received,
        )
        _replace_current(session, table, key_columns, key, row, incoming_received)
        updated += 1
        revised += reason == "value_changed"

    if revisions is None:
        return {"inserted": inserted, "unchanged": unchanged}
    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "revised": revised,
    }


def received_at(row: Mapping[str, Any]) -> datetime | None:
    """When a stored row's current value was received: its revision, else its first receipt."""

    return _utc_instant(row.get("revised_at_utc")) or _utc_instant(row.get("observed_at_utc"))


def _utc_instant(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _append_revision(
    session: Session,
    table: Any,
    existing: Mapping[str, Any],
    incoming: Mapping[str, Any],
    *,
    reason: str,
    changed_fields: list[str],
    prior_received: datetime,
    superseded_at: datetime,
) -> None:
    """Write the version being replaced to the append-only revision table."""

    from eurogas_nexus.db.models.observation import ObservationRevisionRecord

    revisions = ObservationRevisionRecord.__table__
    session.execute(
        revisions.insert().values(
            revision_id=f"rev-{uuid4().hex}",
            observation_table=table.name,
            observation_id=str(existing["observation_id"]),
            source_system=str(existing.get("source_system") or ""),
            reason=reason,
            changed_fields=list(changed_fields),
            prior_row_json={name: _json_value(value) for name, value in existing.items()},
            prior_received_at_utc=prior_received,
            superseded_at_utc=superseded_at,
            prior_source_reference=str(existing.get("source_reference") or "")[:128],
            superseding_source_reference=str(incoming.get("source_reference") or "")[:128],
            recorded_at_utc=datetime.now(UTC),
        )
    )


def _replace_current(
    session: Session,
    table: Any,
    key_columns: list[str],
    key: tuple[Any, ...],
    row: Mapping[str, Any],
    received: datetime,
) -> None:
    """The current row takes the incoming content; its first receipt is kept."""

    values = {
        name: value
        for name, value in row.items()
        if name in table.columns and name not in key_columns and name != "observed_at_utc"
    }
    values["revised_at_utc"] = received
    match = zip(key_columns, key, strict=True)
    where = [table.columns[name] == value for name, value in match]
    session.execute(update(table).where(*where).values(**values))


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


def _metadata_semantic_mismatches(
    existing: Mapping[str, Any],
    incoming: Mapping[str, Any],
    keys: tuple[str, ...],
) -> list[str]:
    """Compare only explicitly allowlisted metadata keys, without echoing values.

    A key that is absent, present with an explicit JSON ``null`` and present with
    a value are distinct. Unlisted metadata (receipt, archive id, run id, hash,
    labels or any other churn) is never compared. A malformed stored/incoming
    metadata value is a typed revision refusal rather than an ignored field or an
    ``AttributeError``.
    """

    if not keys:
        return []
    existing_metadata = existing.get("metadata_json")
    incoming_metadata = incoming.get("metadata_json")
    if existing_metadata is None:
        existing_metadata = {}
    if incoming_metadata is None:
        incoming_metadata = {}
    if not isinstance(existing_metadata, Mapping) or not isinstance(incoming_metadata, Mapping):
        return ["metadata_json"]

    missing = object()
    changed: list[str] = []
    for name in keys:
        old = existing_metadata.get(name, missing)
        new = incoming_metadata.get(name, missing)
        if old is missing and new is missing:
            continue
        if (
            old is missing
            or new is missing
            or type(old) is not type(new)
            or old != new
        ):
            changed.append(f"metadata_json.{name}")
    return changed


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
