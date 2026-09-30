"""Focused tests for ``POST /api/research/cash-valuation``.

The endpoint is the sandbox-only HTTP adaptation of the shared dated cash
valuation engine: exact decimal strings in, exact decimal strings out, the
engine as the single arithmetic authority, no entity lookup, no persistence, no
provider call and stable typed refusals. All inputs are explicitly labeled
synthetic test data; nothing here is a market fact.

The hand-calculable reference schedule (EUR purchase -100 at the valuation date
with DF 1; USD sale +150 at EUR/USD 0.8 with DF 0.95; EUR storage cost -10 with
DF 0.95) produces undiscounted cash 10 and NPV 4.50 - the same case the domain
engine and the LNG adapter value, so the API is proven to delegate rather than
re-implement.
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
from eurogas_nexus.domain.ontology.actions import ActionKind
from eurogas_nexus.security.permissions import (
    Permission,
    permission_for_path,
    serves_commercial_data,
)

PUBLIC_TOKEN = "test-public-api-token"
PATH = "/api/research/cash-valuation"

PURCHASE_SOURCE = "synthetic-test-input:purchase-1"
SALE_SOURCE = "synthetic-test-input:sale-1"
FX_SOURCE = "synthetic-test-input:fx-1"
STORAGE_SOURCE = "synthetic-test-input:storage-1"
DF_SOURCE = "synthetic-test-input:df-1"
DF_CURVE = "synthetic-test-curve:eur-usd-flat"

_BASELINE_WARNINGS = [
    "RESEARCH_ONLY_DECISION_SUPPORT_NOT_ACCOUNTING_CUSTODY_OR_SETTLEMENT",
    "NPV_IS_NOT_NETBACK_MARK_TO_MARKET_OR_MARGIN",
]


def _client() -> TestClient:
    return TestClient(create_app())


def _golden_body() -> dict:
    """Hand-calculable synthetic schedule: cash EUR10, NPV EUR4.50."""

    def discount_factor(payment_date: str, factor: str) -> dict:
        return {
            "payment_date": payment_date,
            "factor": factor,
            "curve_reference": DF_CURVE,
            "source_reference": DF_SOURCE,
            "as_of": "2026-09-29",
        }

    return {
        "business_context": [
            "portfolio:portfolio-synthetic-1",
            "pipeline:pipeline-synthetic-1",
        ],
        "valuation_date": "2026-09-29",
        "reporting_currency": "EUR",
        "legs": [
            {
                "leg_id": "supply-purchase-1",
                "category": "other",
                "payment_date": "2026-09-29",
                "signed_amount": "-100",
                "currency": "EUR",
                "source_reference": PURCHASE_SOURCE,
            },
            {
                "leg_id": "hub-sale-1",
                "category": "other",
                "payment_date": "2026-11-30",
                "signed_amount": "150",
                "currency": "USD",
                "source_reference": SALE_SOURCE,
                "fx": {
                    "rate_reporting_per_leg": "0.8",
                    "source_reference": FX_SOURCE,
                    "as_of": "2026-09-28",
                },
            },
            {
                "leg_id": "storage-cost-1",
                "category": "storage",
                "payment_date": "2026-12-31",
                "signed_amount": "-10",
                "currency": "EUR",
                "source_reference": STORAGE_SOURCE,
            },
        ],
        "discount_factors": [
            discount_factor("2026-09-29", "1"),
            discount_factor("2026-11-30", "0.95"),
            discount_factor("2026-12-31", "0.95"),
        ],
    }


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


def test_golden_case_returns_exact_strings_and_explicit_metadata() -> None:
    response = _client().post(PATH, json=_golden_body())

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    data = payload["data"]
    assert data["model_version"] == "cash-valuation/v1"
    assert data["action"] == ActionKind.COMPUTE_CASH_FLOW.value
    assert data["business_context"] == [
        "portfolio:portfolio-synthetic-1",
        "pipeline:pipeline-synthetic-1",
    ]
    assert data["valuation_date"] == "2026-09-29"
    assert data["reporting_currency"] == "EUR"

    legs = {leg["leg_id"]: leg for leg in data["leg_valuations"]}
    assert set(legs) == {"supply-purchase-1", "hub-sale-1", "storage-cost-1"}
    purchase = legs["supply-purchase-1"]
    assert purchase["cash_amount_reporting_ccy"] == "-100.0000"
    assert purchase["present_value_reporting_ccy"] == "-100.0000"
    assert purchase["fx_rate_reporting_per_leg"] == "1"
    assert purchase["fx_source_reference"] is None
    assert purchase["fx_as_of"] is None
    sale = legs["hub-sale-1"]
    assert sale["currency"] == "USD"
    assert sale["signed_amount"] == "150"
    assert sale["fx_rate_reporting_per_leg"] == "0.8"
    assert sale["fx_source_reference"] == FX_SOURCE
    assert sale["fx_as_of"] == "2026-09-28"
    assert sale["cash_amount_reporting_ccy"] == "120.0000"
    assert sale["present_value_reporting_ccy"] == "114.0000"
    assert sale["discount_factor"] == "0.95"
    assert sale["discount_curve_reference"] == DF_CURVE
    assert sale["discount_source_reference"] == DF_SOURCE
    assert sale["discount_as_of"] == "2026-09-29"
    storage = legs["storage-cost-1"]
    assert storage["category"] == "storage"
    assert storage["cash_amount_reporting_ccy"] == "-10.0000"
    assert storage["present_value_reporting_ccy"] == "-9.5000"

    # Hand calculation: -100 + 150*0.8 - 10 = 10; -100 + 114 - 9.5 = 4.5.
    assert data["total_undiscounted_cash_reporting_ccy"] == "10.0000"
    assert data["net_present_value_reporting_ccy"] == "4.5000"
    assert data["lineage"] == ["cash-valuation", "cash-valuation/v1"]
    assert data["research_only"] is True
    assert data["human_review_required"] is True
    assert data["warnings"] == _BASELINE_WARNINGS
    assert any("not a netback" in item for item in data["assumptions"])

    meta = payload["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
    assert meta["decision_context"] == "SANDBOX_SCENARIO"
    assert meta["caller_supplied"] is True
    assert meta["references_verified"] is False
    assert meta["customer_approval"] is False
    assert meta["source_references"] == data["source_references"]
    assert meta["warnings"] == data["warnings"]


def test_golden_case_is_deterministic_and_db_free() -> None:
    """Equal inputs produce equal payloads; no runtime database can be required."""

    client = _client()
    first = client.post(PATH, json=_golden_body()).json()
    second = client.post(PATH, json=_golden_body()).json()
    assert first == second


def test_supplied_sources_are_echoed_including_fx_and_discount_provenance() -> None:
    response = _client().post(PATH, json=_golden_body())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_references"] == sorted(
        {PURCHASE_SOURCE, SALE_SOURCE, FX_SOURCE, STORAGE_SOURCE, DF_SOURCE}
    )
    legs = {leg["leg_id"]: leg for leg in data["leg_valuations"]}
    assert legs["supply-purchase-1"]["source_reference"] == PURCHASE_SOURCE
    assert legs["hub-sale-1"]["source_reference"] == SALE_SOURCE
    assert legs["storage-cost-1"]["source_reference"] == STORAGE_SOURCE


def test_high_precision_decimal_survives_the_round_trip_exactly() -> None:
    """A float64 could not carry this value; the API must (no binary-float step)."""

    body = _golden_body()
    body["legs"][1]["signed_amount"] = "150.000000000000000001"
    response = _client().post(PATH, json=body)

    assert response.status_code == 200
    payload = response.json()
    _assert_no_floats(payload)
    sale = {leg["leg_id"]: leg for leg in payload["data"]["leg_valuations"]}["hub-sale-1"]
    assert sale["signed_amount"] == "150.000000000000000001"
    assert sale["cash_amount_reporting_ccy"] == "120.0000"


@pytest.mark.parametrize("signed_amount", ["1,5", "NaN", "Infinity", "-inf", "1e3", "", " 10"])
def test_rejected_decimal_strings_are_never_reinterpreted(signed_amount: str) -> None:
    body = _golden_body()
    body["legs"][0]["signed_amount"] = signed_amount

    detail = _refused(_client().post(PATH, json=body))
    assert detail["code"] == "cash_valuation_input_invalid"
    assert "DECIMAL_STRING_INVALID" in detail["codes"]
    assert all(item["detail"] for item in detail["violations"])


@pytest.mark.parametrize("payment_date", ["2026-02-30", "2026-9-29", "29.09.2026", "TBD"])
def test_rejected_dates_fail_closed(payment_date: str) -> None:
    body = _golden_body()
    body["legs"][0]["payment_date"] = payment_date

    detail = _refused(_client().post(PATH, json=body))
    assert detail["code"] == "cash_valuation_input_invalid"
    assert "DATE_STRING_INVALID" in detail["codes"]


def test_unknown_category_and_malformed_reference_are_refused() -> None:
    body = _golden_body()
    body["legs"][0]["category"] = "not_a_category"
    body["business_context"] = ["portfolio-synthetic-1"]

    detail = _refused(_client().post(PATH, json=body))
    assert detail["code"] == "cash_valuation_input_invalid"
    assert "LEG_CATEGORY_INVALID" in detail["codes"]
    assert "BUSINESS_CONTEXT_REFERENCE_INVALID" in detail["codes"]


def test_missing_fields_are_refused_without_a_partial_result() -> None:
    client = _client()
    for body in ({}, {"valuation_date": "2026-09-29"}):
        response = client.post(PATH, json=body)
        assert response.status_code == 422
        assert "data" not in response.json()


def test_oversized_lists_are_refused_by_the_bounded_request_contract() -> None:
    client = _client()
    oversized_legs = _golden_body()
    oversized_legs["legs"] = [dict(oversized_legs["legs"][0]) for _ in range(257)]
    legs_response = client.post(PATH, json=oversized_legs)
    assert legs_response.status_code == 422
    assert "data" not in legs_response.json()
    assert any(item.get("type") == "too_long" for item in legs_response.json()["detail"])

    oversized_context = _golden_body()
    oversized_context["business_context"] = [
        f"portfolio:portfolio-{index}" for index in range(65)
    ]
    context_response = client.post(PATH, json=oversized_context)
    assert context_response.status_code == 422
    assert "data" not in context_response.json()
    assert any(item.get("type") == "too_long" for item in context_response.json()["detail"])


def test_json_numbers_are_never_accepted_as_decimals() -> None:
    body = _golden_body()
    body["legs"][0]["signed_amount"] = 100.25
    response = _client().post(PATH, json=body)

    assert response.status_code == 422
    assert "data" not in response.json()
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("type") == "string_type" for item in detail)


def test_runtime_decision_claim_is_refused_by_the_sandbox_gate() -> None:
    body = _golden_body()
    body["decision_context"] = "RUNTIME_DECISION"

    response = _client().post(PATH, json=body)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "runtime_decision_not_supported"
    assert detail["research_only"] is True


def test_a_request_cannot_grant_research_or_customer_authority() -> None:
    """Authority-like claims are not part of the contract and cannot be smuggled in."""

    body = _golden_body()
    body.update(
        {
            "research_only": False,
            "customer_approval": True,
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


def test_unsupported_model_version_is_refused_with_the_engine_code() -> None:
    body = _golden_body()
    body["model_version"] = "cash-valuation/v2"

    detail = _refused(_client().post(PATH, json=body))
    assert detail["code"] == "cash_valuation_refused"
    assert detail["codes"] == ["MODEL_VERSION_UNSUPPORTED"]


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda body: body["legs"][0].update({"payment_date": "2026-09-28"}),
            "LEG_PAYMENT_DATE_BEFORE_VALUATION",
        ),
        (
            lambda body: body["legs"][1].update({"payment_date": "2026-12-01"}),
            "DISCOUNT_FACTOR_MISSING_FOR_LEG_PAYMENT_DATE",
        ),
        (
            lambda body: body["legs"][1].pop("fx"),
            "FX_RATE_MISSING_FOR_CROSS_CURRENCY_LEG",
        ),
        (
            lambda body: body["legs"][1]["fx"].update({"as_of": "2026-10-01"}),
            "FX_AS_OF_IN_FUTURE",
        ),
        (
            lambda body: body["legs"][0].update({"fx": dict(body["legs"][1]["fx"])}),
            "FX_NOT_APPLICABLE_SAME_CURRENCY",
        ),
        (
            lambda body: body["discount_factors"][1].update({"source_reference": ""}),
            "DISCOUNT_FACTOR_SOURCE_MISSING",
        ),
        (
            lambda body: body["legs"][0].update({"source_reference": ""}),
            "LEG_SOURCE_REFERENCE_MISSING",
        ),
        (
            lambda body: body["legs"][0].update({"signed_amount": "0"}),
            "LEG_AMOUNT_ZERO",
        ),
        (
            lambda body: body.update({"business_context": []}),
            "BUSINESS_CONTEXT_MISSING",
        ),
        (
            lambda body: body.update({"legs": []}),
            "NO_CASH_FLOW_LEGS",
        ),
        (
            lambda body: body["legs"].append(dict(body["legs"][0])),
            "DUPLICATE_LEG_ID",
        ),
    ],
)
def test_engine_refusals_map_to_stable_codes(mutate, expected_code: str) -> None:
    body = _golden_body()
    mutate(body)

    detail = _refused(_client().post(PATH, json=body))
    assert detail["code"] == "cash_valuation_refused"
    assert expected_code in detail["codes"]
    assert all(item["code"] for item in detail["violations"])


def test_fabricated_reference_is_echoed_unverified_and_never_resolved() -> None:
    """A reference that cannot name a persisted entity still values: no lookup exists."""

    body = _golden_body()
    body["business_context"] = ["contract:does-not-exist-0001"]
    response = _client().post(PATH, json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["business_context"] == ["contract:does-not-exist-0001"]
    assert payload["meta"]["references_verified"] is False
    assert payload["meta"]["customer_approval"] is False


def test_route_is_covered_by_the_existing_permission_and_commercial_gates() -> None:
    assert permission_for_path(PATH, "POST") is Permission.GOVERNED
    assert serves_commercial_data(PATH) is True


def test_anonymous_caller_is_denied_before_any_computation() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(PATH, json=_golden_body())

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "public_api_token_missing"


def _prepare_identity_db(tmp_path, monkeypatch) -> str:
    db_path = tmp_path / "cash-valuation.sqlite"
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
        session, row.principal_id, display_name="cash-valuation-test"
    )
    return bearer


def _headers(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def test_disallowed_roles_are_denied_and_a_persona_claim_cannot_grant(
    tmp_path, monkeypatch
) -> None:
    """Rank, commercial access and work-mode composition are all backend facts."""

    database_url = _prepare_identity_db(tmp_path, monkeypatch)
    with Session(create_engine(database_url, future=True)) as session:
        viewer = _bearer(session, name="cv-viewer", role="VIEWER", scopes=["ENTSOG"])
        admin = _bearer(session, name="cv-admin", role="ADMIN", scopes=[])
        analyst = _bearer(session, name="cv-analyst", role="ANALYST", scopes=["ENTSOG"])
        session.commit()

    client = TestClient(create_app(Settings(api_profile="release")))

    # A VIEWER holds no ANALYST-floor permission, and claiming a research
    # persona/work mode in the body changes nothing.
    claim = dict(_golden_body())
    claim.update({"work_mode": "TRADING_ANALYSIS", "persona": "TRADER"})
    viewer_response = client.post(PATH, json=claim, headers=_headers(viewer))
    assert viewer_response.status_code == 403
    assert viewer_response.json()["detail"]["error"] == "identity_role_forbidden"

    # Platform administration is not commercial access, persona claim or not.
    admin_response = client.post(PATH, json=claim, headers=_headers(admin))
    assert admin_response.status_code == 403
    assert admin_response.json()["detail"]["error"] == "commercial_access_not_granted"

    # The ANALYST floor reaches the route through the same existing gates.
    analyst_response = client.post(PATH, json=_golden_body(), headers=_headers(analyst))
    assert analyst_response.status_code == 200
    assert analyst_response.json()["data"]["net_present_value_reporting_ccy"] == "4.5000"
