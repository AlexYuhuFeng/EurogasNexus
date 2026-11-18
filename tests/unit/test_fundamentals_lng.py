"""LNG send-out against its own history (CP-17; design basis 2, D.2 "LNG").

Golden case: constant daily send-out per prior gas year (TWh/d), so the 7-day mean equals it:

    gas year   2020/21 2021/22 2022/23 2023/24 2024/25 2025/26 2026/27
    send-out     1.0     2.0     3.0     4.0     5.0     6.0     4.5

The band uses 2021/22..2025/26: low 2,000, high 6,000, mean 4,000 GWh/d; today 4,500 is
+500 against the mean, -1,500 against last year, 62.5 % up the range. A terminal with three
prior years (from 2023) shows each year as a line.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application.fundamentals_lng import ALSI_COUNTRIES, lng_read, mean_7d
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.observation import LngObservationRecord
from eurogas_nexus.domain.fundamentals.storage_history import gas_year_of, season_index
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime(2026, 11, 16, 9, tzinfo=UTC)
LAST = date(2026, 11, 15)
LEVEL = {2020: 1.0, 2021: 2.0, 2022: 3.0, 2023: 4.0, 2024: 5.0, 2025: 6.0, 2026: 4.5}


def _rows(code: str, first: date, *, source: str = "GIE") -> list[dict]:
    rows, day = [], first
    while day <= LAST:
        start = datetime(day.year, day.month, day.day, 5, tzinfo=UTC)
        rows.append({
            "observation_id": f"{source}-{code}-{day}", "source_dataset": "ALSI",
            "terminal_id": code, "terminal_name": code, "country": code,
            "inventory_twh": 2.0, "send_out_twh_d": LEVEL[gas_year_of(day)], "dtmi_twh": 4.0,
            "period_start_utc": start, "period_end_utc": start + timedelta(days=1),
            "observed_at_utc": start + timedelta(days=2), "source_system": source,
            "source_reference": "t", "freshness": "daily", "research_only": True,
        })
        day += timedelta(days=1)
    return rows


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'lng.sqlite'}")
    Base.metadata.create_all(engine)
    rows = _rows("eu", date(2020, 10, 1)) + _rows("NL", date(2020, 10, 1))
    rows += _rows("DE", date(2023, 10, 1))  # a terminal from 2023: three prior years
    rows += _rows("BE", date(2020, 10, 1), source="DEMO_Sim")
    with Session(engine) as session:
        session.bulk_insert_mappings(LngObservationRecord, rows)
        session.commit()
    return engine


def _principal(*scopes):
    return AuthenticatedPrincipal(principal_id="p", name="p", principal_type="USER",
                                  role="ANALYST", status="ACTIVE", data_scopes=scopes,
                                  roles=("ANALYST",))


def test_seven_day_mean_only_where_all_seven_days_are_held() -> None:
    values = {date(2026, 1, 1) + timedelta(days=k): float(k) for k in range(10)}
    del values[date(2026, 1, 9)]
    means = mean_7d(values)
    assert means[date(2026, 1, 7)] == 3.0  # (0 + 1 + ... + 6) / 7
    assert date(2026, 1, 9) not in means and date(2026, 1, 10) not in means


def test_band_and_comparisons_golden(store) -> None:
    with Session(store) as session:
        data = lng_read(session, _principal("DEMO"), season=["EU", "DE"], now=NOW)
    region = data["region"]
    assert region["send_out_7d_gwh_d"] == 4500.0
    assert region["vs_last_year"]["diff_gwh_d"] == -1500.0
    average = region["vs_average"]
    assert (average["years"], average["mean_gwh_d"], average["low_gwh_d"],
            average["high_gwh_d"]) == (5, 4000.0, 2000.0, 6000.0)
    assert average["diff_gwh_d"] == 500.0 and average["range_position"] == 62.5
    assert region["inventory_pct_of_dtmi"] == 50.0
    band = region["season"]["band"]
    at = season_index(LAST)
    assert (band["low"][at], band["high"][at], band["mean"][at]) == (2000.0, 6000.0, 4000.0)
    germany = next(c for c in data["countries"] if c["code"] == "DE")
    assert germany["history"]["label"] == "3 prior years held"
    assert germany["season"]["band"] is None
    assert [line["gas_year"] for line in germany["season"]["lines"]] == ["2023/24", "2024/25"]


def test_simulated_never_mixes_and_missing_countries_are_named(store) -> None:
    with Session(store) as session:
        demo = lng_read(session, _principal("DEMO"), now=NOW)
        public = lng_read(session, _principal(), now=NOW)
    belgium = next(c for c in demo["countries"] if c["code"] == "BE")
    assert belgium["simulated"] and demo["simulated"]
    assert "BE" not in {c["code"] for c in public["countries"]}
    missing = {m["code"] for m in public["missing"]}
    assert missing == set(ALSI_COUNTRIES) - {"NL", "DE"}
    assert {c["code"] for c in public["countries"]} == {"NL", "DE"}


def test_the_route(store, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", str(store.url))
    response = TestClient(create_app()).get("/api/fundamentals/lng", params={"season": "eu"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["attribution"].startswith("Source: GIE")
    assert "season" in body["data"]["region"]
