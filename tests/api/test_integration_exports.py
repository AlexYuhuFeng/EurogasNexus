"""ERP/ETRM integration: signed decision hand-offs, CSV report exports, ETRM trade loads."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ScreenOrderObservationRecord, TradingBookRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.ingestion.etrm_trades import EtrmImportError, parse_etrm_trades

KEY = "k" * 40
PUBLIC_TOKEN = "test-public-api-token"


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'integration.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    bearers = {}
    with Session(engine) as session:
        for name, role in (("analyst", "ANALYST"), ("reviewer", "REVIEWER")):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            bearers[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    return engine, bearers


def test_only_a_decided_case_is_handed_off_and_the_signature_verifies(tmp_path, monkeypatch):
    _engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    case_id = client.post(
        "/api/decision-cases",
        headers=who["analyst"],
        json={"objective": "Hedge December NBP length.", "gas_day": "2026-11-01"},
    ).json()["data"]["case_id"]
    client.post(
        f"/api/decision-cases/{case_id}/evidence",
        headers=who["analyst"],
        json={"kind": "ROUTE_RECOMMENDATION", "ref": "ladder-1", "snapshot_id": "snap-1"},
    )
    monkeypatch.delenv("EUROGAS_NEXUS_HANDOFF_SIGNING_KEY", raising=False)
    path = f"/api/decision-cases/{case_id}/handoff"
    assert client.get(path, headers=who["analyst"]).status_code == 503
    monkeypatch.setenv("EUROGAS_NEXUS_HANDOFF_SIGNING_KEY", KEY)
    undecided = client.get(path, headers=who["analyst"])
    assert undecided.status_code == 409
    client.post(
        f"/api/decision-cases/{case_id}/decisions",
        headers=who["reviewer"],
        json={"outcome": "accepted", "note": "Sell 10 MW Dec-26 NBP."},
    ).raise_for_status()
    handoff = client.get(path, headers=who["analyst"])
    assert handoff.status_code == 200, handoff.text
    body = handoff.json()["data"]
    signature = body.pop("signature")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    expected = hmac.new(KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert signature == {"algorithm": "HMAC-SHA256", "value": expected}
    assert body["schema"] == "eurogas-nexus-handoff/v1" and "Not an order" in body["boundary"]
    again = client.get(path, headers=who["analyst"]).json()["data"]
    assert again["idempotency_key"] == body["idempotency_key"]


def test_etrm_extract_loads_into_books_and_exports_as_csv(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    start = (datetime.now(UTC).date().replace(day=1) + timedelta(days=40)).replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    extract = (
        "trade_id,trade_time,book_id,hub,side,delivery_start,delivery_end,quantity,"
        "quantity_unit,price,price_unit,status\n"
        f"T1,2026-10-30T09:00:00Z,uk-nbp,NBP,SELL,{start},{end},10000,th/d,95,GBp/th,LIVE\n"
        f"T2,2026-10-30T09:05:00Z,nl-ttf,TTF,BUY,{start},{end},10,MW,35,EUR/MWh,LIVE\n"
        f"T3,2026-10-30T09:10:00Z,nl-ttf,TTF,BUY,{start},{end},5,MW,35,EUR/MWh,CANCELLED\n"
    )
    result = parse_etrm_trades(extract, system="Endur", source_reference="test")
    assert [row["external_order_id"] for row in result.upserts] == ["T1", "T2"]
    assert result.cancelled_ids == ["etrm-endur-T3"]
    nbp = result.upserts[0]
    assert nbp["unit"] == "GBP/MWh" and nbp["price"] == pytest.approx(0.95 * 34.1214163, rel=1e-6)
    days = (end - start).days + 1
    assert nbp["quantity_mwh"] == pytest.approx(10000 / 34.1214163 * days, rel=1e-6)
    with pytest.raises(EtrmImportError, match="trades in GBP"):
        parse_etrm_trades(
            extract.replace("95,GBp/th", "35,EUR/MWh"), system="E", source_reference="t"
        )

    now = datetime.now(UTC)
    with Session(engine) as session:
        for book_id, entity in (("uk-nbp", "EGN-UK"), ("nl-ttf", "EGN-NL")):
            session.add(
                TradingBookRecord(
                    book_id=book_id,
                    name=book_id,
                    legal_entity=entity,
                    region="europe",
                    business="NW Europe gas",
                    base_currency="EUR",
                    active=True,
                    updated_by="t",
                    updated_at_utc=now,
                )
            )
        for row in result.upserts:
            session.add(ScreenOrderObservationRecord(**row))
        session.commit()

    client = TestClient(create_app())
    csv = client.get(
        "/api/portfolio/position-ladder?months=4&group_by=legal_entity&format=csv",
        headers=who["analyst"],
    )
    assert csv.status_code == 200, csv.text
    assert csv.headers["content-type"].startswith("text/csv")
    assert "attachment;" in csv.headers["content-disposition"]
    lines = csv.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("group,level,physical_mwh,financial_mwh,net_mwh")
    assert {line.split(",")[0] for line in lines[1:]} == {"EGN-NL", "EGN-UK"}
    assert csv.headers["x-eurogas-report-rows"] == "2"
