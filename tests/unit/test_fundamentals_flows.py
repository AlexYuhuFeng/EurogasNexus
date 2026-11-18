"""Pipeline landings against their own history (CP-17; design basis 2, D.2 "Flows").

Golden case: every registry landing point lands 10 x L GWh/d, L constant per gas year:

    gas year   2020/21 2021/22 2022/23 2023/24 2024/25 2025/26 2026/27
    L            1       2       3       4       5       6      4.5

Norway (eight points): 80 x L. Band from 2021/22..2025/26: low 160, high 480, mean 320 GWh/d;
on 15 Nov 2026 the 7-day mean is 360: +40 against the mean, -120 against last year (480).
Dornum (two points) is 20 x L = 90; Emden (three points) 30 x L = 135. The UK terminals
(two points) are 20 x L, their own scope.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application.fundamentals_flows import flows_read
from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
from eurogas_nexus.db.base import Base
from eurogas_nexus.domain.fundamentals.storage_history import gas_year_of, season_index
from eurogas_nexus.domain.market.gas_day import gas_day_start_utc
from eurogas_nexus.security.identity import AuthenticatedPrincipal

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 16, 12, tzinfo=UTC)
LAST = date(2026, 11, 15)
LEVEL = {2020: 1.0, 2021: 2.0, 2022: 3.0, 2023: 4.0, 2024: 5.0, 2025: 6.0, 2026: 4.5}


def _seed_module():
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk_flows", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_demo_desk_flows"] = module
    spec.loader.exec_module(module)
    return module


def _rows(seed, first: date, last: date, source: str = "ENTSOG"):
    rows = []
    day = first
    while day <= last:
        start = gas_day_start_utc(datetime(day.year, day.month, day.day, 12, tzinfo=UTC))
        end = gas_day_start_utc(start + timedelta(hours=30))
        for point in LANDING_POINTS:
            row = seed._flow_row(point.point_id, point.label, point.operator, "entry",
                                 10 * LEVEL[gas_year_of(day)], day, start, end, NOW)
            row.source_system = source
            row.observation_id = f"{source}-{row.observation_id}"[:64]
            rows.append(row)
        day += timedelta(days=1)
    return rows


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    path = tmp_path_factory.mktemp("flows") / "flows.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{path}")
    Base.metadata.create_all(engine)
    seed = _seed_module()
    with Session(engine) as session:
        session.add_all(_rows(seed, date(2020, 10, 1), LAST))
        session.commit()
    return engine


def _principal(*scopes):
    return AuthenticatedPrincipal(principal_id="p", name="p", principal_type="USER",
                                  role="ANALYST", status="ACTIVE", data_scopes=scopes,
                                  roles=("ANALYST",))


def test_norway_total_against_its_band_golden(store) -> None:
    with Session(store) as session:
        data = flows_read(session, _principal(), season=["norway"], now=NOW)
    norway = next(item for item in data["totals"] if item["code"] == "norway")
    assert norway["as_of"] == "2026-11-15"
    assert norway["flow_7d_gwh_d"] == 360.0
    assert norway["vs_last_year"]["diff_gwh_d"] == -120.0
    average = norway["vs_average"]
    assert (average["years"], average["mean_gwh_d"], average["low_gwh_d"],
            average["high_gwh_d"], average["diff_gwh_d"]) == (5, 320.0, 160.0, 480.0, 40.0)
    band = norway["season"]["band"]
    at = season_index(LAST)
    assert (band["low"][at], band["high"][at], band["mean"][at]) == (160.0, 480.0, 320.0)
    uk = next(item for item in data["totals"] if item["code"] == "uk_terminal")
    assert uk["flow_7d_gwh_d"] == 90.0 and uk["scope"] == "uk_terminal"


def test_landings_sum_their_points_and_are_ordered_by_flow(store) -> None:
    with Session(store) as session:
        data = flows_read(session, _principal(), now=NOW)
    by_code = {item["code"]: item for item in data["landings"]}
    assert by_code["emden"]["flow_7d_gwh_d"] == 135.0  # three points
    assert by_code["dornum"]["flow_7d_gwh_d"] == 90.0  # two points
    assert by_code["nybro"]["flow_7d_gwh_d"] == 45.0
    assert data["landings"][0]["code"] == "emden"
    assert by_code["st_fergus"]["scope"] == "uk_terminal"
    assert "season" not in by_code["emden"], "the full season only on request"


def test_part_simulated_landings_are_not_added(store, tmp_path) -> None:
    seed = _seed_module()
    with Session(store) as session:
        session.add_all(_rows(seed, LAST, LAST, source="DEMO_Sim")[:1])
        session.flush()
        data = flows_read(session, _principal("DEMO"), now=NOW)
        session.rollback()
    assert data["totals"] == [] and data["landings"] == [] and data["warnings"]
