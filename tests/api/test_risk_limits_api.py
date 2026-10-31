"""Credit exposure and trader mandates over the position ladder's legs and marks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    MarketObservationRecord,
    ScreenOrderObservationRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'risk.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    month_start = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=5, minute=0, second=0, microsecond=0
    )
    who = {}
    with Session(engine) as session:
        for name, role in (("analyst", "ANALYST"), ("risk", "REVIEWER"), ("jdoe", "REVIEWER")):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {
                "X-Eurogas-Api-Key": PUBLIC_TOKEN,
                "X-Eurogas-Identity": bearer,
                "principal": row.principal_id,
            }
        session.add(
            UpstreamResourceContractRecord(
                contract_id="nbp-supply",
                contract_name="NBP supply",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="NBP",
                gas_year=f"{now.year - 1}+",
                delivery_quantity_mwh_per_day=1_000.0,
                contract_price_gbp_mwh=30.0,
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=2.0,
                nomination_tolerance_pct=1.0,
                tolerance_risk_allowance_gbp_mwh=None,
                annual_financing_rate_pct=5.0,
                owned_entry_capacity_mwh_per_day=None,
                owned_exit_capacity_mwh_per_day=None,
                allowed_exit_points=["NBP"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                notes=None,
                book_id="uk-phys",
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        for oid, provider, account in (
            ("hedge-1", "ICE_OCM", "jdoe"),
            ("etrm-1", "ETRM", "Centrica plc"),
        ):
            session.add(
                ScreenOrderObservationRecord(
                    order_observation_id=oid,
                    provider_id=provider,
                    venue="ICE",
                    account_label=account,
                    external_order_id=oid,
                    side="SELL",
                    order_type="LIMIT",
                    hub="NBP",
                    product="M+1",
                    contract_code="NBP-M1",
                    delivery_start_utc=month_start,
                    delivery_end_utc=month_start + timedelta(days=30),
                    price=32.0,
                    currency="GBP",
                    unit="GBP/MWh",
                    quantity_mwh=18_000,
                    filled_quantity_mwh=18_000,
                    remaining_quantity_mwh=0,
                    status="FILLED",
                    observed_at_utc=now,
                    source_system="fixture",
                    source_reference="fixture",
                    linked_strategy_id=None,
                    linked_resource_id=None,
                    research_only=True,
                    human_review_required=True,
                )
            )
        for day in range(30):
            session.add(
                MarketObservationRecord(
                    observation_id=f"nbp-{day}",
                    market_venue="ICE",
                    product="NBP month-ahead",
                    price=35.0,
                    unit="GBP/MWh",
                    currency="GBP",
                    period_start_utc=month_start,
                    period_end_utc=month_start + timedelta(days=30),
                    observed_at_utc=now - timedelta(days=30 - day),
                    source_system="ICE_OCM",
                    source_reference=f"nbp:{day}",
                    freshness="end_of_day",
                    quality_score=0.9,
                    research_only=True,
                    metadata_json={"hub": "NBP", "tenor": "month-ahead"},
                )
            )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine, who


def _h(who, name):
    return {k: v for k, v in who[name].items() if k != "principal"}


def test_credit_lines_and_mandates_are_maintained_by_risk_and_measured(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    line = {
        "name": "Centrica plc",
        "aliases": ["CENTRICA"],
        "limit_amount": 1_000_000,
        "currency": "GBP",
        "collateral_amount": 0,
        "contract_ids": ["nbp-supply"],
    }
    denied = client.put("/api/portfolio/credit-lines/CNA", json=line, headers=_h(who, "analyst"))
    assert denied.status_code == 403
    saved = client.put("/api/portfolio/credit-lines/CNA", json=line, headers=_h(who, "risk"))
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["created"] is True

    exposure = client.get("/api/portfolio/credit-exposure", headers=_h(who, "analyst"))
    assert exposure.status_code == 200, exposure.text
    (row,) = exposure.json()["data"]["rows"]
    assert row["counterparty"] == "Centrica plc" and row["legs"] == 2
    # Supply bought at 30 against a 35 mark is in our favour; the ETRM sale at 32 is not;
    # netted, the replacement exposure is the supply's gain less the sale's loss.
    assert row["replacement_exposure"] > 0
    assert row["status"] in {"ok", "watch", "breach"}
    assert row["net_exposure"] == row["replacement_exposure"] + row["receivable_exposure"]

    mandate = {
        "trader": who["jdoe"]["principal"],
        "display_name": "J. Doe",
        "hubs": ["ttf"],
        "max_net_mwh_per_month": 10_000,
        "max_tenor_months": 12,
    }
    own = client.put("/api/portfolio/trader-mandates/M1", json=mandate, headers=_h(who, "jdoe"))
    assert own.status_code == 403 and own.json()["detail"]["code"] == "own_mandate"
    mandate["trader"] = "jdoe"  # the account label on the trader's screen trades
    ok = client.put("/api/portfolio/trader-mandates/M1", json=mandate, headers=_h(who, "risk"))
    assert ok.status_code == 200, ok.text
    usage = client.get("/api/portfolio/mandate-usage", headers=_h(who, "analyst")).json()
    (mrow,) = usage["data"]["rows"]
    assert mrow["status"] == "breach" and mrow["legs"] == 1
    assert "NBP is outside" in mrow["breaches"] and "over 10,000 MWh" in mrow["breaches"]

    pdf = client.get("/api/portfolio/mandate-usage?format=pdf", headers=_h(who, "analyst"))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xlsx = client.get("/api/portfolio/credit-exposure?format=xlsx", headers=_h(who, "analyst"))
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")

    with Session(engine) as session:
        actions = {e.action for e in session.query(AuditEventRecord).all()}
    assert {"risk.credit_line.update", "risk.mandate.update"} <= actions


def test_delivery_performance_reads_allocations_for_visible_contracts(tmp_path, monkeypatch):
    from datetime import date

    from eurogas_nexus.db.models import ContractDeliveryRecord

    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    empty = client.get("/api/contracts/delivery-performance", headers=_h(who, "analyst"))
    assert empty.status_code == 200 and empty.json()["data"]["rows"] == []
    assert "import_contract_deliveries" in empty.json()["meta"]["warnings"][0]
    today = date.today()
    with Session(engine) as session:
        for i in range(1, 21):
            session.add(
                ContractDeliveryRecord(
                    contract_id="nbp-supply",
                    gas_day=today - timedelta(days=i),
                    nominated_mwh=1_000.0,
                    allocated_mwh=900.0 if i % 2 else 1_000.0,
                    tso="National Gas",
                    point="Bacton",
                    source_system="NATIONAL_GAS",
                    source_reference="t",
                    updated_at_utc=datetime.now(UTC),
                )
            )
        session.commit()
    body = client.get(
        "/api/contracts/delivery-performance?contract_id=nbp-supply", headers=_h(who, "analyst")
    ).json()["data"]
    (row,) = body["rows"]
    assert row["short_days"] == 10 and row["imbalance_mwh"] == 1_000.0
    assert row["tso"] == "National Gas" and len(body["series"]) == 20
    xlsx = client.get("/api/contracts/delivery-performance?format=xlsx", headers=_h(who, "analyst"))
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")


def test_lng_cargo_bid_prices_each_terminal_from_the_curve(tmp_path, monkeypatch):
    _engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    terms = {
        "name": "Isle of Grain",
        "country": "GB",
        "hub": "nbp",
        "regas_tariff_per_mwh": 1.0,
        "fuel_retention_pct": 1.0,
        "port_costs_per_cargo": 50_000,
        "source_note": "firm's capacity contract, 2026 tariff schedule",
    }
    saved = client.put(
        "/api/portfolio/lng-terminal-terms/grain", json=terms, headers=_h(who, "analyst")
    )
    assert saved.status_code == 200, saved.text
    listed = client.get("/api/portfolio/lng-terminal-terms", headers=_h(who, "analyst")).json()
    assert listed["data"]["rows"][0]["currency"] == "GBP"
    nxt = (datetime.now(UTC).replace(day=1) + timedelta(days=32)).strftime("%Y-%m")
    bid = client.post(
        "/api/portfolio/lng-cargo-bid",
        json={"cargo_mmbtu": 3_400_000, "arrival_month": nxt, "ranking_currency": "GBP"},
        headers=_h(who, "analyst"),
    )
    assert bid.status_code == 200, bid.text
    data = bid.json()["data"]
    (row,) = data["rows"]
    assert row["hub_mark"] == 35.0 and row["max_bid_per_mwh"] < 35.0
    assert data["regions"][0]["country"] == "GB"
    assert data["cargo_mwh"] == round(3_400_000 * 0.29307107, 1)
    both = client.post(
        "/api/portfolio/lng-cargo-bid",
        json={"cargo_mwh": 1, "cargo_mmbtu": 1, "arrival_month": nxt},
        headers=_h(who, "analyst"),
    )
    assert both.status_code == 422


def test_contract_intake_returns_a_draft_and_audits_only_the_digest(tmp_path, monkeypatch):
    from eurogas_nexus.core.report_files import pdf_bytes

    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    pdf = pdf_bytes(
        [
            {"Clause": "Contract Reference: SUP-77"},
            {"Clause": "Seller: Centrica plc"},
            {"Clause": "Delivery Point: NBP"},
            {"Clause": "Daily Contract Quantity: 10,000 MWh/d"},
        ],
        title="Confirmation",
    )
    headers = {**_h(who, "analyst"), "Content-Type": "application/pdf"}
    response = client.post(
        "/api/contracts/intake?file_name=SUP-77.pdf", content=pdf, headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["record"]["contract_id"] == "SUP-77"
    assert data["record"]["delivery_quantity_mwh_per_day"] == 10_000
    assert data["record"]["document_status"] == "PDF_EXTRACTED_REVIEW_REQUIRED"
    assert len(data["sha256"]) == 64
    bad = client.post("/api/contracts/intake", content=b"not a pdf", headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "pdf_unreadable"
    with Session(engine) as session:
        events = [
            e for e in session.query(AuditEventRecord).all() if e.action == "contract.intake.read"
        ]
    assert len(events) == 1 and data["sha256"] in events[0].detail


def test_retiring_a_contract_takes_it_out_of_positions_and_keeps_history(tmp_path, monkeypatch):
    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    headers = _h(who, "analyst")
    (contract,) = client.get("/api/route-cost/upstream-contracts", headers=headers).json()["data"]
    assert contract["retired_at_utc"] is None
    ladder = client.get("/api/portfolio/position-ladder?months=3", headers=headers).json()
    assert ladder["data"]["legs"]["physical"] == 1

    path = "/api/route-cost/upstream-contracts/nbp-supply"
    stale = client.post(
        f"{path}/retire",
        json={"reason": "terminated", "expected_edit_token": "0" * 64},
        headers=headers,
    )
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "contract_edit_conflict"
    short = client.post(
        f"{path}/retire", json={"reason": "x", "expected_edit_token": "0" * 64}, headers=headers
    )
    assert short.status_code == 422
    retired = client.post(
        f"{path}/retire",
        json={
            "reason": "Supply agreement terminated by mutual consent",
            "expected_edit_token": contract["edit_token"],
        },
        headers=headers,
    )
    assert retired.status_code == 200, retired.text
    assert retired.json()["data"]["retired_by"] == who["analyst"]["principal"]
    assert client.get("/api/route-cost/upstream-contracts", headers=headers).json()["data"] == []
    listed = client.get(
        "/api/route-cost/upstream-contracts?include_retired=true", headers=headers
    ).json()["data"]
    assert listed[0]["retire_reason"].startswith("Supply agreement")
    ladder = client.get("/api/portfolio/position-ladder?months=3", headers=headers).json()
    assert ladder["data"]["legs"]["physical"] == 0
    again = client.post(
        f"{path}/retire",
        json={"reason": "again", "expected_edit_token": listed[0]["edit_token"]},
        headers=headers,
    )
    assert again.json()["detail"]["code"] == "contract_already_retired"
    back = client.post(
        f"{path}/reinstate",
        json={"reason": "Agreement restored", "expected_edit_token": listed[0]["edit_token"]},
        headers=headers,
    )
    assert back.status_code == 200 and back.json()["data"]["retired_at_utc"] is None
    with Session(engine) as session:
        actions = [e.action for e in session.query(AuditEventRecord).all()]
    assert "contract.retire" in actions and "contract.reinstate" in actions


def test_sell_down_plan_uses_measured_delivery_and_falls_back_to_tolerance(tmp_path, monkeypatch):
    from datetime import date

    from eurogas_nexus.db.models import ContractDeliveryRecord

    engine, who = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    body = {
        "hub": "NBP",
        "da_price": 34.0,
        "wd_expected_price": 33.8,
        "short_penalty_per_mwh": 2.0,
        "long_discount_per_mwh": 0.3,
    }
    first = client.post("/api/portfolio/sell-down-plan", json=body, headers=_h(who, "analyst"))
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["volatility_basis"].startswith("contract nomination tolerance")
    assert data["sell_day_ahead_mwh"] < 1_000 and data["keep_within_day_mwh"] > 0
    with Session(engine) as session:
        for i in range(1, 31):
            session.add(
                ContractDeliveryRecord(
                    contract_id="nbp-supply",
                    gas_day=date.today() - timedelta(days=i),
                    nominated_mwh=1_000.0,
                    allocated_mwh=1_000.0 - (50.0 if i % 2 else -50.0),
                    tso=None,
                    point=None,
                    source_system="T",
                    source_reference="t",
                    updated_at_utc=datetime.now(UTC),
                )
            )
        session.commit()
    measured = client.post(
        "/api/portfolio/sell-down-plan", json=body, headers=_h(who, "analyst")
    ).json()["data"]
    assert measured["volatility_basis"] == "measured over 30 gas days"
    assert measured["supply_stdev_mwh"] == 50
    none = client.post(
        "/api/portfolio/sell-down-plan", json={**body, "hub": "TTF"}, headers=_h(who, "analyst")
    )
    assert none.status_code == 422 and none.json()["detail"]["code"] == "no_supply_at_hub"
