"""Every flow reader takes one operator's report per point and gas day, energy as published.

Live ENTSOG (2026-11-12): both operators at an interconnection publish the point, each from
its own side, and native rows carry energy (kWh/d) with the volume column NULL. Readers that
added the operators' rows counted one flow twice; readers of the volume column saw nothing.
The fixture is the live shape at ITP-00011 (HR -> HU, 25.4 GWh on the day).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.routes.public import analysis as analysis_module
from eurogas_nexus.api.routes.public.research_data import _fundamental_evidence
from eurogas_nexus.application.agents import db_bridge
from eurogas_nexus.application.map_situation import build_map_situation
from eurogas_nexus.application.physical_native_rates import serialize_native_rate
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord, ReferenceNode
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.ingestion.entsog_native_units import parse_entsog_native_rate

DAY = datetime(2026, 11, 10, 5, tzinfo=UTC)
NOW = DAY + timedelta(days=1, hours=8)
FLOW_KWH = 25_425_000.0  # 25.425 GWh

#: (observation, operator, direction, kWh/d) as the two operators publish them.
INTERCONNECTION = (
    ("hr-entry", "HR-TSO-0001", "entry", 0.0),
    ("hr-exit", "HR-TSO-0001", "exit", FLOW_KWH),
    ("hu-entry", "HU-TSO-0001", "entry", FLOW_KWH),
    ("hu-exit", "HU-TSO-0001", "exit", 0.0),
)


def _native_row(observation_id, operator, direction, kwh) -> FlowObservationRecord:
    native = serialize_native_rate(parse_entsog_native_rate(repr(kwh), "kWh/d"))
    return FlowObservationRecord(
        observation_id=observation_id,
        point_id="ITP-00011",
        point_name="Dravaszerdahely",
        direction=direction,
        kind="actual",
        flow_mcm_d=None,  # native energy rows leave the volume column empty
        original_value=kwh,
        original_unit="kWh/d",
        period_start_utc=DAY,
        period_end_utc=DAY + timedelta(days=1),
        observed_at_utc=DAY + timedelta(days=1, hours=2),
        source_system="ENTSOG",
        source_reference="entsog-operationaldatas",
        freshness="daily",
        research_only=True,
        metadata_json={"operatorKey": operator},
        normalizer_version=native["normalizer_version"],
        native_rate_json=native,
    )


@pytest.fixture
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'flows.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(_native_row(*row) for row in INTERCONNECTION)
        session.add(
            ReferenceNode(
                id="entsog-itp-00011", name="Dravaszerdahely", node_type="interconnection",
                country="HU", lat=45.8, lon=17.8, source_system="ENTSOG",
                source_record_id="ITP-00011", data_quality="entsog", metadata_json={},
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    for name in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)
    return engine


def _exit_total(rows, key):
    return sum(row[key] for row in rows if row["direction"] == "exit" and row[key] is not None)


def test_agent_bridge_reads_energy_once_from_one_operator(engine):
    with Session(engine) as session:
        rows = db_bridge.flow_rows(session)
    assert {row["operator_key"] for row in rows} == {"HR-TSO-0001"}
    assert all(row["flow_mcm_d"] is None for row in rows)  # unknown volume, not zero
    assert _exit_total(rows, "energy_gwh_d") == pytest.approx(25.425)
    # Before: the native rows had no admissible volume and the agent saw no flow at all.
    assert len(rows) == 2


def test_analysis_snapshot_reads_energy_once_from_one_operator(engine):
    snapshot = analysis_module._load_snapshot()
    rows = snapshot.flow_observations
    assert {row["operator_key"] for row in rows} == {"HR-TSO-0001"}
    assert _exit_total(rows, "flow_mwh_per_day") == pytest.approx(25_425.0)
    assert all(row["flow_mcm_d"] is None for row in rows)


def test_map_shows_one_side_of_the_interconnection(engine):
    with Session(engine) as session:
        situation = build_map_situation(
            session, now=NOW, entitled=lambda rows: list(rows), include_positions=False
        )
    flows = {flow["direction"]: flow for flow in situation["flows"]}
    assert {flow["operator_key"] for flow in flows.values()} == {"HR-TSO-0001"}
    # Entry and exit from the same side: the 25.4 GWh flow leaves HR, nothing enters it.
    assert flows["exit"]["gwh_d"] == pytest.approx(25.425)
    assert flows["entry"]["gwh_d"] == 0.0


def test_research_flow_series_hold_one_value_per_day(engine):
    definitions = {d.provider.casefold(): d for d in source_definitions()}
    with Session(engine) as session:
        records, _ = _fundamental_evidence(
            session,
            {"flow.gwh_d.ITP-00011.exit", "flow.mcm_d.ITP-00011.exit"},
            definitions,
            history_start=DAY - timedelta(days=1),
            end=DAY + timedelta(days=2),
            requested_entity_ids=set(),
        )
    assert [(r.series_id, r.value, r.unit) for r in records] == [
        ("flow.gwh_d.ITP-00011.exit", pytest.approx(25.425), "GWh/d")
    ]  # one operator's report; no mcm/d value is invented from the energy


def test_physical_volume_listing_says_native_energy_rows_were_withheld(engine):
    response = TestClient(create_app()).get("/api/physical/flows")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] == []
    warnings = " ".join(payload["meta"]["warnings"])
    assert "quantity_basis=native" in warnings and "not a zero value" in warnings


def test_glossary_usage_never_averages_entry_with_exit(engine):
    from eurogas_nexus.domain.analysis.glossary_context import _capacity_usage

    usage = _capacity_usage(analysis_module._load_snapshot(), ["Dravaszerdahely"])
    assert usage["observations_count"] == 1
    assert usage["used_mwh_per_day"] in (0.0, 25_425.0)  # one direction, never 12,712.5
