"""Provider revisions keep history: the current row is the latest, earlier values stay readable.

ENTSOG and GIE publish provisional values and revise them. Until 2026-11-13 any revision
refused the whole batch, so the scheduled rolling refresh failed and the newest days kept
their first values. Now a later value under the same source and natural key replaces the
current row and the replaced version goes to ``observation_revisions`` in the same
transaction. These run the real persistence and readers on SQLite.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.application import data_quality_report
from eurogas_nexus.application.agents import db_bridge
from eurogas_nexus.application.pipeline_supply import (
    landed_supply,
    published_after_close,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CapacityObservationRecord,
    FlowObservationRecord,
    LngObservationRecord,
    ObservationRevisionRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.repositories.entsog_observation_persistence import (
    EntsogRevisionIdentityConflictError,
    upsert_entsog_observation_rows,
)
from eurogas_nexus.db.repositories.observation_revisions import (
    all_versions,
    versions_as_of,
)
from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    GIE_REVISABLE_FIELDS,
    GieRevisionIdentityConflictError,
    RevisionPolicy,
    upsert_revision_safe_observation_rows,
)
from eurogas_nexus.domain.research.datasets import DatasetEvidenceRecord, _as_of_candidates
from eurogas_nexus.ingestion.public_sources import (
    entsog_capacity_observations_from_json,
    entsog_flow_observations_from_json,
)

#: Gas day 12 Nov 2026 (05:00 to 05:00 UTC), the live Dornum case.
START = datetime(2026, 11, 12, 5, tzinfo=UTC)
END = START + timedelta(days=1)
OPEN_RECEIPT = datetime(2026, 11, 12, 11, 56, tzinfo=UTC)  # day still open
CLOSED_RECEIPT = datetime(2026, 11, 13, 14, 0, tzinfo=UTC)
LATER_RECEIPT = CLOSED_RECEIPT + timedelta(hours=6)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            FlowObservationRecord.__table__,
            CapacityObservationRecord.__table__,
            StorageObservationRecord.__table__,
            LngObservationRecord.__table__,
            ObservationRevisionRecord.__table__,
        ],
    )
    with Session(engine) as active:
        yield active
    engine.dispose()


def _entsog(point="ITP-00126", operator="DE-TSO-0009", value=157793678.9, *, indicator=None):
    record = {
        "id": f"{point}-entry",
        "indicator": indicator or "Physical Flow",
        "pointKey": point,
        "pointLabel": "Dornum / NETRA",
        "operatorKey": operator,
        "directionKey": "entry",
        "unit": "kWh/d",
        "value": value,
        "flowStatus": "Provisional",
        "periodFrom": "2026-11-12T06:00:00+01:00",
        "periodTo": "2026-11-13T06:00:00+01:00",
    }
    return record


def _rows(records, receipt, *, capacity=False):
    payload = json.loads(json.dumps({"operationaldatas": records}), parse_float=str)
    normalizer = (
        entsog_capacity_observations_from_json if capacity else entsog_flow_observations_from_json
    )
    rows = normalizer(payload, observed_at_utc=receipt)
    for row in rows:
        row["source_reference"] = f"entsog-test;receipt={receipt.isoformat()}"
    return rows


def _flow(session, observation_id):
    return session.execute(
        select(FlowObservationRecord).where(FlowObservationRecord.observation_id == observation_id)
    ).scalar_one()


def _revisions(session):
    return session.execute(select(ObservationRevisionRecord)).scalars().all()


def _utc(moment):
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def test_revised_value_updates_current_row_and_writes_one_revision(session):
    first = _rows([_entsog(), _entsog("ITP-00080", value=1000.0)], CLOSED_RECEIPT)
    assert upsert_entsog_observation_rows(session, FlowObservationRecord, first) == {
        "inserted": 2, "updated": 0, "unchanged": 0, "revised": 0,
    }
    dornum_id, emden_id = first[0]["observation_id"], first[1]["observation_id"]
    emden_before = {c.name: getattr(_flow(session, emden_id), c.name)
                    for c in FlowObservationRecord.__table__.columns}

    revised = _rows([_entsog(value=740123456.7), _entsog("ITP-00080", value=1000.0)],
                    LATER_RECEIPT)
    outcome = upsert_entsog_observation_rows(session, FlowObservationRecord, revised)
    session.expire_all()

    assert outcome == {"inserted": 0, "updated": 1, "unchanged": 1, "revised": 1}
    dornum = _flow(session, dornum_id)
    assert dornum.original_value == pytest.approx(740123456.7)
    assert _utc(dornum.observed_at_utc) == CLOSED_RECEIPT  # first receipt kept
    assert _utc(dornum.revised_at_utc) == LATER_RECEIPT
    (revision,) = _revisions(session)
    assert revision.observation_id == dornum_id
    assert revision.observation_table == "flow_observations"
    assert revision.reason == "value_changed"
    assert revision.prior_row_json["original_value"] == pytest.approx(157793678.9)
    assert _utc(revision.prior_received_at_utc) == CLOSED_RECEIPT
    assert _utc(revision.superseded_at_utc) == LATER_RECEIPT
    assert "original_value" in revision.changed_fields
    # The unchanged row is untouched, column for column.
    emden_after = {c.name: getattr(_flow(session, emden_id), c.name)
                   for c in FlowObservationRecord.__table__.columns}
    assert emden_after == emden_before


def test_as_of_read_before_the_revision_returns_the_old_value(session):
    upsert_entsog_observation_rows(session, FlowObservationRecord, _rows([_entsog()],
                                                                          CLOSED_RECEIPT))
    upsert_entsog_observation_rows(
        session, FlowObservationRecord, _rows([_entsog(value=740123456.7)], LATER_RECEIPT)
    )
    rows = session.execute(select(FlowObservationRecord)).scalars().all()

    (before,) = versions_as_of(session, rows, LATER_RECEIPT - timedelta(minutes=1))
    (after,) = versions_as_of(session, rows, LATER_RECEIPT)
    assert before.original_value == pytest.approx(157793678.9)
    assert after.original_value == pytest.approx(740123456.7)
    assert versions_as_of(session, rows, CLOSED_RECEIPT - timedelta(minutes=1)) == []
    assert [v.original_value for v in all_versions(session, rows)] == pytest.approx(
        [157793678.9, 740123456.7]
    )

    # The balance's pipeline read (as_of) takes the value known at as_of.
    early = landed_supply(session, date(2026, 11, 1), as_of=LATER_RECEIPT - timedelta(minutes=1))
    late = landed_supply(session, date(2026, 11, 1), as_of=LATER_RECEIPT + timedelta(minutes=1))
    assert early.points_reporting and late.points_reporting
    day = START.date()
    assert early.by_day[day] == pytest.approx(157.7936789)
    assert late.by_day[day] == pytest.approx(740.1234567)


def test_different_source_or_identity_collision_is_still_refused(session):
    rows = _rows([_entsog()], CLOSED_RECEIPT)
    upsert_entsog_observation_rows(session, FlowObservationRecord, rows)
    other_operator = _rows([_entsog(operator="DE-TSO-0005", value=1.0)], LATER_RECEIPT)
    other_operator[0]["observation_id"] = rows[0]["observation_id"]
    with pytest.raises(EntsogRevisionIdentityConflictError) as caught:
        upsert_entsog_observation_rows(session, FlowObservationRecord, other_operator)
    assert caught.value.code == "entsog_revision_identity_conflict"
    assert _revisions(session) == []

    # GIE: a row from another source under an existing key is not a revision either.
    gie = _storage_row(inventory=100.0, receipt=CLOSED_RECEIPT)
    policy = RevisionPolicy(GIE_REVISABLE_FIELDS["storage_observations"])
    upsert_revision_safe_observation_rows(session, StorageObservationRecord, [gie],
                                          revisions=policy)
    intruder = {**_storage_row(inventory=50.0, receipt=LATER_RECEIPT),
                "source_system": "NATIONAL_GAS"}
    with pytest.raises(GieRevisionIdentityConflictError) as refused:
        with session.begin_nested():
            upsert_revision_safe_observation_rows(
                session, StorageObservationRecord, [intruder], revisions=policy
            )
    assert refused.value.code == "gie_revision_identity_conflict"
    stored = session.execute(select(StorageObservationRecord)).scalar_one()
    assert stored.inventory_twh == 100.0 and stored.source_system == "GIE"
    assert _revisions(session) == []


def _storage_row(*, inventory, receipt, day=START):
    return {
        "observation_id": f"gie-agsi-DE-{day.date().isoformat()}",
        "source_dataset": "AGSI",
        "facility_id": "DE",
        "facility_name": "Germany",
        "country": "DE",
        "inventory_twh": inventory,
        "working_capacity_twh": 250.0,
        "fill_pct": 57.7,
        "injection_twh_d": 0.0,
        "withdrawal_twh_d": 1.1,
        "period_start_utc": day,
        "period_end_utc": day + timedelta(days=1),
        "observed_at_utc": receipt,
        "source_system": "GIE",
        "source_reference": "gie-agsi-api",
        "source_record_id": f"DE-{day.date().isoformat()}",
        "freshness": "live",
        "research_only": True,
        "metadata_json": {},
    }


def test_gie_revision_and_as_of_daily_sum(session):
    from eurogas_nexus.api.routes.public.fundamentals import _daily_sum

    policy = RevisionPolicy(GIE_REVISABLE_FIELDS["storage_observations"])
    first = _storage_row(inventory=100.0, receipt=CLOSED_RECEIPT)
    assert upsert_revision_safe_observation_rows(
        session, StorageObservationRecord, [first], revisions=policy
    )["inserted"] == 1
    revised = {**_storage_row(inventory=100.0, receipt=LATER_RECEIPT), "withdrawal_twh_d": 1.4}
    outcome = upsert_revision_safe_observation_rows(
        session, StorageObservationRecord, [revised], revisions=policy
    )
    assert outcome == {"inserted": 0, "updated": 1, "unchanged": 0, "revised": 1}
    column = StorageObservationRecord.withdrawal_twh_d
    first_day = date(2026, 11, 1)
    before = _daily_sum(session, column, StorageObservationRecord, [], first_day,
                        as_of=LATER_RECEIPT - timedelta(minutes=1))
    after = _daily_sum(session, column, StorageObservationRecord, [], first_day,
                       as_of=LATER_RECEIPT + timedelta(minutes=1))
    assert before == {START.date(): pytest.approx(1.1)}
    assert after == {START.date(): pytest.approx(1.4)}


def test_open_gas_day_snapshot_is_replaced_at_close_and_never_read_as_closed(session):
    """The open-day rule: a snapshot is stored, flagged open, and replaced at day close."""

    snapshot = _rows([_entsog()], OPEN_RECEIPT)
    upsert_entsog_observation_rows(session, FlowObservationRecord, snapshot)
    row = _flow(session, snapshot[0]["observation_id"])
    assert not published_after_close(row)

    # Closed-day readers leave it out; a reader asking for within-day data sees it, flagged.
    assert db_bridge.flow_rows(session) == []
    (open_row,) = db_bridge.flow_rows(session, include_open_day=True)
    assert open_row["open_gas_day"] is True
    assert landed_supply(session, date(2026, 11, 1)).by_day == {}

    # The first receipt after the close replaces it even with an equal value.
    same_value = _rows([_entsog()], CLOSED_RECEIPT)
    outcome = upsert_entsog_observation_rows(session, FlowObservationRecord, same_value)
    assert outcome == {"inserted": 0, "updated": 1, "unchanged": 0, "revised": 0}
    (record,) = _revisions(session)
    assert record.reason == "period_closed" and record.changed_fields == []
    session.expire_all()
    row = _flow(session, snapshot[0]["observation_id"])
    assert published_after_close(row)
    (closed_row,) = db_bridge.flow_rows(session)
    assert closed_row["open_gas_day"] is False
    # Read as of a moment while the day was open, the snapshot is still not a closed day.
    while_open = versions_as_of(session, [row], END - timedelta(hours=1))
    assert [published_after_close(v) for v in while_open] == [False]

    # A capacity row is published ahead of its period by nature: no close rule.
    capacity = _rows([_entsog(indicator="Firm Technical")], OPEN_RECEIPT, capacity=True)
    upsert_entsog_observation_rows(session, CapacityObservationRecord, capacity)
    again = _rows([_entsog(indicator="Firm Technical")], CLOSED_RECEIPT, capacity=True)
    assert upsert_entsog_observation_rows(session, CapacityObservationRecord, again)[
        "unchanged"
    ] == 1


def test_data_quality_report_counts_revised_rows(session):
    upsert_entsog_observation_rows(session, FlowObservationRecord, _rows([_entsog()],
                                                                          CLOSED_RECEIPT))
    upsert_entsog_observation_rows(
        session, FlowObservationRecord, _rows([_entsog(value=740123456.7)], LATER_RECEIPT)
    )
    spec = next(s for s in data_quality_report.SPECS if s.dataset == "ENTSOG flows")
    # SQLite has no ->> operator: measure only the revision count here.
    result = data_quality_report.DatasetQuality(spec.dataset, spec.source)
    data_quality_report._revisions(session, spec, result, datetime.now(UTC))
    assert result.revised_rows == 1 and result.closed_snapshots == 0


def test_research_builder_takes_the_version_known_at_each_origin():
    def record(value, available):
        return DatasetEvidenceRecord(
            record_id=f"r-{value}",
            series_id="flow.gwh_d.ITP-00126.entry",
            observed_at=START,
            available_at=available,
            value=value,
            unit="GWh/d",
        )

    from eurogas_nexus.domain.research.datasets import DatasetSpec

    spec = DatasetSpec(
        dataset_spec_id="spec-revisions",
        name="revisions",
        description="Revision-aware point-in-time selection",
        target_ids=[],
        start=START,
        end=START + timedelta(days=3),
        forecast_origin_frequency="1d",
    )
    versions = [record(157.8, CLOSED_RECEIPT), record(740.1, LATER_RECEIPT)]
    early = _as_of_candidates(versions, LATER_RECEIPT - timedelta(minutes=1), spec=spec)
    late = _as_of_candidates(versions, LATER_RECEIPT, spec=spec)
    assert [r.value for r in early["flow.gwh_d.ITP-00126.entry"]] == [157.8]
    assert [r.value for r in late["flow.gwh_d.ITP-00126.entry"]] == [740.1]


def test_closed_day_rule_touches_measured_flows_only():
    """Nominations, allocations and forecasts are published ahead of their period."""

    from types import SimpleNamespace

    from eurogas_nexus.application.pipeline_supply import closed_day_clause

    def row(kind):
        return SimpleNamespace(kind=kind, period_end_utc=END, observed_at_utc=OPEN_RECEIPT,
                               revised_at_utc=None)

    assert not published_after_close(row("actual"))
    for kind in ("nomination", "allocation", "forecast"):
        assert published_after_close(row(kind))
    assert "kind" in str(closed_day_clause(FlowObservationRecord))
