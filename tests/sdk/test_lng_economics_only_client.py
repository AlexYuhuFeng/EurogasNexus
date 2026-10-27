"""SDK wire-contract tests for the LNG economics-only research client."""

from __future__ import annotations

from datetime import date

import httpx
import pytest
from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk.lng_economics_only import (
    LNG_ECONOMICS_ONLY_MODEL_VERSION,
    LngEconomicsOnlyCashValuation,
    LngEconomicsOnlyEnergyBalance,
    LngEconomicsOnlyRequest,
    LngEconomicsOnlyResult,
)
from eurogas_nexus_sdk.research import (
    calculate_lng_economics_only,
    compute_lng_economics_only,
)
from pydantic import ValidationError

VALUATION_DATE = date(2026, 9, 29)
SALE_DATE = date(2026, 11, 30)

PURCHASE_SOURCE = "synthetic-test-input:purchase-price-1"
SALE_SOURCE = "synthetic-test-input:sale-price-1"
COST_SOURCE = "synthetic-test-input:invoiced-cost-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-flat"
STAGE_1_SOURCE = "synthetic-test-input:stage-shipping-1"
STAGE_2_SOURCE = "synthetic-test-input:stage-regas-1"


def _request(**overrides) -> LngEconomicsOnlyRequest:
    fields = {
        "contract_id": "contract-synthetic-lng-1",
        "cargo_id": "cargo-synthetic-1",
        "terminal_id": "terminal-synthetic-regas-1",
        "resource_id": "resource-synthetic-supply-1",
        "valuation_date": VALUATION_DATE,
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
        "purchase_payment_date": VALUATION_DATE,
        "sale_payment_date": SALE_DATE,
        "downstream_costs": [
            {
                "cost_id": "regas-1",
                "category": "regas",
                "amount_eur": "150",
                "payment_date": VALUATION_DATE,
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
                "payment_date": VALUATION_DATE,
                "factor": "1",
                "curve_reference": DF_CURVE,
                "source_reference": DF_SOURCE,
                "as_of": VALUATION_DATE,
            },
            {
                "payment_date": SALE_DATE,
                "factor": "0.975",
                "curve_reference": DF_CURVE,
                "source_reference": DF_SOURCE,
                "as_of": VALUATION_DATE,
            },
        ],
    }
    fields.update(overrides)
    return LngEconomicsOnlyRequest(**fields)


def _cash_leg(
    leg_id: str,
    category: str,
    signed_amount: str,
    cash_amount: str,
    present_value: str,
    payment_date: str,
    *,
    discount_factor: str = "1",
    source_reference: str,
) -> dict:
    return {
        "leg_id": leg_id,
        "category": category,
        "payment_date": payment_date,
        "currency": "EUR",
        "signed_amount": signed_amount,
        "cash_amount_reporting_ccy": cash_amount,
        "present_value_reporting_ccy": present_value,
        "discount_factor": discount_factor,
        "discount_curve_reference": DF_CURVE,
        "discount_source_reference": DF_SOURCE,
        "discount_as_of": "2026-09-29",
        "source_reference": source_reference,
        "fx_rate_reporting_per_leg": "1",
        "fx_source_reference": None,
        "fx_as_of": None,
        "description": "",
    }


def _result_payload() -> dict:
    return {
        "research_only": True,
        "human_review_required": True,
        "model_version": LNG_ECONOMICS_ONLY_MODEL_VERSION,
        "action": "compute_cash_flow",
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
        "total_consumed_energy_mwh": "7",
        "physical_loss_energy_mwh": "3",
        "total_reduction_energy_mwh": "10",
        "purchase_basis": "DES",
        "purchase_included_cost_items": [],
        "cost_scope_statement": (
            "Synthetic scope: the DES purchase price covers the cargo only; regas"
            " is invoiced separately below."
        ),
        "purchase_unit_price_eur_per_mwh": "20",
        "sale_unit_price_eur_per_mwh": "30",
        "unit_netback_eur_per_purchased_mwh": "25.5000",
        "sale_basis_eur_per_delivered_mwh": "30.0000",
        "purchase_outlay_eur": "2000.0000",
        "sale_proceeds_eur": "2700.0000",
        "total_downstream_costs_eur": "150.0000",
        "cargo_margin_eur": "550.0000",
        "margin_reconciliation_gap_eur": "0.0000",
        "margin_reconciliation_tolerance_eur": "0.0052",
        "net_present_value_eur": "482.5000",
        "total_undiscounted_cash_eur": "550.0000",
        "cash_valuation": {
            "model_version": "lng-cargo-cash-valuation/v1",
            "contract_id": "contract-synthetic-lng-1",
            "cargo_id": "cargo-synthetic-1",
            "terminal_id": "terminal-synthetic-regas-1",
            "resource_id": "resource-synthetic-supply-1",
            "valuation_date": "2026-09-29",
            "reporting_currency": "EUR",
            "leg_valuations": [
                _cash_leg(
                    "cargo-purchase",
                    "cargo_purchase",
                    "-2000.0000",
                    "-2000.0000",
                    "-2000.0000",
                    "2026-09-29",
                    source_reference=PURCHASE_SOURCE,
                ),
                _cash_leg(
                    "cargo-sale",
                    "cargo_sale",
                    "2700.0000",
                    "2700.0000",
                    "2632.5000",
                    "2026-11-30",
                    discount_factor="0.975",
                    source_reference=SALE_SOURCE,
                ),
                _cash_leg(
                    "downstream-cost:regas-1",
                    "regas",
                    "-150.0000",
                    "-150.0000",
                    "-150.0000",
                    "2026-09-29",
                    source_reference=COST_SOURCE,
                ),
            ],
            "total_undiscounted_cash_reporting_ccy": "550.0000",
            "net_present_value_reporting_ccy": "482.5000",
            "assumptions": ["synthetic cash assumption"],
            "warnings": [
                "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
                "NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN",
            ],
            "source_references": sorted(
                {PURCHASE_SOURCE, SALE_SOURCE, COST_SOURCE, DF_SOURCE}
            ),
            "lineage": [
                "lng-cargo-cash-valuation",
                "lng-cargo-cash-valuation/v1",
            ],
            "research_only": True,
            "human_review_required": True,
        },
        "energy_balance": {
            "model_version": "lng-energy-balance/v1",
            "purchased_energy_mwh": "100",
            "delivered_energy_mwh": "90",
            "energy_basis_reference": "synthetic-basis:gcV-energy-mwh",
            "energy_unit": "MWh",
            "total_consumed_energy_mwh": "7",
            "physical_loss_energy_mwh": "3",
            "total_reduction_energy_mwh": "10",
            "stage_count": 2,
            "stages": [
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
            "warnings": [
                "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
                "EXPLICIT_ENERGY_STAGES_ONLY_NO_VOLUME_OR_FX_CONVERSION",
                "CONSUMED_ENERGY_AND_PHYSICAL_LOSS_DISCLOSED_SEPARATELY_NOT_MONETIZED",
            ],
            "source_references": sorted({STAGE_1_SOURCE, STAGE_2_SOURCE}),
            "research_only": True,
            "human_review_required": True,
        },
        "physical_readiness": "NOT_ASSESSED",
        "readiness_assessed": False,
        "assumptions": ["synthetic economics assumption"],
        "warnings": [
            "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
            "NO_TRADE_EXECUTION_NOMINATION_OR_SETTLEMENT",
            "EUR_ONLY_NO_FX_CONVERSION_PERFORMED",
            "PHYSICAL_READINESS_NOT_ASSESSED",
            "IN_KIND_ENERGY_CONSUMPTION_AND_PHYSICAL_LOSS_ARE_NOT_MONETIZED",
        ],
        "source_references": sorted(
            {
                PURCHASE_SOURCE,
                SALE_SOURCE,
                COST_SOURCE,
                DF_SOURCE,
                STAGE_1_SOURCE,
                STAGE_2_SOURCE,
            }
        ),
        "lineage": [
            "lng-economics-only",
            "lng-economics-only/v1",
            "lng-energy-balance",
            "lng-energy-balance/v1",
            "lng-cargo-cash-valuation/v1",
        ],
    }


def _install_mock_transport(monkeypatch, handler) -> dict:
    """Route the SDK's real ``_http.post`` through an httpx MockTransport."""

    captured: dict = {}
    transport = httpx.MockTransport(handler)

    def fake_post(
        url: str,
        *,
        json=None,
        timeout: float = 15.0,
        headers=None,
        **kwargs,
    ):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["headers"] = dict(headers or {})
        request = httpx.Request("POST", url, json=json, headers=headers or {})
        return transport.handle_request(request)

    monkeypatch.setattr(_http.httpx, "post", fake_post)
    return captured


def test_client_posts_exact_endpoint_body_and_identity(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "test-public-token")
    monkeypatch.setenv("EUROGAS_NEXUS_IDENTITY_BEARER", "identity-test-bearer")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": _result_payload(),
                "meta": {
                    "research_only": True,
                    "human_review_required": True,
                    "decision_context": "SANDBOX_SCENARIO",
                    "references_verified": False,
                    "physical_readiness": "NOT_ASSESSED",
                    "readiness_assessed": False,
                    "customer_approval": False,
                },
            },
            request=request,
        )

    captured = _install_mock_transport(monkeypatch, handler)

    result = calculate_lng_economics_only("http://testserver", request=_request())

    assert captured["url"] == "http://testserver/api/research/lng-economics-only"
    assert captured["headers"]["Authorization"] == "Bearer test-public-token"
    assert (
        captured["headers"]["X-Eurogas-Identity"] == "identity-test-bearer"
    )
    body = captured["json"]
    assert set(body) == {
        "contract_id",
        "cargo_id",
        "terminal_id",
        "resource_id",
        "valuation_date",
        "reporting_currency",
        "energy_basis_reference",
        "energy_unit",
        "purchased_energy_mwh",
        "delivered_energy_mwh",
        "purchase_unit_price_eur_per_mwh",
        "sale_unit_price_eur_per_mwh",
        "purchase_price_source_reference",
        "sale_price_source_reference",
        "purchase_basis",
        "purchase_included_cost_items",
        "cost_scope_statement",
        "purchase_payment_date",
        "sale_payment_date",
        "downstream_costs",
        "energy_stages",
        "discount_factors",
        "model_version",
    }
    assert body["valuation_date"] == "2026-09-29"
    assert body["sale_payment_date"] == "2026-11-30"
    assert body["purchased_energy_mwh"] == "100"
    assert body["purchase_unit_price_eur_per_mwh"] == "20"
    assert body["purchase_basis"] == "DES"
    assert body["downstream_costs"][0]["payment_date"] == "2026-09-29"
    assert body["downstream_costs"][0]["amount_eur"] == "150"
    assert body["downstream_costs"][0]["charge_basis"] == "invoiced_cash"
    assert body["energy_stages"][1]["input_energy_mwh"] == "96"
    assert body["discount_factors"][1]["factor"] == "0.975"
    assert body["model_version"] == LNG_ECONOMICS_ONLY_MODEL_VERSION

    assert isinstance(result, LngEconomicsOnlyResult)
    assert isinstance(result.cash_valuation, LngEconomicsOnlyCashValuation)
    assert isinstance(result.energy_balance, LngEconomicsOnlyEnergyBalance)
    assert result.model_version == "lng-economics-only/v1"
    assert result.action == "compute_cash_flow"
    assert result.valuation_date == VALUATION_DATE
    assert result.purchase_outlay_eur == "2000.0000"
    assert result.sale_proceeds_eur == "2700.0000"
    assert result.total_downstream_costs_eur == "150.0000"
    assert result.cargo_margin_eur == "550.0000"
    assert result.net_present_value_eur == "482.5000"
    assert result.total_consumed_energy_mwh == "7"
    assert result.physical_loss_energy_mwh == "3"
    assert result.total_reduction_energy_mwh == "10"
    assert result.physical_readiness == "NOT_ASSESSED"
    assert result.readiness_assessed is False
    assert result.research_only is True
    assert result.human_review_required is True
    assert isinstance(result.cargo_margin_eur, str)
    assert isinstance(
        result.cash_valuation.leg_valuations[1].present_value_reporting_ccy, str
    )
    assert (
        result.cash_valuation.leg_valuations[1].present_value_reporting_ccy
        == "2632.5000"
    )
    assert result.cash_valuation.leg_valuations[1].payment_date == SALE_DATE
    assert result.cash_valuation.leg_valuations[1].fx_as_of is None
    assert result.energy_balance.stage_count == 2
    assert result.energy_balance.stages[1].kind == "regasification"
    assert result.energy_balance.stages[1].source_references == [STAGE_2_SOURCE]


def test_keyword_fields_build_the_same_request(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": _result_payload(), "meta": {}},
            request=request,
        )

    captured = _install_mock_transport(monkeypatch, handler)
    fields = _request().model_dump(mode="python")

    result = compute_lng_economics_only("http://testserver", **fields)

    assert captured["json"] == _request().model_dump(mode="json")
    assert result.cargo_margin_eur == "550.0000"


def test_client_propagates_the_exact_domain_refusal(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": {
                    "code": "lng_economics_only_refused",
                    "codes": ["IN_KIND_COST_NOT_A_CASH_CHARGE"],
                    "research_only": True,
                    "human_review_required": True,
                }
            },
            request=request,
        )

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError) as info:
        calculate_lng_economics_only("http://testserver", request=_request())
    assert info.value.response.status_code == 422
    detail = info.value.response.json()["detail"]
    assert detail["code"] == "lng_economics_only_refused"
    assert detail["codes"] == ["IN_KIND_COST_NOT_A_CASH_CHARGE"]


def test_typed_request_refuses_numeric_dates_and_authority_fields() -> None:
    with pytest.raises(ValidationError):
        _request(purchased_energy_mwh=100)

    with pytest.raises(ValidationError):
        _request(valuation_date="2026-02-30")

    with pytest.raises(ValidationError):
        _request(physical_readiness="READY")

    with pytest.raises(ValidationError):
        _request(decision_context="RUNTIME_DECISION")

    with pytest.raises(ValidationError):
        _request(
            downstream_costs=[
                {
                    "cost_id": "regas-1",
                    "category": "regas",
                    "amount_eur": 150,
                    "payment_date": VALUATION_DATE,
                    "source_reference": COST_SOURCE,
                    "charge_basis": "invoiced_cash",
                }
            ]
        )


def test_both_request_and_keyword_fields_are_refused() -> None:
    with pytest.raises(TypeError):
        calculate_lng_economics_only(
            "http://testserver",
            request=_request(),
            valuation_date=VALUATION_DATE,
        )
