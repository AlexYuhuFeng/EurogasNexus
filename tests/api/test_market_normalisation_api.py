"""Comparable-price reads: /api/market/fx-forward and /api/market/normalise.

And the spread lab accepting legs in different units (NBP in GBP against TTF in EUR) through
the normalisation service.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    InterestRateObservationRecord,
    MarketObservationRecord,
)
from eurogas_nexus.security.permissions import Permission, permission_for_path

SPOT = date(2026, 11, 16)
START = datetime(2026, 8, 1, 16, 30, tzinfo=UTC)


def _fx(day: date, quote: str, rate: float, *, source: str = "ECB",
        rate_type: str = "reference", value_date: date | None = None) -> FxObservationRecord:
    return FxObservationRecord(
        observation_id=f"fx-{source}-{rate_type}-{quote}-{(value_date or day).isoformat()}",
        pair=f"EUR{quote}",
        base_currency="EUR",
        quote_currency=quote,
        rate=rate,
        rate_type=rate_type,
        value_date=(value_date or day).isoformat(),
        observed_at_utc=datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        + timedelta(hours=14),
        source_system=source,
        source_reference="test",
        freshness="daily",
        research_only=True,
    )


def _fixing(day: date, benchmark: str, rate: float) -> InterestRateObservationRecord:
    currency = {"SONIA": "GBP", "ESTR": "EUR", "SOFR": "USD"}[benchmark]
    admin = {"SONIA": "BOE", "ESTR": "ECB", "SOFR": "NYFED"}[benchmark]
    return InterestRateObservationRecord(
        observation_id=f"{benchmark}-{day.isoformat()}",
        benchmark_id=benchmark,
        currency=currency,
        value_date=day,
        rate_pct=rate,
        day_count="ACT/365F" if benchmark == "SONIA" else "ACT/360",
        source_system=admin,
        source_reference="test",
        ingested_at_utc=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
    )


def _price(hub: str, day: int, price: float, *, unit: str, currency: str,
           tenor: str = "month-ahead", source: str = "Settlement_Import",
           simulated: bool = False) -> MarketObservationRecord:
    observed = START + timedelta(days=day)
    month = (observed.date().replace(day=1) + timedelta(days=32)).replace(day=1)
    following = (month + timedelta(days=32)).replace(day=1)
    return MarketObservationRecord(
        observation_id=f"p-{hub}-{tenor}-{source}-{day}",
        market_venue="EEX",
        product=f"{hub} {tenor}",
        price=price,
        unit=unit,
        currency=currency,
        period_start_utc=datetime(month.year, month.month, 1, 5, tzinfo=UTC),
        period_end_utc=datetime(following.year, following.month, 1, 5, tzinfo=UTC),
        observed_at_utc=observed,
        source_system=source,
        source_reference=f"t:{hub}:{day}",
        freshness="end_of_day",
        quality_score=0.9,
        research_only=True,
        metadata_json={"hub": hub, "tenor": tenor, "simulated": simulated,
                       "settlement": source == "Settlement_Import"},
    )


def _client(tmp_path, monkeypatch, *, rows=(), scopes=("*",), role="ANALYST") -> TestClient:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'norm.sqlite').as_posix()}"
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
        session.add_all(list(rows))
        principal = create_identity_principal(
            session, name="norm-user", display_name="Norm User", role=role,
            data_scopes=list(scopes),
        )
        _, bearer = create_identity_api_key(session, principal.principal_id, scopes=["*"])
        session.commit()
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer},
    )


def _rates(day: date = SPOT) -> list:
    return [
        _fx(day, "GBP", 0.87),
        _fx(day, "USD", 1.16),
        _fixing(day, "SONIA", 3.75),
        _fixing(day, "ESTR", 1.90),
        _fixing(day, "SOFR", 4.30),
    ]


def test_fx_forward_golden_eurgbp_jan27(tmp_path, monkeypatch):
    """EUR/GBP for Jan-27 on 16 Nov 2026: 0.87 × (1 + 0.0375·60/365)/(1 + 0.019·60/360) = 0.8726."""

    client = _client(tmp_path, monkeypatch, rows=_rates())
    response = client.get(
        "/api/market/fx-forward",
        params={"base": "EUR", "quote": "GBP", "product": "Jan-27", "as_of": SPOT.isoformat()},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert round(data["rate"], 4) == 0.8726
    assert data["method"] == "derived: covered interest parity"
    assert data["label"].startswith("derived (interest parity from")
    assert data["value_date"] == "2027-01-15"
    assert data["delivery"]["label"] == "Jan-27"
    assert data["spot"]["value_date"] == "2026-11-16"
    assert {r["benchmark"] for r in data["rates"]} == {"SONIA", "ESTR"}
    assert data["tolerance"]["relative_pct"] == 0.1
    assert data["as_of"] == "2026-11-16"
    spot = client.get(
        "/api/market/fx-forward",
        params={"base": "EUR", "quote": "GBP", "product": "DA", "as_of": SPOT.isoformat()},
    ).json()["data"]
    assert spot["method"] == "spot: ECB reference rate" and spot["rate"] == 0.87


def test_fx_forward_refusals(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, rows=_rates())
    far = client.get(
        "/api/market/fx-forward",
        params={"base": "EUR", "quote": "GBP", "product": "Cal-29", "as_of": SPOT.isoformat()},
    )
    assert far.status_code == 422
    assert far.json()["detail"]["code"] == "beyond_horizon"
    missing = client.get(
        "/api/market/fx-forward",
        params={"base": "EUR", "quote": "JPY", "as_of": SPOT.isoformat()},
    )
    assert missing.status_code == 422
    assert missing.json()["detail"]["message"] == "not convertible: no EURJPY rate held"
    unknown = client.get(
        "/api/market/fx-forward",
        params={"base": "EUR", "quote": "GBP", "product": "Xyz-27"},
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "unknown_product_code"


def test_licensed_forward_is_used_only_with_the_entitlement(tmp_path, monkeypatch):
    licensed = _fx(SPOT, "GBP", 0.8800, source="WMR", rate_type="forward_outright",
                   value_date=date(2027, 1, 15))
    params = {"base": "EUR", "quote": "GBP", "product": "Jan-27", "as_of": SPOT.isoformat()}
    entitled = _client(tmp_path, monkeypatch, rows=[*_rates(), licensed])
    data = entitled.get("/api/market/fx-forward", params=params).json()["data"]
    assert data["method"] == "licensed" and data["rate"] == 0.88
    assert data["label"] == "sourced (WMR)"


def test_licensed_forward_hidden_from_a_caller_without_the_scope(tmp_path, monkeypatch):
    licensed = _fx(SPOT, "GBP", 0.8800, source="WMR", rate_type="forward_outright",
                   value_date=date(2027, 1, 15))
    params = {"base": "EUR", "quote": "GBP", "product": "Jan-27", "as_of": SPOT.isoformat()}
    restricted = _client(
        tmp_path, monkeypatch, rows=[*_rates(), licensed], scopes=("ECB", "BOE"),
    )
    data = restricted.get("/api/market/fx-forward", params=params).json()["data"]
    assert data["method"] == "derived: covered interest parity"


def test_normalise_values_and_series(tmp_path, monkeypatch):
    """78 p/th NBP Jan-27 → 30.500 EUR/MWh (forward), 30.592 (spot); no USD/JPY → refused."""

    client = _client(tmp_path, monkeypatch, rows=_rates())
    response = client.post(
        "/api/market/normalise",
        json={
            "to_unit": "EUR/MWh",
            "values": [
                {"value": 78.0, "unit": "p/th", "product": "Jan-27", "as_of": "2026-11-16",
                 "label": "NBP Jan-27"},
                {"value": 78.0, "unit": "p/th", "as_of": "2026-11-16"},
                {"value": 30.0, "unit": "EUR/MWh", "simulated": True},
                {"value": 500.0, "unit": "JPY/MMBtu", "as_of": "2026-11-16"},
            ],
            "series": {
                "unit": "GBP/MWh",
                "points": [{"day": "2026-11-16", "value": 26.6147047, "product": "Jan-27"},
                           {"day": "2026-10-01", "value": 26.0, "product": "Jan-27"}],
            },
        },
    )
    assert response.status_code == 200, response.text
    values = response.json()["data"]["values"]
    assert round(values[0]["value"], 3) == 30.500
    assert values[0]["label"] == "NBP Jan-27"
    assert values[0]["normalisation"]["fx"]["method"] == "derived: covered interest parity"
    assert values[0]["tolerance"]["relative_pct"] == 0.1
    assert round(values[1]["value"], 3) == 30.592
    assert values[2]["simulated"] is True and values[2]["value"] == 30.0
    assert values[3]["value"] is None
    assert values[3]["refused"]["message"] == "not convertible: no EURJPY rate held"
    series = response.json()["data"]["series"]
    assert series["converted"] == 1
    assert series["refused"][0]["reason"] == "not convertible: no EURGBP rate held"
    assert response.json()["meta"]["warnings"]


def test_normalise_rejects_unknown_units(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, rows=_rates())
    bad = client.post("/api/market/normalise",
                      json={"to_unit": "EUR/t", "values": [{"value": 1, "unit": "EUR/MWh"}]})
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "normalise_invalid"
    empty = client.post("/api/market/normalise", json={"to_unit": "EUR/MWh"})
    assert empty.status_code == 422


def test_instrument_catalogue_is_hierarchical_and_entitled(tmp_path, monkeypatch):
    rows = [
        *[_price("TTF", day, 30 + day / 100, unit="EUR/MWh", currency="EUR")
          for day in range(40)],
        *[_price("NBP", day, 26 + day / 100, unit="GBP/MWh", currency="GBP")
          for day in range(10)],
        _price("TTF", 39, 31.0, unit="EUR/MWh", currency="EUR", tenor="jan-27"),
        _price("TTF", 39, 31.5, unit="EUR/MWh", currency="EUR", tenor="q1-27"),
        _price("TTF", 39, 29.0, unit="EUR/MWh", currency="EUR", tenor="day-ahead"),
        _price("THE", 39, 32.0, unit="EUR/MWh", currency="EUR", source="DEMO_Sim",
               simulated=True),
        _price("PEG", 39, 30.5, unit="EUR/MWh", currency="EUR", source="ICE_Endex"),
    ]
    client = _client(tmp_path, monkeypatch, rows=rows)
    response = client.get("/api/market/instruments")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["levels"] == ["hub", "product_kind", "tenor"]
    hubs = [hub["hub"] for hub in data["hubs"]]
    assert hubs == ["TTF", "NBP", "THE", "PEG"]
    ttf = data["hubs"][0]
    assert ttf["native_unit"] == "EUR/MWh"
    assert [kind["kind"] for kind in ttf["kinds"]] == ["spot", "rolling", "month", "quarter"]
    rolling = ttf["kinds"][1]["instruments"][0]
    assert rolling["id"] == "TTF:M+1" and rolling["tenor"] == "month-ahead"
    assert rolling["observations"] == 40 and rolling["thin"] is False
    assert rolling["source_class"] == "indicative"
    assert rolling["instrument_kind"] == "outright"
    month = ttf["kinds"][2]["instruments"][0]
    assert month["id"] == "TTF:Jan-27" and month["delivery"]["first_gas_day"] == "2027-01-01"
    nbp = data["hubs"][1]
    assert nbp["native_unit"] == "GBp/th" and nbp["currency"] == "GBP"
    nbp_m1 = nbp["kinds"][0]["instruments"][0]
    assert nbp_m1["stored_unit"] == "GBP/MWh" and nbp_m1["thin"] is True
    the = data["hubs"][2]
    assert the["simulated"] is True
    assert the["kinds"][0]["instruments"][0]["source_class"] == "simulated"
    # Every level is short: no flat month × product list.
    assert all(len(kind["instruments"]) <= 12 for hub in data["hubs"] for kind in hub["kinds"])

    (tmp_path / "r").mkdir()
    restricted = _client(tmp_path / "r", monkeypatch, rows=[], scopes=("EIA",))
    assert restricted.get("/api/market/instruments").json()["data"]["hubs"] == []


def test_instrument_catalogue_hides_unentitled_sources(tmp_path, monkeypatch):
    rows = [
        _price("PEG", 1, 30.5, unit="EUR/MWh", currency="EUR", source="ICE_Endex"),
        _price("TTF", 1, 30.0, unit="EUR/MWh", currency="EUR", source="EEX"),
    ]
    client = _client(tmp_path, monkeypatch, rows=rows, scopes=("EEX",))
    hubs = [hub["hub"] for hub in client.get("/api/market/instruments").json()["data"]["hubs"]]
    assert hubs == ["TTF"]


def test_spread_lab_accepts_nbp_against_ttf_in_mixed_units(tmp_path, monkeypatch):
    """NBP (GBP/MWh stored) − TTF (EUR/MWh) in EUR/MWh, each day at that day's forward FX."""

    rows = []
    for day in range(45):
        on = (START + timedelta(days=day)).date()
        rows += [
            _fx(on, "GBP", 0.87),
            _fixing(on, "SONIA", 3.75),
            _fixing(on, "ESTR", 1.90),
            _price("NBP", day, 26.6 + 0.01 * day, unit="GBP/MWh", currency="GBP"),
            _price("TTF", day, 30.0 + 0.01 * day, unit="EUR/MWh", currency="EUR"),
        ]
    client = _client(tmp_path, monkeypatch, rows=rows)
    response = client.post(
        "/api/research/spread-analysis",
        json={"legs": [{"hub": "NBP", "tenor": "month-ahead", "weight": 1},
                       {"hub": "TTF", "tenor": "month-ahead", "weight": -1}],
              "unit": "EUR/MWh",
              "rule": {"kind": "zscore", "lookback": 20, "entry_z": 2.0, "exit_z": 0.5,
                       "volume_mwh_per_day": 100, "cost_per_mwh": 0}},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["unit"] == "EUR/MWh"
    assert data["statistics"]["days"] == 45
    nbp = data["normalisation"][0]
    assert nbp["from_unit"] == "GBP/MWh" and nbp["to_unit"] == "EUR/MWh"
    assert nbp["fx_methods"] == ["derived: covered interest parity"]
    assert nbp["converted"] == 45 and nbp["refused"] == []
    # Without a unit, the display unit is the first leg's native one (p/th for NBP).
    native = client.post(
        "/api/research/spread-analysis",
        json={"legs": [{"hub": "NBP", "tenor": "month-ahead", "weight": 1},
                       {"hub": "TTF", "tenor": "month-ahead", "weight": -1}]},
    )
    assert native.status_code == 200, native.text
    assert native.json()["data"]["unit"] == "p/th"


def test_spread_lab_mixed_units_without_fx_say_what_is_missing(tmp_path, monkeypatch):
    rows = [
        *[_price("NBP", day, 26.6, unit="GBP/MWh", currency="GBP") for day in range(30)],
        *[_price("TTF", day, 30.0, unit="EUR/MWh", currency="EUR") for day in range(30)],
    ]
    client = _client(tmp_path, monkeypatch, rows=rows)
    response = client.post(
        "/api/research/spread-analysis",
        json={"legs": [{"hub": "NBP", "tenor": "month-ahead", "weight": 1},
                       {"hub": "TTF", "tenor": "month-ahead", "weight": -1}],
              "unit": "EUR/MWh"},
    )
    assert response.status_code == 422
    assert "not convertible: no EURGBP rate held" in response.json()["detail"]["message"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/market/fx-forward"), ("POST", "/api/market/normalise"),
]
)
def test_new_reads_are_read_permission(method, path):
    assert permission_for_path(path, method) is Permission.READ


def test_a_viewer_may_read_all_three(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, rows=_rates(), role="VIEWER")
    assert client.get("/api/market/instruments").status_code == 200
    assert client.get(
        "/api/market/fx-forward", params={"base": "EUR", "quote": "GBP", "as_of": "2026-11-16"}
    ).status_code == 200
    assert client.post(
        "/api/market/normalise", json={"to_unit": "EUR/MWh", "values": [{"value": 1,
                                                                       "unit": "p/th"}]}
    ).status_code == 200
