"""Append-only persistence for National Gas REST actual-demand revisions.

The REST adapter owns source parsing and revision identity.  This module only
validates that an opaque adapter revision is self-consistent, maps it onto the
existing ``national_gas_actual_demand`` table, and appends it atomically.

A replay of the same REST identity is an idempotent duplicate: the first local
receipt is retained and no provider or availability timestamp is rewritten.  A
different content payload under an existing identity is refused.  Provider wall
clocks are retained as raw text and, for the two legacy naive columns, as the
original wall clock with the offset stripped.  Those naive values are never
claimed to be UTC.  The aware UTC instants and all raw clocks stay explicit in
``rest_provenance``.  ``published_at_utc`` remains NULL because the provider
clocks do not prove first publication; ``available_at_utc`` is the actual local
receipt/availability chosen by the adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.repositories.demand import (
    DemandPersistenceError,
    DemandPublicationConflict,
)
from eurogas_nexus.ingestion.national_gas_demand import (
    NTS_DEMAND_D1,
    NTS_DEMAND_D6,
    gas_day_period_utc,
)
from eurogas_nexus.ingestion.national_gas_rest import (
    API_URL,
    APPROVED_PUBLICATION_IDS,
    EVIDENCE_BASIS,
    HASH_SCHEMA,
    REGION,
    SERIES_KEY,
    SOURCE_SYSTEM,
    UNIT,
    NationalGasRestPublication,
    QualityFlag,
)

_QUERY_CHUNK = 400
_DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_HEX_64_RE = re.compile(r"[0-9a-f]{64}\Z")
_SERIES_BY_PUBLICATION = {
    NTS_DEMAND_D1.provider_item_id: NTS_DEMAND_D1,
    NTS_DEMAND_D6.provider_item_id: NTS_DEMAND_D6,
}
_QUALITY_BY_RAW = {
    "": QualityFlag.UNKNOWN,
    "A": QualityFlag.AMENDED,
    "S": QualityFlag.SUBSTITUTED,
}
_SUBSTITUTED_BY_RAW = {"": None, "Y": True, "N": False}


class DemandRestPersistenceError(DemandPersistenceError):
    """Base repository failure for the REST demand namespace."""

    code = "DEMAND_REST_PERSISTENCE_ERROR"


class DemandRestPublicationConflict(DemandRestPersistenceError, DemandPublicationConflict):
    """A REST identity already exists, or is presented, with different content."""

    code = "DEMAND_REST_PUBLICATION_CONFLICT"


@dataclass(frozen=True)
class DemandRestInsertSummary:
    """Deterministic batch accounting without implying source finality."""

    rows_seen: int
    inserted: int
    duplicates: int
    publications: int


# Compatibility spelling for callers that name the operation after the module.
DemandRestPersistenceSummary = DemandRestInsertSummary


def insert_demand_rest_rows(
    session: Session,
    rows: Sequence[NationalGasRestPublication],
) -> DemandRestInsertSummary:
    """Append a validated REST batch atomically and classify replays.

    The caller owns the outer transaction.  A savepoint keeps a conflict that is
    discovered after earlier rows from leaving a partial batch behind.  The
    receipt, ingestion, raw-response hash and volatile provenance of an existing
    identity are never updated.
    """

    batch = tuple(rows)
    if not batch:
        return DemandRestInsertSummary(
            rows_seen=0, inserted=0, duplicates=0, publications=0
        )

    # Validate and map every DTO before touching the session.  Identity hashes
    # are recomputed with the REST adapter's namespace, so a CSV identity or a
    # caller-tampered payload cannot be reinterpreted as a REST revision.
    prepared = tuple(_to_record(row) for row in batch)

    _ensure_sqlite_begin(session)
    try:
        with session.begin_nested():
            existing_by_record, existing_by_publication = _load_existing(session, batch)
            seen_records: dict[str, tuple] = {}
            seen_publications: dict[str, str] = {}
            pending: list[NationalGasActualDemandRecord] = []
            duplicates = 0

            for row, record in zip(batch, prepared, strict=True):
                signature = _dto_signature(row)

                prior = seen_records.get(row.record_id)
                if prior is not None:
                    if prior != signature:
                        raise DemandRestPublicationConflict(
                            "same REST record identity appears with different content"
                        )
                    duplicates += 1
                    continue

                existing_signature = existing_by_record.get(row.record_id)
                if existing_signature is not None:
                    if existing_signature != signature:
                        raise DemandRestPublicationConflict(
                            "existing REST record identity has different content"
                        )
                    seen_records[row.record_id] = signature
                    duplicates += 1
                    continue

                prior_publication = existing_by_publication.get(
                    row.source_publication_id
                )
                if (
                    prior_publication is not None
                    and prior_publication != row.record_id
                ):
                    raise DemandRestPublicationConflict(
                        "REST source publication identity already has a different revision"
                    )
                prior_batch_publication = seen_publications.get(
                    row.source_publication_id
                )
                if (
                    prior_batch_publication is not None
                    and prior_batch_publication != row.record_id
                ):
                    raise DemandRestPublicationConflict(
                        "REST source publication identity appears twice with "
                        "different revisions"
                    )

                seen_records[row.record_id] = signature
                seen_publications[row.source_publication_id] = row.record_id
                pending.append(record)

            session.add_all(pending)
            session.flush()
    except IntegrityError as exc:
        raise DemandRestPublicationConflict(
            "database uniqueness refused a conflicting REST source publication"
        ) from exc

    return DemandRestInsertSummary(
        rows_seen=len(batch),
        inserted=len(pending),
        duplicates=duplicates,
        publications=len({row.source_publication_id for row in batch}),
    )


def _load_existing(
    session: Session,
    rows: Sequence[NationalGasRestPublication],
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


def _to_record(row: NationalGasRestPublication) -> NationalGasActualDemandRecord:
    _validate_row(row)
    period_start, period_end = gas_day_period_utc(row.applicable_for)
    _, applicable_wall = _provider_clock(row.applicable_at_raw, "applicableAt")
    _, generated_wall = _provider_clock(row.generated_at_raw, "generatedTimeStamp")
    return NationalGasActualDemandRecord(
        record_id=row.record_id,
        source_publication_id=row.source_publication_id,
        provider_item_id=row.publication_id,
        series_key=SERIES_KEY,
        region=REGION,
        term=row.term,
        label=row.publication_name,
        gas_day=row.applicable_for,
        period_start_utc=period_start,
        period_end_utc=period_end,
        value_text=row.value_text,
        unit=row.unit,
        received_at_utc=_require_aware_utc(row.received_at_utc, "received_at_utc"),
        available_at_utc=_require_aware_utc(row.available_at_utc, "available_at_utc"),
        ingested_at_utc=_require_aware_utc(row.ingested_at_utc, "ingested_at_utc"),
        published_at_utc=None,
        applicable_at_raw=row.applicable_at_raw,
        generated_at_raw=row.generated_at_raw,
        applicable_at_naive=applicable_wall,
        generated_at_naive=generated_wall,
        quality_indicator=row.quality_indicator_raw or None,
        provisional_status=row.provisional_status,
        is_provisional=row.is_provisional,
        raw_sha256=row.raw_sha256,
        source_url=row.source_url,
        hash_schema=row.hash_schema,
        value_is_blank=row.value_is_blank,
        source_format="REST",
        rest_provenance=_rest_provenance(row),
    )


def _validate_row(row: NationalGasRestPublication) -> None:
    if not isinstance(row, NationalGasRestPublication):
        raise DemandRestPersistenceError(
            "REST demand row must be a NationalGasRestPublication"
        )

    if not isinstance(row.publication_id, str):
        raise DemandRestPersistenceError("REST publication is not an approved NTS series")
    series = _SERIES_BY_PUBLICATION.get(row.publication_id)
    if series is None or row.publication_id not in APPROVED_PUBLICATION_IDS:
        raise DemandRestPersistenceError("REST publication is not an approved NTS series")
    if (
        row.publication_name != series.label
        or row.term != series.term
        or row.provisional_status != series.provisional_status
        or row.is_provisional != series.is_provisional
    ):
        raise DemandRestPersistenceError(
            "REST series identity does not match the approved adapter catalogue"
        )
    if row.unit != UNIT or row.source_url != API_URL:
        raise DemandRestPersistenceError(
            "REST unit or source origin does not match the approved adapter contract"
        )
    if row.hash_schema != HASH_SCHEMA or row.evidence_basis != EVIDENCE_BASIS:
        raise DemandRestPersistenceError(
            "REST hash schema or timestamp evidence basis is not the approved namespace"
        )
    if not _is_sha256(row.raw_sha256):
        raise DemandRestPersistenceError("REST raw response hash is not a SHA256 digest")
    if not _is_sha256(row.record_id) or not _is_sha256(row.source_publication_id):
        raise DemandRestPersistenceError(
            "REST record and source-publication identities must be SHA256 digests"
        )

    if not isinstance(row.applicable_for, date) or isinstance(
        row.applicable_for, datetime
    ):
        raise DemandRestPersistenceError("REST applicableFor must be a calendar date")
    if row.applicable_for_raw != row.applicable_for.isoformat():
        raise DemandRestPersistenceError(
            "REST applicableFor raw text and calendar date disagree"
        )

    applicable_utc, _ = _provider_clock(row.applicable_at_raw, "applicableAt")
    generated_utc, _ = _provider_clock(row.generated_at_raw, "generatedTimeStamp")
    created_utc, _ = _provider_clock(row.created_at_raw, "createdDate")

    if _require_aware_utc(row.applicable_at_utc, "applicable_at_utc") != applicable_utc:
        raise DemandRestPersistenceError(
            "REST applicableAt UTC instant disagrees with its raw clock"
        )
    if _require_aware_utc(row.generated_at_utc, "generated_at_utc") != generated_utc:
        raise DemandRestPersistenceError(
            "REST generatedTimeStamp UTC instant disagrees with its raw clock"
        )
    if _require_aware_utc(row.created_at_utc, "created_at_utc") != created_utc:
        raise DemandRestPersistenceError(
            "REST createdDate UTC instant disagrees with its raw clock"
        )

    upper_bound = _require_aware_utc(
        row.provider_timestamp_upper_bound_utc,
        "provider_timestamp_upper_bound_utc",
    )
    if upper_bound != max(applicable_utc, generated_utc, created_utc):
        raise DemandRestPersistenceError(
            "REST provider timestamp upper bound is inconsistent with its clocks"
        )

    received = _require_aware_utc(row.received_at_utc, "received_at_utc")
    available = _require_aware_utc(row.available_at_utc, "available_at_utc")
    _require_aware_utc(row.ingested_at_utc, "ingested_at_utc")
    if available < received:
        raise DemandRestPersistenceError(
            "REST available_at_utc must not precede the actual local receipt"
        )

    _validate_value(row)
    _validate_quality_and_substitution(row)

    expected_publication, expected_record = _expected_identities(row)
    if (
        row.source_publication_id != expected_publication
        or row.record_id != expected_record
    ):
        raise DemandRestPublicationConflict(
            "REST identity does not match the adapter-derived raw content"
        )


def _validate_value(row: NationalGasRestPublication) -> None:
    if not isinstance(row.value_text, str):
        raise DemandRestPersistenceError("REST value must be exact provider text")
    if not isinstance(row.value_is_blank, bool):
        raise DemandRestPersistenceError("REST value_is_blank must be an explicit boolean")
    if row.value_text == "":
        if not row.value_is_blank or row.value_decimal is not None:
            raise DemandRestPersistenceError(
                "blank REST value requires value_is_blank and no decimal"
            )
        return
    if row.value_is_blank:
        raise DemandRestPersistenceError(
            "non-empty REST value cannot be marked blank"
        )
    if (
        row.value_text != row.value_text.strip()
        or len(row.value_text) > 64
        or _DECIMAL_RE.fullmatch(row.value_text) is None
    ):
        raise DemandRestPersistenceError(
            "REST value is not the exact bounded provider decimal text"
        )
    if not isinstance(row.value_decimal, Decimal):
        raise DemandRestPersistenceError("REST non-blank value requires a Decimal")
    try:
        parsed = Decimal(row.value_text)
    except InvalidOperation as exc:  # pragma: no cover - regex already excludes this
        raise DemandRestPersistenceError("REST value is not a decimal") from exc
    if not parsed.is_finite() or parsed != row.value_decimal:
        raise DemandRestPersistenceError(
            "REST value decimal disagrees with the exact provider text"
        )


def _validate_quality_and_substitution(row: NationalGasRestPublication) -> None:
    if not isinstance(row.quality_indicator_raw, str):
        raise DemandRestPersistenceError("REST quality indicator must be raw text")
    if not isinstance(row.substituted_raw, str):
        raise DemandRestPersistenceError("REST substituted flag must be raw text")
    expected_quality = _QUALITY_BY_RAW.get(row.quality_indicator_raw)
    if expected_quality is None or row.quality_flag != expected_quality:
        raise DemandRestPersistenceError(
            "REST quality flag disagrees with the raw quality indicator"
        )
    expected_substituted = _SUBSTITUTED_BY_RAW.get(row.substituted_raw)
    if row.substituted_raw not in _SUBSTITUTED_BY_RAW or (
        row.is_substituted != expected_substituted
    ):
        raise DemandRestPersistenceError(
            "REST substitution state disagrees with the raw substituted flag"
        )


def _provider_clock(raw: str, field: str) -> tuple[datetime, datetime]:
    """Return the aware UTC instant and the original wall clock without offset."""

    if not isinstance(raw, str) or not raw:
        raise DemandRestPersistenceError(f"REST {field} raw clock must be text")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DemandRestPersistenceError(
            f"REST {field} raw clock is not an ISO timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DemandRestPersistenceError(
            f"REST {field} raw clock must carry an explicit offset"
        )
    # The naive column keeps the provider's displayed wall clock.  It is not a
    # UTC conversion; conversion to UTC is retained separately in provenance.
    return parsed.astimezone(UTC), parsed.replace(tzinfo=None)


def _rest_provenance(row: NationalGasRestPublication) -> dict[str, object]:
    applicable_utc, applicable_wall = _provider_clock(
        row.applicable_at_raw, "applicableAt"
    )
    generated_utc, generated_wall = _provider_clock(
        row.generated_at_raw, "generatedTimeStamp"
    )
    created_utc, created_wall = _provider_clock(row.created_at_raw, "createdDate")
    return {
        "source_format": "REST",
        "source_system": SOURCE_SYSTEM,
        "hash_schema": row.hash_schema,
        "series_key": SERIES_KEY,
        "region": REGION,
        "publication_id": row.publication_id,
        "publication_name": row.publication_name,
        "term": row.term,
        "provisional_status": row.provisional_status,
        "is_provisional": row.is_provisional,
        "applicable_for_raw": row.applicable_for_raw,
        "applicable_at_raw": row.applicable_at_raw,
        "applicable_at_utc": applicable_utc.isoformat(),
        "applicable_at_wall_clock_naive": applicable_wall.isoformat(),
        "generated_at_raw": row.generated_at_raw,
        "generated_at_utc": generated_utc.isoformat(),
        "generated_at_wall_clock_naive": generated_wall.isoformat(),
        "created_at_raw": row.created_at_raw,
        "created_at_utc": created_utc.isoformat(),
        "created_at_wall_clock_naive": created_wall.isoformat(),
        "provider_timestamp_upper_bound_utc": (
            _require_aware_utc(
                row.provider_timestamp_upper_bound_utc,
                "provider_timestamp_upper_bound_utc",
            ).isoformat()
        ),
        "evidence_basis": row.evidence_basis,
        "quality_indicator_raw": row.quality_indicator_raw,
        "quality_flag": str(row.quality_flag),
        "substituted_raw": row.substituted_raw,
        "is_substituted": row.is_substituted,
        "value_text": row.value_text,
        "value_decimal": None if row.value_decimal is None else str(row.value_decimal),
        "value_is_blank": row.value_is_blank,
        "unit": row.unit,
        "received_at_utc": _require_aware_utc(
            row.received_at_utc, "received_at_utc"
        ).isoformat(),
        "available_at_utc": _require_aware_utc(
            row.available_at_utc, "available_at_utc"
        ).isoformat(),
        "ingested_at_utc": _require_aware_utc(
            row.ingested_at_utc, "ingested_at_utc"
        ).isoformat(),
        "published_at_utc": None,
        "raw_sha256": row.raw_sha256,
        "source_url": row.source_url,
    }


def _expected_identities(row: NationalGasRestPublication) -> tuple[str, str]:
    identity = [
        HASH_SCHEMA,
        SOURCE_SYSTEM,
        row.publication_id,
        str(row.publication_name),
        str(row.term),
        str(row.provisional_status),
        row.applicable_for_raw,
        row.applicable_at_raw,
        row.generated_at_raw,
        row.created_at_raw,
        row.value_text,
        UNIT,
        row.quality_indicator_raw,
        row.substituted_raw,
    ]
    source_publication_id = _sha256_json(identity)
    record_id = _sha256_json(["RECORD", REGION, SERIES_KEY, *identity])
    return source_publication_id, record_id


def _dto_signature(row: NationalGasRestPublication) -> tuple:
    period_start, period_end = gas_day_period_utc(row.applicable_for)
    _, applicable_wall = _provider_clock(row.applicable_at_raw, "applicableAt")
    _, generated_wall = _provider_clock(row.generated_at_raw, "generatedTimeStamp")
    return (
        row.record_id,
        row.source_publication_id,
        row.publication_id,
        SERIES_KEY,
        REGION,
        row.term,
        row.publication_name,
        row.applicable_for,
        _utc(period_start),
        _utc(period_end),
        row.value_text,
        row.value_is_blank,
        row.unit,
        row.quality_indicator_raw or None,
        row.provisional_status,
        row.is_provisional,
        row.applicable_at_raw,
        row.generated_at_raw,
        applicable_wall,
        generated_wall,
        row.created_at_raw,
        row.substituted_raw,
        row.is_substituted,
        _utc(row.provider_timestamp_upper_bound_utc),
        row.evidence_basis,
        row.hash_schema,
    )


def _model_signature(record: NationalGasActualDemandRecord) -> tuple:
    provenance = record.rest_provenance or {}
    if not isinstance(provenance, dict):
        raise DemandRestPersistenceError("stored REST provenance is not a JSON object")
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
        bool(record.value_is_blank),
        record.unit,
        record.quality_indicator,
        record.provisional_status,
        record.is_provisional,
        record.applicable_at_raw,
        record.generated_at_raw,
        _strip_offset(record.applicable_at_naive),
        _strip_offset(record.generated_at_naive),
        provenance.get("created_at_raw"),
        provenance.get("substituted_raw"),
        provenance.get("is_substituted"),
        _json_utc(provenance.get("provider_timestamp_upper_bound_utc")),
        provenance.get("evidence_basis"),
        record.hash_schema,
    )


def _json_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _strip_offset(value: datetime) -> datetime:
    """Return the stored wall clock without claiming a timezone."""

    return value.replace(tzinfo=None)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        # SQLite returns timezone=True values without an offset, but they were
        # written as UTC.  This normalization is only for content comparison.
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise DemandRestPersistenceError(f"REST {field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise DemandRestPersistenceError(f"REST {field} must be timezone-aware")
    return value.astimezone(UTC)


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and _HEX_64_RE.fullmatch(value) is not None


def _sha256_json(parts: list[str]) -> str:
    canonical = json.dumps(parts, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _ensure_sqlite_begin(session: Session) -> None:
    """Force a real SQLite transaction before opening the batch savepoint."""

    connection = session.connection()
    if connection.dialect.name != "sqlite":
        return
    dbapi_connection = connection.connection.driver_connection
    if not dbapi_connection.in_transaction:
        connection.exec_driver_sql("BEGIN")


# Explicit alternate spellings keep the bounded operation discoverable without
# changing the established import path.
insert_rest_demand_rows = insert_demand_rest_rows
persist_demand_rest_rows = insert_demand_rest_rows
