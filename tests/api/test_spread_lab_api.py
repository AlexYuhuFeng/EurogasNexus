"""Spread lab API: entitled daily series catalogue and spread analysis."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord

START = datetime(2026, 8, 1, 16, 30, tzinfo=UTC)


def _observation(
    hub: str, day: int, price: float, *, unit: str = "EUR/MWh"
) -> MarketObservationRecord:
    observed = START + timedelta(days=day)
    return MarketObservationRecord(
        observation_id=f"sl-{hub}-{day}-{unit}",
        market_venue="EEX",
        product=f"{hub} month-ahead",
        price=price,
        unit=unit,
        currency="EUR",
        period_start_utc=datetime(2026, 10, 1, 4, tzinfo=UTC),
        period_end_utc=datetime(2026, 11, 1, 5, tzinfo=UTC),
        observed_at_utc=observed,
        source_system="Settlement_Import",
        source_reference=f"sl:{hub}:{day}",
        freshness="end_of_day",
        quality_score=0.9,
        research_only=True,
        metadata_json={"hub": hub, "tenor": "month-ahead"},
    )


def _client(tmp_path, monkeypatch, *, extra=()) -> TestClient:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'spread-lab.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    with Session(engine) as session:
        for day in range(45):
            session.add(_observation("THE", day, 35.0 + 0.1 * day + (0.6 if day == 40 else 0.0)))
            session.add(_observation("TTF", day, 34.0 + 0.1 * day + (0.05 if day % 2 else -0.05)))
        session.add_all(list(extra))
        analyst = create_identity_principal(
            session, name="spread-analyst", display_name="Spread Analyst", role="ANALYST",
            data_scopes=["*"],
        )
        _, bearer = create_identity_api_key(session, analyst.principal_id, scopes=["*"])
        session.commit()
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer},
    )


def test_catalogue_lists_entitled_daily_series(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/api/research/spread-series")
    assert response.status_code == 200, response.text
    series = response.json()["data"]
    assert [(item["hub"], item["tenor"]) for item in series] == [
        ("THE", "month-ahead"),
        ("TTF", "month-ahead"),
    ]
    assert series[0]["days"] == 45
    assert series[0]["unit"] == "EUR/MWh"
    assert series[0]["first"] == "2026-08-01"


def test_the_ttf_spread_analysis(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/research/spread-analysis",
        json={
            "legs": [
                {"hub": "THE", "tenor": "month-ahead", "weight": 1},
                {"hub": "TTF", "tenor": "month-ahead", "weight": -1},
            ],
            "rule": {"kind": "zscore", "lookback": 20, "entry_z": 2.0, "exit_z": 0.5,
                     "volume_mwh_per_day": 100, "cost_per_mwh": 0},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["unit"] == "EUR/MWh"
    assert data["statistics"]["days"] == 45
    assert data["labels"] == ["THE month-ahead", "TTF month-ahead"]
    assert len(data["analysis_hash"]) == 64
    assert response.json()["meta"]["research_only"] is True


def test_unknown_series_and_mixed_units_are_refused(tmp_path, monkeypatch):
    extra = [_observation("PEG", day, 30.0, unit="GBP/MWh") for day in range(45)]
    client = _client(tmp_path, monkeypatch, extra=extra)
    unknown = client.post(
        "/api/research/spread-analysis",
        json={"legs": [{"hub": "NBP", "tenor": "month-ahead", "weight": 1}]},
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "spread_analysis_invalid"
    bad_rule = client.post(
        "/api/research/spread-analysis",
        json={"legs": [{"hub": "TTF", "tenor": "month-ahead", "weight": 1}],
              "rule": {"kind": "zscore", "entry_z": 0.5, "exit_z": 1.0}},
    )
    assert bad_rule.status_code == 422
    mixed = client.post(
        "/api/research/spread-analysis",
        json={"legs": [{"hub": "PEG", "tenor": "month-ahead", "weight": 1},
                       {"hub": "TTF", "tenor": "month-ahead", "weight": -1}]},
    )
    assert mixed.status_code == 422
    assert "different units" in mixed.json()["detail"]["message"]
