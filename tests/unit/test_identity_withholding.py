"""A row whose provider identifier does not resolve is withheld from readers, not only listed.

The rows stay stored (history and the Sources list keep them); a mapping releases them.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.identity_resolution import (
    entsog_reference_identities,
    identity_clause,
    identity_report,
    record_identities,
    withheld_counts,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import CapacityObservationRecord, FlowObservationRecord
from eurogas_nexus.db.models.observation import StorageObservationRecord

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 10, 5, tzinfo=UTC)


def _capacity(oid: str, point: str, operator: str | None, source: str = "ENTSOG"):
    return CapacityObservationRecord(
        observation_id=oid,
        point_id=point,
        point_name=point,
        direction="entry",
        capacity_type="firm_technical",
        capacity_mcm_d=10.0,
        period_start_utc=T0,
        period_end_utc=T0 + timedelta(days=1),
        observed_at_utc=T0 + timedelta(hours=1),
        source_system=source,
        source_reference="test",
        freshness="daily",
        research_only=True,
        metadata_json={"operatorKey": operator} if operator else {},
    )


def _storage(oid: str, facility: str, source: str = "GIE"):
    return StorageObservationRecord(
        observation_id=oid,
        source_dataset="agsi",
        facility_id=facility,
        facility_name=facility,
        country="DE",
        inventory_twh=10.0,
        working_capacity_twh=20.0,
        period_start_utc=T0,
        period_end_utc=T0 + timedelta(days=1),
        observed_at_utc=T0 + timedelta(hours=30),
        source_system=source,
        source_reference="test",
        freshness="daily",
        research_only=True,
    )


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'id.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                _capacity("known", "ITP-00001", "DE-TSO-0001"),
                _capacity("no-operator", "ITP-00001", None),
                _capacity("old-point", "ITP-00044", "DE-TSO-0001"),
                _capacity("old-operator", "ITP-00001", "DE-TSO-0013"),
                _capacity("demo", "ITP-00044", None, source="DEMO_Sim"),
                _storage("gie-de", "DE"),
                _storage("gie-facility", "REHDEN"),
                _storage("demo-store", "REHDEN", source="DEMO_Sim"),
            ]
        )
        db.commit()
        yield db


def _served(session, model) -> set[str]:
    return set(
        session.scalars(select(model.observation_id).where(identity_clause(session, model)))
    )


def _reference(session):
    record_identities(
        session,
        entsog_reference_identities(
            [{"source_system": "ENTSOG", "source_record_id": "ITP-00001", "name": "Point"}],
            [{"point_key": "ITP-00001", "operator_key": "DE-TSO-0001", "operator_name": "TSO"}],
        ),
    )
    session.commit()


def test_before_the_first_reference_read_entsog_keys_are_not_judged(session):
    assert _served(session, CapacityObservationRecord) == {
        "known", "no-operator", "old-point", "old-operator", "demo",
    }


def test_unresolved_point_and_operator_keys_are_withheld_once_the_reference_is_read(session):
    _reference(session)
    assert _served(session, CapacityObservationRecord) == {"known", "no-operator", "demo"}
    # Stored rows are untouched.
    assert session.scalar(select(func.count()).select_from(CapacityObservationRecord)) == 5
    counts = withheld_counts(session)
    assert counts["capacity_observations"] == 2
    assert counts["flow_observations"] == 0
    # The Sources list names exactly what is withheld.
    unresolved = identity_report(session)["src-entsog"]["unresolved"]
    assert {(item["identifier"], item["withheld"]) for item in unresolved} == {
        ("ITP-00044", True), ("DE-TSO-0013", True),
    }


def test_gie_identifiers_outside_the_published_list_are_withheld(session):
    assert _served(session, StorageObservationRecord) == {"gie-de", "demo-store"}


def test_a_mapping_releases_the_rows_and_retiring_it_withholds_them_again(session):
    from eurogas_nexus.db.models import SourceEntityMappingRecord

    _reference(session)
    spec = importlib.util.spec_from_file_location(
        "release", ROOT / "scripts" / "ops" / "release_quarantined_identifier.py"
    )
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    dry = release.release(
        session,
        source_id="src-entsog",
        entity_type="entsog_point",
        identifiers=["ITP-00044"],
        evidence="Dragor, ENTSOG 2019 reference",
    )
    assert dry["withheld_rows_before"]["capacity_observations"] == 2
    assert dry["withheld_rows_after"]["capacity_observations"] == 1
    assert "old-point" not in _served(session, CapacityObservationRecord)  # rolled back
    done = release.release(
        session,
        source_id="src-entsog",
        entity_type="entsog_point",
        identifiers=["ITP-00044"],
        evidence="Dragor, ENTSOG 2019 reference",
        commit=True,
    )
    assert done["committed"] and "old-point" in _served(session, CapacityObservationRecord)
    mapping = session.get(SourceEntityMappingRecord, "map:src-entsog:entsog_point:ITP-00044")
    mapping.mapping_status = "RETIRED"
    session.commit()
    assert "old-point" not in _served(session, CapacityObservationRecord)


def test_an_identifier_mapped_to_two_entities_is_withheld(session):
    from eurogas_nexus.db.models import CanonicalEntityRecord, SourceEntityMappingRecord

    _reference(session)
    now = datetime.now(UTC)
    session.add(
        CanonicalEntityRecord(
            canonical_entity_id="ent:point:OTHER", entity_type="point",
            canonical_code="OTHER", display_name="Other", description="", created_at_utc=now,
        )
    )
    session.add(
        SourceEntityMappingRecord(
            mapping_id="map:dup", canonical_entity_id="ent:point:OTHER", source_id="src-entsog",
            source_entity_type="entsog_point", source_identifier="ITP-00001",
            valid_from_utc=now - timedelta(days=1), mapping_status="ACTIVE",
            confidence="CONFIRMED", evidence="test", created_at_utc=now,
        )
    )
    session.commit()
    assert _served(session, CapacityObservationRecord) == {"demo"}


def test_the_storage_reader_serves_only_resolved_rows(session, monkeypatch):
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", str(session.get_bind().url))
    response = TestClient(create_app()).get("/api/storage/observations")
    assert response.status_code == 200, response.text
    served = {row["observation_id"] for row in response.json()["data"]}
    assert served == {"gie-de", "demo-store"}  # GIE "REHDEN" is not a GIE identifier


def test_flow_rows_follow_the_same_rule(session):
    _reference(session)
    session.add(
        FlowObservationRecord(
            observation_id="flow-old", point_id="ITP-00044", point_name="Dragor",
            direction="entry", flow_mcm_d=1.0, period_start_utc=T0,
            period_end_utc=T0 + timedelta(days=1), observed_at_utc=T0 + timedelta(days=1),
            source_system="ENTSOG", source_reference="test", freshness="daily",
            research_only=True,
        )
    )
    session.commit()
    assert "flow-old" not in _served(session, FlowObservationRecord)
