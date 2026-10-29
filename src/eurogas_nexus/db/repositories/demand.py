"""Append-only repository for National Gas NTS actual-demand revisions.

The repository owns SQL and transaction boundaries.  It never updates or deletes
an existing source publication; identical replays are idempotent duplicates and
a changed row with the same publication identity is refused atomically.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.ingestion.national_gas_demand import (
    ALLOWED_PROVIDER_ITEM_IDS,
    NationalGasActualDemand,
)

_QUERY_CHUNK = 400
MAX_DEMAND_TARGET_READ_LIMIT = 10_000
DEMAND_TARGET_SOURCE_FORMATS = frozenset({"CSV", "REST"})
DEMAND_TARGET_REGION = "GB_NTS"
DEMAND_TARGET_UNIT = "mscm"


class DemandPersistenceError(RuntimeError):
    """Base repository failure with a stable operator-safe code."""

    code = "DEMAND_PERSISTENCE_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class DemandPublicationConflict(DemandPersistenceError):
    """A source publication identity already exists with different content."""

    code = "DEMAND_PUBLICATION_CONFLICT"


class DemandTargetReadError(RuntimeError):
    """Base failure for bounded, point-in-time demand-target reads."""

    code = "DEMAND_TARGET_READ_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"{self.code}: {message}")


class DemandTargetReadValidationError(DemandTargetReadError):
    """A read argument is missing, malformed or outside the allowlist."""

    code = "DEMAND_TARGET_READ_VALIDATION_ERROR"


class DemandTargetReadOverflow(DemandTargetReadError):
    """The result exceeded the explicit limit; rows are never silently trimmed."""

    code = "DEMAND_TARGET_READ_OVERFLOW"


@dataclass(frozen=True)
class DemandInsertSummary:
    """Deterministic batch accounting without implying source finality."""

    rows_seen: int
    inserted: int
    duplicates: int
    publications: int


def insert_demand_rows(
    session: Session,
    rows: Sequence[NationalGasActualDemand],
) -> DemandInsertSummary:
    """Append a batch atomically, classifying duplicates and conflicts.

    The caller owns the outer transaction.  A savepoint ensures that a conflict
    discovered after earlier rows in this batch cannot leave a partial insert.
    """

    if not rows:
        return DemandInsertSummary(rows_seen=0, inserted=0, duplicates=0, publications=0)

    _ensure_sqlite_begin(session)
    try:
        with session.begin_nested():
            existing_by_record, existing_by_publication = _load_existing(session, rows)
            seen_records: dict[str, tuple] = {}
            seen_publications: dict[str, str] = {}
            pending: list[NationalGasActualDemand] = []
            duplicates = 0

            for row in rows:
                signature = _dto_signature(row)
                prior = seen_records.get(row.record_id)
                if prior is not None:
                    if prior != signature:
                        raise DemandPublicationConflict(
                            "same record id appears with different canonical content"
                        )
                    duplicates += 1
                    continue

                existing_signature = existing_by_record.get(row.record_id)
                if existing_signature is not None:
                    if existing_signature != signature:
                        raise DemandPublicationConflict(
                            "existing record id has different canonical content"
                        )
                    seen_records[row.record_id] = signature
                    duplicates += 1
                    continue

                prior_publication = existing_by_publication.get(row.source_publication_id)
                if prior_publication is not None and prior_publication != row.record_id:
                    raise DemandPublicationConflict(
                        "source publication identity already has a different revision"
                    )
                prior_batch_publication = seen_publications.get(row.source_publication_id)
                if (
                    prior_batch_publication is not None
                    and prior_batch_publication != row.record_id
                ):
                    raise DemandPublicationConflict(
                        "source publication identity appears twice with different revisions"
                    )

                seen_records[row.record_id] = signature
                seen_publications[row.source_publication_id] = row.record_id
                pending.append(row)

            for row in pending:
                session.add(_to_record(row))
            session.flush()
    except IntegrityError as exc:
        raise DemandPublicationConflict(
            "database uniqueness refused a conflicting source publication"
        ) from exc

    return DemandInsertSummary(
        rows_seen=len(rows),
        inserted=len(pending),
        duplicates=duplicates,
        publications=len({row.source_publication_id for row in rows}),
    )


def list_demand_rows(
    session: Session,
    *,
    series_key: str | None = None,
    provider_item_id: str | None = None,
    term: str | None = None,
    gas_day_from: date | None = None,
    gas_day_to: date | None = None,
    limit: int = 500,
) -> list[NationalGasActualDemandRecord]:
    """Return bounded append-only rows ordered by gas day and source revision."""

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    if gas_day_from is not None and gas_day_to is not None and gas_day_from > gas_day_to:
        raise ValueError("gas_day_from must not be after gas_day_to")

    statement = select(NationalGasActualDemandRecord)
    if series_key is not None:
        statement = statement.where(NationalGasActualDemandRecord.series_key == series_key)
    if provider_item_id is not None:
        statement = statement.where(
            NationalGasActualDemandRecord.provider_item_id == provider_item_id
        )
    if term is not None:
        statement = statement.where(NationalGasActualDemandRecord.term == term)
    if gas_day_from is not None:
        statement = statement.where(NationalGasActualDemandRecord.gas_day >= gas_day_from)
    if gas_day_to is not None:
        statement = statement.where(NationalGasActualDemandRecord.gas_day <= gas_day_to)
    statement = statement.order_by(
        NationalGasActualDemandRecord.gas_day,
        NationalGasActualDemandRecord.generated_at_naive,
        NationalGasActualDemandRecord.record_id,
    ).limit(limit)
    return list(session.scalars(statement).all())


def read_demand_target_revisions(
    session: Session,
    *,
    provider_item_id: str,
    source_format: str,
    gas_day_from: date,
    gas_day_to: date,
    available_at_utc: datetime,
    limit: int = 1_000,
) -> list[NationalGasActualDemandRecord]:
    """Read one source format's revisions that were actually available by a cutoff.

    The query is deliberately narrow and read-only: one allowlisted provider item,
    one explicit ``CSV`` or ``REST`` copy, the fixed GB NTS throughput region and
    native ``mscm`` unit, an inclusive gas-day window, and receipt availability at
    or before an aware cutoff.  Published clocks are never substituted for receipt
    evidence.  ``limit + 1`` is fetched so an over-limit result is refused rather
    than silently trimmed.  The caller owns the transaction; this function neither
    commits nor mutates a row.
    """

    _validate_target_read_arguments(
        provider_item_id=provider_item_id,
        source_format=source_format,
        gas_day_from=gas_day_from,
        gas_day_to=gas_day_to,
        available_at_utc=available_at_utc,
        limit=limit,
    )
    cutoff_utc = available_at_utc.astimezone(UTC)

    statement = (
        select(NationalGasActualDemandRecord)
        .where(
            NationalGasActualDemandRecord.provider_item_id == provider_item_id,
            NationalGasActualDemandRecord.source_format == source_format,
            NationalGasActualDemandRecord.region == DEMAND_TARGET_REGION,
            NationalGasActualDemandRecord.unit == DEMAND_TARGET_UNIT,
            NationalGasActualDemandRecord.gas_day >= gas_day_from,
            NationalGasActualDemandRecord.gas_day <= gas_day_to,
            NationalGasActualDemandRecord.available_at_utc <= cutoff_utc,
        )
        .order_by(
            NationalGasActualDemandRecord.gas_day,
            NationalGasActualDemandRecord.available_at_utc,
            NationalGasActualDemandRecord.record_id,
        )
        .limit(limit + 1)
    )
    # A read must never flush pending caller writes.  Scope autoflush suppression
    # to this query only and leave the caller's unit of work exactly as it was.
    with session.no_autoflush:
        rows = list(session.scalars(statement).all())
    if len(rows) > limit:
        raise DemandTargetReadOverflow(
            "demand target read exceeded the explicit limit; rows are never silently trimmed"
        )
    return rows


def _validate_target_read_arguments(
    *,
    provider_item_id: str,
    source_format: str,
    gas_day_from: date,
    gas_day_to: date,
    available_at_utc: datetime,
    limit: int,
) -> None:
    if (
        not isinstance(provider_item_id, str)
        or provider_item_id not in ALLOWED_PROVIDER_ITEM_IDS
    ):
        raise DemandTargetReadValidationError(
            "provider_item_id must be one of the allowlisted National Gas actual-demand items"
        )
    if not isinstance(source_format, str) or source_format not in DEMAND_TARGET_SOURCE_FORMATS:
        raise DemandTargetReadValidationError("source_format must be CSV or REST")
    for name, value in (("gas_day_from", gas_day_from), ("gas_day_to", gas_day_to)):
        if not isinstance(value, date) or isinstance(value, datetime):
            raise DemandTargetReadValidationError(f"{name} must be a calendar date")
        if not date(2000, 1, 1) <= value <= date(2100, 12, 31):
            raise DemandTargetReadValidationError(f"{name} is outside the supported range")
    if gas_day_from > gas_day_to:
        raise DemandTargetReadValidationError("gas_day_from must not be after gas_day_to")
    if (
        not isinstance(available_at_utc, datetime)
        or available_at_utc.tzinfo is None
        or available_at_utc.utcoffset() is None
    ):
        raise DemandTargetReadValidationError("available_at_utc must be an aware datetime")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise DemandTargetReadValidationError("limit must be an integer")
    if not 1 <= limit <= MAX_DEMAND_TARGET_READ_LIMIT:
        raise DemandTargetReadValidationError(
            f"limit must be between 1 and {MAX_DEMAND_TARGET_READ_LIMIT}"
        )


def _ensure_sqlite_begin(session: Session) -> None:
    """Force a real SQLite transaction before opening the batch savepoint.

    Python's pysqlite driver defers ``BEGIN`` until the first DML statement.
    A ``SAVEPOINT`` opened before that point is the outermost transaction, so
    releasing it commits the batch and a later outer rollback cannot remove
    the rows.  Issue ``BEGIN`` explicitly so the savepoint is genuinely nested
    under the caller's transaction.  Other dialects already begin eagerly.
    """

    connection = session.connection()
    if connection.dialect.name != "sqlite":
        return
    dbapi_connection = connection.connection.driver_connection
    if not dbapi_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")


def _load_existing(
    session: Session,
    rows: Sequence[NationalGasActualDemand],
) -> tuple[dict[str, tuple], dict[str, str]]:
    record_ids = sorted({row.record_id for row in rows})
    publication_ids = sorted({row.source_publication_id for row in rows})
    by_record: dict[str, tuple] = {}
    by_publication: dict[str, str] = {}
    for chunk in _chunks(record_ids):
        found = session.scalars(
            select(NationalGasActualDemandRecord).where(
                NationalGasActualDemandRecord.record_id.in_(chunk)
            )
        )
        for record in found:
            by_record[record.record_id] = _model_signature(record)
    for chunk in _chunks(publication_ids):
        found = session.scalars(
            select(NationalGasActualDemandRecord).where(
                NationalGasActualDemandRecord.source_publication_id.in_(chunk)
            )
        )
        for record in found:
            by_publication[record.source_publication_id] = record.record_id
    return by_record, by_publication


def _chunks(values: Sequence[str]):
    for start in range(0, len(values), _QUERY_CHUNK):
        yield values[start : start + _QUERY_CHUNK]


def _to_record(row: NationalGasActualDemand) -> NationalGasActualDemandRecord:
    return NationalGasActualDemandRecord(
        record_id=row.record_id,
        source_publication_id=row.source_publication_id,
        provider_item_id=row.provider_item_id,
        series_key=row.series_key,
        region=row.region,
        term=row.term,
        label=row.label,
        gas_day=row.gas_day,
        period_start_utc=row.period_start_utc,
        period_end_utc=row.period_end_utc,
        value_text=row.value_text,
        unit=row.unit,
        received_at_utc=row.received_at_utc,
        available_at_utc=row.available_at_utc,
        ingested_at_utc=row.ingested_at_utc,
        published_at_utc=row.published_at_utc,
        applicable_at_raw=row.applicable_at_raw,
        generated_at_raw=row.generated_at_raw,
        applicable_at_naive=row.applicable_at_naive,
        generated_at_naive=row.generated_at_naive,
        quality_indicator=row.quality_indicator,
        provisional_status=row.provisional_status,
        is_provisional=row.is_provisional,
        raw_sha256=row.raw_sha256,
        source_url=row.source_url,
        hash_schema=row.hash_schema,
    )


def _dto_signature(row: NationalGasActualDemand) -> tuple:
    return (
        row.record_id,
        row.source_publication_id,
        row.provider_item_id,
        row.series_key,
        row.region,
        row.term,
        row.label,
        row.gas_day,
        _utc(row.period_start_utc),
        _utc(row.period_end_utc),
        row.value_text,
        row.unit,
        row.quality_indicator,
        row.provisional_status,
        row.is_provisional,
    )


def _model_signature(record: NationalGasActualDemandRecord) -> tuple:
    return (
        record.record_id,
        record.source_publication_id,
        record.provider_item_id,
        record.series_key,
        record.region,
        record.term,
        record.label,
        record.gas_day,
        _utc(record.period_start_utc),
        _utc(record.period_end_utc),
        record.value_text,
        record.unit,
        record.quality_indicator,
        record.provisional_status,
        record.is_provisional,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
