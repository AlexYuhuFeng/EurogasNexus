"""/api/research/spreads: describe → spec → result, end to end on a store with settlements,
ECB and benchmark rates and the BBL tariffs.

The worked example's arithmetic is in ``tests/unit/test_spreads_workbench.py``; this checks the
same figures through the API, the questions, and that the model is not used when not allowed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    InterestRateObservationRecord,
    MarketObservationRecord,
    TsoTariffRecord,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path

SPOT = date(2026, 11, 16)


def _price(hub, price, unit):
    observed = datetime(2026, 11, 16, 18, tzinfo=UTC)
    return MarketObservationRecord(
        observation_id=f"jan27-{hub}", market_venue="EEX", product=f"{hub} Jan-27", price=price,
        unit=unit, currency=unit.split("/")[0],
        period_start_utc=datetime(2027, 1, 1, 5, tzinfo=UTC),
        period_end_utc=datetime(2027, 2, 1, 5, tzinfo=UTC), observed_at_utc=observed,
        source_system="Settlement_Import", source_reference="t", freshness="end_of_day",
        quality_score=1.0, research_only=True,
        metadata_json={"hub": hub, "tenor": "jan-27", "settlement": True},
    )


def _tariff(point, tso, direction, value):
    return TsoTariffRecord(
        tariff_id=f"t-{point}-{tso}-{direction}".lower().replace(" ", "-"), document_id="fixture",
        country="NL", tso=tso, market_area="X", gas_year="2026/27", point_id=point,
        source_point_name=point, direction=direction, capacity_product="ANNUAL",
        firmness="FIRM", tariff_value=value, currency="EUR", unit="EUR/MWh",
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=datetime(2027, 9, 30, tzinfo=UTC), tariff_status="FINAL",
        source_table="ENTSOG TP tariffsfulls (fixture)", source_page=None, source_refs=[],
        manual_review_required=False, created_at_utc=datetime(2026, 11, 1, tzinfo=UTC),
    )


def _client(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'spreads.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    stamp = datetime(2026, 11, 16, 14, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all([
            _price("TTF", 30.00, "EUR/MWh"),
            _price("NBP", 26.6147047, "GBP/MWh"),
            FxObservationRecord(
                observation_id="ecb-gbp", pair="EURGBP", base_currency="EUR",
                quote_currency="GBP", rate=0.87, rate_type="reference",
                value_date=SPOT.isoformat(), observed_at_utc=stamp, source_system="ECB",
                source_reference="ecb", freshness="daily", research_only=True,
            ),
            *[
                InterestRateObservationRecord(
                    observation_id=f"{bench}-{SPOT}", benchmark_id=bench, currency=ccy,
                    value_date=SPOT, rate_pct=rate, day_count=dc, source_system=admin,
                    source_reference="t", ingested_at_utc=stamp,
                )
                for bench, ccy, rate, dc, admin in (
                    ("SONIA", "GBP", 3.75, "ACT/365F", "BOE"),
                    ("ESTR", "EUR", 1.90, "ACT/360", "ECB"),
                )
            ],
            _tariff("ITP-00063", "GTS", "EXIT", 0.56),
            _tariff("ITP-00207", "BBL company", "EXIT", 1.20),
            _tariff("ITP-00207", "National Gas TSO", "ENTRY", 0.12),
        ])
        analyst = create_identity_principal(
            session, name="spreads-analyst", display_name="Spreads Analyst", role="ANALYST",
            data_scopes=["*"],
        )
        _, bearer = create_identity_api_key(session, analyst.principal_id, scopes=["*"])
        session.commit()
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer},
    )


def test_describe_then_evaluate_the_worked_example(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    interpreted = client.post(
        "/api/research/spreads/interpret",
        json={"text": "forward spread net of transport tariff between TTF and NBP"},
    )
    assert interpreted.status_code == 200, interpreted.text
    data = interpreted.json()["data"]
    assert data["ready"] is True and data["ai"] == "off" and data["basis"] == "parser"
    spec = data["spec"]
    assert [(leg["hub"], leg["weight"]) for leg in spec["legs"]] == [("NBP", 1.0), ("TTF", -1.0)]
    evaluated = client.post("/api/research/spreads/evaluate",
                            json={"spec": spec, "as_of": SPOT.isoformat()})
    assert evaluated.status_code == 200, evaluated.text
    result = evaluated.json()["data"]["result"]
    row = next(item for item in result["rows"] if item["label"] == "Jan-27")
    assert round(row["gross"], 3) == 0.500
    assert round(row["cost"], 3) == 1.880
    assert round(row["net"], 3) == -1.380
    assert result["route"]["gas_years"] == ["2026/27"]
    assert result["route"]["input_class"] == "sourced"
    assert result["simulated"] is False


def test_questions_instead_of_refusals(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    unknown = client.post("/api/research/spreads/interpret", json={"text": "XYZ vs TTF"})
    issues = unknown.json()["data"]["issues"]
    assert issues[0]["code"] == "hub_not_held" and issues[0]["choices"] == ["TTF", "NBP"]
    vague = client.post("/api/research/spreads/interpret", json={"text": "make me money"})
    assert vague.json()["data"]["issues"][0]["code"] == "instruments_unclear"
    no_route = client.post("/api/research/spreads/evaluate", json={"spec": {
        "kind": "curve", "legs": [{"hub": "NBP", "weight": 1}, {"hub": "TTF", "weight": -1}],
        "unit": "EUR/MWh", "cost": {"from_hub": "NBP", "to_hub": "TTF"}}})
    body = no_route.json()["data"]
    # The route NBP → TTF exists; its tariffs are not held: no question, the cost is missing.
    assert body["issues"] == []
    assert body["result"]["rows"][0]["cost"] is None
    assert body["result"]["rows"][0]["net"] is None
    assert body["result"]["rows"][0]["input_class"] == "missing"


def test_spreads_routes_are_research_governed():
    for path in ("/api/research/spreads/interpret", "/api/research/spreads/evaluate"):
        assert permission_for_path(path, "POST") is Permission.GOVERNED


def test_the_model_is_not_called_when_ai_is_off(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(
        "eurogas_nexus.application.spreads_workbench.translation_messages",
        lambda *a, **k: called.append(1) or [],
    )
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/research/spreads/interpret",
                           json={"text": "NBP vs TTF jan27", "language": "zh-CN"})
    assert response.json()["data"]["ai"] == "off"
    assert called == []
