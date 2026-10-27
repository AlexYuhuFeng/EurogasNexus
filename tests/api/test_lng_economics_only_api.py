"""Focused tests for ``POST /api/research/lng-economics-only``.

The endpoint is the sandbox-only HTTP adaptation of the completed economics-only
composition and its explicit ordered energy balance. Every amount is an exact
decimal string in and out, the domain composition is the single arithmetic
authority, and the regas readiness assessor is never called. All inputs are
explicitly labelled synthetic test data; nothing here is a market fact, a booked
right or a delivery-feasibility assessment.

The synthetic golden is purchased 100 MWh at EUR20/MWh, delivered 90 MWh sold at
EUR30/MWh and one separately invoiced EUR150 cost, so cargo margin and
undiscounted cash are EUR550. The sale date carries the explicit factor 0.975,
giving NPV EUR482.50. The two explicit stages are 100 -> 96 (consumed 3, loss 1)
and 96 -> 90 (consumed 4, loss 2): total consumed 7 MWh, physical loss 3 MWh and
total reduction 10 MWh.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.ontology.actions import ActionKind
from eurogas_nexus.domain.research import lng_cargo_economics as economics_module
from eurogas_nexus.security.permissions import (
    Permission,
    permission_for_path,
    serves_commercial_data,
)

PUBLIC_TOKEN = "test-public-api-token"
PATH = "/api/research/lng-economics-only"

PURCHASE_SOURCE = "synthetic-test-input:purchase-price-1"
SALE_SOURCE = "synthetic-test-input:sale-price-1"
COST_SOURCE = "synthetic-test-input:invoiced-cost-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-flat"
STAGE_1_SOURCE = "synthetic-test-input:stage-shipping-1"
STAGE_2_SOURCE = "synthetic-test-input:stage-regas-1"

_ECONOMICS_ONLY_WARNINGS = [
    "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
    "NO_TRADE_EXECUTION_NOMINATION_OR_SETTLEMENT",
    "EUR_ONLY_NO_FX_CONVERSION_PERFORMED",
    "PHYSICAL_READINESS_NOT_ASSESSED",
    (
        "PROFITABLE_ECONOMICS_IS_NOT_DELIVERY_FEASIBILITY_TERMINAL_SLOT_STORAGE_"
        "RIGHTS_OR_NOMINATION_AUTHORITY"
    ),
    "IN_KIND_ENERGY_CONSUMPTION_AND_PHYSICAL_LOSS_ARE_NOT_MONETIZED",
    (
        "TOTAL_REDUCTION_DISCLOSED_AS_CONSUMED_PLUS_PHYSICAL_LOSS_NOT_"
        "ADDITIONALLY_MONETIZED"
    ),
]


def _client() -> TestClient:
    return TestClient(create_app())


def _body(**overrides) -> dict:
    """Build the explicit synthetic golden economics-only request."""

    body = {
        "contract_id": "contract-synthetic-lng-1",
        "cargo_id": "cargo-synthetic-1",
        "terminal_id": "terminal-synthetic-regas-1",
        "resource_id": "resource-synthetic-supply-1",
        "valuation_date": "2026-09-29",
        "reporting_currency": "EUR",
        "energy_basis_reference": "synthetic-basis:gcV-energy-mwh",
        "energy_unit": "MWh",
        "purchased_energy_mwh": "100",
        "delivered_energy_mwh": "90",
        "purchase_unit_price_eur_per_mwh": "20",
        "sale_unit_price_eur_per_mwh": "30",
        "purchase_price_source_reference": PURCHASE_SOURCE,
        "sale_price_source_reference": SALE_SOURCE,
        "purchase_basis": "DES",
        "purchase_included_cost_items": [],
        "cost_scope_statement": (
            "Synthetic scope: the DES purchase price covers the cargo only; regas"
            " is invoiced separately below."
        ),
        "purchase_payment_date": "2026-09-29",
        "sale_payment_date": "2026-11-30",
        "downstream_costs": [
            {
                "cost_id": "regas-1",
                "category": "regas",
                "amount_eur": "150",
                "payment_date": "2026-09-29",
                "source_reference": COST_SOURCE,
                "charge_basis": "invoiced_cash",
            }
        ],
        "energy_stages": [
            {
                "stage_id": "shipping-1",
                "kind": "shipping",
                "input_energy_mwh": "100",
                "output_energy_mwh": "96",
                "consumed_energy_mwh": "3",
                "physical_loss_energy_mwh": "1",
                "source_references": [STAGE_1_SOURCE],
            },
            {
                "stage_id": "regas-1",
                "kind": "regasification",
                "input_energy_mwh": "96",
                "output_energy_mwh": "90",
                "consumed_energy_mwh": "4",
                "physical_loss_energy_mwh": "2",
                "source_references": [STAGE_2_SOURCE],
            },
        ],
        "discount_factors": [
            {
                "payment_date": "2026-09-29",
                "factor": "1",
                "curve_reference": DF_CURVE,
                "source_reference": DF_SOURCE,
                "as_of": "2026-09-29",
            },
            {
                "payment_date": "2026-11-30",
                "factor": "0.975",
                "curve_reference": DF_CURVE,
                "source_reference": DF_SOURCE,
                "as_of": "2026-09-29",
            },
        ],
    }
    body.update(overrides)
    return body


def _assert_no_floats(value: object) -> None:
    """Fail when any binary float reached the payload (no float encoder allowed)."""

    if isinstance(value, float):
        raise AssertionError(f"binary float leaked into the payload: {value!r}")
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_floats(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_floats(item)


def _refused(response) -> dict:
    """Assert a typed 422 refusal with no partial result, and return its detail."""

    assert response.status_code == 422
    payload = response.json()
    assert "data" not in payload
    detail = payload["detail"]
    assert isinstance(detail, dict)
    assert detail["research_only"] is True
    assert detail["human_review_required"] is True
    return detail


def test_golden_case_returns_exact_mapped_economics_and_energy() -> None:
    response = _client().post(PATH, json=_body())

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["model_version"] == "lng-economics-only/v1"
    assert data["action"] == ActionKind.COMPUTE_CASH_FLOW.value
    assert data["contract_id"] == "contract-synthetic-lng-1"
    assert data["cargo_id"] == "cargo-synthetic-1"
    assert data["terminal_id"] == "terminal-synthetic-regas-1"
    assert data["resource_id"] == "resource-synthetic-supply-1"
    assert data["valuation_date"] == "2026-09-29"
    assert data["reporting_currency"] == "EUR"
    assert data["energy_basis_reference"] == "synthetic-basis:gcV-energy-mwh"
    assert data["energy_unit"] == "MWh"
    assert data["purchase_basis"] == "DES"
    assert data["purchase_included_cost_items"] == []

    assert data["purchased_energy_mwh"] == "100"
    assert data["delivered_energy_mwh"] == "90"
    assert data["purchase_unit_price_eur_per_mwh"] == "20"
    assert data["sale_unit_price_eur_per_mwh"] == "30"
    # Hand calculation: 100*20 = 2000; 90*30 = 2700; 2700-150-2000 = 550.
    assert data["purchase_outlay_eur"] == "2000.0000"
    assert data["sale_proceeds_eur"] == "2700.0000"
    assert data["total_downstream_costs_eur"] == "150.0000"
    assert data["cargo_margin_eur"] == "550.0000"
    assert data["total_undiscounted_cash_eur"] == "550.0000"
    assert data["unit_netback_eur_per_purchased_mwh"] == "25.5000"
    assert data["sale_basis_eur_per_delivered_mwh"] == "30.0000"
    assert data["margin_reconciliation_gap_eur"] == "0.0000"
    # 2700 * 0.975 - 2000 - 150 = 482.50.
    assert data["net_present_value_eur"] == "482.5000"

    assert data["total_consumed_energy_mwh"] == "7"
    assert data["physical_loss_energy_mwh"] == "3"
    assert data["total_reduction_energy_mwh"] == "10"

    balance = data["energy_balance"]
    assert balance["model_version"] == "lng-energy-balance/v1"
    assert balance["stage_count"] == 2
    assert balance["total_consumed_energy_mwh"] == "7"
    assert balance["physical_loss_energy_mwh"] == "3"
    assert balance["total_reduction_energy_mwh"] == "10"
    assert [stage["stage_id"] for stage in balance["stages"]] == [
        "shipping-1",
        "regas-1",
    ]
    assert [stage["kind"] for stage in balance["stages"]] == [
        "shipping",
        "regasification",
    ]
    assert balance["stages"][0]["input_energy_mwh"] == "100"
    assert balance["stages"][0]["output_energy_mwh"] == "96"
    assert balance["stages"][0]["consumed_energy_mwh"] == "3"
    assert balance["stages"][0]["physical_loss_energy_mwh"] == "1"
    assert balance["stages"][1]["source_references"] == [STAGE_2_SOURCE]

    cash = data["cash_valuation"]
    assert cash["model_version"] == "lng-cargo-cash-valuation/v1"
    assert cash["total_undiscounted_cash_reporting_ccy"] == "550.0000"
    assert cash["net_present_value_reporting_ccy"] == "482.5000"
    legs = {leg["leg_id"]: leg for leg in cash["leg_valuations"]}
    assert set(legs) == {
        "cargo-purchase",
        "cargo-sale",
        "downstream-cost:regas-1",
    }
    assert legs["cargo-purchase"]["signed_amount"] == "-2000.0000"
    assert legs["cargo-purchase"]["present_value_reporting_ccy"] == "-2000.0000"
    assert legs["cargo-sale"]["signed_amount"] == "2700.0000"
    assert legs["cargo-sale"]["discount_factor"] == "0.975"
    assert legs["cargo-sale"]["present_value_reporting_ccy"] == "2632.5000"
    # The shared cash primitive preserves the explicit leg coefficient;
    # composed money totals are separately quantized to four places.
    assert legs["downstream-cost:regas-1"]["signed_amount"] == "-150"
    assert legs["downstream-cost:regas-1"]["category"] == "regas"

    assert data["physical_readiness"] == "NOT_ASSESSED"
    assert data["readiness_assessed"] is False
    assert "readiness" not in data
    assert data["research_only"] is True
    assert data["human_review_required"] is True
    assert data["warnings"] == _ECONOMICS_ONLY_WARNINGS
    assert all("READINESS_WARNING" not in warning for warning in data["warnings"])
    assert data["lineage"] == [
        "lng-economics-only",
        "lng-economics-only/v1",
        "lng-energy-balance",
        "lng-energy-balance/v1",
        "lng-cargo-cash-valuation/v1",
    ]
    assert data["source_references"] == sorted(
        {
            PURCHASE_SOURCE,
            SALE_SOURCE,
            COST_SOURCE,
            DF_SOURCE,
            STAGE_1_SOURCE,
            STAGE_2_SOURCE,
        }
    )

    meta = payload["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
    assert meta["decision_context"] == "SANDBOX_SCENARIO"
    assert meta["caller_supplied"] is True
    assert meta["references_verified"] is False
    assert meta["physical_readiness"] == "NOT_ASSESSED"
    assert meta["readiness_assessed"] is False
    assert meta["customer_approval"] is False
    assert meta["source_references"] == data["source_references"]
    assert meta["warnings"] == data["warnings"]


def test_readiness_assessor_is_never_called_and_output_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode(*args: object, **kwargs: object) -> object:
        raise AssertionError("economics-only path must not assess physical readiness")

    monkeypatch.setattr(economics_module, "assess_lng_regas_readiness", _explode)

    client = _client()
    first = client.post(PATH, json=_body())
    second = client.post(PATH, json=_body())

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["data"]["cargo_margin_eur"] == "550.0000"


def test_zero_explicit_downstream_costs_are_valid_and_synthetic() -> None:
    response = _client().post(PATH, json=_body(downstream_costs=[]))

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["total_downstream_costs_eur"] == "0.0000"
    # 2700 - 0 - 2000 = 700; 2700 * 0.975 - 2000 = 632.50.
    assert data["cargo_margin_eur"] == "700.0000"
    assert data["net_present_value_eur"] == "632.5000"
    assert set(
        leg["leg_id"] for leg in data["cash_valuation"]["leg_valuations"]
    ) == {"cargo-purchase", "cargo-sale"}


def test_signed_prices_are_preserved_when_the_domain_allows_them() -> None:
    response = _client().post(
        PATH, json=_body(sale_unit_price_eur_per_mwh="-30")
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["sale_unit_price_eur_per_mwh"] == "-30"
    assert data["sale_proceeds_eur"] == "-2700.0000"
    assert data["cargo_margin_eur"] == "-4850.0000"
    assert data["net_present_value_eur"] == "-4782.5000"
    assert "NEGATIVE_CARGO_MARGIN" in data["warnings"]
    assert "NEGATIVE_UNIT_NETBACK" in data["warnings"]
    assert "NEGATIVE_NET_PRESENT_VALUE" in data["warnings"]


def test_duplicate_in_kind_and_included_cash_double_charges_are_refused() -> None:
    duplicate = _body()
    duplicate["downstream_costs"].append(deepcopy(duplicate["downstream_costs"][0]))
    duplicate_detail = _refused(_client().post(PATH, json=duplicate))
    assert duplicate_detail["code"] == "lng_economics_only_refused"
    assert "DUPLICATE_COST_ID" in duplicate_detail["codes"]

    in_kind = _body()
    in_kind["downstream_costs"][0]["charge_basis"] = "in_kind"
    in_kind_detail = _refused(_client().post(PATH, json=in_kind))
    assert in_kind_detail["codes"] == ["IN_KIND_COST_NOT_A_CASH_CHARGE"]

    included = _body(purchase_included_cost_items=["regas"])
    included_detail = _refused(_client().post(PATH, json=included))
    assert included_detail["codes"] == [
        "DOWNSTREAM_COST_DOUBLES_INCLUDED_PURCHASE_COST"
    ]


def test_malformed_energy_chain_is_refused_with_domain_codes() -> None:
    broken = _body()
    broken["energy_stages"][1]["input_energy_mwh"] = "95"
    detail = _refused(_client().post(PATH, json=broken))
    assert detail["code"] == "lng_economics_only_refused"
    assert "STAGE_CONSERVATION_FAILED" in detail["codes"]

    empty = _body(energy_stages=[])
    empty_detail = _refused(_client().post(PATH, json=empty))
    assert empty_detail["codes"] == ["STAGE_COUNT_INVALID"]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda body: body.update({"energy_unit": "MMBtu"}),
            "ENERGY_UNIT_UNSUPPORTED",
        ),
        (
            lambda body: body["downstream_costs"][0].update(
                {"category": "not_a_category"}
            ),
            "COST_CATEGORY_INVALID",
        ),
        (
            lambda body: body["energy_stages"][0].update({"kind": "not_a_kind"}),
            "STAGE_KIND_INVALID",
        ),
        (
            lambda body: body.update({"purchase_basis": "CIF"}),
            "PURCHASE_BASIS_INVALID",
        ),
    ],
)
def test_malformed_units_vocabulary_and_basis_are_refused(
    mutate, expected_code: str
) -> None:
    body = _body()
    mutate(body)

    detail = _refused(_client().post(PATH, json=body))
    assert detail["code"] == "lng_economics_only_refused"
    assert expected_code in detail["codes"]
    assert all(item["code"] for item in detail["violations"])


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e3", " 20"])
def test_nonfinite_and_nonplain_decimal_strings_are_refused(value: str) -> None:
    detail = _refused(
        _client().post(PATH, json=_body(purchased_energy_mwh=value))
    )
    assert detail["code"] == "lng_economics_only_input_invalid"
    assert "DECIMAL_STRING_INVALID" in detail["codes"]


def test_naive_datetime_text_is_refused_as_a_calendar_date() -> None:
    detail = _refused(
        _client().post(PATH, json=_body(valuation_date="2026-09-29T00:00:00"))
    )
    assert detail["code"] == "lng_economics_only_input_invalid"
    assert "DATE_STRING_INVALID" in detail["codes"]


def test_json_numbers_are_never_accepted_as_decimal_strings() -> None:
    response = _client().post(PATH, json=_body(purchased_energy_mwh=100))

    assert response.status_code == 422
    assert "data" not in response.json()
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("type") == "string_type" for item in detail)


def test_runtime_decision_claim_is_refused_by_the_sandbox_gate() -> None:
    body = _body()
    body["decision_context"] = "RUNTIME_DECISION"
    response = _client().post(PATH, json=body)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "runtime_decision_not_supported"
    assert detail["research_only"] is True


def test_unknown_readiness_and_authority_claims_are_refused() -> None:
    body = _body()
    body.update(
        {
            "physical_readiness": "READY",
            "readiness_assessed": True,
            "work_mode": "TRADING_ANALYSIS",
            "persona": "TRADER",
        }
    )
    response = _client().post(PATH, json=body)

    assert response.status_code == 422
    assert "data" not in response.json()
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("type") == "extra_forbidden" for item in detail)


def test_route_is_covered_by_the_existing_permission_and_commercial_gates() -> None:
    assert permission_for_path(PATH, "POST") is Permission.GOVERNED
    assert serves_commercial_data(PATH) is True


def test_anonymous_caller_is_denied_before_any_computation() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(PATH, json=_body())

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "public_api_token_missing"


def _prepare_identity_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "lng-economics-only.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return database_url


def _bearer(session: Session, *, name: str, role: str, scopes: list[str]) -> str:
    row = create_identity_principal(
        session,
        name=name,
        display_name=name.title(),
        role=role,
        data_scopes=scopes,
    )
    _key, bearer = create_identity_api_key(
        session, row.principal_id, display_name="lng-economics-only-test"
    )
    return bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_disallowed_roles_are_denied_and_a_persona_claim_cannot_grant(
    tmp_path, monkeypatch
) -> None:
    database_url = _prepare_identity_db(tmp_path, monkeypatch)
    with Session(create_engine(database_url, future=True)) as session:
        viewer = _bearer(session, name="lng-viewer", role="VIEWER", scopes=["ENTSOG"])
        admin = _bearer(session, name="lng-admin", role="ADMIN", scopes=[])
        analyst = _bearer(
            session, name="lng-analyst", role="ANALYST", scopes=["ENTSOG"]
        )
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    claim = _body()
    claim.update({"work_mode": "TRADING_ANALYSIS", "persona": "TRADER"})
    viewer_response = client.post(PATH, json=claim, headers=_headers(viewer))
    assert viewer_response.status_code == 403
    assert viewer_response.json()["detail"]["error"] == "identity_role_forbidden"

    admin_response = client.post(PATH, json=claim, headers=_headers(admin))
    assert admin_response.status_code == 403
    assert (
        admin_response.json()["detail"]["error"]
        == "commercial_access_not_granted"
    )

    analyst_response = client.post(PATH, json=_body(), headers=_headers(analyst))
    assert analyst_response.status_code == 200
    assert (
        analyst_response.json()["data"]["cargo_margin_eur"] == "550.0000"
    )
