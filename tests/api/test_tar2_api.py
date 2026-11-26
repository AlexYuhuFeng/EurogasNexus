"""TAR-2 routes: tariff years, the firm's bookings, capacity cost contracted before public,
the source-precedence reads, the optimiser's held capacity and the governed settings write.

SQLite runtime store, the real app; made-up figures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import tariff_book as book
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import AuditEventRecord, FxObservationRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from tests.unit.test_tar2_capacity_costs import BOOKINGS, booked, daily_row

NOW = datetime.now(UTC).replace(microsecond=0)


def _client(engine, role: str) -> TestClient:
    with Session(engine) as session:
        # Book isolation is on by default (security review H1): a person with no BOOKS:
        # scope sees no bookings. This is a caller entitled to the book, so it holds the
        # head-office scope (BOOKS:* includes firm-level rows, which these bookings are).
        principal = create_identity_principal(
            session,
            name=f"tar2-{role.lower()}",
            display_name=role,
            role=role,
            data_scopes=["BOOKS:*"],
        )
        _, bearer = create_identity_api_key(session, principal.principal_id, scopes=["*"])
        session.commit()
    return TestClient(
        create_app(),
        headers={"X-Eurogas-Identity": bearer, "X-Eurogas-Api-Key": "test-public-api-token"},
    )


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'tar2.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.merge(daily_row(0.0125, status="FINAL", at=NOW - timedelta(days=2)))
        session.flush()
        book.capture_tariffs(session, now_utc=NOW - timedelta(days=2))
        booked(session, BOOKINGS, at=NOW - timedelta(days=1))
        session.add(FxObservationRecord(
            observation_id="ecb-usd", pair="EURUSD", base_currency="EUR", quote_currency="USD",
            rate=1.10, rate_type="reference",
            value_date=(NOW.date() - timedelta(days=1)).isoformat(),
            observed_at_utc=NOW - timedelta(hours=12), source_system="ECB",
            source_reference="test", freshness="daily", research_only=True,
        ))
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine


def test_tariff_years_show_both_versions_and_the_one_used(engine):
    client = _client(engine, "ANALYST")
    body = client.get("/api/tariffs/years", params={"facility": "ITP-1"}).json()
    (year,) = [row for row in body["data"]["years"] if row["product"] == "DAILY"]
    assert year["tariff_year"]["label"] == "GY 2026/27"
    assert year["used"] == "FINAL" and "published_at_stated" in year["FINAL"]
    assert year["FINAL"]["recorded_at_utc"]
    assert year["INDICATIVE"] is None
    assert client.get("/api/tariffs/years").status_code == 422


def test_bookings_and_the_capacity_cost_read_name_layers_versions_and_sources(engine):
    client = _client(engine, "ANALYST")
    rows = client.get("/api/capacity/bookings", params={"kind": "exit"}).json()["data"]["rows"]
    assert [row["booking_id"] for row in rows] == ["ENDUR:LT-7"]
    assert rows[0]["acquired_via"] == "long_term" and rows[0]["price_recorded"]
    cost = client.get(
        "/api/capacity/cost",
        params={"kind": "pipeline", "facility": "ITP-1", "direction": "EXIT",
                "first": "2027-01-01", "last": "2027-01-31", "mwh_per_day": 100,
                "product": "DAILY", "premium": 0.05},
    )
    assert cost.status_code == 200, cost.text
    data = cost.json()["data"]
    assert [layer["layer"] for layer in data["layers"]] == ["contracted", "public"]
    public = data["layers"][1]
    assert (public["status"], public["tariff_year"]) == ("FINAL", "GY 2026/27")
    # ENTSOG states no publication date: the record time is given and the date is not invented.
    assert public["version_id"] and public["recorded_at"] and "published_at" in public
    assert [s["tier"] for s in data["sources"]] == [
        "contracted", "public_final", "public_indicative"
    ]
    assert data["total_cost"] == 1482.83
    missing = client.get("/api/capacity/cost", params={"kind": "pipeline", "facility": "ITP-1"})
    assert missing.status_code == 422
    assert missing.json()["detail"]["code"] == "capacity_cost_input_missing"
    slot = client.get(
        "/api/capacity/cost",
        params={"kind": "terminal", "facility": "zeebrugge:term", "arrival": "2027-03-10",
                "cargo_mwh": 900000},
    ).json()["data"]
    assert slot["total_cost"] == 450000.0 and slot["layers"][0]["layer"] == "contracted"


def test_fx_rate_lists_the_sources_in_precedence_order(engine):
    client = _client(engine, "ANALYST")
    body = client.get("/api/pricing/fx-rate", params={"from": "USD", "to": "EUR"}).json()
    data = body["data"]
    assert data["value"] == pytest.approx(1 / 1.10) and data["used_tier"] == "ecb_reference"
    assert [s["tier"] for s in data["sources"]] == [
        "contracted_bank", "published_reference", "ecb_reference"
    ]
    assert [s["used"] for s in data["sources"]] == [False, False, True]
    order = client.get("/api/pricing/source-precedence").json()["data"]
    assert {row["kind"] for row in order["kinds"]} >= {"fx_rate", "capacity_cost"}
    assert "credentials" in order["live_feed_terms"]


def test_the_source_order_and_banks_are_an_audited_admin_setting_and_are_validated(engine):
    analyst = _client(engine, "ANALYST")
    denied = analyst.put("/api/settings/organisation",
                         json={"source_precedence": {"fx_rate": ["ecb_reference"]}})
    assert denied.status_code == 403
    admin = _client(engine, "ADMIN")
    bad = admin.put("/api/settings/organisation",
                    json={"source_precedence": {"fx_rate": ["public_final"]}})
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "setting_invalid"
    secret = admin.put("/api/settings/organisation", json={"financial_institutions": {
        "ABCBANK": {"name": "ABC", "provides": ["fx"], "password": "x"}}})
    assert secret.status_code == 422
    ok = admin.put("/api/settings/organisation", json={
        "source_precedence": {"fx_rate@lng_demurrage": ["ecb_reference", "contracted_bank"]},
        "financial_institutions": {"ABCBANK": {"name": "ABC Bank", "contracted": True,
                                               "provides": ["fx"]}},
    })
    assert ok.status_code == 200, ok.text
    merged = admin.put("/api/settings/organisation",
                       json={"source_precedence": {"capacity_cost": ["contracted",
                                                                     "public_final"]}})
    stored = merged.json()["data"]["source_precedence"]
    assert set(stored) == {"fx_rate@lng_demurrage", "capacity_cost"}
    order = admin.get("/api/pricing/source-precedence",
                      params={"context": "lng_demurrage"}).json()["data"]
    fx = next(row for row in order["kinds"] if row["kind"] == "fx_rate")
    assert fx["order"] == ["ecb_reference", "contracted_bank"]
    assert order["institutions"][0]["source_system"] == "BANK:ABCBANK"
    removed = admin.put("/api/settings/organisation",
                        json={"financial_institutions": {"ABCBANK": None}})
    assert removed.json()["data"]["financial_institutions"] == {}
    with Session(engine) as session:
        audits = session.scalars(select(AuditEventRecord).where(
            AuditEventRecord.action == "settings.organisation.update")).all()
    assert len(audits) == 3


def test_the_optimiser_covers_held_capacity_first(engine):
    client = _client(engine, "ANALYST")
    response = client.post("/api/optimization/capacity", json={
        "products": [
            {"product_id": "day", "capacity_mwh": 50, "fixed_cost_gbp": 100},
            {"product_id": "month", "capacity_mwh": 120, "fixed_cost_gbp": 300},
        ],
        "required_capacity_mwh": 100,
        "held_capacity_mwh": 60,
        "held_cost_gbp": 90,
    })
    assert response.status_code == 200, response.text
    result = response.json()["data"]["result"] if "result" in response.json()["data"] else (
        response.json()["data"]
    )
    flat = result.get("output", result)
    assert flat["held_capacity_mwh"] == 60 and flat["selected_product_ids"] == ["day"]
    assert flat["total_cost_gbp"] == 190
    assert [layer["layer"] for layer in flat["layers"]] == ["contracted", "public"]


def test_without_a_runtime_store_the_tar2_reads_degrade_and_say_so(monkeypatch):
    for name in ("RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        monkeypatch.delenv(name, raising=False)
    client = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"})
    for path, params in (
        ("/api/tariffs/years", {"facility": "ITP-1"}),
        ("/api/capacity/bookings", {}),
        ("/api/capacity/cost", {"kind": "terminal", "facility": "t", "arrival": "2027-01-01",
                                "cargo_mwh": 1}),
        ("/api/pricing/fx-rate", {"from": "USD", "to": "EUR"}),
        ("/api/pricing/source-precedence", {}),
    ):
        response = client.get(path, params=params)
        assert response.status_code == 200, (path, response.text)
        assert response.json()["meta"]["warnings"], path
