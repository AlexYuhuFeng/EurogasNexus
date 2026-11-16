"""PostgreSQL: ENTSOG UMM versions in the REMIT store, and GIE facility identity.

Each test creates a disposable schema holding the tables its code reads and writes
(``remit_umm_messages``; ``canonical_entities`` and ``source_entity_mappings`` for the
identity), and drops it afterwards. Skipped unless an explicit PostgreSQL URL is configured.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.application.remit_outages import load_outage_rows
from eurogas_nexus.db.models import (
    CanonicalEntityRecord,
    RemitUmmRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.db.repositories.gie_facilities import (
    load_gie_facilities,
    upsert_gie_facilities,
)
from eurogas_nexus.db.repositories.remit import store_umm_messages
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion.entsog_umm import acer_messages
from eurogas_nexus.ingestion.gie_facilities import one_per_eic, parse_listing

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; each test uses a disposable schema.",
)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "remit"
NOW = datetime(2026, 11, 16, 9, 0, tzinfo=UTC)


@contextmanager
def _session():
    url = make_url(_POSTGRES_URL)
    connect_args = {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"outageidentity_{uuid4().hex}"
    created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (RemitUmmRecord, CanonicalEntityRecord, SourceEntityMappingRecord):
                model.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        try:
            if created:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()


def test_entsog_versions_stored_once_and_inactive_ends_the_event():
    records = json.loads((FIXTURES / "entsog_umm_page.json").read_text())[
        "urgentmarketmessages"
    ]
    messages = parse_umm_export(
        json.dumps(acer_messages(records, since=NOW - timedelta(days=7))),
        source_reference="ENTSOG_TP:terms-published:api:20261116T0900Z",
    )
    with _session() as session:
        first = store_umm_messages(session, messages, now=NOW, source_system="ENTSOG_UMM")
        again = store_umm_messages(session, messages, now=NOW, source_system="ENTSOG_UMM")
        session.flush()
        assert first["inserted"] == 7 and again == {"inserted": 0, "updated": 0,
                                                     "unchanged": 7}
        statuses = dict(session.execute(
            select(RemitUmmRecord.record_id, RemitUmmRecord.event_status)
        ).all())
        assert statuses["25102721X-FR-A-A0A0A-S001:5"] == "inactive"
        rows = {row["event_id"]: row for row in load_outage_rows(
            session, now=NOW, horizon_days=90)}
    assert "25102721X-FR-A-A0A0A-S001" not in rows  # inactive: the event is over
    assert "V0025728/1---------------" not in rows  # dismissed
    assert rows["26030821X-BE-A-A0A0A-Y003"]["attribution"] == (
        "ENTSOG TP [16-11-2026] https://transparency.entsog.eu/"
    )


def test_gie_facility_identity_upsert_retire_restore():
    listing = json.loads((FIXTURES / "gie_facility_listing.json").read_text())
    facilities, _ = one_per_eic(
        parse_listing(listing["agsi"], "storage") + parse_listing(listing["alsi"], "lng")
    )
    with _session() as session:
        assert upsert_gie_facilities(session, facilities, now=NOW)["inserted"] == 7
        assert upsert_gie_facilities(
            session, facilities[1:], now=NOW + timedelta(days=1)
        )["retired"] == 1
        assert len(load_gie_facilities(session)) == 6
        retired = session.scalars(select(SourceEntityMappingRecord).where(
            SourceEntityMappingRecord.mapping_status == "RETIRED")).one()
        assert retired.valid_to_utc is not None
        assert upsert_gie_facilities(session, facilities, now=NOW)["restored"] == 1
        assert len(load_gie_facilities(session)) == 7
        assert session.execute(
            select(CanonicalEntityRecord.entity_type).distinct()
        ).scalars().all() == ["gie_facility"]
