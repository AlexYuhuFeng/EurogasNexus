"""Contract kinds through the governed write: MSPA, a cargo under it, a tender."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MarketEventRecord,
    UpstreamContractRevisionRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.db.repositories.route_cost import list_upstream_contracts
from eurogas_nexus.domain.contracts.examples import cargo_terms, mspa_terms, tender_terms

PATH = "/api/route-cost/upstream-contracts"
TOKEN = "test-public-api-token"
TODAY = date.today()


def _client(tmp_path, monkeypatch) -> tuple[TestClient, dict, str]:
    url = f"sqlite+pysqlite:///{(tmp_path / 'kinds.sqlite').as_posix()}"
    Base.metadata.create_all(create_engine(url, future=True))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(create_engine(url, future=True)) as session:
        row = create_identity_principal(
            session,
            name="lng-trader",
            display_name="LNG Trader",
            role="ANALYST",
            data_scopes=["*"],
        )
        _key, bearer = create_identity_api_key(
            session, row.principal_id, display_name="kinds", scopes=["*"]
        )
        session.commit()
    headers = {"X-Eurogas-Api-Key": TOKEN, "X-Eurogas-Identity": bearer}
    return TestClient(create_app(Settings(api_profile="release"))), headers, url


def _post(client, headers, **body):
    return client.post(PATH, json=body, headers=headers)


def test_master_cargo_and_tender_are_saved_with_derived_columns(tmp_path, monkeypatch) -> None:
    client, headers, url = _client(tmp_path, monkeypatch)
    master = _post(
        client,
        headers,
        contract_id="mspa-atlantic",
        contract_name="Atlantic MSPA",
        contract_kind="LNG_MSPA",
        kind_terms=mspa_terms(TODAY),
        unmodelled_terms="Price review: none. Heel: seller retains.",
    )
    assert master.status_code == 200, master.text
    data = master.json()["data"]
    assert data["contract_kind"] == "LNG_MSPA"
    assert data["contract_kind_reviewed"] is True
    assert data["delivery_quantity_mwh_per_day"] == 0.0
    assert data["unmodelled_terms"].startswith("Price review")
    assert data["boundary_issues"] == []

    cargo = _post(
        client,
        headers,
        contract_id="mspa-atlantic-cn07",
        contract_name="Atlantic CN-07",
        contract_kind="LNG_CARGO",
        kind_terms=cargo_terms(TODAY),
        master_contract_id="mspa-atlantic",
    )
    assert cargo.status_code == 200, cargo.text
    cargo_data = cargo.json()["data"]
    assert cargo_data["master_contract_id"] == "mspa-atlantic"
    assert cargo_data["delivery_point_name"] == "Gate terminal"
    assert cargo_data["headline"]["unit"] == "TBtu"

    tender = _post(
        client,
        headers,
        contract_id="tender-skarv-q1",
        contract_name="Skarv West tender Q1",
        contract_kind="UPSTREAM_TENDER",
        kind_terms=tender_terms(TODAY),
        # A base column sent for a typed kind is replaced by the derived one.
        delivery_quantity_mwh_per_day=1.0,
    )
    assert tender.status_code == 200, tender.text
    tender_data = tender.json()["data"]
    assert tender_data["delivery_quantity_mwh_per_day"] == pytest.approx(4982.208, abs=1e-3)
    assert tender_data["nomination_tolerance_pct"] == 20.0

    with Session(create_engine(url, future=True)) as session:
        revisions = {
            row.contract_id: row.schema_version
            for row in session.query(UpstreamContractRevisionRecord).all()
        }
        assert set(revisions.values()) == {"upstream-contract-revision/v5"}
        # The book's consumers see the cargo and the tender, never the master.
        book = {row["contract_id"] for row in list_upstream_contracts(session)}
        assert book == {"mspa-atlantic-cn07", "tender-skarv-q1"}
        # M5b: each governed write published its contract.changed event in its transaction.
        published = {
            row.subject_key: row.revision
            for row in session.query(MarketEventRecord)
            .filter(MarketEventRecord.event_type == "contract.changed")
            .all()
        }
        assert published == {
            "contract:mspa-atlantic": 1,
            "contract:mspa-atlantic-cn07": 1,
            "contract:tender-skarv-q1": 1,
        }

    listed = client.get(PATH, headers=headers).json()["data"]
    assert {row["contract_kind"] for row in listed} == {"LNG_MSPA", "LNG_CARGO", "UPSTREAM_TENDER"}

    # The master cannot be retired while the cargo under it is active.
    token = next(row for row in listed if row["contract_id"] == "mspa-atlantic")["edit_token"]
    retired = client.post(
        f"{PATH}/mspa-atlantic/retire",
        json={"reason": "terminated", "expected_edit_token": token},
        headers=headers,
    )
    assert retired.status_code == 409
    assert retired.json()["detail"]["code"] == "contract_has_active_confirmations"
    with Session(create_engine(url, future=True)) as session:
        # The refused retirement rolled back: no event for it.
        assert (
            session.query(MarketEventRecord)
            .filter(MarketEventRecord.subject_key == "contract:mspa-atlantic")
            .count()
            == 1
        )


def test_refusals_name_the_problem(tmp_path, monkeypatch) -> None:
    client, headers, _url = _client(tmp_path, monkeypatch)
    cases = [
        ({"contract_kind": "SPOT"}, "contract_kind_unknown"),
        ({"contract_kind": "HUB_TRADE"}, "contract_kind_not_authorable"),
        (
            {
                "contract_kind": "UPSTREAM_TENDER",
                "kind_terms": {**tender_terms(TODAY), "max_dcq_mwh_per_day": 1},
            },
            "contract_kind_terms_invalid",
        ),
        (
            {"contract_kind": "LNG_CARGO", "kind_terms": cargo_terms(TODAY)},
            "contract_master_required",
        ),
        (
            {
                "contract_kind": "LNG_CARGO",
                "kind_terms": cargo_terms(TODAY),
                "master_contract_id": "nope",
            },
            "contract_master_not_found",
        ),
        ({"contract_kind": "SUPPLY_GSA"}, "contract_field_missing"),
    ]
    for extra, code in cases:
        response = _post(client, headers, contract_id="x-1", contract_name="X", **extra)
        assert response.status_code == 422, (code, response.text)
        assert response.json()["detail"]["code"] == code


def test_older_client_body_still_saves_a_gsa(tmp_path, monkeypatch) -> None:
    client, headers, url = _client(tmp_path, monkeypatch)
    body = {
        "contract_id": "gsa-1",
        "contract_name": "GSA",
        "resource_type": "PIPELINE_IMPORT",
        "delivery_point_name": "TTF",
        "gas_year": "2026/27",
        "delivery_quantity_mwh_per_day": 100,
        "contract_price_gbp_mwh": 30,
        "settlement_frequency": "monthly",
        "upstream_payment_lag_days": 20,
        "screen_sale_cash_lag_days": 1,
        "delivery_tolerance_pct": 2,
        "nomination_tolerance_pct": 1,
        "annual_financing_rate_pct": 6,
    }
    response = client.post(PATH, json=body, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["contract_kind"] == "SUPPLY_GSA"
    assert data["contract_kind_reviewed"] is False
    with Session(create_engine(url, future=True)) as session:
        row = session.query(UpstreamContractRevisionRecord).one()
        assert row.schema_version == "upstream-contract-revision/v1"
        assert session.get(UpstreamResourceContractRecord, "gsa-1").kind_terms is None


def test_tender_and_des_cargo_reach_the_ladder_and_the_master_does_not(
    tmp_path, monkeypatch
) -> None:
    client, headers, _url = _client(tmp_path, monkeypatch)
    for body in (
        {
            "contract_id": "m",
            "contract_name": "M",
            "contract_kind": "LNG_MSPA",
            "kind_terms": mspa_terms(TODAY),
        },
        {
            "contract_id": "m-c1",
            "contract_name": "C1",
            "contract_kind": "LNG_CARGO",
            "kind_terms": cargo_terms(TODAY),
            "master_contract_id": "m",
        },
        {
            "contract_id": "t",
            "contract_name": "T",
            "contract_kind": "UPSTREAM_TENDER",
            "kind_terms": tender_terms(TODAY),
        },
    ):
        assert client.post(PATH, json=body, headers=headers).status_code == 200
    response = client.get("/api/portfolio/position-ladder?months=6", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["legs"]["physical"] == 2
    tender = tender_terms(TODAY)
    first_month = tender["period_start"][:7]
    nbp = next(r for r in data["rows"] if r["hub"] == "NBP" and r["month"] == first_month)
    assert nbp["physical_mwh"] > 0
    # The tender is priced at the NBP day-ahead index: its volume is on the ladder, its
    # flat-price exposure on the index (quant review 2026-11-26), so nothing to hedge.
    assert nbp["index_mwh"] == -nbp["physical_mwh"]
    assert nbp["price_exposure_mwh"] == 0
    assert nbp["hedge_ratio"] is None
    cargo = cargo_terms(TODAY)
    ttf = next(
        r for r in data["rows"] if r["hub"] == "TTF" and r["month"] == cargo["window_start"][:7]
    )
    assert round(ttf["physical_mwh"]) == round(3_600_000 * 0.29307107)
    warnings = " ".join(response.json()["meta"].get("warnings") or [])
    assert "price floats" in warnings


def test_a_contract_is_priced_for_a_month_from_its_formula_and_the_held_index(
    tmp_path, monkeypatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from eurogas_nexus.db.models import MarketObservationRecord

    client, headers, url = _client(tmp_path, monkeypatch)
    first = (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
    last = date.today().replace(day=1) - timedelta(days=1)
    terms = {
        **tender_terms(TODAY),
        "period_start": first.isoformat(),
        "period_end": last.isoformat(),
    }
    assert (
        _post(
            client,
            headers,
            contract_id="t-past",
            contract_name="T past",
            contract_kind="UPSTREAM_TENDER",
            kind_terms=terms,
        ).status_code
        == 200
    )
    with Session(create_engine(url, future=True)) as session:
        for offset in range(3):
            day = first + timedelta(days=offset)
            session.add(
                MarketObservationRecord(
                    observation_id=f"nbp-da-{offset}",
                    market_venue="ICE",
                    product="NBP day-ahead",
                    price=84.0 + offset,  # p/th, as NBP is quoted
                    unit="p/th",
                    currency="GBP",
                    period_start_utc=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    period_end_utc=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    observed_at_utc=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    source_system="ICE_ENDEX",
                    source_reference=f"nbp:{offset}",
                    freshness="end_of_day",
                    quality_score=0.9,
                    research_only=True,
                    metadata_json={"hub": "NBP", "tenor": "day-ahead", "settlement": True},
                )
            )
        session.commit()
    response = client.get(f"/api/contracts/t-past/price?month={first:%Y-%m}", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    result = data["result"]
    # Average of 84, 85, 86 p/th = 85.00 p/th, less the 0.40 p/th discount.
    assert result["unit"] == "GBp/th"
    assert result["value"] == pytest.approx(84.60, abs=1e-6)
    assert result["input_class"] == "settlement"
    assert result["inputs"][0]["observations"] == 3
    assert "NBP day-ahead" in result["words"]
    missing = client.get("/api/contracts/nope/price?month=2027-01", headers=headers)
    assert missing.status_code == 404
