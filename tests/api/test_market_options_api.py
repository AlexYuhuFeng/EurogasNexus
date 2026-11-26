"""GET /api/market/options/*: entitlement first, then source precedence, then smile metrics."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import OptionSettlementRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.market.options import black76_price, ice_endex_ttf_monthly_expiry
from eurogas_nexus.domain.market.products import resolve_product
from eurogas_nexus.ingestion.option_settlements import parse_option_settlements
from eurogas_nexus.ingestion.simulated_option_settlements import (
    generate_simulated_option_settlements,
)

FORWARD = 31.0


def _business_day(day: date) -> date:
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _file(trade: date, vol: float, *, source: str) -> str:
    label = resolve_product("M+2", trade).label  # never expired, whatever today is
    expiry = ice_endex_ttf_monthly_expiry(resolve_product(label, trade).first_gas_day)
    tenor = (expiry - trade).days / 365.0
    lines = [
        "trade_date,hub,contract,expiry,strike,option_type,settlement,underlying,"
        "open_interest,style"
    ]
    for step in range(-16, 17):
        strike = FORWARD + step * 0.5
        for option_type in ("C", "P"):
            price = black76_price(option_type, FORWARD, strike, vol, tenor)
            interest = 200 if option_type == "P" else 100
            lines.append(
                f"{trade},TTF,{label},{expiry},{strike},{option_type},{price:.6f},{FORWARD},"
                f"{interest},futures_style"
            )
    return "\n".join(lines) + "\n"


@pytest.fixture()
def option_db(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'options.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    trade = _business_day(datetime.now(UTC).date() - timedelta(days=1))
    bearers = {}
    with Session(engine) as session:
        for name, scopes in (
            ("all", ["*"]),
            ("ice", ["ICE_ENDEX"]),
            ("vendor", ["Argus"]),
            ("none", []),
        ):
            owner = create_identity_principal(
                session, name=f"opt-{name}", display_name=name, role="ANALYST", data_scopes=scopes
            )
            _, bearer = create_identity_api_key(
                session, owner.principal_id, display_name=name, scopes=["*"]
            )
            bearers[name] = bearer
        for source, vol in (("ICE_ENDEX", 0.50), ("Argus", 0.70)):
            parsed = parse_option_settlements(
                _file(trade, vol, source=source), source_system=source, source_reference=source
            )
            for row in parsed.rows:
                session.add(OptionSettlementRecord(**row))
        for row in generate_simulated_option_settlements(trade - timedelta(days=3), trade).rows:
            session.merge(OptionSettlementRecord(**row))
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return trade, bearers


def _client(bearer: str) -> TestClient:
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    )


def _contracts(bearer: str, trade: date) -> dict[str, dict]:
    response = _client(bearer).get(f"/api/market/options/surface?hub=TTF&trade_date={trade}")
    assert response.status_code == 200, response.text
    return {item["contract"]: item for item in response.json()["data"]["contracts"]}


def test_exchange_settlement_outranks_vendor_and_simulator(option_db) -> None:
    trade, bearers = option_db
    contracts = _contracts(bearers["all"], trade)
    label = resolve_product("M+2", trade).label
    chosen = contracts[label]
    assert chosen["source_system"] == "ICE_ENDEX" and chosen["source_tier"] == "exchange"
    assert chosen["simulated"] is False
    assert {alt["source_system"] for alt in chosen["alternatives"]} >= {"Argus"}
    assert chosen["metrics"]["atm_iv_pct"] == pytest.approx(50.0, abs=1e-3)
    assert chosen["metrics"]["rr25_vol_pts"] == pytest.approx(0.0, abs=1e-3)
    assert chosen["metrics"]["put_call_oi_ratio"] == pytest.approx(2.0)
    strike = next(item for item in chosen["strikes"] if item["strike"] == FORWARD)
    assert strike["call"]["iv_pct"] == pytest.approx(50.0, abs=1e-3)
    # Contracts only the simulator carries are served, flagged, with the warning.
    simulated = [item for item in contracts.values() if item["simulated"]]
    assert simulated and all(item["source_system"] == "ICE_ENDEX_Sim" for item in simulated)


def test_entitlement_is_applied_before_precedence(option_db) -> None:
    trade, bearers = option_db
    label = resolve_product("M+2", trade).label
    # Only the vendor licence: the vendor's smile, never the exchange's.
    vendor = _contracts(bearers["vendor"], trade)
    assert set(vendor) == {label}
    assert vendor[label]["source_system"] == "Argus"
    assert vendor[label]["alternatives"] == []
    assert vendor[label]["metrics"]["atm_iv_pct"] == pytest.approx(70.0, abs=1e-3)
    # ICE Endex scope: the exchange file and the ICE Endex-family simulator.
    ice = _contracts(bearers["ice"], trade)
    assert ice[label]["source_system"] == "ICE_ENDEX"
    assert all(alt["source_system"] != "Argus" for alt in ice[label]["alternatives"])
    # No licensed scope: nothing, and the licensing hint.
    response = _client(bearers["none"]).get(f"/api/market/options/surface?trade_date={trade}")
    assert response.json()["data"]["contracts"] == []
    assert "licensed" in response.json()["meta"]["warnings"][0]


def test_front_month_metric_series(option_db) -> None:
    trade, bearers = option_db
    response = _client(bearers["all"]).get(
        f"/api/market/options/metrics?hub=TTF&tenor=M1&days=10&end={trade}"
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["units"]["atm_iv_pct"] == "%"
    points = data["points"]
    assert points and points[-1]["trade_date"] == trade.isoformat()
    assert [p["trade_date"] for p in points] == sorted(p["trade_date"] for p in points)
    assert all(point["atm_iv_pct"] is not None for point in points)


def test_unknown_hub_and_bad_tenor_are_refused(option_db) -> None:
    _, bearers = option_db
    client = _client(bearers["all"])
    assert client.get("/api/market/options/surface?hub=EUA").status_code == 422
    assert client.get("/api/market/options/metrics?tenor=Q1").status_code == 422
