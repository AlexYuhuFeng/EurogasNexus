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
