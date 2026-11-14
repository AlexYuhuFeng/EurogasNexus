"""National Gas GB storage/LNG keep provider revisions with history (real PostgreSQL).

A nomination-based (provisional) value replaced by the allocation, and a stock published
after the first run, must replace the current row and append the replaced version to
``observation_revisions``; the row keeps its first receipt. Runs in a throwaway schema.
"""

from __future__ import annotations

import importlib.util
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    LngObservationRecord,
    ObservationRevisionRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GieRevisionIdentityConflictError,
    upsert_revision_safe_observation_rows,
)
from eurogas_nexus.ingestion.national_gas_supply import NOMINATION, _row

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; tables use a disposable schema.",
)

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ops/ingest_national_gas_supply.py"
FIRST = datetime(2026, 11, 13, 9, tzinfo=UTC)
SECOND = FIRST + timedelta(days=1)
DAY = date(2026, 11, 12)


def _script():
    spec = importlib.util.spec_from_file_location("ingest_national_gas_supply", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _session():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    schema = f"ngtest_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (
                StorageObservationRecord,
                LngObservationRecord,
                ObservationRevisionRecord,
            ):
                model.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _storage(received, *, withdrawal, stock, basis):
    row = _row("storage", DAY, [], received)
    row.update({"withdrawal_twh_d": withdrawal, "injection_twh_d": 0.0, "inventory_twh": stock})
    row["metadata_json"] = {
        **row["metadata_json"],
        "basis": dict(basis),
        "provisional": NOMINATION in basis.values(),
    }
    return row


def _write(session, script, model, rows):
    return upsert_revision_safe_observation_rows(
        session,
        model,
        rows,
        semantic_metadata_keys=script.NATIONAL_GAS_REVISABLE_METADATA,
        revisions=script.national_gas_revision_policy(model.__tablename__),
    )


def test_allocation_and_late_stock_are_revisions_with_first_receipt_kept():
    script = _script()
    nomination = {"withdrawal_twh_d": NOMINATION, "injection_twh_d": NOMINATION}
    allocation = {"withdrawal_twh_d": "allocation", "injection_twh_d": "allocation"}
    with _session() as session:
        first = _write(
            session, script, StorageObservationRecord,
            [_storage(FIRST, withdrawal=0.0785, stock=None, basis=nomination)],
        )
        assert first["inserted"] == 1
        # Same day re-read unchanged: nothing written.
        again = _write(
            session, script, StorageObservationRecord,
            [_storage(FIRST + timedelta(hours=1), withdrawal=0.0785, stock=None, basis=nomination)],
        )
        assert again["unchanged"] == 1 and again["revised"] == 0
        # D+2: the allocation and the stock arrive.
        later = _write(
            session, script, StorageObservationRecord,
            [_storage(SECOND, withdrawal=0.0810, stock=9.6,
                      basis={**allocation, "inventory_twh": "stock"})],
        )
        assert later == {"inserted": 0, "updated": 1, "unchanged": 0, "revised": 1}
        row = session.execute(select(StorageObservationRecord)).scalar_one()
        assert row.withdrawal_twh_d == 0.0810 and row.inventory_twh == 9.6
        assert row.observed_at_utc == FIRST and row.revised_at_utc == SECOND
        assert row.metadata_json["provisional"] is False
        (revision,) = session.execute(select(ObservationRevisionRecord)).scalars()
        assert revision.reason == "value_changed"
        assert revision.prior_row_json["withdrawal_twh_d"] == 0.0785
        assert revision.prior_row_json["metadata_json"]["provisional"] is True
        assert {"withdrawal_twh_d", "inventory_twh", "metadata_json.provisional"} <= set(
            revision.changed_fields
        )
        assert revision.prior_received_at_utc == FIRST and revision.superseded_at_utc == SECOND


def test_a_final_figure_equal_to_the_nomination_is_still_recorded_as_final():
    script = _script()
    with _session() as session:
        _write(session, script, StorageObservationRecord, [_storage(
            FIRST, withdrawal=0.05, stock=None,
            basis={"withdrawal_twh_d": NOMINATION, "injection_twh_d": NOMINATION})])
        outcome = _write(session, script, StorageObservationRecord, [_storage(
            SECOND, withdrawal=0.05, stock=None,
            basis={"withdrawal_twh_d": "allocation", "injection_twh_d": "allocation"})])
        assert outcome["updated"] == 1
        (revision,) = session.execute(select(ObservationRevisionRecord)).scalars()
        assert "metadata_json.provisional" in revision.changed_fields


def test_an_identity_change_is_refused():
    script = _script()
    with _session() as session:
        row = _storage(FIRST, withdrawal=0.05, stock=None, basis={"withdrawal_twh_d": "allocation"})
        _write(session, script, StorageObservationRecord, [row])
        moved = {**_storage(SECOND, withdrawal=0.06, stock=None,
                            basis={"withdrawal_twh_d": "allocation"}), "country": "IE"}
        with pytest.raises(GieRevisionIdentityConflictError):
            _write(session, script, StorageObservationRecord, [moved])
