"""Pipeline landings: named ENTSOG points, energy as published, missing never zero."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.pipeline_supply import (
    LANDING_POINTS,
    landed_supply,
    row_energy_gwh,
    row_operator,
    select_operator_rows,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord

DAY = datetime(2026, 11, 10, 5, tzinfo=UTC)
AS_OF = DAY + timedelta(days=3)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def _flow(session, key, point_id, operator, kwh=None, *, name="x", direction="entry",
          mcm=None, day=DAY):
    session.add(
        FlowObservationRecord(
            observation_id=key, point_id=point_id, point_name=name, direction=direction,
            flow_mcm_d=mcm, original_value=kwh, original_unit="kWh/d" if kwh is not None else None,
            period_start_utc=day, period_end_utc=day + timedelta(days=1),
            observed_at_utc=day + timedelta(days=1, hours=6), source_system="ENTSOG",
            source_reference="t", freshness="live", research_only=True,
            metadata_json={"operatorKey": operator} if operator else None,
            # A native row carries its normaliser's evidence (the table's own constraint).
            normalizer_version="entsog-native-units-v1" if kwh is not None else None,
            native_rate_json={"value": str(kwh), "unit": "kWh/d"} if kwh is not None else None,
        )
    )


def test_energy_is_read_as_published_and_one_flow_is_counted_once(session):
    _flow(session, "a", "ITP-00126", "DE-TSO-0009", 700e6, name="Dornum / NETRA (OGE)")
    # The same Dornum flow under a second point label, and the other side's meter at Emden:
    _flow(session, "b", "ITP-00525", "DE-TSO-0009", 700e6, name="Dornum GASPOOL")
    _flow(session, "c", "ITP-00081", "DE-TSO-0005", 320e6, name="Emden (EPT1) (GUD)")
    _flow(session, "d", "ITP-00105", "DE-TSO-0002", 320e6, name="Emden (EPT1) (Thyssengas)")
    # An LNG terminal whose name contains a landing's name, and an exit at a landing:
    _flow(session, "e", "ITP-99999", "FR-TSO-0003", 400e6, name="Dunkerque GNL")
    _flow(session, "f", "ITP-00126", "DE-TSO-0009", 50e6, direction="exit")
    session.commit()

    supply = landed_supply(session, date(2026, 11, 1), as_of=AS_OF)
    assert supply.basis == "registry"
    assert supply.by_day == {DAY.date(): pytest.approx(1020.0)}  # 700 + 320 GWh, each once


def test_uk_terminals_are_included_and_named_as_mixed(session):
    _flow(session, "a", "ITP-00091", "UK-TSO-0001", 800e6, name="Easington")
    _flow(session, "b", "ITP-00106", "BE-TSO-0001", 480e6, name="Zeebrugge ZPT")
    session.commit()
    supply = landed_supply(session, date(2026, 11, 1), as_of=AS_OF)
    assert supply.by_scope["uk_terminal"][DAY.date()] == pytest.approx(800.0)
    assert supply.by_scope["norway"][DAY.date()] == pytest.approx(480.0)
    assert {point.scope for point in LANDING_POINTS} == {"norway", "uk_terminal"}


def test_a_day_without_rows_is_absent_and_an_open_day_is_not_counted(session):
    _flow(session, "a", "ITP-00106", "BE-TSO-0001", 480e6)
    _flow(session, "b", "ITP-00106", "BE-TSO-0001", 90e6, day=AS_OF)  # still open at as_of
    session.commit()
    supply = landed_supply(session, date(2026, 11, 1), as_of=AS_OF)
    assert list(supply.by_day) == [DAY.date()]  # no zero for the days in between


def test_rows_from_before_the_native_adapter_convert_volume_and_say_so(session):
    _flow(session, "a", "emden", None, mcm=100.0, name="Emden (EPT1)")
    session.commit()
    supply = landed_supply(session, date(2026, 11, 1), as_of=AS_OF)
    assert supply.basis == "legacy_names" and supply.legacy_rows == 1
    assert supply.by_day[DAY.date()] == pytest.approx(1100.0)  # 100 mcm at 11 kWh/m3


def test_row_energy_units():
    class Row:
        def __init__(self, value, unit, mcm=None):
            self.original_value, self.original_unit, self.flow_mcm_d = value, unit, mcm

    assert row_energy_gwh(Row(5e6, "kWh/d")) == (5.0, False)
    assert row_energy_gwh(Row(5e3, "MWh/d")) == (5.0, False)
    assert row_energy_gwh(Row(0.0, "kWh/d")) == (0.0, False)  # a zero flow is a value
    assert row_energy_gwh(Row(None, None, mcm=2.0)) == (22.0, True)
    assert row_energy_gwh(Row(None, None)) == (None, False)


# --- One operator per point and gas day (the rule every flow reader shares) ----------


def _rows(session):
    return session.query(FlowObservationRecord).order_by(FlowObservationRecord.observation_id).all()


def test_two_operators_at_an_interconnection_are_not_added(session):
    # HR -> HU, 25.4 GWh: HR reports it as its exit, HU as its entry; each also reports
    # zero for the other direction. Per point *and direction* the first operator would
    # be HR for entry (0) and HR for exit (25.4); per point the choice stays on one side.
    _flow(session, "a", "ITP-00011", "HR-TSO-0001", 0.0, direction="entry")
    _flow(session, "b", "ITP-00011", "HR-TSO-0001", 25.4e6, direction="exit")
    _flow(session, "c", "ITP-00011", "HU-TSO-0001", 25.4e6, direction="entry")
    _flow(session, "d", "ITP-00011", "HU-TSO-0001", 0.0, direction="exit")
    session.commit()

    kept = select_operator_rows(_rows(session))
    assert [row.observation_id for row in kept] == ["a", "b"]  # HR sorts first
    by_direction = {row.direction: row_energy_gwh(row)[0] for row in kept}
    assert by_direction == {"entry": 0.0, "exit": pytest.approx(25.4)}
    # Summing the point's exit over the kept rows counts the flow once, not twice.
    assert sum(row_energy_gwh(r)[0] for r in kept if r.direction == "exit") == pytest.approx(25.4)


def test_the_registry_operator_wins_and_null_volume_is_not_zero(session):
    # A native row: energy published, the legacy volume column NULL.
    _flow(session, "a", "ITP-00106", "BE-TSO-0001", 480e6)
    _flow(session, "b", "ITP-00106", "AA-TSO-0001", 480e6)  # sorts first, not the registry's
    session.commit()

    kept = select_operator_rows(_rows(session))
    assert [row_operator(row) for row in kept] == ["BE-TSO-0001"]
    assert kept[0].flow_mcm_d is None
    assert row_energy_gwh(kept[0]) == (pytest.approx(480.0), False)


def test_an_operator_with_no_value_that_day_is_not_chosen(session):
    _flow(session, "a", "ITP-00500", "AA-TSO-0001", 1.0)
    _flow(session, "b", "ITP-00500", "BB-TSO-0001", 12e6)
    session.commit()
    # AA's row is stored but carries no value for the day.
    blank = session.get(FlowObservationRecord, "a")
    blank.original_value = blank.original_unit = None
    session.commit()
    kept = select_operator_rows(_rows(session))
    assert [row.observation_id for row in kept] == ["b"]


def test_energy_comes_from_the_native_payload_when_no_original_value_was_kept():
    class Row:
        original_value = original_unit = flow_mcm_d = None
        native_rate_json = {"energy_kwh_per_day": "7000000", "volume_mcm_per_day": None}

    assert row_energy_gwh(Row()) == (pytest.approx(7.0), False)


# --- Coverage: a partly reported newest day is left out --------------------------------


def _full_day(session, day, scale=1.0, *, skip=()):
    for index, point in enumerate(LANDING_POINTS):
        if point.point_id in skip:
            continue
        _flow(session, f"{day:%m%d}-{index}", point.point_id, point.operator,
              450e6 * scale, day=day)


def test_a_partly_reported_day_is_left_out_but_a_low_complete_day_is_kept(session):
    as_of = DAY + timedelta(days=12)
    for offset in range(8):
        _full_day(session, DAY + timedelta(days=offset))
    # Day 9: every point reports, at a fifth of normal (an outage), one at zero.
    outage_day = DAY + timedelta(days=8)
    _full_day(session, outage_day, scale=0.2, skip={"ITP-00106"})
    _flow(session, "outage-zero", "ITP-00106", "BE-TSO-0001", 0.0, day=outage_day)
    # Days 10 and 11: ENTSOG has filled in only some points so far.
    partial = [point.point_id for point in LANDING_POINTS[:7]]
    _full_day(session, DAY + timedelta(days=9), skip=set(partial[:3]))
    _full_day(session, DAY + timedelta(days=10), skip=set(partial))
    session.commit()

    supply = landed_supply(session, date(2026, 11, 1), as_of=as_of)
    assert supply.incomplete_days == [
        (DAY + timedelta(days=9)).date(),
        (DAY + timedelta(days=10)).date(),
    ]
    assert supply.complete_through == outage_day.date()
    # The outage day is low supply, not a gap: 9 points at 90 GWh, one at zero.
    assert supply.by_day[outage_day.date()] == pytest.approx(9 * 90.0)
    assert supply.points_reporting[(DAY + timedelta(days=10)).date()] == 3


# --- Same physical point, stable operator, closed-day rows, alias candidates -----------


def test_a_second_key_for_one_physical_point_is_not_counted_twice(session):
    from eurogas_nexus.application.pipeline_supply import SAME_PHYSICAL_POINT

    # Live: Dornum GASPOOL (ITP-00525) publishes the OGE Dornum flow to the kWh.
    assert SAME_PHYSICAL_POINT["ITP-00525"].canonical == "ITP-00126"
    _flow(session, "a", "ITP-00126", "DE-TSO-0009", 742e6)
    _flow(session, "b", "ITP-00525", "DE-TSO-0009", 742e6)
    # The next day only the alias key has reported: it is kept, not lost.
    _flow(session, "c", "ITP-00525", "DE-TSO-0009", 746e6, day=DAY + timedelta(days=1))
    session.commit()

    kept = select_operator_rows(_rows(session))
    assert [row.observation_id for row in kept] == ["a", "c"]
    # A reader that loads only the alias key still sees its rows.
    alias_only = [row for row in _rows(session) if row.point_id == "ITP-00525"]
    assert [row.observation_id for row in select_operator_rows(alias_only)] == ["b", "c"]


def test_the_operator_stays_on_the_side_chosen_the_day_before(session):
    # Bacton IUK, live: National Gas (UK-TSO-0001) had not reported 11 Nov, IUK had.
    for offset, operators in enumerate(
        (("UK-TSO-0001", "UK-TSO-0003"), ("UK-TSO-0003",), ("UK-TSO-0001", "UK-TSO-0003"))
    ):
        for operator in operators:
            _flow(session, f"{offset}-{operator}", "ITP-00005", operator, 32e6,
                  day=DAY + timedelta(days=offset))
    session.commit()

    kept = select_operator_rows(_rows(session))
    by_day = {gas_day_of(row): row_operator(row) for row in kept}
    assert list(by_day.values()) == ["UK-TSO-0001", "UK-TSO-0003", "UK-TSO-0003"]


def gas_day_of(row):
    return row.period_start_utc.date()


def test_a_row_received_while_its_gas_day_was_open_is_not_the_days_flow(session):
    from eurogas_nexus.application.pipeline_supply import published_after_close

    for offset in range(4):
        _full_day(session, DAY + timedelta(days=offset))
    # Day 5: every point reported, but Dornum's row is a snapshot taken mid-day.
    snapshot_day = DAY + timedelta(days=4)
    _full_day(session, snapshot_day, skip={"ITP-00126"})
    _flow(session, "snapshot", "ITP-00126", "DE-TSO-0009", 157e6, day=snapshot_day)
    session.commit()
    snapshot = session.get(FlowObservationRecord, "snapshot")
    snapshot.observed_at_utc = snapshot_day + timedelta(hours=7)  # before the day ended
    session.commit()

    assert not published_after_close(snapshot)
    supply = landed_supply(session, date(2026, 11, 1), as_of=DAY + timedelta(days=8))
    # The snapshot is neither a flow nor a report: the day is incomplete, not low.
    assert supply.incomplete_days == [snapshot_day.date()]
    assert snapshot_day.date() not in supply.by_day


def test_identical_series_are_listed_as_candidates_and_nothing_else(session):
    from eurogas_nexus.application.pipeline_supply import (
        identical_series_candidates,
        load_alias_candidates,
    )

    for offset in range(5):
        day = DAY + timedelta(days=offset)
        value = (700 + offset * 10) * 1e6
        _flow(session, f"a{offset}", "ITP-00126", "DE-TSO-0009", value, day=day)
        _flow(session, f"b{offset}", "ITP-00525", "DE-TSO-0009", value, day=day)
        _flow(session, f"c{offset}", "ITP-00188", "DE-TSO-0005", value * 1.0003, day=day)
        _flow(session, f"d{offset}", "ITP-00106", "BE-TSO-0001", 480e6, day=day)
        _flow(session, f"e{offset}", "ITP-00045", "FR-TSO-0003", 480e6, day=day)
        # All-zero series match each other trivially and are not listed.
        _flow(session, f"z{offset}", "ITP-00126", "DE-TSO-0009", 0.0, day=day,
              direction="exit")
        _flow(session, f"y{offset}", "ITP-00525", "DE-TSO-0009", 0.0, day=day,
              direction="exit")
    session.commit()

    exact = identical_series_candidates(_rows(session), days=5)
    pairs = {(c.first[0], c.second[0]) for c in exact}
    # A flat 480 GWh at two unrelated points over five days matches too: a candidate is a
    # question for a person, which is why nothing is applied automatically.
    assert pairs == {("ITP-00126", "ITP-00525"), ("ITP-00045", "ITP-00106")}
    listed = {(c.first[0], c.second[0]): c.as_dict()["already_listed"] for c in exact}
    assert listed[("ITP-00126", "ITP-00525")] is True
    near = identical_series_candidates(_rows(session), days=5, tolerance=0.0005)
    assert ("ITP-00126", "ITP-00188") in {(c.first[0], c.second[0]) for c in near}
    # Too few days to judge: nothing.
    assert identical_series_candidates(_rows(session), days=6) == []
    # The loader reads closed days from the store.
    loaded = load_alias_candidates(session, days=5, now=DAY + timedelta(days=7))
    assert {(c.first[0], c.second[0]) for c in loaded} == pairs
