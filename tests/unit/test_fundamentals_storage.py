"""Storage against its own history (CP-04; design basis 2, D.2, E, F.2; reliability gate K.0).

Golden cases are hand-computed. The application fixture holds constant fills per prior gas
year, so every band figure can be checked by eye:

    prior gas year   2020/21 2021/22 2022/23 2023/24 2024/25 2025/26
    fill (%)           50      60      70      65      55      75

The band uses the last five complete years (2021/22..2025/26): low 55, high 75,
mean (60 + 70 + 65 + 55 + 75) / 5 = 65. The current gas year rises 0.5 points a day from
60.0 on 1 October 2026, so on 15 November 2026 (45 days on) it is 82.5: day change +0.5,
week change +3.5, vs the 5-yr mean +17.5 (above the range), and +7.5 against the same gas
day last year (75.0). The EU total is the sum of its four real countries (DE 250, IT 200,
NL 140, FR 130 TWh of capacity = 720), so it reconciles exactly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.fundamentals_storage import EU_STORAGE_COUNTRIES, storage_read
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.observation import StorageObservationRecord
from eurogas_nexus.domain.fundamentals.storage_history import (
    band_from_years,
    gas_year_of,
    history_plan,
    is_complete,
    same_day_last_year,
    season_index,
    season_keys,
)
from eurogas_nexus.security.identity import AuthenticatedPrincipal

NOW = datetime(2026, 11, 16, 9, tzinfo=UTC)
LAST = date(2026, 11, 15)
PRIOR = {2020: 50.0, 2021: 60.0, 2022: 70.0, 2023: 65.0, 2024: 55.0, 2025: 75.0}


# ---------------------------------------------------------------- domain: golden cases


def test_gas_year_axis_has_365_days_and_no_leap_day() -> None:
    keys = season_keys()
    assert len(keys) == 365 and keys[0] == "10-01" and keys[-1] == "09-30"
    assert season_index(date(2026, 11, 17)) == 47
    assert season_index(date(2024, 2, 29)) == -1
    assert gas_year_of(date(2026, 9, 30)) == 2025 and gas_year_of(date(2026, 10, 1)) == 2026
    assert same_day_last_year(date(2028, 2, 29)) == date(2027, 2, 28)


def test_history_rule_never_claims_more_years_than_held() -> None:
    assert history_plan([], date(2026, 3, 1)).mode == "none"
    assert history_plan([], date(2026, 3, 1)).label.startswith("History from 1 Mar 2026")
    one = history_plan([2025], None)
    assert (one.mode, one.label) == ("lines", "1 prior year held")
    four = history_plan([2022, 2023, 2024, 2025], None)
    assert (four.mode, four.label) == ("lines", "4 prior years held")
    band = history_plan(range(2018, 2026), None)
    assert band.mode == "band" and band.years == (2021, 2022, 2023, 2024, 2025)
    assert band.label == "5-yr range 2021/22–2025/26"


def test_band_statistics_golden() -> None:
    # Day 0: 60, 70, 65, 55, 75 -> low 55, high 75, mean 65. Day 1: one year missing -> gap.
    years = [[60.0, 61.0], [70.0, None], [65.0, 66.0], [55.0, 56.0], [75.0, 76.0]]
    band = band_from_years([y + [None] * 363 for y in years])
    assert (band.low[0], band.high[0], band.mean[0]) == (55.0, 75.0, 65.0)
    assert (band.low[1], band.high[1], band.mean[1]) == (None, None, None)
    assert band.years == 5


def test_a_year_is_held_with_values_on_95_percent_of_its_days() -> None:
    assert is_complete([1.0] * 347 + [None] * 18)
    assert not is_complete([1.0] * 346 + [None] * 19)


# ---------------------------------------------------------------- the read on a store


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p-analyst",
        name="analyst",
        principal_type="USER",
        role="ANALYST",
        status="ACTIVE",
        data_scopes=scopes,
        roles=("ANALYST",),
    )


def _fill(day: date) -> float:
    year = gas_year_of(day)
    if year in PRIOR:
        return PRIOR[year]
    return 60.0 + 0.5 * (day - date(2026, 10, 1)).days


def _rows(code: str, first: date, last: date, *, source: str = "GIE", capacity: float = 100.0,
          scale: float = 1.0) -> list[dict]:
    rows = []
    day = first
    while day <= last:
        fill = _fill(day)
        start = datetime(day.year, day.month, day.day, 5, tzinfo=UTC)
        rows.append({
            "observation_id": f"{source}-{code}-{day.isoformat()}",
            "source_dataset": "AGSI",
            "facility_id": code,
            "facility_name": code,
            "country": code,
            "inventory_twh": round(capacity * scale * fill / 100, 6),
            "working_capacity_twh": capacity * scale,
            "fill_pct": fill,
            "injection_twh_d": 0.2 * scale,
            "withdrawal_twh_d": 0.1 * scale,
            "period_start_utc": start,
            "period_end_utc": start + timedelta(days=1),
            "observed_at_utc": start + timedelta(days=1, hours=20),
            "source_system": source,
            "source_reference": "test",
            "source_record_id": f"{code}-{day.isoformat()}",
            "freshness": "daily",
            "research_only": True,
            "metadata_json": {"simulated": True} if source.endswith("_Sim") else {},
        })
        day += timedelta(days=1)
    return rows


@pytest.fixture
def store(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'storage.sqlite'}")
    Base.metadata.create_all(engine)
    first = date(2020, 10, 1)
    rows = []
    for code, capacity in (("DE", 250.0), ("NL", 140.0), ("FR", 130.0)):
        rows += _rows(code, first, LAST, capacity=capacity)
    # GIE's EU total: here the sum of the real countries (inventory and capacity).
    # GIE stores its EU total under "eu" (the provider code; the identity rule knows it).
    rows += _rows("eu", first, LAST, capacity=720.0)
    # Italy holds only three prior gas years: lines, not a band.
    rows += _rows("IT", date(2023, 10, 1), LAST, capacity=200.0)
    # Austria is simulated only (demo); Germany has a demo copy that must never be used.
    rows += _rows("AT", first, LAST, source="DEMO_Sim", capacity=100.0)
    rows += _rows("DE", date(2026, 10, 1), LAST, source="DEMO_Sim", capacity=999.0)
    with Session(engine) as session:
        session.bulk_insert_mappings(StorageObservationRecord, rows)
        session.commit()
    return engine


def _read(engine, **kwargs):
    with Session(engine) as session:
        return storage_read(session, _principal("DEMO"), now=NOW, **kwargs)


def test_the_region_band_and_comparisons_match_the_hand_computed_figures(store) -> None:
    data = _read(store, season=["EU", "DE"])
    region = data["region"]
    assert region["code"] == "EU" and region["as_of"] == "2026-11-15"
    assert region["fill_pct"] == 82.5
    assert region["day_change_pts"] == 0.5 and region["week_change_pts"] == 3.5
    assert region["vs_last_year"] == {"day": "2025-11-15", "fill_pct": 75.0, "diff_pts": 7.5}
    average = region["vs_average"]
    assert (average["years"], average["mean_pct"], average["low_pct"], average["high_pct"]) == (
        5, 65.0, 55.0, 75.0)
    assert average["diff_pts"] == 17.5 and average["outside"] == "above"
    assert region["history"]["label"] == "5-yr range 2021/22–2025/26"
    assert region["net_withdrawal_7d_twh_d"] == pytest.approx(-0.1)
    assert region["target"]["pct"] == 90.0 and region["target"]["gap_pts"] == -7.5
    # 7.5 points to go at 0.5 points a day: 15 days.
    assert region["target"]["days_to_target_at_7d_rate"] == 15
    band = region["season"]["band"]
    at = season_index(LAST)
    assert (band["low"][at], band["high"][at], band["mean"][at]) == (55.0, 75.0, 65.0)
    assert band["years"] == ["2021/22", "2022/23", "2023/24", "2024/25", "2025/26"]
    assert region["season"]["this_year"][at] == 82.5
    assert region["season"]["this_year"][at + 1] is None, "no value after the last day held"
    assert region["season"]["last_year"]["values"][at] == 75.0
    assert len(region["spark"]) == 30 and region["spark"][-1] == {"day": "2026-11-15",
                                                                  "fill_pct": 82.5}


def test_countries_are_ordered_by_size_and_a_short_history_is_lines(store) -> None:
    data = _read(store, season=["IT"])
    codes = [c["code"] for c in data["countries"]]
    assert codes[:3] == ["DE", "IT", "NL"]
    italy = next(c for c in data["countries"] if c["code"] == "IT")
    assert italy["history"]["mode"] == "lines" and italy["history"]["label"] == "3 prior years held"
    assert italy["vs_average"]["years"] == 3 and italy["vs_average"]["label"] == "3-yr avg"
    assert italy["season"]["band"] is None
    # Last year is drawn as its own ghost, the other held year as a line.
    assert [line["gas_year"] for line in italy["season"]["lines"]] == ["2023/24", "2024/25"]
    focused = _read(store, focus=["FR"])
    assert focused["countries"][0]["code"] == "FR"


def test_missing_countries_are_stated_with_the_reason(store) -> None:
    data = _read(store)
    missing = {item["code"]: item["reason"] for item in data["missing"]}
    held = {c["code"] for c in data["countries"]}
    assert held | set(missing) == set(EU_STORAGE_COUNTRIES)
    assert "ES" in missing and missing["ES"] == "No storage rows held for this country"


def test_real_and_simulated_never_mix(store) -> None:
    data = _read(store)
    germany = next(c for c in data["countries"] if c["code"] == "DE")
    assert not germany["simulated"] and germany["sources"] == ["GIE"]
    assert germany["working_capacity_twh"] == 250.0, "the demo copy (999 TWh) is not used"
    austria = next(c for c in data["countries"] if c["code"] == "AT")
    assert austria["simulated"] and austria["sources"] == ["DEMO_Sim"]
    assert data["simulated"] is True
    # A caller without the demo scope sees no simulated country at all.
    with Session(store) as session:
        public = storage_read(session, _principal(), now=NOW)
    assert "AT" not in {c["code"] for c in public["countries"]}


def test_the_region_reconciles_with_its_countries(store) -> None:
    rec = _read(store)["reconciliation"]
    # EU 720 TWh x 82.5 % = 594.0; DE + IT + NL + FR = (250 + 200 + 140 + 130) x 82.5 % = 594.0.
    assert rec["region_stock_twh"] == 594.0
    assert rec["countries_stock_twh"] == 594.0
    assert rec["difference_twh"] == 0.0
    assert rec["countries_counted"] == 4, "the simulated AT is never added to a real total"
    assert rec["complete"] is False


def test_north_west_europe_is_the_sum_of_its_countries_and_refuses_a_mixed_sum(store) -> None:
    data = _read(store, region="nwe")
    region = data["region"]
    assert region["code"] == "NWE"
    # DE + NL + FR (BE, DK not held): capacity 520, fill 82.5.
    assert region["working_capacity_twh"] == 520.0 and region["fill_pct"] == 82.5
    assert {m["code"] for m in data["missing"]} >= {"GB", "LU", "BE", "DK"}
    with Session(store) as session:
        session.bulk_insert_mappings(
            StorageObservationRecord, _rows("BE", date(2025, 10, 1), LAST, source="DEMO_Sim")
        )
        session.commit()
    mixed = _read(store, region="nwe")
    assert mixed["region"] is None and mixed["warnings"]


def test_unknown_region_is_refused(store) -> None:
    with pytest.raises(ValueError):
        _read(store, region="asia")


def test_the_route_returns_the_read_with_the_gie_attribution(store, tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", str(store.url))
    client = TestClient(create_app())
    response = client.get("/api/fundamentals/storage", params={"region": "eu", "season": "eu,de"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["attribution"].startswith("Source: GIE")
    assert body["data"]["region"]["code"] == "EU"
    assert "season" in body["data"]["region"]
    assert client.get("/api/fundamentals/storage", params={"region": "asia"}).status_code == 422
