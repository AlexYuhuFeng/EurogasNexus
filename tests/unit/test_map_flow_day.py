"""The map shows a point's newest closed gas day, from one operator that does not flip.

Live (2026-11-12/13): the map showed each point's newest gas day, which could be the open
day or one only partly reported, and the operator could change between days (Bacton IUK,
ITP-00005: National Gas on 10 November, IUK on 11 November), flipping the side the
direction was read from.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.map_situation import FLOW_DAY_RULE, build_map_situation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord, ReferenceNode

DAY = datetime(2026, 11, 8, 5, tzinfo=UTC)  # gas day 8 November (CET: 06:00 = 05:00 UTC)
NOW = datetime(2026, 11, 12, 11, 56, tzinfo=UTC)  # gas day 12 November is open


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            ReferenceNode(
                id="entsog-itp-00005", name="Bacton (IUK)", node_type="interconnection",
                country="GB", lat=52.85, lon=1.46, source_system="ENTSOG",
                source_record_id="ITP-00005", data_quality="entsog", metadata_json={},
            )
        )
        yield db


def _flow(db, key, operator, direction, kwh, *, day, observed=None):
    db.add(
        FlowObservationRecord(
            observation_id=key, point_id="ITP-00005", point_name="Bacton (IUK)",
            direction=direction, kind="actual", flow_mcm_d=None, original_value=kwh,
            original_unit="kWh/d", period_start_utc=day,
            period_end_utc=day + timedelta(days=1),
            observed_at_utc=observed or day + timedelta(days=1, hours=4),
            source_system="ENTSOG", source_reference="t", freshness="daily",
            research_only=True, metadata_json={"operatorKey": operator},
            normalizer_version="entsog-native-units-v1",
            native_rate_json={"value": str(kwh), "unit": "kWh/d"},
        )
    )


def _side(db, day, operator, flow_kwh, prefix):
    # National Gas reports the GB -> Belgium flow as its exit, IUK as its entry.
    exit_side = operator == "UK-TSO-0001"
    _flow(db, f"{prefix}-x", operator, "exit", flow_kwh if exit_side else 0.0, day=day)
    _flow(db, f"{prefix}-n", operator, "entry", 0.0 if exit_side else flow_kwh, day=day)


def _situation(db):
    return build_map_situation(
        db, now=NOW, entitled=lambda rows: list(rows), include_positions=False
    )


def test_the_newest_closed_day_is_shown_with_its_gas_day_and_operator(session):
    for offset in range(3):  # 8, 9, 10 November, both operators
        day = DAY + timedelta(days=offset)
        _side(session, day, "UK-TSO-0001", 30e6 + offset * 1e6, f"ng{offset}")
        _side(session, day, "UK-TSO-0003", 30e6 + offset * 1e6, f"iuk{offset}")
    # 11 November closed at 05:00 UTC on the 12th; 12 November is open (a mid-day
    # snapshot), 13 November is ENTSOG's next-day row.
    _side(session, DAY + timedelta(days=3), "UK-TSO-0001", 33e6, "ng3")
    open_day = DAY + timedelta(days=4)
    _flow(session, "open", "UK-TSO-0001", "exit", 8e6, day=open_day,
          observed=open_day + timedelta(hours=6))
    _flow(session, "next", "UK-TSO-0001", "exit", 0.0, day=open_day + timedelta(days=1),
          observed=open_day + timedelta(hours=6))
    session.commit()

    situation = _situation(session)
    flows = {flow["direction"]: flow for flow in situation["flows"]}
    assert {flow["gas_day"] for flow in flows.values()} == {"2026-11-11"}
    assert flows["exit"]["gwh_d"] == pytest.approx(33.0)
    assert flows["exit"]["operator_key"] == "UK-TSO-0001"
    assert flows["exit"]["gas_day_end_utc"] == "2026-11-12T05:00:00+00:00"
    assert situation["flow_rule"] == FLOW_DAY_RULE


def test_a_snapshot_taken_while_the_day_was_open_is_not_shown_once_it_closed(session):
    _side(session, DAY + timedelta(days=2), "UK-TSO-0001", 32e6, "full")
    partial_day = DAY + timedelta(days=3)  # 11 November, captured at 11:56 that day
    _flow(session, "partial", "UK-TSO-0001", "exit", 8e6, day=partial_day,
          observed=partial_day + timedelta(hours=7))
    session.commit()

    flows = {flow["direction"]: flow for flow in _situation(session)["flows"]}
    assert flows["exit"]["gas_day"] == "2026-11-10"
    assert flows["exit"]["gwh_d"] == pytest.approx(32.0)


def test_the_operator_does_not_flip_back_once_the_other_side_was_used(session):
    # 9 Nov both sides; 10 Nov only IUK has reported; 11 Nov both again.
    _side(session, DAY + timedelta(days=1), "UK-TSO-0001", 30e6, "ng1")
    _side(session, DAY + timedelta(days=1), "UK-TSO-0003", 30e6, "iuk1")
    _side(session, DAY + timedelta(days=2), "UK-TSO-0003", 31e6, "iuk2")
    _side(session, DAY + timedelta(days=3), "UK-TSO-0001", 32e6, "ng3")
    _side(session, DAY + timedelta(days=3), "UK-TSO-0003", 32e6, "iuk3")
    session.commit()

    flows = {flow["direction"]: flow for flow in _situation(session)["flows"]}
    assert {flow["operator_key"] for flow in flows.values()} == {"UK-TSO-0003"}
    # Read from IUK's side: the GB -> Belgium flow is its entry.
    assert flows["entry"]["gwh_d"] == pytest.approx(32.0)
    assert flows["exit"]["gwh_d"] == 0.0
