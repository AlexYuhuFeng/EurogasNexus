"""Re-split ENTSOG capacity ranges and power revisions on real PostgreSQL.

The re-split pass reads JSON metadata and timestamp columns with PostgreSQL types, and the
data-quality overlap count uses ``->>``; power history goes through the widened
``observation_revisions`` checks of migration 0063. Runs in a throwaway schema.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from eurogas_nexus.application import data_quality_report
from eurogas_nexus.application.capacity_resolution import (
    resolve_capacity,
    resolve_capacity_as_of,
)
from eurogas_nexus.db.models import CapacityObservationRecord, ObservationRevisionRecord
from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.db.repositories.entsog_observation_persistence import (
    upsert_entsog_observation_rows,
)
from eurogas_nexus.db.repositories.observation_revisions import versions_as_of
from eurogas_nexus.db.repositories.power import upsert_power_observations
from eurogas_nexus.ingestion.entsoe_transparency import PowerObservation
from eurogas_nexus.ingestion.public_sources import entsog_capacity_observations_from_json

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; tables use a disposable schema.",
)

READ_1 = datetime(2026, 11, 12, 11, 56, 28, tzinfo=UTC)
READ_2 = datetime(2026, 11, 13, 15, 45, tzinfo=UTC)
READ_3 = datetime(2026, 11, 14, 1, 3, 58, tzinfo=UTC)
LONG, DAY_AHEAD = 64367976, 28127976


@contextmanager
def _session():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    schema = f"crtest_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (
                CapacityObservationRecord,
                PowerObservationRecord,
                ObservationRevisionRecord,
            ):
                model.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _record(start: str, end: str, value: int):
    return {
        "id": f"1Firm TechnicaldayDE-TSO-0001UGS-00397entrykWh/d{start}{end}",
        "indicator": "Firm Technical",
        "pointKey": "UGS-00397",
        "pointLabel": "UGS Epe",
        "operatorKey": "DE-TSO-0001",
        "directionKey": "entry",
        "unit": "kWh/d",
        "periodType": "day",
        "value": value,
        "periodFrom": f"{start}T06:00:00+01:00",
        "periodTo": f"{end}T06:00:00+01:00",
    }


def _store(session, records, receipt):
    payload = json.loads(
        json.dumps({"operationaldatas": records}), parse_float=str, parse_int=str
    )
    rows = entsog_capacity_observations_from_json(payload, observed_at_utc=receipt)
    for row in rows:
        row["source_reference"] = f"entsog-test;receipt={receipt.isoformat()}"
    return upsert_entsog_observation_rows(session, CapacityObservationRecord, rows)


def _on(resolved, day):
    moment = datetime(2026, 11, day, 5, tzinfo=UTC)
    return [item.original_value for item in resolved if item.start <= moment < item.end]


def test_resplit_ranges_resolve_and_a_republished_range_moves_forward():
    with _session() as session:
        _store(session, [_record("2026-11-13", "2026-12-01", LONG)], READ_1)
        _store(
            session,
            [
                _record("2026-11-13", "2026-11-14", DAY_AHEAD),
                _record("2026-11-14", "2026-12-01", LONG),
            ],
            READ_2,
        )
        rows = session.execute(select(CapacityObservationRecord)).scalars().all()
        assert _on(resolve_capacity(rows), 13) == [DAY_AHEAD]

        spec = next(s for s in data_quality_report.SPECS if s.dataset == "ENTSOG capacity")
        quality = data_quality_report.measure(session, spec, READ_3)
        assert quality.duplicate_keys == 0 and quality.overlapping_rows == 3

        outcome = _store(session, [_record("2026-11-13", "2026-12-01", LONG)], READ_3)
        assert outcome["resplit"] == 1
        session.expire_all()
        rows = session.execute(select(CapacityObservationRecord)).scalars().all()
        assert _on(resolve_capacity(rows), 13) == [LONG]
        before = resolve_capacity_as_of(session, rows, READ_3 - timedelta(minutes=5))
        assert _on(before, 13) == [DAY_AHEAD]
        record = session.execute(select(ObservationRevisionRecord)).scalar_one()
        assert record.reason == "range_resplit" and record.prior_received_at_utc == READ_1


def test_power_revision_history_on_postgres():
    start = datetime(2026, 11, 13, 10, tzinfo=UTC)

    def load(value):
        return PowerObservation(
            zone="NL", metric="load_actual", period_start_utc=start,
            period_end_utc=start + timedelta(minutes=15), value=value, unit="MW",
            published_at_utc=start + timedelta(hours=1, minutes=15),
            source_reference="entsoe:test", process_type="A16",
        )

    with _session() as session:
        upsert_power_observations(session, [load(11_250.0)], now=READ_2)
        counts = upsert_power_observations(session, [load(11_312.5)], now=READ_3)
        assert counts["revised"] == 1
        rows = session.execute(select(PowerObservationRecord)).scalars().all()
        assert [v.value for v in versions_as_of(session, rows, READ_3 - timedelta(hours=1))] == [
            11_250.0
        ]
        spec = next(s for s in data_quality_report.SPECS if s.dataset == "Power (ENTSO-E)")
        quality = data_quality_report.DatasetQuality(spec.dataset, spec.source)
        data_quality_report._revisions(session, spec, quality, READ_3 + timedelta(hours=1))
        assert quality.revised_rows == 1
