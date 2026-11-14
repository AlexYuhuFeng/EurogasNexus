"""FRESH-01: every dataset declares its freshness in its manifest; one service reads it."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import data_quality_report
from eurogas_nexus.application.freshness_contract import (
    freshness_contract,
    next_expected_update,
    receipt_state,
)
from eurogas_nexus.application.physical_native_rates import serialize_native_rate
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.domain.connectors.registry import connector_manifests
from eurogas_nexus.domain.dataops.contracts import (
    MANUAL_REGISTER,
    FreshnessState,
    ScheduleType,
)
from eurogas_nexus.domain.dataops.freshness import FreshnessEvidence, evaluate_source_freshness
from eurogas_nexus.domain.dataops.registry import definition_for_source, source_definitions
from eurogas_nexus.domain.dataops.schedule import next_scheduled_instant
from eurogas_nexus.ingestion.entsog_native_units import parse_entsog_native_rate

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)  # a Saturday


def test_every_manifest_declares_its_receipt_policy_explicitly() -> None:
    undeclared = [
        m.source_id for m in connector_manifests() if "freshness_policy" not in m.operations
    ]
    assert undeclared == []


def test_every_measured_dataset_is_declared_once_and_every_declaration_is_measured() -> None:
    declared = [
        (m.source_id, item.dataset) for m in connector_manifests() for item in m.dataset_freshness
    ]
    measured = [(spec.source_id, spec.dataset) for spec in data_quality_report.SPECS]
    assert len(declared) == len(set(declared))
    assert sorted(declared) == sorted(measured)


def test_a_scheduled_source_is_not_judged_late_before_its_next_run_could_deliver() -> None:
    for definition in source_definitions():
        if not definition.schedulable:
            continue
        spec = definition.schedule
        cadence = (
            int(spec.interval_seconds) / 60 if spec.schedule_type == ScheduleType.INTERVAL else 1440
        )
        assert definition.freshness_policy.normal_max_age_minutes >= cadence, definition.source_id


def test_receipt_states() -> None:
    entsog = definition_for_source("src-entsog")
    assert receipt_state(entsog, None, NOW) == "never"
    assert receipt_state(entsog, NOW - timedelta(minutes=30), NOW) == "current"
    assert receipt_state(entsog, NOW - timedelta(hours=3), NOW) == "late"
    assert receipt_state(entsog, NOW - timedelta(hours=7), NOW) == "stale"


def test_a_weekend_is_not_counted_against_a_weekday_fixing() -> None:
    sonia = definition_for_source("src-boe")
    friday = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)
    monday_morning = datetime(2026, 11, 16, 8, tzinfo=UTC)
    assert receipt_state(sonia, friday, monday_morning) == "current"
    # The same 70 hours on an every-day source would be stale-ish: here it is counted.
    gb = definition_for_source("src-national-gas-supply")
    assert receipt_state(gb, friday, monday_morning) == "late"


def test_tariff_registers_are_manual_and_raise_no_freshness_alarm() -> None:
    tariffs = [d for d in source_definitions() if d.integration == MANUAL_REGISTER]
    assert {d.source_id for d in tariffs} == {
        "src-national-gas-nts", "src-bbl", "src-iuk", "src-gts", "src-natran",
        "src-german-tso", "src-fluxys-belgium", "src-cnmc-enagas",
    }
    ancient = NOW - timedelta(days=400)
    for definition in tariffs:
        assert receipt_state(definition, ancient, NOW) == "manual"
        evaluation = evaluate_source_freshness(
            definition, FreshnessEvidence(observed_at_utc=ancient), now_utc=NOW
        )
        assert evaluation.state is FreshnessState.NOT_EXPECTED
        assert next_expected_update(definition, None, NOW) == (None, "not_scheduled")


def test_next_expected_update_is_the_schedulers_own() -> None:
    entsog = definition_for_source("src-entsog")
    activated = NOW - timedelta(hours=5, minutes=20)
    scheduler_next = next_scheduled_instant(entsog, activated_at=activated, after=NOW)
    state = {"enabled": True, "next_run_at_utc": scheduler_next.isoformat()}
    assert next_expected_update(entsog, state, NOW) == (scheduler_next, "scheduler")
    assert next_expected_update(entsog, {"enabled": False}, NOW) == (None, "scheduler_disabled")
    # No scheduler state yet: what the scheduler sets on first sight.
    first = next_scheduled_instant(entsog, activated_at=NOW, after=NOW)
    assert next_expected_update(entsog, None, NOW) == (first, "schedule")
    # A weekday source on a Saturday: Monday at its daily time.
    ecb = definition_for_source("src-ecb")
    moment, basis = next_expected_update(ecb, None, NOW)
    assert basis == "schedule" and moment.weekday() == 0
    gie = replace(definition_for_source("src-gie"))
    moment, _ = next_expected_update(gie, None, NOW)
    assert moment == next_scheduled_instant(gie, activated_at=NOW, after=NOW)


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_the_service_reports_every_dataset_with_last_receipt_and_state(session) -> None:
    day = datetime(2026, 11, 12, 5, tzinfo=UTC)
    received = NOW - timedelta(minutes=40)
    native = serialize_native_rate(parse_entsog_native_rate("1.0", "kWh/d"))
    session.add(
        FlowObservationRecord(
            observation_id="f1", point_id="ITP-00106", point_name="Zeebrugge ZPT",
            direction="entry", kind="actual", flow_mcm_d=None, original_value=1.0,
            original_unit="kWh/d", period_start_utc=day, period_end_utc=day + timedelta(days=1),
            observed_at_utc=day + timedelta(days=1), revised_at_utc=received,
            source_system="ENTSOG", source_reference="t", freshness="daily",
            research_only=True, metadata_json={},
            normalizer_version=native["normalizer_version"], native_rate_json=native,
        )
    )
    session.commit()
    rows = freshness_contract(session, now=NOW)
    by_key = {(row["source_id"], row["dataset"]): row for row in rows}
    flows = by_key[("src-entsog", "ENTSOG flows")]
    # Last received is the revision, not the first receipt.
    assert flows["last_received_at_utc"] == received.isoformat()
    assert flows["last_period_at_utc"] == day.isoformat()
    assert flows["state"] == "current"
    assert flows["expected"]["period_late_hours"] == 54
    assert flows["expected"]["interval_minutes"] == 60
    assert by_key[("src-entsog", "ENTSOG capacity")]["state"] == "never"
    bbl = [row for row in rows if row["source_id"] == "src-bbl"]
    assert [row["state"] for row in bbl] == ["manual"]
    assert {row["state"] for row in rows} <= {"current", "late", "stale", "never", "manual"}
    # Every registered source has at least one row: nothing goes undeclared.
    assert {d.source_id for d in source_definitions()} == {row["source_id"] for row in rows}
