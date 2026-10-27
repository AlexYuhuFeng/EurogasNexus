"""Focused tests for ``POST /api/research/capacity-billing``.

The endpoint is the sandbox-only HTTP adaptation of the shared exact capacity
billing primitive: decimal strings in, decimal strings out, the domain engine as
the single arithmetic authority, no entity lookup, no persistence, no provider
call and stable typed refusals. All inputs are explicitly labeled synthetic test
data; nothing here is a market fact or a booked right.

The 23h/25h and pence cases are hand-checkable: a 10 MWh/h booking over 23h at
2 EUR/(MWh/h)/h bills 230 MWh of capacity energy, i.e. 460 EUR, and allocating
that cost over 115 delivered MWh gives 4 EUR/MWh. The 24h pence case bills
0.035827 * 240 * 10 = 85.9848 GBP and allocates 0.7165 GBP per delivered MWh.
"""

from __future__ import annotations

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
from eurogas_nexus.security.permissions import (
    Permission,
    permission_for_path,
    serves_commercial_data,
)

PUBLIC_TOKEN = "test-public-api-token"
PATH = "/api/research/capacity-billing"
START = "2026-01-01T00:00:00+00:00"
END_23 = "2026-01-01T23:00:00+00:00"
END_24 = "2026-01-02T00:00:00+00:00"
END_25 = "2026-01-02T01:00:00+00:00"
REFERENCES = (
    "synthetic-test-input:booking-1",
    "synthetic-test-input:tariff-1",
)


def _client() -> TestClient:
    return TestClient(create_app())


def _body(**overrides) -> dict:
    """Build one explicitly synthetic capacity-billing request."""

    body = {
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
    body.update(overrides)
    return body


def _pence_body(**overrides) -> dict:
    body = _body(
        tariff_rate="0.035827",
        currency="GBP",
        tariff_unit="p/(kWh/h)/h",
        billing_end=END_24,
        billed_capacity_energy_mwh="240",
        delivered_energy_mwh="120",
    )
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


def test_23_hour_case_returns_exact_strings_and_explicit_metadata() -> None:
    response = _client().post(PATH, json=_body())

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["model_version"] == "capacity-billing/v1"
    assert data["scenario_id"] == "scenario-synthetic-1"
    assert data["tariff_id"] == "tariff-synthetic-1"
    assert data["currency"] == "EUR"
    assert data["tariff_unit"] == "EUR/(MWh/h)/h"
    assert data["tariff_rate"] == "2"
    assert data["booked_capacity_mwh_per_h"] == "10"
    assert data["billed_capacity_energy_mwh"] == "230"
    assert data["delivered_energy_mwh"] == "115"
    assert data["billing_start"] == START
    assert data["billing_end"] == END_23
    assert data["duration_microseconds"] == 23 * 3_600_000_000
    assert data["duration_hours"] == "23"
    # Hand calculation: 2 * 230 = 460; 460 / 115 = 4.
    assert data["total_cost"] == "460.0000"
    assert data["cost_per_delivered_mwh"] == "4.0000"
    assert data["basis"] == {
        "tariff_rate": "2",
        "tariff_unit": "EUR/(MWh/h)/h",
        "booked_capacity_mwh_per_h": "10",
        "billed_capacity_energy_mwh": "230",
        "delivered_energy_mwh": "115",
        "billing_start_utc": START,
        "billing_end_utc": END_23,
        "duration_microseconds": 23 * 3_600_000_000,
    }
    assert data["provenance"] == sorted(REFERENCES)
    assert data["source_references"] == sorted(REFERENCES)
    assert data["lineage"] == ["capacity-billing", "capacity-billing/v1"]
    assert data["research_only"] is True
    assert data["human_review_required"] is True
    assert data["physical_readiness"] == "NOT_ASSESSED"
    assert data["warnings"] == [
        "RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT",
        "CAPACITY_BILLING_DOES_NOT_ESTABLISH_BOOKED_RIGHTS_OR_DELIVERABILITY",
    ]

    meta = payload["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
    assert meta["decision_context"] == "SANDBOX_SCENARIO"
    assert meta["caller_supplied"] is True
    assert meta["references_verified"] is False
    assert meta["booked_rights_established"] is False
    assert meta["physical_readiness"] == "NOT_ASSESSED"
    assert meta["customer_approval"] is False
    assert meta["source_references"] == data["source_references"]
    assert meta["warnings"] == data["warnings"]


def test_25_hour_case_keeps_billed_cost_and_per_delivered_allocation_distinct() -> None:
    response = _client().post(
        PATH,
        json=_body(
            billing_end=END_25,
            billed_capacity_energy_mwh="250",
            delivered_energy_mwh="125",
        ),
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["duration_microseconds"] == 25 * 3_600_000_000
    assert data["duration_hours"] == "25"
    assert data["total_cost"] == "500.0000"
    assert data["cost_per_delivered_mwh"] == "4.0000"


def test_pence_capacity_tariff_uses_the_exact_factor_and_never_an_energy_price() -> None:
    response = _client().post(PATH, json=_pence_body())

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["currency"] == "GBP"
    assert data["tariff_unit"] == "p/(kWh/h)/h"
    assert data["duration_microseconds"] == 24 * 3_600_000_000
    # 0.035827 p/(kWh/h)/h * 240 MWh * 10 = 85.9848 GBP.
    assert data["total_cost"] == "85.9848"
    # Allocated over 120 delivered MWh, not treated as an energy price.
    assert data["cost_per_delivered_mwh"] == "0.7165"
    assert data["cost_per_delivered_mwh"] != "0.3583"


def test_subsecond_duration_is_preserved_as_exact_microseconds() -> None:
    response = _client().post(
        PATH,
        json=_body(
            billing_end="2026-01-01T00:00:00.000001+00:00",
            booked_capacity_mwh_per_h="3600000000",
            billed_capacity_energy_mwh="1",
            delivered_energy_mwh="1",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["duration_microseconds"] == 1
    assert data["basis"]["duration_microseconds"] == 1
    assert data["total_cost"] == "2.0000"
    assert data["cost_per_delivered_mwh"] == "2.0000"


@pytest.mark.parametrize("value", [2, 2.5, True])
def test_json_numbers_and_booleans_are_never_accepted_as_decimal_strings(
    value: object,
) -> None:
    response = _client().post(PATH, json=_body(tariff_rate=value))

    assert response.status_code == 422
    assert "data" not in response.json()
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("type") == "string_type" for item in detail)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e3", " 2"])
def test_nonfinite_and_non_plain_decimal_strings_are_refused(value: str) -> None:
    response = _client().post(PATH, json=_body(tariff_rate=value))

    detail = _refused(response)
    assert detail["code"] == "capacity_billing_input_invalid"
    assert "DECIMAL_STRING_INVALID" in detail["codes"]


def test_naive_billing_start_is_refused_before_any_computation() -> None:
    response = _client().post(
        PATH, json=_body(billing_start="2026-01-01T00:00:00")
    )

    detail = _refused(response)
    assert detail["code"] == "capacity_billing_input_invalid"
    assert "DATETIME_AWARENESS_REQUIRED" in detail["codes"]


def test_inconsistent_billed_capacity_energy_is_refused() -> None:
    response = _client().post(
        PATH, json=_body(billed_capacity_energy_mwh="231")
    )

    detail = _refused(response)
    assert detail["code"] == "capacity_billing_refused"
    assert "BILLED_CAPACITY_ENERGY_INCONSISTENT" in detail["codes"]


def test_unsupported_and_mismatched_capacity_units_are_refused() -> None:
    unsupported = _refused(
        _client().post(PATH, json=_body(tariff_unit="EUR/MWh"))
    )
    assert unsupported["code"] == "capacity_billing_refused"
    assert "TARIFF_UNIT_UNSUPPORTED" in unsupported["codes"]

    mismatched = _refused(
        _client().post(
            PATH,
            json=_body(tariff_unit="p/(kWh/h)/h", currency="EUR"),
        )
    )
    assert mismatched["code"] == "capacity_billing_refused"
    assert "TARIFF_UNIT_CURRENCY_MISMATCH" in mismatched["codes"]


def test_zero_tariff_is_explicit_and_never_inferred() -> None:
    response = _client().post(PATH, json=_body(tariff_rate="0"))

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["tariff_rate"] == "0"
    assert data["basis"]["tariff_rate"] == "0"
    assert data["total_cost"] == "0.0000"
    assert data["cost_per_delivered_mwh"] == "0.0000"

    missing_body = _body()
    missing_body.pop("tariff_rate")
    missing = _client().post(PATH, json=missing_body)
    assert missing.status_code == 422
    assert "data" not in missing.json()


def test_missing_and_empty_provenance_are_refused() -> None:
    missing_body = _body()
    missing_body.pop("source_references")
    missing = _client().post(PATH, json=missing_body)
    assert missing.status_code == 422
    assert "data" not in missing.json()

    empty = _refused(_client().post(PATH, json=_body(source_references=[])))
    assert empty["code"] == "capacity_billing_refused"
    assert "SOURCE_REFERENCES_MISSING" in empty["codes"]


def test_extra_authority_fields_are_refused() -> None:
    response = _client().post(
        PATH,
        json=_body(booked_rights_established=True, physical_readiness="READY"),
    )

    assert response.status_code == 422
    assert "data" not in response.json()
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("type") == "extra_forbidden" for item in detail)


def test_runtime_decision_claim_is_refused_by_the_sandbox_gate() -> None:
    response = _client().post(
        PATH, json=_body(decision_context="RUNTIME_DECISION")
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "runtime_decision_not_supported"
    assert detail["research_only"] is True


def test_route_is_covered_by_the_existing_permission_and_commercial_gates() -> None:
    assert permission_for_path(PATH, "POST") is Permission.GOVERNED
    assert serves_commercial_data(PATH) is True


def test_anonymous_caller_is_denied_before_any_computation() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(PATH, json=_body())

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "public_api_token_missing"


def _prepare_identity_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "capacity-billing.sqlite"
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
        session, row.principal_id, display_name="capacity-billing-test"
    )
    return bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_disallowed_roles_are_denied_and_a_persona_claim_cannot_grant(
    tmp_path, monkeypatch
) -> None:
    database_url = _prepare_identity_db(tmp_path, monkeypatch)
    with Session(create_engine(database_url, future=True)) as session:
        viewer = _bearer(session, name="cb-viewer", role="VIEWER", scopes=["ENTSOG"])
        admin = _bearer(session, name="cb-admin", role="ADMIN", scopes=[])
        analyst = _bearer(session, name="cb-analyst", role="ANALYST", scopes=["ENTSOG"])
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    claim = dict(_body())
    claim.update({"work_mode": "TRADING_ANALYSIS", "persona": "TRADER"})
    viewer_response = client.post(PATH, json=claim, headers=_headers(viewer))
    assert viewer_response.status_code == 403
    assert viewer_response.json()["detail"]["error"] == "identity_role_forbidden"

    admin_response = client.post(PATH, json=claim, headers=_headers(admin))
    assert admin_response.status_code == 403
    assert admin_response.json()["detail"]["error"] == "commercial_access_not_granted"

    analyst_response = client.post(PATH, json=_body(), headers=_headers(analyst))
    assert analyst_response.status_code == 200
    assert analyst_response.json()["data"]["total_cost"] == "460.0000"
