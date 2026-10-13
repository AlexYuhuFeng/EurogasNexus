"""PostgreSQL-only revision-safety tests for the GIE persistence path.

These tests exercise the **real** ``upsert_revision_safe_observation_rows``
helper against a real PostgreSQL engine, not a mock and not a compile-only
assertion. Each test runs inside a uniquely named throwaway schema of the
configured test database (created and dropped by the helper), so no existing
table, row or schema is touched.

What they pin down (REAL-SOURCES-02):

* a new natural key is inserted with its own first-seen instant and exact archive
  lineage;
* a second unchanged poll with a **different receipt and run id** leaves the
  stored row byte-for-byte unchanged -- original first-seen, original archive id,
  original ``metadata_json`` -- while the new poll's raw archive exists
  separately;
* a genuinely revised value is refused with ``gie_revision_requires_history``
  rather than overwriting the original;
* a mixed batch writes nothing at all: the savepoint rollback leaves every
  original row untouched and no partial canonical write survives;
* a conflicting concurrent ingest serializes on the natural-key row lock: the
  loser either verifies the winner's identical row or is refused, never silently
  overwritten.

Skip when ``RUNTIME_STORE_DATABASE_URL`` is not a PostgreSQL URL; run via
``scripts/ci/run_postgres_ci.sh`` or against the disposable local test database.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.db.models import (
    AuditEventRecord,
    LngObservationRecord,
    RawPayloadArchiveRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionRequiresHistoryError,
    upsert_revision_safe_observation_rows,
)
from eurogas_nexus.ingestion.public_sources import (
    gie_lng_observations_from_json,
    gie_storage_observations_from_json,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason=(
        "RUNTIME_STORE_DATABASE_URL must point at PostgreSQL; run via "
        "scripts/ci/run_postgres_ci.sh or the disposable local test database"
    ),
)

_CODE = "TSTGIE"
_FIRST_RECEIPT = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
_SECOND_RECEIPT = _FIRST_RECEIPT + timedelta(hours=1)

_ARCHIVE_FIELDS = {
    "raw_archive_id": "raw-0000000000000000aaaa",
    "payload_sha256": "a" * 64,
    "fetch_reference": "gie-test-api:pages=1/1;complete=true",
}


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _agsi_payload(
    *,
    gas: str = "650.25",
    updated_at: str = "2026-06-01 08:00:00",
) -> dict[str, Any]:
    return {
        "data": [
            {
                "code": _CODE,
                "name": "Test storage",
                "gasDayStart": "2026-06-01",
                "gasDayEnd": "2026-06-02",
                "gasInStorage": gas,
                "workingGasVolume": "1100.50",
                "full": "59.1",
                "injection": "2.5",
                "withdrawal": "1.2",
                "updatedAt": updated_at,
            }
        ]
    }


def _alsi_payload(
    *,
    inventory_gwh: str = "42.5",
    updated_at: str = "2026-06-01 08:00:00",
) -> dict[str, Any]:
    return {
        "data": [
            {
                "code": _CODE,
                "name": "Test LNG terminal",
                "gasDayStart": "2026-06-01",
                "gasDayEnd": "2026-06-02",
                "inventory": {"lng": "9.5", "gwh": inventory_gwh},
                "sendOut": "3.4",
                "dtmi": {"lng": "14.4", "gwh": "65.0"},
                "updatedAt": updated_at,
            }
        ]
    }


def _normalized_row(
    normalizer: Any, payload: dict[str, Any], *, receipt: datetime
) -> dict[str, Any]:
    """Normalize one payload the way the ingestion path does, archive included."""

    row = normalizer(payload, observed_at_utc=receipt)[0]
    metadata = dict(row.get("metadata_json") or {})
    metadata.update(
        {
            "source_page": 1,
            "source_page_size": 30,
            "provider_last_page": 1,
            "provider_total_on_page": 1,
            "source_receipt_at_utc": receipt.isoformat(),
            **_ARCHIVE_FIELDS,
        }
    )
    row["metadata_json"] = metadata
    return row


def _poll_row(
    row: dict[str, Any], *, receipt: datetime, run_id: str, archive_id: str
) -> dict[str, Any]:
    """Apply the poll-scoped lineage a fresh poll would stamp on its own rows."""

    metadata = dict(row["metadata_json"])
    metadata["source_receipt_at_utc"] = receipt.isoformat()
    metadata["ingestion_run_id"] = run_id
    metadata["adapter_version"] = "public-source-ingestor/1"
    metadata["raw_archive_id"] = archive_id
    return {**row, "metadata_json": metadata}


@contextmanager
def _isolated_session() -> Iterator[Session]:
    """Create a throwaway schema, yield a session, then drop the schema."""

    url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    engine: Engine = create_engine(url, future=True)
    schema = f"gierev_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            StorageObservationRecord.__table__.create(bind=connection)
            LngObservationRecord.__table__.create(bind=connection)
            RawPayloadArchiveRecord.__table__.create(bind=connection)
            AuditEventRecord.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _row_snapshot(session: Session, model: Any, key_column: str) -> dict[str, Any]:
    """Return every stored column value of the one natural-key row, raw and unrounded."""

    table = model.__table__
    row = session.execute(
        select(table).where(table.columns[key_column] == _CODE)
    ).mappings().first()
    assert row is not None
    return dict(row)


_PRODUCTS = [
    pytest.param(
        StorageObservationRecord,
        gie_storage_observations_from_json,
        _agsi_payload,
        "facility_id",
        id="agsi",
    ),
    pytest.param(
        LngObservationRecord,
        gie_lng_observations_from_json,
        _alsi_payload,
        "terminal_id",
        id="alsi",
    ),
]


@pytest.mark.parametrize(("model", "normalizer", "payload_factory", "key_column"), _PRODUCTS)
def test_new_row_is_inserted_with_exact_archive_lineage(
    model: Any,
    normalizer: Any,
    payload_factory: Any,
    key_column: str,
) -> None:
    with _isolated_session() as session:
        row = _normalized_row(normalizer, payload_factory(), receipt=_FIRST_RECEIPT)
        outcome = upsert_revision_safe_observation_rows(session, model, [row])
        session.flush()
        stored = _row_snapshot(session, model, key_column)

    assert outcome == {"inserted": 1, "unchanged": 0}
    assert _as_utc(stored["observed_at_utc"]) == _as_utc(row["observed_at_utc"])
    assert stored["metadata_json"]["raw_archive_id"] == _ARCHIVE_FIELDS["raw_archive_id"]
    assert stored["metadata_json"]["payload_sha256"] == _ARCHIVE_FIELDS["payload_sha256"]


@pytest.mark.parametrize(("model", "normalizer", "payload_factory", "key_column"), _PRODUCTS)
def test_second_unchanged_poll_with_new_receipt_keeps_row_byte_for_byte(
    model: Any,
    normalizer: Any,
    payload_factory: Any,
    key_column: str,
) -> None:
    with _isolated_session() as session:
        first = _poll_row(
            _normalized_row(normalizer, payload_factory(), receipt=_FIRST_RECEIPT),
            receipt=_FIRST_RECEIPT,
            run_id="run-first",
            archive_id=_ARCHIVE_FIELDS["raw_archive_id"],
        )
        upsert_revision_safe_observation_rows(session, model, [first])
        session.flush()
        before = _row_snapshot(session, model, key_column)

        # Second poll: same semantic values, but a different receipt, run id and
        # archive id (a new raw page was archived for this poll).
        second = _poll_row(
            _normalized_row(normalizer, payload_factory(), receipt=_SECOND_RECEIPT),
            receipt=_SECOND_RECEIPT,
            run_id="run-second",
            archive_id="raw-0000000000000000bbbb",
        )
        outcome = upsert_revision_safe_observation_rows(session, model, [second])
        session.flush()
        after = _row_snapshot(session, model, key_column)

    assert outcome == {"inserted": 0, "unchanged": 1}
    # Byte-for-byte: every stored column, including the first-seen instant and the
    # original archive/receipt lineage, is unchanged.
    assert after == before
    assert after["metadata_json"]["ingestion_run_id"] == "run-first"
    assert after["metadata_json"]["raw_archive_id"] == _ARCHIVE_FIELDS["raw_archive_id"]
    assert after["metadata_json"]["source_receipt_at_utc"] == _FIRST_RECEIPT.isoformat()


@pytest.mark.parametrize(
    ("model", "normalizer", "payload_factory", "key_column", "revised_payload"),
    [
        pytest.param(
            StorageObservationRecord,
            gie_storage_observations_from_json,
            _agsi_payload,
            "facility_id",
            lambda: _agsi_payload(gas="700.00", updated_at="2026-06-01 10:00:00"),
            id="agsi",
        ),
        pytest.param(
            LngObservationRecord,
            gie_lng_observations_from_json,
            _alsi_payload,
            "terminal_id",
            lambda: _alsi_payload(inventory_gwh="50.0", updated_at="2026-06-01 10:00:00"),
            id="alsi",
        ),
    ],
)
def test_revised_value_is_refused_and_original_row_survives(
    model: Any,
    normalizer: Any,
    payload_factory: Any,
    key_column: str,
    revised_payload: Any,
) -> None:
    with _isolated_session() as session:
        first = _poll_row(
            _normalized_row(normalizer, payload_factory(), receipt=_FIRST_RECEIPT),
            receipt=_FIRST_RECEIPT,
            run_id="run-first",
            archive_id=_ARCHIVE_FIELDS["raw_archive_id"],
        )
        upsert_revision_safe_observation_rows(session, model, [first])
        session.flush()
        before = _row_snapshot(session, model, key_column)

        revised = _poll_row(
            _normalized_row(normalizer, revised_payload(), receipt=_SECOND_RECEIPT),
            receipt=_SECOND_RECEIPT,
            run_id="run-revised",
            archive_id="raw-0000000000000000cccc",
        )
        with pytest.raises(GieRevisionRequiresHistoryError) as refusal:
            # The ingest path wraps the batch in a savepoint; the refusal unwinds
            # only that savepoint, leaving the unchanged original row in place.
            with session.begin_nested():
                upsert_revision_safe_observation_rows(session, model, [revised])
                session.flush()

        after = _row_snapshot(session, model, key_column)
        session.rollback()

    assert refusal.value.code == "gie_revision_requires_history"
    assert after == before


@pytest.mark.parametrize(("model", "normalizer", "payload_factory", "key_column"), _PRODUCTS)
def test_mixed_batch_rolls_back_the_whole_savepoint(
    model: Any,
    normalizer: Any,
    payload_factory: Any,
    key_column: str,
) -> None:
    """One mismatch must leave all original rows unchanged and write nothing partial."""

    with _isolated_session() as session:
        original = _poll_row(
            _normalized_row(normalizer, payload_factory(), receipt=_FIRST_RECEIPT),
            receipt=_FIRST_RECEIPT,
            run_id="run-first",
            archive_id=_ARCHIVE_FIELDS["raw_archive_id"],
        )
        upsert_revision_safe_observation_rows(session, model, [original])
        session.flush()
        before = _row_snapshot(session, model, key_column)

        # A brand-new observation plus a revised one in the same batch. Persisting
        # the new row first and failing afterwards would leave a partial write, so
        # the whole batch runs in a savepoint that must roll back.
        pk_column = next(iter(model.__table__.primary_key.columns)).name
        new_row = dict(original)
        new_row[pk_column] = f"gie-{model.__tablename__}-new"
        new_row["source_record_id"] = "new-record"
        new_row["facility_id" if model is StorageObservationRecord else "terminal_id"] = "NEW"
        revised_row = dict(original)
        revised_row["inventory_twh"] = 999.0

        with pytest.raises(GieRevisionRequiresHistoryError):
            with session.begin_nested():
                upsert_revision_safe_observation_rows(session, model, [new_row, revised_row])
                session.flush()

        # The outer transaction is still usable -- exactly how the ingest path
        # records the real failed run after a revision refusal.
        session.add(
            AuditEventRecord(
                event_id="audit-mixed-batch",
                event_type="ingestion",
                severity="warning",
                principal="operator",
                action="public_source_ingest",
                resource="source:GIE-TEST",
                outcome="failed",
                detail="persist:gie_revision_requires_history",
                event_ts_utc=datetime.now(UTC),
                source_system="eurogas-nexus",
                human_review_required=True,
            )
        )
        session.flush()
        after = _row_snapshot(session, model, key_column)
        row_count = session.execute(
            select(text("count(*)")).select_from(model.__table__)
        ).scalar_one()
        audit_count = session.execute(
            select(text("count(*)")).select_from(AuditEventRecord.__table__)
        ).scalar_one()
        session.commit()

    assert after == before
    assert row_count == 1, "a partial canonical write survived the failed batch"
    assert audit_count == 1, "the failure record must survive the savepoint rollback"


@pytest.mark.parametrize(("model", "normalizer", "payload_factory", "key_column"), _PRODUCTS)
def test_conflicting_concurrent_ingest_serializes_on_the_natural_key(
    model: Any,
    normalizer: Any,
    payload_factory: Any,
    key_column: str,
) -> None:
    """Two overlapping ingests of the same key: the loser re-reads, never overwrites.

    The winner holds the row lock (its INSERT is flushed but not committed) while
    the loser's ``INSERT ... ON CONFLICT DO NOTHING`` runs and blocks on it. Only
    after the loser has reached its INSERT does the winner commit; the loser's
    insert then reports a conflict, the helper re-reads the committed row and
    verifies it instead of duplicating or rewriting it.
    """

    url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    engine: Engine = create_engine(url, future=True)
    schema = f"gierev_{uuid4().hex}"
    factory = sessionmaker(bind=engine, future=True)
    result: dict[str, Any] = {}
    loser_ready = threading.Event()
    loser_at_insert = threading.Event()
    loser_finished = threading.Event()
    winner_committed = threading.Event()
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            model.__table__.create(bind=connection)

        first = _poll_row(
            _normalized_row(normalizer, payload_factory(), receipt=_FIRST_RECEIPT),
            receipt=_FIRST_RECEIPT,
            run_id="run-winner",
            archive_id=_ARCHIVE_FIELDS["raw_archive_id"],
        )
        # Same semantic values, different receipt/run/archive: a second poll that
        # must verify rather than duplicate or rewrite.
        identical = _poll_row(
            _normalized_row(normalizer, payload_factory(), receipt=_FIRST_RECEIPT),
            receipt=_SECOND_RECEIPT,
            run_id="run-loser",
            archive_id="raw-0000000000000000dddd",
        )

        def loser() -> None:
            with factory() as session:
                session.execute(text(f'SET search_path TO "{schema}"'))
                loser_ready.set()
                # The winner stays open until this thread reaches (and blocks in)
                # its INSERT, which keeps the overlap deterministic.
                loser_at_insert.wait(timeout=10)
                try:
                    result["outcome"] = upsert_revision_safe_observation_rows(
                        session, model, [identical]
                    )
                except Exception as exc:  # noqa: BLE001 - recorded for the assertion
                    result["error"] = exc
                finally:
                    loser_finished.set()
                winner_committed.wait(timeout=10)
                session.commit()

        worker = threading.Thread(target=loser)
        worker.start()
        assert loser_ready.wait(timeout=10)

        with factory() as winner:
            winner.execute(text(f'SET search_path TO "{schema}"'))
            upsert_revision_safe_observation_rows(winner, model, [first])
            winner.flush()  # the INSERT holds the row lock; the transaction is open
            loser_at_insert.set()
            # The loser cannot finish while the winner's row is uncommitted.
            assert not loser_finished.wait(timeout=1.0), "the loser did not block on the row lock"
            winner.commit()
        winner_committed.set()
        worker.join(timeout=15)

        assert not worker.is_alive(), "the loser never completed after the winner committed"
        assert "error" not in result, f"concurrent identical poll failed: {result.get('error')}"
        assert result["outcome"] == {"inserted": 0, "unchanged": 1}

        with factory() as session:
            session.execute(text(f'SET search_path TO "{schema}"'))
            stored = _row_snapshot(session, model, key_column)

        # The winner's row survives with the winner's original lineage.
        assert stored["metadata_json"]["ingestion_run_id"] == "run-winner"
    finally:
        loser_at_insert.set()
        winner_committed.set()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_conflicting_concurrent_revision_is_refused_not_overwritten() -> None:
    """A concurrent revised value loses the race and is refused, not merged."""

    url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    engine: Engine = create_engine(url, future=True)
    schema = f"gierev_{uuid4().hex}"
    factory = sessionmaker(bind=engine, future=True)
    result: dict[str, Any] = {}
    loser_ready = threading.Event()
    loser_at_insert = threading.Event()
    loser_finished = threading.Event()
    winner_committed = threading.Event()
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            StorageObservationRecord.__table__.create(bind=connection)

        first = _poll_row(
            _normalized_row(
                gie_storage_observations_from_json, _agsi_payload(), receipt=_FIRST_RECEIPT
            ),
            receipt=_FIRST_RECEIPT,
            run_id="run-winner",
            archive_id=_ARCHIVE_FIELDS["raw_archive_id"],
        )
        revised = _poll_row(
            _normalized_row(
                gie_storage_observations_from_json,
                _agsi_payload(gas="700.00"),
                receipt=_FIRST_RECEIPT,
            ),
            receipt=_SECOND_RECEIPT,
            run_id="run-loser",
            archive_id="raw-0000000000000000eeee",
        )

        def loser() -> None:
            with factory() as session:
                session.execute(text(f'SET search_path TO "{schema}"'))
                loser_ready.set()
                loser_at_insert.wait(timeout=10)
                try:
                    result["outcome"] = upsert_revision_safe_observation_rows(
                        session, StorageObservationRecord, [revised]
                    )
                except GieRevisionRequiresHistoryError as exc:
                    result["code"] = exc.code
                finally:
                    loser_finished.set()
                winner_committed.wait(timeout=10)
                session.commit()

        worker = threading.Thread(target=loser)
        worker.start()
        assert loser_ready.wait(timeout=10)

        with factory() as winner:
            winner.execute(text(f'SET search_path TO "{schema}"'))
            upsert_revision_safe_observation_rows(winner, StorageObservationRecord, [first])
            winner.flush()
            loser_at_insert.set()
            assert not loser_finished.wait(timeout=1.0), "the loser did not block on the row lock"
            winner.commit()
        winner_committed.set()
        worker.join(timeout=15)

        assert not worker.is_alive(), "the loser never completed after the winner committed"
        assert result.get("code") == "gie_revision_requires_history"
        assert "outcome" not in result

        with factory() as session:
            session.execute(text(f'SET search_path TO "{schema}"'))
            stored = _row_snapshot(session, StorageObservationRecord, "facility_id")

        assert stored["inventory_twh"] == pytest.approx(650.25)
        assert stored["metadata_json"]["ingestion_run_id"] == "run-winner"
    finally:
        loser_at_insert.set()
        winner_committed.set()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_batch_repeating_a_natural_key_is_refused() -> None:
    with _isolated_session() as session:
        row = _normalized_row(
            gie_storage_observations_from_json, _agsi_payload(), receipt=_FIRST_RECEIPT
        )
        with pytest.raises(ValueError, match="repeats natural key"):
            upsert_revision_safe_observation_rows(
                session, StorageObservationRecord, [row, dict(row)]
            )
