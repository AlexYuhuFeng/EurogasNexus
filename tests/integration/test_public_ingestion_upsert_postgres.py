"""PostgreSQL-only persistence tests for GIE observation upserts.

These tests exercise the **real** ``upsert_observation_rows`` helper against a
real PostgreSQL engine, not a mock and not a compile-only assertion. Each test
runs inside a uniquely named throwaway schema of the configured test database
(created and dropped by the helper), so no existing table, row or schema is
touched.

What they pin down:

* a new response receipt on every poll changes ``metadata_json`` (receipt instant,
  ingestion run, adapter version) but must **not** create a second row and must
  **not** rewrite the first-seen ``observed_at_utc``;
* a genuinely changed provider value is written in place and stays visible in the
  revised provider stamp, but the observation tables have no per-observation
  revision/history row -- that limitation is asserted, not papered over;
* availability metadata follows the latest poll while ``observed_at_utc`` stays
  first-seen, which is the precise schema limitation this slice reports.

Skip when ``RUNTIME_STORE_DATABASE_URL`` is not a PostgreSQL URL; run via
``scripts/ci/run_postgres_ci.sh`` or against the disposable local test database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import LngObservationRecord, StorageObservationRecord
from eurogas_nexus.db.repositories.public_ingestion_upsert import upsert_observation_rows
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

_CODE = "TSTGIEUP"
_FIRST_RECEIPT = datetime(2026, 5, 29, 15, 0, tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalize a driver timestamp (naive or aware) to an aware UTC instant."""

    return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _agsi_payload(
    *,
    gas: str = "650.25",
    updated_at: str = "2026-05-29 12:00:00",
) -> dict[str, Any]:
    return {
        "data": [
            {
                "code": _CODE,
                "name": "Test storage",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
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
    updated_at: str = "2026-05-29 12:00:00",
) -> dict[str, Any]:
    return {
        "data": [
            {
                "code": _CODE,
                "name": "Test LNG terminal",
                "gasDayStart": "2026-05-29",
                "gasDayEnd": "2026-05-30",
                "inventory": {"lng": "9.5", "gwh": inventory_gwh},
                "sendOut": "3.4",
                "dtmi": {"lng": "14.4", "gwh": "65.0"},
                "updatedAt": updated_at,
            }
        ]
    }


def _poll_row(
    row: dict[str, Any], *, receipt: datetime, run_id: str
) -> dict[str, Any]:
    """Apply the poll-scoped lineage the ingest script adds before persistence."""

    metadata = dict(row["metadata_json"])
    metadata["source_receipt_at_utc"] = receipt.isoformat()
    metadata["ingestion_run_id"] = run_id
    metadata["adapter_version"] = "public-source-ingestor/1"
    return {**row, "metadata_json": metadata}


@contextmanager
def _isolated_session() -> Iterator[Session]:
    """Create a throwaway schema, yield a session, then drop the schema."""

    url = os.environ["RUNTIME_STORE_DATABASE_URL"]
    engine: Engine = create_engine(url, future=True)
    schema = f"gieupsert_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET search_path TO "{schema}"'))
            StorageObservationRecord.__table__.create(bind=connection)
            LngObservationRecord.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


_PRODUCTS = [
    pytest.param(
        StorageObservationRecord,
        gie_storage_observations_from_json,
        _agsi_payload,
        "facility_id",
        "inventory_twh",
        650.25,
        id="agsi",
    ),
    pytest.param(
        LngObservationRecord,
        gie_lng_observations_from_json,
        _alsi_payload,
        "terminal_id",
        "inventory_twh",
        0.0425,
        id="alsi",
    ),
]


def _select_row(session: Session, model: Any, key_column: str, value_column: str):
    column = getattr(model, key_column)
    return session.execute(
        select(
            model.observed_at_utc,
            getattr(model, value_column),
            model.metadata_json,
        ).where(column == _CODE)
    ).all()


@pytest.mark.parametrize(
    ("model", "normalizer", "payload_factory", "key_column", "value_column", "expected_value"),
    _PRODUCTS,
)
def test_unchanged_semantic_rows_preserve_first_seen_without_a_revision_row(
    model: Any,
    normalizer: Any,
    payload_factory: Any,
    key_column: str,
    value_column: str,
    expected_value: float,
) -> None:
    """Two polls with a new receipt must not create a row or rewrite first-seen."""

    second_receipt = _FIRST_RECEIPT + timedelta(hours=1)

    with _isolated_session() as session:
        first = normalizer(payload_factory(), observed_at_utc=_FIRST_RECEIPT)[0]
        upsert_observation_rows(
            session,
            model,
            [_poll_row(first, receipt=_FIRST_RECEIPT, run_id="run-first")],
        )
        session.flush()

        second = normalizer(payload_factory(), observed_at_utc=second_receipt)[0]
        upsert_observation_rows(
            session,
            model,
            [_poll_row(second, receipt=second_receipt, run_id="run-second")],
        )
        session.flush()

        rows = _select_row(session, model, key_column, value_column)

    assert len(rows) == 1
    observed_at, value, metadata = rows[0]
    assert _as_utc(observed_at) == _FIRST_RECEIPT
    assert value == pytest.approx(expected_value)
    # The poll metadata did churn -- but that is metadata, not a new observation.
    assert metadata["source_receipt_at_utc"] == second_receipt.isoformat()
    assert metadata["ingestion_run_id"] == "run-second"
    assert metadata["availability_basis"] == "response_receipt"


def test_changed_value_updates_in_place_and_stays_visible_in_metadata() -> None:
    """A revised value overwrites the row; the provider stamp records the revision."""

    second_receipt = _FIRST_RECEIPT + timedelta(hours=1)

    with _isolated_session() as session:
        first = gie_storage_observations_from_json(
            _agsi_payload(gas="650.25", updated_at="2026-05-29 10:00:00"),
            observed_at_utc=_FIRST_RECEIPT,
        )[0]
        upsert_observation_rows(
            session,
            StorageObservationRecord,
            [_poll_row(first, receipt=_FIRST_RECEIPT, run_id="run-1")],
        )
        session.flush()

        revised = gie_storage_observations_from_json(
            _agsi_payload(gas="700.00", updated_at="2026-05-29 14:00:00"),
            observed_at_utc=second_receipt,
        )[0]
        upsert_observation_rows(
            session,
            StorageObservationRecord,
            [_poll_row(revised, receipt=second_receipt, run_id="run-2")],
        )
        session.flush()

        rows = _select_row(
            session, StorageObservationRecord, "facility_id", "inventory_twh"
        )

    assert len(rows) == 1
    observed_at, value, metadata = rows[0]
    assert value == pytest.approx(700.0)
    # No revision/history row exists; the change is visible in the value and the
    # revised provider stamp, while observed_at_utc stays the first-seen instant.
    assert _as_utc(observed_at) == _FIRST_RECEIPT
    assert metadata["updatedAt"] == "2026-05-29 14:00:00"


def test_provider_offset_poll_updates_availability_but_not_first_seen() -> None:
    """The single-row schema cannot retain per-poll availability; assert the limit."""

    second_receipt = _FIRST_RECEIPT + timedelta(hours=1)

    with _isolated_session() as session:
        first = gie_storage_observations_from_json(
            _agsi_payload(updated_at="2026-05-29 12:00:00"),
            observed_at_utc=_FIRST_RECEIPT,
        )[0]
        upsert_observation_rows(
            session,
            StorageObservationRecord,
            [_poll_row(first, receipt=_FIRST_RECEIPT, run_id="run-bare")],
        )
        session.flush()

        # The second poll carries a proven offset, so the normalizer uses the
        # provider instant and labels the availability basis accordingly.
        second = gie_storage_observations_from_json(
            _agsi_payload(updated_at="2026-05-29T14:00:00+02:00"),
            observed_at_utc=second_receipt,
        )[0]
        assert second["observed_at_utc"] == datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
        upsert_observation_rows(
            session,
            StorageObservationRecord,
            [_poll_row(second, receipt=second_receipt, run_id="run-offset")],
        )
        session.flush()

        rows = _select_row(
            session, StorageObservationRecord, "facility_id", "inventory_twh"
        )

    assert len(rows) == 1
    observed_at, _, metadata = rows[0]
    # first-seen is preserved ...
    assert _as_utc(observed_at) == _FIRST_RECEIPT
    # ... while availability metadata describes the latest poll. There is no
    # per-poll availability column, so this mixing is the precise limitation.
    assert metadata["availability_basis"] == "provider_updated_at"
    assert metadata["provider_updated_at_zone"] == "provider_offset"
    assert metadata["source_receipt_at_utc"] == second_receipt.isoformat()
