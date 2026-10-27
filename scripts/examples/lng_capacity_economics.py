#!/usr/bin/env python
"""Reproducible typed-SDK acceptance example for capacity and LNG economics.

This bounded example sends *caller-supplied synthetic* inputs to the two existing
research sandboxes through the repository's typed Python SDK:

* ``POST /api/research/capacity-billing``
* ``POST /api/research/lng-economics-only``

It performs no local financial or energy arithmetic. Every number is asserted
against the backend's exact decimal-string result, and both refusal contracts are
checked by stable code. Nothing is persisted, seeded, granted or retrieved from a
provider.

Configuration is explicit and has no defaults:

* ``EUROGAS_UAT_API_BASE_URL`` -- API origin, for example
  ``http://127.0.0.1:8000``;
* ``EUROGAS_UAT_ALLOW_NON_LOOPBACK`` -- unset, or exactly ``1`` to opt in to an
  explicit HTTPS non-loopback UAT API;
* the existing SDK helpers read ``EUROGAS_NEXUS_PUBLIC_API_TOKEN`` (or its
  legacy fallback), ``EUROGAS_NEXUS_PRINCIPAL`` and
  ``EUROGAS_NEXUS_IDENTITY_BEARER`` from the environment when present. This
  example never reads, echoes or constructs those values itself.

The process prints one safe JSON object. It never prints credentials, response
bodies, authenticated exception text or tracebacks. Refusal output is narrowed to
the HTTP status and the backend's stable codes.

Expected synthetic goldens (see ``docs/release/acceptance/24_ECONOMICS_WORKFLOW_ACCEPTANCE.md``):

* capacity: 23 h ``460.0000`` / ``4.0000``; 25 h ``500.0000`` / ``4.0000``;
  pence 24 h ``85.9848`` / ``0.7165``;
* LNG: cargo margin ``550.0000`` EUR, NPV ``482.5000`` EUR, consumed ``7`` MWh,
  physical loss ``3`` MWh and total reduction ``10`` MWh,
  ``physical_readiness=NOT_ASSESSED``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import eurogas_nexus_sdk
    import httpx
    from eurogas_nexus_sdk.capacity_billing import CapacityBillingRequest
    from eurogas_nexus_sdk.lng_economics_only import (
        LngEconomicsOnlyDiscountFactorRequest,
        LngEconomicsOnlyDownstreamCostRequest,
        LngEconomicsOnlyEnergyStageRequest,
        LngEconomicsOnlyRequest,
    )
    from eurogas_nexus_sdk.research import (
        calculate_capacity_billing,
        calculate_lng_economics_only,
    )
except ImportError:  # pragma: no cover - exercised by the documented clean-config path
    SDK_IMPORT_ERROR = True
else:
    SDK_IMPORT_ERROR = False

API_BASE_URL_ENV = "EUROGAS_UAT_API_BASE_URL"
ALLOW_NON_LOOPBACK_ENV = "EUROGAS_UAT_ALLOW_NON_LOOPBACK"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
CAPACITY_MODEL_VERSION = "capacity-billing/v1"
LNG_MODEL_VERSION = "lng-economics-only/v1"
NOT_ASSESSED = "NOT_ASSESSED"

CAPACITY_GOLDENS: tuple[dict[str, Any], ...] = (
    {
        "id": "capacity-23h",
        "scenario_id": "synthetic-capacity-23h",
        "tariff_id": "synthetic-tariff-23h",
        "tariff_rate": "2",
        "currency": "EUR",
        "tariff_unit": "EUR/(MWh/h)/h",
        "booked_capacity_mwh_per_h": "10",
        "delivered_energy_mwh": "115",
        "billed_capacity_energy_mwh": "230",
        "billing_start": "2026-01-01T00:00:00+00:00",
        "billing_end": "2026-01-01T23:00:00+00:00",
        "source_references": [
            "synthetic-input:booking-23h",
            "synthetic-input:tariff-23h",
        ],
        "expected_total_cost": "460.0000",
        "expected_cost_per_delivered_mwh": "4.0000",
        "expected_duration_microseconds": 82_800_000_000,
        "expected_duration_hours": "23",
    },
    {
        "id": "capacity-25h",
        "scenario_id": "synthetic-capacity-25h",
        "tariff_id": "synthetic-tariff-25h",
        "tariff_rate": "2",
        "currency": "EUR",
        "tariff_unit": "EUR/(MWh/h)/h",
        "booked_capacity_mwh_per_h": "10",
        "delivered_energy_mwh": "125",
        "billed_capacity_energy_mwh": "250",
        "billing_start": "2026-01-02T00:00:00+00:00",
        "billing_end": "2026-01-03T01:00:00+00:00",
        "source_references": [
            "synthetic-input:booking-25h",
            "synthetic-input:tariff-25h",
        ],
        "expected_total_cost": "500.0000",
        "expected_cost_per_delivered_mwh": "4.0000",
        "expected_duration_microseconds": 90_000_000_000,
        "expected_duration_hours": "25",
    },
    {
        "id": "capacity-pence-24h",
        "scenario_id": "synthetic-capacity-pence-24h",
        "tariff_id": "synthetic-tariff-pence-24h",
        "tariff_rate": "0.035827",
        "currency": "GBP",
        "tariff_unit": "p/(kWh/h)/h",
        "booked_capacity_mwh_per_h": "10",
        "delivered_energy_mwh": "120",
        "billed_capacity_energy_mwh": "240",
        "billing_start": "2026-01-04T00:00:00+00:00",
        "billing_end": "2026-01-05T00:00:00+00:00",
        "source_references": [
            "synthetic-input:booking-pence-24h",
            "synthetic-input:tariff-pence-24h",
        ],
        "expected_total_cost": "85.9848",
        "expected_cost_per_delivered_mwh": "0.7165",
        "expected_duration_microseconds": 86_400_000_000,
        "expected_duration_hours": "24",
    },
)

LNG_GOLDEN: dict[str, Any] = {
    "contract_id": "synthetic-contract-lng-1",
    "cargo_id": "synthetic-cargo-lng-1",
    "terminal_id": "synthetic-terminal-lng-1",
    "resource_id": "synthetic-resource-lng-1",
    "valuation_date": "2026-09-29",
    "purchase_payment_date": "2026-09-29",
    "sale_payment_date": "2026-11-30",
    "purchased_energy_mwh": "100",
    "delivered_energy_mwh": "90",
    "purchase_unit_price_eur_per_mwh": "20",
    "sale_unit_price_eur_per_mwh": "30",
    "purchase_price_source_reference": "synthetic-input:purchase-price-1",
    "sale_price_source_reference": "synthetic-input:sale-price-1",
    "purchase_basis": "FOB",
    "cost_scope_statement": (
        "Synthetic acceptance input: the purchase price excludes shipping, "
        "regasification and the separately invoiced downstream cost."
    ),
    "cost_id": "synthetic-cost-1",
    "cost_category": "regas",
    "cost_amount_eur": "150",
    "cost_payment_date": "2026-09-29",
    "cost_source_reference": "synthetic-input:invoiced-cost-1",
    "charge_basis": "invoiced_cash",
    "discount_as_of": "2026-09-29",
    "discount_curve_reference": "synthetic-curve:eur-flat",
    "discount_source_reference": "synthetic-input:discount-factor-1",
    "sale_discount_factor": "0.975",
    "energy_basis_reference": "synthetic-energy-basis:cargo-mwh",
    "energy_unit": "MWh",
    "reporting_currency": "EUR",
    "stage_1_input": "100",
    "stage_1_output": "96",
    "stage_1_consumed": "3",
    "stage_1_loss": "1",
    "stage_2_input": "96",
    "stage_2_output": "90",
    "stage_2_consumed": "4",
    "stage_2_loss": "2",
    "expected_purchase_outlay_eur": "2000.0000",
    "expected_sale_proceeds_eur": "2700.0000",
    "expected_downstream_costs_eur": "150.0000",
    "expected_cargo_margin_eur": "550.0000",
    "expected_net_present_value_eur": "482.5000",
    "expected_total_undiscounted_cash_eur": "550.0000",
    "expected_total_consumed_energy_mwh": "7",
    "expected_physical_loss_energy_mwh": "3",
    "expected_total_reduction_energy_mwh": "10",
    "expected_physical_readiness": NOT_ASSESSED,
    "expected_refusal_code": "lng_economics_only_refused",
    "expected_refusal_violation": "STAGE_CONSERVATION_FAILED",
}


class ConfigurationError(RuntimeError):
    """A safe, user-actionable configuration failure."""


class AcceptanceError(RuntimeError):
    """A controlled acceptance-check failure with a step label."""

    def __init__(self, step: str, message: str) -> None:
        """Record the failing acceptance step and a credential-free message."""

        self.step = step
        self.message = message
        super().__init__(message)


def _check(step: str, condition: bool, message: str) -> None:
    """Raise one controlled acceptance failure without echoing server data."""

    if not condition:
        raise AcceptanceError(step, message)


def resolve_api_base_url(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, bool]:
    """Resolve the explicit API origin and whether it is an opted-in remote UAT.

    Args:
        environ: Optional environment mapping for focused tests. The process
            environment is used when omitted.

    Returns:
        ``(origin, remote_uat)`` where ``origin`` has no path, query, fragment or
        userinfo.

    Raises:
        ConfigurationError: When the base URL is missing, malformed, contains
            credentials, or is non-loopback without an explicit HTTPS UAT opt-in.
    """

    source = os.environ if environ is None else environ
    raw_base = (source.get(API_BASE_URL_ENV) or "").strip()
    if not raw_base:
        raise ConfigurationError(
            f"{API_BASE_URL_ENV} is required; this example has no default API URL."
        )

    raw_allow = (source.get(ALLOW_NON_LOOPBACK_ENV) or "").strip()
    if raw_allow not in {"", "1"}:
        raise ConfigurationError(
            f"{ALLOW_NON_LOOPBACK_ENV} must be unset or exactly '1'."
        )

    try:
        parsed = urlsplit(raw_base)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("The configured API URL is not a valid origin.") from exc

    if parsed.scheme not in {"http", "https"} or not host or port == 0:
        raise ConfigurationError(
            "The configured API URL must be an http(s) origin without a path."
        )
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError(
            "The configured API URL must not contain embedded credentials."
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ConfigurationError(
            "The configured API URL must be an origin only (no path, query or fragment)."
        )

    loopback = host in LOOPBACK_HOSTS
    remote_uat = raw_allow == "1" and not loopback
    if not loopback:
        if raw_allow != "1":
            raise ConfigurationError(
                "Non-loopback API access requires explicit UAT opt-in via "
                f"{ALLOW_NON_LOOPBACK_ENV}=1."
            )
        if parsed.scheme != "https":
            raise ConfigurationError(
                "An opted-in non-loopback UAT API must use HTTPS."
            )

    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")), remote_uat


def sdk_mode() -> str:
    """Report whether the imported SDK is the repository source or installed."""

    source_root = (
        Path(__file__).resolve().parents[2] / "packages" / "python-sdk" / "src"
    ).resolve()
    imported = Path(eurogas_nexus_sdk.__file__).resolve()
    return "source" if imported.is_relative_to(source_root) else "installed"


def refusal_summary(response: Any) -> dict[str, Any]:
    """Return only stable refusal metadata from an HTTP response.

    The backend's free-text ``message`` and individual violation details are
    deliberately omitted: they may echo caller input and are not needed for the
    acceptance verdict. Codes are bounded to the documented refusal vocabulary.
    """

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, dict):
        detail = {}
    raw_codes = detail.get("codes")
    codes = raw_codes if isinstance(raw_codes, list) else []
    return {
        "status": int(response.status_code),
        "code": str(detail.get("code") or "")[:80],
        "codes": [str(code)[:80] for code in codes[:20]],
    }


def _capacity_request(case: Mapping[str, Any]) -> Any:
    """Build one typed capacity-billing request from a documented golden."""

    return CapacityBillingRequest(
        scenario_id=case["scenario_id"],
        tariff_id=case["tariff_id"],
        tariff_rate=case["tariff_rate"],
        currency=case["currency"],
        tariff_unit=case["tariff_unit"],
        booked_capacity_mwh_per_h=case["booked_capacity_mwh_per_h"],
        delivered_energy_mwh=case["delivered_energy_mwh"],
        billed_capacity_energy_mwh=case["billed_capacity_energy_mwh"],
        billing_start=datetime.fromisoformat(case["billing_start"]),
        billing_end=datetime.fromisoformat(case["billing_end"]),
        source_references=list(case["source_references"]),
    )


def _lng_request(*, break_conservation: bool = False) -> Any:
    """Build the documented synthetic LNG request, optionally breaking conservation."""

    valuation_date = date.fromisoformat(LNG_GOLDEN["valuation_date"])
    sale_date = date.fromisoformat(LNG_GOLDEN["sale_payment_date"])
    first_loss = "2" if break_conservation else LNG_GOLDEN["stage_1_loss"]

    return LngEconomicsOnlyRequest(
        contract_id=LNG_GOLDEN["contract_id"],
        cargo_id=LNG_GOLDEN["cargo_id"],
        terminal_id=LNG_GOLDEN["terminal_id"],
        resource_id=LNG_GOLDEN["resource_id"],
        valuation_date=valuation_date,
        reporting_currency=LNG_GOLDEN["reporting_currency"],
        energy_basis_reference=LNG_GOLDEN["energy_basis_reference"],
        energy_unit=LNG_GOLDEN["energy_unit"],
        purchased_energy_mwh=LNG_GOLDEN["purchased_energy_mwh"],
        delivered_energy_mwh=LNG_GOLDEN["delivered_energy_mwh"],
        purchase_unit_price_eur_per_mwh=(
            LNG_GOLDEN["purchase_unit_price_eur_per_mwh"]
        ),
        sale_unit_price_eur_per_mwh=LNG_GOLDEN["sale_unit_price_eur_per_mwh"],
        purchase_price_source_reference=(
            LNG_GOLDEN["purchase_price_source_reference"]
        ),
        sale_price_source_reference=LNG_GOLDEN["sale_price_source_reference"],
        purchase_basis=LNG_GOLDEN["purchase_basis"],
        purchase_included_cost_items=[],
        cost_scope_statement=LNG_GOLDEN["cost_scope_statement"],
        purchase_payment_date=valuation_date,
        sale_payment_date=sale_date,
        downstream_costs=[
            LngEconomicsOnlyDownstreamCostRequest(
                cost_id=LNG_GOLDEN["cost_id"],
                category=LNG_GOLDEN["cost_category"],
                amount_eur=LNG_GOLDEN["cost_amount_eur"],
                payment_date=valuation_date,
                source_reference=LNG_GOLDEN["cost_source_reference"],
                charge_basis=LNG_GOLDEN["charge_basis"],
            )
        ],
        energy_stages=[
            LngEconomicsOnlyEnergyStageRequest(
                stage_id="synthetic-stage-1",
                kind="shipping",
                input_energy_mwh=LNG_GOLDEN["stage_1_input"],
                output_energy_mwh=LNG_GOLDEN["stage_1_output"],
                consumed_energy_mwh=LNG_GOLDEN["stage_1_consumed"],
                physical_loss_energy_mwh=first_loss,
                source_references=["synthetic-input:stage-shipping-1"],
            ),
            LngEconomicsOnlyEnergyStageRequest(
                stage_id="synthetic-stage-2",
                kind="regasification",
                input_energy_mwh=LNG_GOLDEN["stage_2_input"],
                output_energy_mwh=LNG_GOLDEN["stage_2_output"],
                consumed_energy_mwh=LNG_GOLDEN["stage_2_consumed"],
                physical_loss_energy_mwh=LNG_GOLDEN["stage_2_loss"],
                source_references=["synthetic-input:stage-regas-1"],
            ),
        ],
        discount_factors=[
            LngEconomicsOnlyDiscountFactorRequest(
                payment_date=valuation_date,
                factor="1",
                curve_reference=LNG_GOLDEN["discount_curve_reference"],
                source_reference=LNG_GOLDEN["discount_source_reference"],
                as_of=valuation_date,
            ),
            LngEconomicsOnlyDiscountFactorRequest(
                payment_date=sale_date,
                factor=LNG_GOLDEN["sale_discount_factor"],
                curve_reference=LNG_GOLDEN["discount_curve_reference"],
                source_reference=LNG_GOLDEN["discount_source_reference"],
                as_of=valuation_date,
            ),
        ],
    )


def _run_capacity(base_url: str, checks: list[dict[str, Any]]) -> None:
    """Run all capacity goldens and the exact inconsistency refusal."""

    for case in CAPACITY_GOLDENS:
        case_id = case["id"]
        result = calculate_capacity_billing(
            base_url,
            request=_capacity_request(case),
        )
        _check(
            f"{case_id}/total_cost",
            result.total_cost == case["expected_total_cost"],
            f"{case_id}: expected total_cost {case['expected_total_cost']}.",
        )
        _check(
            f"{case_id}/cost_per_delivered",
            result.cost_per_delivered_mwh
            == case["expected_cost_per_delivered_mwh"],
            f"{case_id}: expected cost_per_delivered_mwh "
            f"{case['expected_cost_per_delivered_mwh']}.",
        )
        _check(
            f"{case_id}/duration_microseconds",
            result.duration_microseconds
            == case["expected_duration_microseconds"],
            f"{case_id}: exact UTC duration changed.",
        )
        _check(
            f"{case_id}/duration_hours",
            result.duration_hours == case["expected_duration_hours"],
            f"{case_id}: display duration changed.",
        )
        _check(
            f"{case_id}/model_version",
            result.model_version == CAPACITY_MODEL_VERSION,
            f"{case_id}: unexpected model version.",
        )
        _check(
            f"{case_id}/physical_readiness",
            result.physical_readiness == NOT_ASSESSED,
            f"{case_id}: physical readiness must stay NOT_ASSESSED.",
        )
        checks.append(
            {
                "check": case_id,
                "status": "pass",
                "total_cost": result.total_cost,
                "cost_per_delivered_mwh": result.cost_per_delivered_mwh,
                "duration_microseconds": result.duration_microseconds,
                "physical_readiness": result.physical_readiness,
            }
        )

    refusal_case = dict(CAPACITY_GOLDENS[0])
    refusal_case["billed_capacity_energy_mwh"] = "240"
    try:
        calculate_capacity_billing(
            base_url,
            request=_capacity_request(refusal_case),
        )
    except httpx.HTTPStatusError as exc:
        summary = refusal_summary(exc.response)
        _check(
            "capacity/refusal/status",
            summary["status"] == 422,
            "capacity refusal: expected HTTP 422.",
        )
        _check(
            "capacity/refusal/code",
            summary["code"] == "capacity_billing_refused",
            "capacity refusal: expected capacity_billing_refused.",
        )
        _check(
            "capacity/refusal/violation",
            "BILLED_CAPACITY_ENERGY_INCONSISTENT" in summary["codes"],
            "capacity refusal: expected BILLED_CAPACITY_ENERGY_INCONSISTENT.",
        )
        checks.append(
            {
                "check": "capacity-refusal-inconsistent-billed-energy",
                "status": "pass",
                "http_status": summary["status"],
                "code": summary["code"],
                "codes": summary["codes"],
            }
        )
    else:
        raise AcceptanceError(
            "capacity/refusal",
            "capacity inconsistency was accepted instead of refused.",
        )


def _run_lng(base_url: str, checks: list[dict[str, Any]]) -> None:
    """Run the LNG golden and the exact energy-conservation refusal."""

    result = calculate_lng_economics_only(
        base_url,
        request=_lng_request(),
    )
    expected = {
        "purchase_outlay_eur": LNG_GOLDEN["expected_purchase_outlay_eur"],
        "sale_proceeds_eur": LNG_GOLDEN["expected_sale_proceeds_eur"],
        "total_downstream_costs_eur": LNG_GOLDEN[
            "expected_downstream_costs_eur"
        ],
        "cargo_margin_eur": LNG_GOLDEN["expected_cargo_margin_eur"],
        "net_present_value_eur": LNG_GOLDEN["expected_net_present_value_eur"],
        "total_undiscounted_cash_eur": LNG_GOLDEN[
            "expected_total_undiscounted_cash_eur"
        ],
        "total_consumed_energy_mwh": LNG_GOLDEN[
            "expected_total_consumed_energy_mwh"
        ],
        "physical_loss_energy_mwh": LNG_GOLDEN[
            "expected_physical_loss_energy_mwh"
        ],
        "total_reduction_energy_mwh": LNG_GOLDEN[
            "expected_total_reduction_energy_mwh"
        ],
        "physical_readiness": LNG_GOLDEN["expected_physical_readiness"],
    }
    actual = {
        "purchase_outlay_eur": result.purchase_outlay_eur,
        "sale_proceeds_eur": result.sale_proceeds_eur,
        "total_downstream_costs_eur": result.total_downstream_costs_eur,
        "cargo_margin_eur": result.cargo_margin_eur,
        "net_present_value_eur": result.net_present_value_eur,
        "total_undiscounted_cash_eur": result.total_undiscounted_cash_eur,
        "total_consumed_energy_mwh": result.total_consumed_energy_mwh,
        "physical_loss_energy_mwh": result.physical_loss_energy_mwh,
        "total_reduction_energy_mwh": result.total_reduction_energy_mwh,
        "physical_readiness": result.physical_readiness,
    }
    for field_name, expected_value in expected.items():
        _check(
            f"lng/{field_name}",
            actual[field_name] == expected_value,
            f"lng: {field_name} does not match the documented synthetic golden.",
        )
    _check(
        "lng/readiness_assessed",
        result.readiness_assessed is False,
        "lng: readiness_assessed must be false.",
    )
    _check(
        "lng/model_version",
        result.model_version == LNG_MODEL_VERSION,
        "lng: unexpected model version.",
    )
    checks.append(
        {
            "check": "lng-golden",
            "status": "pass",
            **actual,
            "readiness_assessed": result.readiness_assessed,
            "model_version": result.model_version,
        }
    )

    try:
        calculate_lng_economics_only(
            base_url,
            request=_lng_request(break_conservation=True),
        )
    except httpx.HTTPStatusError as exc:
        summary = refusal_summary(exc.response)
        _check(
            "lng/refusal/status",
            summary["status"] == 422,
            "lng refusal: expected HTTP 422.",
        )
        _check(
            "lng/refusal/code",
            summary["code"] == LNG_GOLDEN["expected_refusal_code"],
            "lng refusal: expected lng_economics_only_refused.",
        )
        _check(
            "lng/refusal/violation",
            LNG_GOLDEN["expected_refusal_violation"] in summary["codes"],
            "lng refusal: expected STAGE_CONSERVATION_FAILED.",
        )
        checks.append(
            {
                "check": "lng-refusal-energy-conservation",
                "status": "pass",
                "http_status": summary["status"],
                "code": summary["code"],
                "codes": summary["codes"],
            }
        )
    else:
        raise AcceptanceError(
            "lng/refusal",
            "broken energy conservation was accepted instead of refused.",
        )


def _emit(summary: Mapping[str, Any]) -> None:
    """Print one JSON document and nothing else."""

    print(json.dumps(summary, indent=2, sort_keys=True))


def main(environ: Mapping[str, str] | None = None) -> int:
    """Run the bounded SDK acceptance example and return its process status."""

    summary: dict[str, Any] = {
        "schema_version": "economics-sdk-example/v1",
        "status": "failed",
        "synthetic_inputs": True,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "checks": [],
    }

    if SDK_IMPORT_ERROR:
        summary.update(
            {
                "status": "error",
                "error": {
                    "code": "SDK_IMPORT_FAILED",
                    "message": (
                        "The typed Python SDK is not importable; install the project "
                        "or set PYTHONPATH as documented. No request was sent."
                    ),
                },
            }
        )
        _emit(summary)
        return 2

    try:
        base_url, remote_uat = resolve_api_base_url(environ)
    except ConfigurationError as exc:
        summary.update(
            {
                "status": "error",
                "error": {"code": "CONFIG_INVALID", "message": str(exc)},
            }
        )
        _emit(summary)
        return 2

    summary.update(
        {
            "sdk_mode": sdk_mode(),
            "api_scope": (
                "explicit-non-loopback-uat" if remote_uat else "loopback"
            ),
            "endpoints": [
                "/api/research/capacity-billing",
                "/api/research/lng-economics-only",
            ],
        }
    )
    checks: list[dict[str, Any]] = summary["checks"]

    try:
        _run_capacity(base_url, checks)
        _run_lng(base_url, checks)
    except AcceptanceError as exc:
        summary["error"] = {"step": exc.step, "message": exc.message}
    except httpx.HTTPStatusError as exc:
        summary["error"] = {
            "step": "http",
            "detail": refusal_summary(exc.response),
        }
    except Exception as exc:  # noqa: BLE001 - deliberate credential-safe boundary
        summary["error"] = {
            "step": "run",
            "type": type(exc).__name__,
            "message": (
                "Unexpected failure. Raw exception text, response bodies and "
                "credentials were not emitted."
            ),
        }
    else:
        summary["status"] = "passed"

    _emit(summary)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
