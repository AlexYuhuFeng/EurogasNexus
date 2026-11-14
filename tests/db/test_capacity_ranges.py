"""ENTSOG capacity ranges re-split between reads resolve to one value per gas day.

Live shape (UGS-00397, DE-TSO-0001, firm technical entry, 2026-11-12/13/14): the 12 Nov read
holds 7-13 Nov and 13 Nov - 1 Dec (64.37 GWh/d); the 13 Nov read holds 13-14 Nov
(28.13 GWh/d) and 14 Nov - 1 Dec (64.37 GWh/d). The provider record id holds the period
end, so all four ranges are stored and 13 Nov is covered twice. These run the real
normaliser, persistence and readers on SQLite.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from eurogas_nexus.application import data_quality_report
from eurogas_nexus.application.agents import db_bridge
from eurogas_nexus.application.capacity_resolution import (
    resolve_capacity,
    resolve_capacity_as_of,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import CapacityObservationRecord, ObservationRevisionRecord
from eurogas_nexus.db.repositories.entsog_observation_persistence import (
    upsert_entsog_observation_rows,
)
from eurogas_nexus.ingestion.public_sources import entsog_capacity_observations_from_json

READ_1 = datetime(2026, 11, 12, 11, 56, 28, tzinfo=UTC)
READ_2 = datetime(2026, 11, 13, 15, 45, 0, tzinfo=UTC)
READ_3 = datetime(2026, 11, 14, 1, 3, 58, tzinfo=UTC)
LONG = 64367976
DAY_AHEAD = 28127976


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(
        engine,
        tables=[CapacityObservationRecord.__table__, ObservationRevisionRecord.__table__],
    )
    with Session(engine) as active:
        yield active
    engine.dispose()


def _record(start: str, end: str, value: int, *, point="UGS-00397", operator="DE-TSO-0001"):
    return {
        "id": f"1Firm Technicalday{operator}{point}entrykWh/d{start}{end}",
        "indicator": "Firm Technical",
        "pointKey": point,
        "pointLabel": "UGS Epe",
        "operatorKey": operator,
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
    outcome = upsert_entsog_observation_rows(session, CapacityObservationRecord, rows)
    session.commit()
    return outcome


def _two_reads(session):
    _store(
        session,
        [_record("2026-11-07", "2026-11-13", 24), _record("2026-11-13", "2026-12-01", LONG)],
        READ_1,
    )
    return _store(
        session,
        [
            _record("2026-11-13", "2026-11-14", DAY_AHEAD),
            _record("2026-11-14", "2026-12-01", LONG),
        ],
        READ_2,
    )


def _rows(session):
    return session.execute(select(CapacityObservationRecord)).scalars().all()


def _gas_day(day: int) -> datetime:
    return datetime(2026, 11, day, 5, tzinfo=UTC)


def _value_on(resolved, day: int) -> list[float]:
    moment = _gas_day(day)
    return [item.original_value for item in resolved if item.start <= moment < item.end]


def _daily_total(resolved, first: int, last: int) -> float:
    """What a reader that adds capacity per gas day gets."""

    return sum(sum(_value_on(resolved, day)) for day in range(first, last + 1))


def test_both_reads_are_stored_and_each_gas_day_has_one_value(session):
    outcome = _two_reads(session)
    assert outcome["inserted"] == 2 and outcome["resplit"] == 0
    assert len(_rows(session)) == 4  # every range the provider stated is kept

    naive_13 = [
        row.original_value
        for row in _rows(session)
        if row.period_start_utc.replace(tzinfo=UTC) <= _gas_day(13)
        < row.period_end_utc.replace(tzinfo=UTC)
    ]
    assert sorted(naive_13) == [DAY_AHEAD, LONG]  # the double count the rule removes

    resolved = resolve_capacity(_rows(session))
    for day in range(7, 31):
        assert len(_value_on(resolved, day)) == 1, day
    assert _value_on(resolved, 13) == [DAY_AHEAD]  # the later read's re-split value
    assert _value_on(resolved, 14) == [LONG]
    assert _value_on(resolved, 12) == [24]
    assert _daily_total(resolved, 13, 15) == DAY_AHEAD + 2 * LONG
    # No two results of the series overlap.
    spans = sorted((item.start, item.end) for item in resolved)
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False))
    # The superseded long range still holds where no later range covers it: nowhere here.
    assert {item.published_period_end_utc.date().isoformat() for item in resolved} == {
        "2026-11-13",
        "2026-11-14",
        "2026-12-01",
    }


def test_as_of_between_the_reads_returns_the_first_reads_value(session):
    _two_reads(session)
    before = resolve_capacity_as_of(session, _rows(session), READ_2 - timedelta(hours=1))
    assert _value_on(before, 13) == [LONG]
    assert _value_on(before, 14) == [LONG]
    after = resolve_capacity_as_of(session, _rows(session), READ_2 + timedelta(minutes=1))
    assert _value_on(after, 13) == [DAY_AHEAD]
    # Before the first read nothing was known.
    assert resolve_capacity_as_of(session, _rows(session), READ_1 - timedelta(seconds=1)) == []


def test_a_range_republished_after_its_re_split_wins_again_with_history(session):
    _two_reads(session)
    # The provider goes back to the 12 Nov split: same record, same value, a new receipt.
    outcome = _store(session, [_record("2026-11-13", "2026-12-01", LONG)], READ_3)
    assert outcome["resplit"] == 1 and outcome["updated"] == 1 and outcome["unchanged"] == 0
    assert outcome["revised"] == 0  # no value changed

    record = session.execute(select(ObservationRevisionRecord)).scalar_one()
    assert record.reason == "range_resplit" and record.changed_fields == []
    assert record.prior_received_at_utc.replace(tzinfo=UTC) == READ_1
    assert record.superseded_at_utc.replace(tzinfo=UTC) == READ_3

    now = resolve_capacity(_rows(session))
    assert _value_on(now, 13) == [LONG]
    # Read as of the hour before the third read: the 13 Nov read's split, unchanged.
    between = resolve_capacity_as_of(session, _rows(session), READ_3 - timedelta(hours=1))
    assert _value_on(between, 13) == [DAY_AHEAD]
    first = resolve_capacity_as_of(session, _rows(session), READ_2 - timedelta(hours=1))
    assert _value_on(first, 13) == [LONG]


def test_unchanged_repeat_of_the_latest_split_moves_nothing(session):
    _two_reads(session)
    outcome = _store(
        session,
        [
            _record("2026-11-13", "2026-11-14", DAY_AHEAD),
            _record("2026-11-14", "2026-12-01", LONG),
        ],
        READ_3,
    )
    assert outcome == {"inserted": 0, "updated": 0, "unchanged": 2, "revised": 0, "resplit": 0}
    assert session.execute(select(ObservationRevisionRecord)).scalars().all() == []


def test_one_operator_per_point_where_both_publish_capacity(session):
    # Both sides of an interconnection publish firm technical capacity for the same days.
    _store(
        session,
        [
            _record("2026-11-13", "2026-11-15", 300, point="ITP-00011", operator="HU-TSO-0001"),
            _record("2026-11-13", "2026-11-15", 280, point="ITP-00011", operator="HR-TSO-0001"),
        ],
        READ_1,
    )
    resolved = resolve_capacity(_rows(session))
    assert [(item.metadata_json["operatorKey"], item.original_value) for item in resolved] == [
        ("HR-TSO-0001", 280)
    ]


def test_agent_bridge_reads_resolved_energy(session):
    _two_reads(session)
    rows = db_bridge.capacity_rows(session, point_id="UGS-00397")
    covering_13 = [
        row
        for row in rows
        if row["period_start"] <= _gas_day(13).isoformat() < row["period_end"]
    ]
    assert len(covering_13) == 1
    assert covering_13[0]["energy_gwh_d"] == pytest.approx(DAY_AHEAD / 1e6)
    assert covering_13[0]["capacity_mcm_d"] is None
    assert covering_13[0]["operator_key"] == "DE-TSO-0001"
    assert len(rows) == 3  # 7-13 Nov, 13-14 Nov, 14 Nov - 1 Dec


def test_data_quality_report_counts_overlaps_not_duplicates(session):
    _two_reads(session)
    spec = next(s for s in data_quality_report.SPECS if s.dataset == "ENTSOG capacity")
    result = data_quality_report.measure(session, spec, READ_3)
    assert result.duplicate_keys == 0
    assert result.overlapping_rows == 3  # the long 12 Nov range and the two 13 Nov ranges
    assert not any(f["severity"] == "critical" for f in result.findings)


def test_replay_script_finds_and_records_a_missed_reconfirmation(session):
    """Rows stored before the rule: the archived third read re-sent the long range."""

    import hashlib
    import importlib.util
    from pathlib import Path

    from eurogas_nexus.db.models.raw_archive import RawPayloadArchiveRecord

    RawPayloadArchiveRecord.__table__.create(bind=session.get_bind())
    _two_reads(session)
    reads = (
        (READ_1, [_record("2026-11-07", "2026-11-13", 24),
                  _record("2026-11-13", "2026-12-01", LONG)]),
        (READ_2, [_record("2026-11-13", "2026-11-14", DAY_AHEAD),
                  _record("2026-11-14", "2026-12-01", LONG)]),
        # Archived but, before the rule, left no trace in the store (all unchanged).
        (READ_3, [_record("2026-11-13", "2026-12-01", LONG)]),
    )
    for number, (receipt, records) in enumerate(reads):
        text = json.dumps({"operationaldatas": records})
        session.add(
            RawPayloadArchiveRecord(
                archive_id=f"raw-{number}",
                source_system="ENTSOG",
                dataset="operationaldatas",
                source_reference=f"entsog-operationaldatas;read={number}",
                payload_text=text,
                payload_sha256=hashlib.sha256(text.encode()).hexdigest(),
                record_count=len(records),
                received_at_utc=receipt,
                research_only=True,
                human_review_required=False,
            )
        )
    session.commit()

    path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "capacity_range_resplits.py"
    spec = importlib.util.spec_from_file_location("capacity_range_resplits", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    stored = module._stored(session)
    counts = module.overlap_counts(stored)
    assert counts["start_keys_held_more_than_once"] == 1
    assert counts["of_which_values_differ"] == 1
    moves = module.replay(stored, module._reads(session))
    assert [(m["prior_received_at_utc"], m["superseded_at_utc"]) for m in moves] == [
        (READ_1, READ_3)
    ]
    assert module.changed_days(stored, moves) == 1  # 13 Nov: 28.1 back to 64.4 GWh/d
    assert module.apply(session, stored, moves) == {"applied": 1, "skipped_revised_later": 0}
    session.commit()
    assert _value_on(resolve_capacity(_rows(session)), 13) == [LONG]
    # Applying again changes nothing.
    stored = module._stored(session)
    assert module.apply(session, stored, moves) == {"applied": 0, "skipped_revised_later": 1}
