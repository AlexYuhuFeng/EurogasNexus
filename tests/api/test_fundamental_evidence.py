"""Storage, flow and power series reach datasets, and only the series a dataset needs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.routes.public.research_data import _fundamental_evidence
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.db.models.observation import StorageObservationRecord
from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.domain.dataops.registry import source_definitions

T0 = datetime(2026, 10, 1, 5, tzinfo=UTC)


def _storage(facility, day, inventory):
    at = T0 + timedelta(days=day)
    return StorageObservationRecord(
        observation_id=f"st-{facility}-{day}",
        source_dataset="agsi",
        facility_id=facility,
        facility_name=facility,
        country="DE",
        inventory_twh=inventory,
        working_capacity_twh=20.0,
        fill_pct=inventory / 20 * 100,
        injection_twh_d=0.1,
        withdrawal_twh_d=0.0,
        period_start_utc=at,
        period_end_utc=at + timedelta(days=1),
        observed_at_utc=at + timedelta(hours=20),
        source_system="GIE",
        source_reference=f"agsi:{facility}:{day}",
        source_record_id=None,
        freshness="daily",
        research_only=True,
        metadata_json={},
    )


def _flow(point, day, value):
    at = T0 + timedelta(days=day)
    return FlowObservationRecord(
        observation_id=f"fl-{point}-{day}",
        point_id=point,
        point_name=point,
        direction="entry",
        kind="physical",
        flow_mcm_d=value,
        original_value=value,
        original_unit="mcm/d",
        period_start_utc=at,
        period_end_utc=at + timedelta(days=1),
        observed_at_utc=at + timedelta(hours=3),
        source_system="ENTSOG",
        source_reference=f"entsog:{point}:{day}",
        source_record_id=None,
        freshness="daily",
        research_only=True,
        metadata_json={},
        normalizer_version=None,
        native_rate_json=None,
    )


def test_only_the_needed_fundamental_series_are_loaded(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'f.sqlite').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for day in range(3):
            session.add(_storage("REHDEN", day, 10.0 + day))
            session.add(_storage("OTHER", day, 5.0))
            session.add(_flow("P1", day, 40.0 + day))
            session.add(_flow("P2", day, 9.0))
        session.add(
            PowerObservationRecord(
                observation_id="pw-1",
                zone="GB",
                metric="load_actual",
                process_type="A16",
                period_start_utc=T0,
                period_end_utc=T0 + timedelta(minutes=30),
                value=30_000,
                unit="MW",
                source_system="ENTSOE",
                source_reference="entsoe:test",
                published_at_utc=T0 + timedelta(hours=1, minutes=30),
                ingested_at_utc=T0,
            )
        )
        session.commit()
        definitions = {d.provider.casefold(): d for d in source_definitions()}
        records, sources = _fundamental_evidence(
            session,
            {"storage.inventory_twh.REHDEN", "flow.mcm_d.P1.entry", "power.load_actual.GB"},
            definitions,
            history_start=T0 - timedelta(days=1),
            end=T0 + timedelta(days=5),
            requested_entity_ids=set(),
        )
    series = sorted({r.series_id for r in records})
    assert series == ["flow.mcm_d.P1.entry", "power.load_actual.GB", "storage.inventory_twh.REHDEN"]
    assert [r.value for r in records if r.series_id.startswith("storage")] == [10.0, 11.0, 12.0]
    assert {"src-gie", "src-entsog", "src-entsoe"} == sources
    storage = next(r for r in records if r.series_id.startswith("storage"))
    assert storage.available_at == T0 + timedelta(hours=20)
