"""ONT-02 and FRESH-01 on PostgreSQL: mappings, the identity report and last receipts."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from eurogas_nexus.application.data_quality_report import SPECS, last_received, measure
from eurogas_nexus.application.identity_resolution import (
    entsog_reference_identities,
    identity_report,
    load_resolver,
    record_identities,
)
from eurogas_nexus.application.physical_native_rates import serialize_native_rate
from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    CapacityObservationRecord,
    FlowObservationRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.ingestion.entsog_native_units import parse_entsog_native_rate

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; tables use a disposable schema.",
)

DAY = datetime(2026, 11, 10, 5, tzinfo=UTC)


@contextmanager
def _session():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    schema = f"idtest_{uuid4().hex}"
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (CanonicalEntityRecord, SourceEntityMappingRecord,
                          FlowObservationRecord, CapacityObservationRecord):
                model.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def _flow(observation_id: str, point: str, operator: str, revised=None):
    native = serialize_native_rate(parse_entsog_native_rate("1000.0", "kWh/d"))
    return FlowObservationRecord(
        observation_id=observation_id, point_id=point, point_name=point, direction="entry",
        kind="actual", flow_mcm_d=None, original_value=1000.0, original_unit="kWh/d",
        period_start_utc=DAY, period_end_utc=DAY + timedelta(days=1),
        observed_at_utc=DAY + timedelta(days=1), revised_at_utc=revised,
        source_system="ENTSOG", source_reference="t", freshness="daily", research_only=True,
        metadata_json={"operatorKey": operator},
        normalizer_version=native["normalizer_version"], native_rate_json=native,
    )


def test_mappings_resolve_and_unknown_keys_are_listed_on_postgresql() -> None:
    with _session() as session:
        identities = entsog_reference_identities(
            [{"source_system": "ENTSOG", "source_record_id": "ITP-00106", "name": "ZPT"}],
            [{"point_key": "ITP-00106", "operator_key": "BE-TSO-0001"}],
        )
        assert record_identities(session, identities)["mappings_added"] == 2
        assert record_identities(session, identities)["mappings_added"] == 0
        revised = DAY + timedelta(days=2)
        session.add_all([
            _flow("a", "ITP-00106", "BE-TSO-0001", revised=revised),
            _flow("b", "ITP-99999", "BE-TSO-0001"),
        ])
        session.flush()
        report = identity_report(session, load_resolver(session))["src-entsog"]
        assert (report["checked"], report["resolved"]) == (3, 2)
        assert [u["identifier"] for u in report["unresolved"]] == ["ITP-99999"]

        # FRESH-01: last received is the later of first receipt and revision.
        spec = next(s for s in SPECS if s.dataset == "ENTSOG flows")
        received, period = last_received(session, spec)
        assert received == revised and period == DAY
        assert measure(session, spec, DAY + timedelta(days=3)).max_age_hours == 54
