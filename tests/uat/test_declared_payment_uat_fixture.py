"""Guard and fixture-validity contracts for the isolated declared-payment UAT seed.

`scripts/uat/seed_declared_payment_uat_fixture.py` prepares the open real-browser
declared-payment visual acceptance. Nothing in this module claims that acceptance:
the tests hold the seed script to its isolation gates (explicit PostgreSQL URL,
dedicated database-name prefix, explicit acknowledgement, no runtime/default
target, no SQLite, no schema creation, no provider calls), to its contamination
guard, and to the reviewed payment-terms domain - the schedules must round-trip
through the canonical decoder, mix INFLOW/OUTFLOW, carry long clearly synthetic
evidence, and stay valid for the repository fixture path.

No database or network is touched: refusal tests run before any connection is
attempted, and the fixture checks call pure domain/repository helpers only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "uat" / "seed_declared_payment_uat_fixture.py"
DEPLOYMENT_BUNDLE_POLICY = ROOT / "scripts" / "release" / "package_deployment_bundle.policy.json"


def _load_fixture_module() -> Any:
    spec = importlib.util.spec_from_file_location("seed_declared_payment_uat_fixture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the fixture declares dataclasses, and `dataclasses`
    # resolves annotated names through `sys.modules[cls.__module__]`.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


FIXTURE = _load_fixture_module()

from eurogas_nexus.domain.ontology.vocabulary import (  # noqa: E402
    BusinessDayConvention,
    PaymentDateSpecificationKind,
    PaymentFlowDirection,
    PaymentOffsetDayKind,
)
from eurogas_nexus.domain.route_cost.payment_terms import (  # noqa: E402
    MAX_PAYMENT_TERMS_TEXT_LENGTH,
    AnchoredPaymentRule,
    ContractPaymentTerms,
    ExplicitPaymentDate,
)


def _url(database_name: str) -> str:
    return f"postgresql://fixture-user:fixture-secret@127.0.0.1:5432/{database_name}"


def _run(env: dict[str, str], *arguments: str) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    for name in (
        "RUNTIME_STORE_DATABASE_URL",
        "DATABASE_URL",
        "EUROGAS_NEXUS_DB_DSN",
        "EUROGAS_NEXUS_ENV",
        "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED",
    ):
        merged.pop(name, None)
    merged.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
        check=False,
    )


# --- guard refusals (configuration gates run before any connection) ----------------


def test_fixture_requires_the_explicit_url_and_never_falls_back() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "DATABASE_URL": _url("eurogas_uat_payment_fallback"),
            "EUROGAS_NEXUS_DB_DSN": _url("eurogas_uat_payment_dsn"),
        }
    )
    assert result.returncode == 2
    assert "RUNTIME_STORE_DATABASE_URL" in result.stdout
    assert "postgresql://" not in result.stdout + result.stderr


def test_fixture_requires_the_acknowledgement_flag() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "RUNTIME_STORE_DATABASE_URL": _url("eurogas_uat_payment_visual"),
        }
    )
    assert result.returncode == 2
    assert "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED" in result.stdout


@pytest.mark.parametrize("environment", ["trial", "release"])
def test_fixture_is_blocked_in_trial_and_release(environment: str) -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": environment,
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": _url("eurogas_uat_payment_visual"),
        }
    )
    assert result.returncode == 2
    assert "blocked in trial/release" in result.stdout


def test_fixture_refuses_the_default_runtime_database_without_printing_credentials() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": _url("eurogas_nexus"),
        }
    )
    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "default runtime database" in output
    assert "fixture-user" not in output
    assert "fixture-secret" not in output
    assert "127.0.0.1" not in output
    assert "postgresql://" not in output


def test_fixture_refuses_a_database_without_the_dedicated_prefix() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": _url("eurogas_nexus_uat"),
        }
    )
    assert result.returncode == 2
    assert FIXTURE.DATABASE_NAME_PREFIX in result.stdout
    assert "fixture-secret" not in result.stdout + result.stderr


def test_fixture_refuses_non_postgresql_targets_without_creating_the_file(
    tmp_path: Path,
) -> None:
    sqlite_target = tmp_path / "never_created.sqlite3"
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": f"sqlite:///{sqlite_target}",
        }
    )
    assert result.returncode == 2
    assert "PostgreSQL" in result.stdout
    assert not sqlite_target.exists()


def test_fixture_refuses_unknown_arguments() -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "development",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": _url("eurogas_uat_payment_visual"),
        },
        "postgresql://secret-user:secret-password@host/private",
    )
    assert result.returncode == 2
    assert "Unexpected command-line arguments" in result.stdout
    assert "secret-password" not in result.stdout + result.stderr
    assert "secret-user" not in result.stdout + result.stderr


def test_target_decision_accepts_only_a_prefixed_postgresql_name() -> None:
    assert (
        FIXTURE.database_target_refusal(
            "postgresql://operator@isolated-host:5432/eurogas_uat_payment_visual_20261006"
        )
        is None
    )
    for refused in (
        "postgresql://operator@isolated-host:5432/eurogas_nexus",
        "postgresql://operator@isolated-host:5432/eurogas_nexus_uat",
        "postgresql://operator@isolated-host:5432/eurogas_uat",
        "postgresql://operator@isolated-host:5432",
        "mysql://operator@isolated-host:3306/eurogas_uat_payment_visual",
        "sqlite:///fixture.sqlite3",
        "not a database url",
    ):
        refusal = FIXTURE.database_target_refusal(refused)
        assert refusal is not None, refused
        assert refused not in refusal
        assert "operator" not in refusal
        assert "isolated-host" not in refusal


def test_owner_guard_refuses_foreign_records_without_echoing_them() -> None:
    owned = [fixture.contract_id for fixture in FIXTURE.fixture_contracts()]
    assert FIXTURE.target_owner_refusal(owned) is None
    assert FIXTURE.target_owner_refusal([]) is None
    refusal = FIXTURE.target_owner_refusal([*owned, "customer-supply-contract-2025"])
    assert refusal is not None
    assert "customer-supply-contract-2025" not in refusal
    assert "nothing was written" in refusal


# --- fixture/domain validity -------------------------------------------------------


def test_fixture_schedules_roundtrip_through_the_canonical_decoder() -> None:
    for fixture in FIXTURE.fixture_contracts():
        document = fixture.payment_terms.canonical_document()
        decoded = ContractPaymentTerms.from_canonical_document(document)
        assert decoded == fixture.payment_terms
        assert decoded.canonical_json() == fixture.payment_terms.canonical_json()


def test_fixture_covers_explicit_and_anchored_unresolved_schedules_with_mixed_directions() -> None:
    by_kind = {fixture.schedule_kind: fixture for fixture in FIXTURE.fixture_contracts()}
    assert set(by_kind) == {"explicit_dates", "anchored_rules"}

    explicit = by_kind["explicit_dates"].payment_terms
    anchored = by_kind["anchored_rules"].payment_terms
    assert explicit.items and anchored.items
    for terms in (explicit, anchored):
        directions = {item.flow_direction for item in terms.items}
        assert directions == {PaymentFlowDirection.INFLOW, PaymentFlowDirection.OUTFLOW}

    for item in explicit.items:
        specification = item.date_specification
        assert isinstance(specification, ExplicitPaymentDate)
        assert specification.kind is PaymentDateSpecificationKind.EXPLICIT_DATE
        assert isinstance(specification.final_payable_date, date)
        assert not isinstance(specification.final_payable_date, datetime)

    for item in anchored.items:
        specification = item.date_specification
        assert isinstance(specification, AnchoredPaymentRule)
        assert specification.kind is PaymentDateSpecificationKind.ANCHORED_RULE
        needs_calendar = (
            specification.offset_day_kind is PaymentOffsetDayKind.BUSINESS_DAYS
            or specification.business_day_convention is not BusinessDayConvention.NONE
        )
        assert (specification.calendar_reference is not None) == needs_calendar


def test_fixture_evidence_is_long_synthetic_and_within_the_domain_guard() -> None:
    references: list[str] = []
    for fixture in FIXTURE.fixture_contracts():
        references.append(fixture.payment_terms.quantity_basis_reference)
        for item in fixture.payment_terms.items:
            references.append(item.source_reference)
            specification = item.date_specification
            references.append(specification.source_reference)
            calendar = getattr(specification, "calendar_reference", None)
            if calendar is not None:
                references.append(calendar)

    assert max(len(reference) for reference in references) > 400
    for reference in references:
        lowered = reference.lower()
        assert 0 < len(reference) <= MAX_PAYMENT_TERMS_TEXT_LENGTH
        assert "synthetic" in lowered
        assert "no real" in lowered or "not a real" in lowered


def test_fixture_identifiers_are_precise_stable_and_clearly_synthetic() -> None:
    fixtures = FIXTURE.fixture_contracts()
    assert [fixture.contract_id for fixture in fixtures] == [
        "uat-declared-payment-explicit-dates-v1",
        "uat-declared-payment-anchored-rules-v1",
    ]
    seen_item_ids: set[str] = set()
    for fixture in fixtures:
        assert fixture.contract_id.startswith(FIXTURE.CONTRACT_ID_PREFIX)
        assert len(fixture.contract_id) <= 128
        assert "synthetic" in fixture.contract_name.lower()
        for item in fixture.payment_terms.items:
            assert item.item_id.startswith("uat-synthetic-")
            assert len(item.item_id) <= MAX_PAYMENT_TERMS_TEXT_LENGTH
            assert item.item_id not in seen_item_ids
            seen_item_ids.add(item.item_id)


def test_fixture_payloads_satisfy_the_reviewed_request_and_repository_contracts() -> None:
    from eurogas_nexus.api.routes.public.route_cost import UpstreamContractUpsertRequest
    from eurogas_nexus.db.repositories.route_cost import _normalized_contract_values

    required_request_fields = {
        "contract_id",
        "contract_name",
        "resource_type",
        "delivery_point_name",
        "gas_year",
        "delivery_quantity_mwh_per_day",
        "contract_price_gbp_mwh",
        "settlement_frequency",
        "upstream_payment_lag_days",
        "screen_sale_cash_lag_days",
        "delivery_tolerance_pct",
        "nomination_tolerance_pct",
        "annual_financing_rate_pct",
    }
    for fixture in FIXTURE.fixture_contracts():
        payload = FIXTURE.contract_payload(fixture)
        assert required_request_fields <= set(payload)
        validated = UpstreamContractUpsertRequest.model_validate(payload)
        assert validated.contract_id == fixture.contract_id
        assert "synthetic" in (validated.notes or "").lower()
        values = _normalized_contract_values(payload)
        assert values["payment_terms_json"] == fixture.payment_terms.canonical_json()
        assert "synthetic" in str(values["notes"]).lower()


# --- the seed stays outside customer defaults and packaging ------------------------


def test_fixture_script_never_creates_schema_or_databases_or_calls_providers() -> None:
    source = SCRIPT.read_text(encoding="utf-8").lower()
    assert "create database" not in source
    assert "create_all" not in source
    assert "base.metadata" not in source
    assert "dialects.sqlite" not in source
    assert "import sqlite" not in source
    assert "import httpx" not in source
    assert "import requests" not in source


def test_fixture_cannot_enter_the_customer_deployment_bundle() -> None:
    policy = json.loads(DEPLOYMENT_BUNDLE_POLICY.read_text(encoding="utf-8"))
    for entry in policy["entries"]:
        assert not entry["source"].startswith("scripts/uat/")
        assert not entry["source"].endswith("/")
