"""GET /api/discoveries (CP-24): one data set, a different first item per job function.

The data: a long TTF supply facing a counterparty whose credit line a +10 % price move would
cross, and a net-positive TTF -> THE spread (the CP-09 golden case) in the opportunity store.
A trader sees the spread first; risk sees the projected credit breach first. A caller outside
the book sees neither; a function the caller does not hold is refused.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.opportunities.service import merge
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CreditLineRecord,
    IdentityPrincipalRecord,
    MarketObservationRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.opportunities.controls import assess, thresholds_from

PUBLIC_TOKEN = "test-public-api-token"
GOLDEN = Path(__file__).resolve().parents[1] / "domain" / "test_opportunity_evaluators.py"


AS_OF = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)  # the golden case's evaluation


def _golden_spread():
    spec = importlib.util.spec_from_file_location("golden_l", GOLDEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ((candidate, _),) = module._run_l(module._l_inputs())
    return candidate


def _month_start(day: date, offset: int) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'disc.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    now = datetime.now(UTC)
    today = now.date()
    last = date(today.year + (today.month >= 10), 9, 30)
    days = (last - today).days + 1
    who = {}
    with Session(engine) as session:
        session.add(
            TradingBookRecord(
                book_id="book-1",
                name="NL",
                legal_entity="E-NL",
                region="europe",
                business="gas",
                base_currency="EUR",
                active=True,
                updated_by="t",
                updated_at_utc=now,
            )
        )
        label = f"{last.year - 1}/{last.year % 100:02d}"
        session.add(
            UpstreamResourceContractRecord(
                contract_id="acme-supply",
                contract_name="Acme supply",
                resource_type="PIPELINE_IMPORT",
                delivery_point_name="TTF",
                gas_year=label,
                delivery_quantity_mwh_per_day=1000.0,
                contract_price_gbp_mwh=30.0,
                contract_price_currency="EUR",
                settlement_frequency="monthly",
                upstream_payment_lag_days=20,
                screen_sale_cash_lag_days=1,
                delivery_tolerance_pct=5.0,
                nomination_tolerance_pct=2.0,
                annual_financing_rate_pct=5.0,
                allowed_exit_points=["TTF"],
                eligible_sale_modes=["LOCAL_MARKET_SALE"],
                book_id="book-1",
                created_at_utc=now,
                updated_at_utc=now,
            )
        )
        # Exposure today = days x 1,000 x (32 - 30); the line sits 5 % above it.
        session.add(
            CreditLineRecord(
                counterparty_id="CP1",
                name="Aldermoor",
                aliases=[],
                legal_entity="E-NL",
                limit_amount=days * 2_000.0 * 1.05,
                currency="EUR",
                collateral_amount=0.0,
                rating="BBB",
                contract_ids=["acme-supply"],
                receivable_days=0,
                valid_until=date(today.year + 2, 9, 30),
                updated_by="risk",
                updated_at_utc=now,
            )
        )
        for offset in range(13):
            first = _month_start(today, offset)
            session.add(
                MarketObservationRecord(
                    observation_id=f"eex-ttf-{first:%Y-%m}",
                    market_venue="EEX",
                    product=f"TTF {first:%b-%y}",
                    price=32.0,
                    unit="EUR/MWh",
                    currency="EUR",
                    period_start_utc=datetime(first.year, first.month, 1, tzinfo=UTC),
                    period_end_utc=datetime.combine(
                        _month_start(first, 1), datetime.min.time(), UTC
                    ),
                    observed_at_utc=now - timedelta(hours=1),
                    source_system="EEX",
                    source_reference="eex",
                    freshness="end_of_day",
                    quality_score=1.0,
                    research_only=True,
                    metadata_json={"hub": "TTF", "tenor": f"{first:%Y-%m}"},
                )
            )
        # The golden case is dated; its validity is moved to "now" so the test does not age.
        candidate = replace(_golden_spread(), expires_at_utc=now + timedelta(days=9))
        thresholds = thresholds_from({"persistence": 1})
        # Assessed as of the golden case's own evaluation (its inputs are fresh then).
        assessment = assess(candidate, thresholds, as_of_utc=AS_OF, demo_desk=False)
        merge(
            session,
            {"locational": [(candidate, assessment)]},
            evaluation_id="e1",
            snapshot_id="s1",
            thresholds=thresholds,
            now=now,
        )
        for name, role, functions, scopes in (
            ("test_trader", "ANALYST", ["TRADER"], ["*"]),
            ("test_risk", "REVIEWER", ["RISK_MANAGER"], ["*"]),
            ("outsider", "ANALYST", ["TRADER"], ["BOOKS:BOOK:OTHER", "EEX"]),
        ):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=scopes
            )
            session.get(IdentityPrincipalRecord, row.principal_id).job_functions = functions
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.commit()
    return TestClient(create_app(Settings(api_profile="release"))), who


def test_one_data_set_two_roles(tmp_path, monkeypatch) -> None:
    client, who = _setup(tmp_path, monkeypatch)
    trader = client.get("/api/discoveries", headers=who["test_trader"]).json()["data"]
    risk = client.get("/api/discoveries", headers=who["test_risk"]).json()["data"]
    assert trader["audience"] == "trader" and risk["audience"] == "risk"
    assert [item["kind"] for item in trader["items"]][0] == "opportunity.locational"
    assert [item["kind"] for item in risk["items"]][0] == "credit.projected"
    first_risk = risk["items"][0]
    assert first_risk["quality"]["class"] == "indicative"  # settlement marks, labelled
    assert "(on indicative marks)" in first_risk["sentence"]
    assert "Aldermoor reaches its" in first_risk["sentence"]
    assert first_risk["method"].startswith("Mark-to-market sensitivity, not a potential")
    shock = next(row for row in first_risk["evidence"] if row["move_pct"] == 10)
    assert shock["breach"] is True and shock["tenor"]
    # The move that reaches the line: 5 % headroom on a 2.00 margin over 32.00 marks.
    assert first_risk["value"]["unit"] == "EUR/MWh"
    assert abs(float(first_risk["value"]["value"]) - 0.10) < 0.002
    assert trader["items"][0]["sentence"].startswith("TTF → THE · Jan-27")
    zh = client.get("/api/discoveries", params={"lang": "zh"}, headers=who["test_risk"]).json()
    assert "信用" in zh["data"]["items"][0]["sentence"]


def test_a_persona_never_widens_what_is_read(tmp_path, monkeypatch) -> None:
    client, who = _setup(tmp_path, monkeypatch)
    outsider = client.get("/api/discoveries", headers=who["outsider"]).json()["data"]
    assert outsider["items"] == []  # neither the book's spread nor its counterparty
    refused = client.get(
        "/api/discoveries", params={"function": "RISK_MANAGER"}, headers=who["test_trader"]
    )
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "function_not_held"
