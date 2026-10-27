"""SDK wire-contract tests for the capacity-billing research client."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk.capacity_billing import (
    CapacityBillingRequest,
    CapacityBillingResult,
)
from eurogas_nexus_sdk.research import calculate_capacity_billing
from pydantic import ValidationError

START = datetime(2026, 1, 1, tzinfo=UTC)
END_23 = datetime(2026, 1, 1, 23, 0, tzinfo=UTC)
REFERENCES = [
    "synthetic-test-input:booking-1",
    "synthetic-test-input:tariff-1",
]


def _request(**overrides) -> CapacityBillingRequest:
    fields = {
        "scenario_id": "scenario-synthetic-1",
        "tariff_id": "tariff-synthetic-1",
        "tariff_rate": "2",
        "currency": "EUR",
        "tariff_unit": "EUR/(MWh/h)/h",
        "booked_capacity_mwh_per_h": "10",
        "delivered_energy_mwh": "115",
        "billed_capacity_energy_mwh": "230",
        "billing_start": START,
        "billing_end": END_23,
        "source_references": list(REFERENCES),
    }
    fields.update(overrides)
    return CapacityBillingRequest(**fields)


def _result_payload() -> dict:
    return {
        "research_only": True,
        "human_review_required": True,
        "model_version": "capacity-billing/v1",
        "scenario_id": "scenario-synthetic-1",
        "tariff_id": "tariff-synthetic-1",
        "currency": "EUR",
        "tariff_unit": "EUR/(MWh/h)/h",
        "tariff_rate": "2",
        "booked_capacity_mwh_per_h": "10",
        "billed_capacity_energy_mwh": "230",
        "delivered_energy_mwh": "115",
        "billing_start": "2026-01-01T00:00:00+00:00",
        "billing_end": "2026-01-01T23:00:00+00:00",
        "duration_microseconds": 82_800_000_000_000,
        "duration_hours": "23",
        "total_cost": "460.0000",
        "cost_per_delivered_mwh": "4.0000",
        "basis": {
            "tariff_rate": "2",
            "tariff_unit": "EUR/(MWh/h)/h",
            "booked_capacity_mwh_per_h": "10",
            "billed_capacity_energy_mwh": "230",
            "delivered_energy_mwh": "115",
            "billing_start_utc": "2026-01-01T00:00:00+00:00",
            "billing_end_utc": "2026-01-01T23:00:00+00:00",
            "duration_microseconds": 82_800_000_000_000,
        },
        "provenance": sorted(REFERENCES),
        "source_references": sorted(REFERENCES),
        "assumptions": ["explicit synthetic basis"],
        "warnings": [
            "RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT",
            "CAPACITY_BILLING_DOES_NOT_ESTABLISH_BOOKED_RIGHTS_OR_DELIVERABILITY",
        ],
        "lineage": ["capacity-billing", "capacity-billing/v1"],
        "physical_readiness": "NOT_ASSESSED",
    }


def _install_mock_transport(monkeypatch, handler) -> dict:
    """Route the SDK's ``_http.post`` through an httpx MockTransport."""

    captured: dict = {}
    transport = httpx.MockTransport(handler)

    def fake_post(url: str, *, json=None, timeout: float = 15, **kwargs):
        request = httpx.Request("POST", url, json=json)
        response = transport.handle_request(request)
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr(_http, "post", fake_post)
    return captured


def test_capacity_billing_client_posts_exactly_the_research_endpoint(monkeypatch) -> None:
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
                    "customer_approval": False,
                },
            },
            request=request,
        )

    captured = _install_mock_transport(monkeypatch, handler)

    result = calculate_capacity_billing("http://testserver", request=_request())

    assert captured["url"] == "http://testserver/api/research/capacity-billing"
    body = captured["json"]
    assert body["scenario_id"] == "scenario-synthetic-1"
    assert body["tariff_rate"] == "2"
    assert body["booked_capacity_mwh_per_h"] == "10"
    assert body["billed_capacity_energy_mwh"] == "230"
    assert body["delivered_energy_mwh"] == "115"
    assert body["billing_start"].startswith("2026-01-01T00:00:00")
    assert body["billing_end"].startswith("2026-01-01T23:00:00")
    assert isinstance(body["source_references"], list)

    assert isinstance(result, CapacityBillingResult)
    assert result.model_version == "capacity-billing/v1"
    assert result.total_cost == "460.0000"
    assert result.cost_per_delivered_mwh == "4.0000"
    assert result.duration_microseconds == 82_800_000_000_000
    assert result.basis.duration_microseconds == 82_800_000_000_000
    assert result.basis.tariff_rate == "2"
    assert result.basis.billing_start_utc == START
    assert result.basis.billing_end_utc == END_23
    assert result.billing_start == START
    assert result.billing_end == END_23
    assert result.physical_readiness == "NOT_ASSESSED"
    assert result.research_only is True
    assert result.human_review_required is True


def test_capacity_billing_client_preserves_pence_strings_and_basis(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _result_payload()
        payload.update(
            {
                "tariff_rate": "0.035827",
                "currency": "GBP",
                "tariff_unit": "p/(kWh/h)/h",
                "billing_end": "2026-01-02T00:00:00+00:00",
                "billed_capacity_energy_mwh": "240",
                "delivered_energy_mwh": "120",
                "duration_microseconds": 86_400_000_000_000,
                "duration_hours": "24",
                "total_cost": "85.9848",
                "cost_per_delivered_mwh": "0.7165",
            }
        )
        payload["basis"] = {
            "tariff_rate": "0.035827",
            "tariff_unit": "p/(kWh/h)/h",
            "booked_capacity_mwh_per_h": "10",
            "billed_capacity_energy_mwh": "240",
            "delivered_energy_mwh": "120",
            "billing_start_utc": "2026-01-01T00:00:00+00:00",
            "billing_end_utc": "2026-01-02T00:00:00+00:00",
            "duration_microseconds": 86_400_000_000_000,
        }
        return httpx.Response(
            200, json={"data": payload, "meta": {}}, request=request
        )

    _install_mock_transport(monkeypatch, handler)

    result = calculate_capacity_billing(
        "http://testserver",
        request=_request(
            tariff_rate="0.035827",
            currency="GBP",
            tariff_unit="p/(kWh/h)/h",
            billing_end=datetime(2026, 1, 2, tzinfo=UTC),
            billed_capacity_energy_mwh="240",
            delivered_energy_mwh="120",
        ),
    )

    assert result.currency == "GBP"
    assert result.tariff_unit == "p/(kWh/h)/h"
    assert result.tariff_rate == "0.035827"
    assert result.total_cost == "85.9848"
    assert result.cost_per_delivered_mwh == "0.7165"
    assert result.basis.tariff_rate == "0.035827"


def test_capacity_billing_client_propagates_server_refusal(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "detail": {
                    "code": "capacity_billing_refused",
                    "codes": ["BILLED_CAPACITY_ENERGY_INCONSISTENT"],
                    "research_only": True,
                    "human_review_required": True,
                }
            },
            request=request,
        )

    _install_mock_transport(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError) as info:
        calculate_capacity_billing("http://testserver", request=_request())
    assert info.value.response.status_code == 422
    assert info.value.response.json()["detail"]["code"] == "capacity_billing_refused"
    assert info.value.response.json()["detail"]["codes"] == [
        "BILLED_CAPACITY_ENERGY_INCONSISTENT"
    ]


def test_typed_request_refuses_numeric_and_naive_inputs() -> None:
    with pytest.raises(ValidationError):
        _request(tariff_rate=2)

    with pytest.raises(ValidationError):
        _request(billing_start=datetime(2026, 1, 1))

    with pytest.raises(ValidationError):
        _request(decision_context="RUNTIME_DECISION")
