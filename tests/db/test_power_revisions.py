"""Power revisions keep history: the earlier value stays readable as of its own time.

Live: ENTSO-E re-stated 44 actual load and generation values in two scheduler runs on
14 November 2026, and the store overwrote them. The parser caps ``published_at_utc`` at
the regulatory deadline (period end + 1 h for actuals), so the first and the revised
publication carry the same time; the revision is therefore available from its receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.api.routes.public.research_data import _fundamental_evidence
from eurogas_nexus.application import data_quality_report
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ObservationRevisionRecord
from eurogas_nexus.db.models.power import PowerObservationRecord
from eurogas_nexus.db.repositories.observation_revisions import (
    all_versions,
    value_received_at,
    versions_as_of,
)
from eurogas_nexus.db.repositories.power import (
    PowerRevisionIdentityConflictError,
    upsert_power_observations,
)
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.ingestion.entsoe_transparency import PowerObservation

START = datetime(2026, 11, 13, 10, tzinfo=UTC)
END = START + timedelta(minutes=15)
DEADLINE = END + timedelta(hours=1)  # what the parser stores as publication for an actual
FIRST_RUN = datetime(2026, 11, 13, 12, 5, tzinfo=UTC)
SECOND_RUN = datetime(2026, 11, 14, 1, 5, tzinfo=UTC)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'p.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as active:
        yield active
    engine.dispose()


def _load(value: float, *, reference: str = "entsoe:A65:NL:first", zone: str = "NL"):
    return PowerObservation(
        zone=zone,
        metric="load_actual",
        period_start_utc=START,
        period_end_utc=END,
        value=value,
        unit="MW",
        published_at_utc=DEADLINE,
        source_reference=reference,
        process_type="A16",
    )


def _row(session):
    return session.execute(select(PowerObservationRecord)).scalar_one()


def _utc(moment):
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def test_a_revised_value_keeps_the_first_and_records_history(session):
    assert upsert_power_observations(session, [_load(11_250.0)], now=FIRST_RUN) == {
        "inserted": 1, "updated": 0, "unchanged": 0, "revised": 0,
    }
    session.commit()
    counts = upsert_power_observations(
        session, [_load(11_312.5, reference="entsoe:A65:NL:second")], now=SECOND_RUN
    )
    session.commit()
    assert counts == {"inserted": 0, "updated": 1, "unchanged": 0, "revised": 1}

    row = _row(session)
    assert row.value == 11_312.5
    # First-receipt semantics: availability and ingestion of the first value are kept.
    assert _utc(row.published_at_utc) == DEADLINE
    assert _utc(row.ingested_at_utc) == FIRST_RUN
    assert _utc(row.revised_at_utc) == SECOND_RUN
    assert row.source_reference == "entsoe:A65:NL:second"

    record = session.execute(select(ObservationRevisionRecord)).scalar_one()
    assert record.observation_table == "power_observations"
    assert record.reason == "value_changed" and record.changed_fields == ["value"]
    assert record.prior_row_json["value"] == 11_250.0
    assert _utc(record.prior_received_at_utc) == DEADLINE
    assert _utc(record.superseded_at_utc) == SECOND_RUN
    assert record.prior_source_reference == "entsoe:A65:NL:first"
    assert record.superseding_source_reference == "entsoe:A65:NL:second"

    # Unchanged on the next run: nothing written.
    assert upsert_power_observations(
        session, [_load(11_312.5)], now=SECOND_RUN + timedelta(hours=1)
    )["unchanged"] == 1
    assert len(session.execute(select(ObservationRevisionRecord)).scalars().all()) == 1


def test_as_of_reads_return_the_value_known_then(session):
    upsert_power_observations(session, [_load(11_250.0)], now=FIRST_RUN)
    session.commit()
    upsert_power_observations(session, [_load(11_312.5)], now=SECOND_RUN)
    session.commit()
    rows = session.execute(select(PowerObservationRecord)).scalars().all()

    assert versions_as_of(session, rows, DEADLINE - timedelta(minutes=1)) == []
    assert [v.value for v in versions_as_of(session, rows, SECOND_RUN - timedelta(hours=1))] == [
        11_250.0
    ]
    assert [v.value for v in versions_as_of(session, rows, SECOND_RUN)] == [11_312.5]

    versions = all_versions(session, rows)
    assert [(v.value, value_received_at(v)) for v in versions] == [
        (11_250.0, DEADLINE),
        (11_312.5, SECOND_RUN),
    ]


def test_research_datasets_get_one_record_per_power_version(session):
    upsert_power_observations(session, [_load(11_250.0)], now=FIRST_RUN)
    session.commit()
    upsert_power_observations(session, [_load(11_312.5)], now=SECOND_RUN)
    session.commit()
    definitions = {d.provider.casefold(): d for d in source_definitions()}
    records, sources = _fundamental_evidence(
        session,
        {"power.load_actual.NL"},
        definitions,
        history_start=START - timedelta(days=1),
        end=START + timedelta(days=1),
        requested_entity_ids=set(),
    )
    assert sources == {"src-entsoe"}
    assert [(r.value, r.available_at) for r in records] == [
        (11_250.0, DEADLINE),
        (11_312.5, SECOND_RUN),
    ]
    assert records[0].record_id.endswith(f"@{SECOND_RUN.isoformat()}")


def test_an_identity_change_under_a_stored_id_is_refused(session):
    upsert_power_observations(session, [_load(11_250.0)], now=FIRST_RUN)
    session.commit()
    changed = _load(11_250.0)
    object.__setattr__(changed, "unit", "GW")
    with pytest.raises(PowerRevisionIdentityConflictError):
        upsert_power_observations(session, [changed], now=SECOND_RUN)
    session.rollback()
    assert _row(session).unit == "MW"


def test_data_quality_report_counts_power_revisions(session):
    upsert_power_observations(session, [_load(11_250.0)], now=FIRST_RUN)
    session.commit()
    upsert_power_observations(session, [_load(11_312.5)], now=SECOND_RUN)
    session.commit()
    spec = next(s for s in data_quality_report.SPECS if s.dataset == "Power (ENTSO-E)")
    result = data_quality_report.measure(session, spec, SECOND_RUN + timedelta(hours=1))
    assert result.revised_rows == 1
