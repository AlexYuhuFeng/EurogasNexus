"""Guard and fixture-validity contracts for the isolated declared-payment UAT seed.

`scripts/uat/seed_declared_payment_uat_fixture.py` prepares the open real-browser
declared-payment visual acceptance. Nothing in this module claims that acceptance:
the tests hold the seed script to its isolation gates (explicit PostgreSQL URL,
dedicated database-name prefix, explicit acknowledgement, explicit
development/test environment, no runtime/default target, no SQLite, no schema
creation, no provider calls), to its exact-id ownership guard, to its sanitized
driver/connection failure reporting, and to the reviewed payment-terms domain -
the schedules must round-trip through the canonical decoder, mix INFLOW/OUTFLOW,
carry long clearly synthetic evidence, and stay valid for the repository fixture
path.

No database server is touched: the in-process refusal tests prove every
configuration refusal returns before engine/session creation, and the fixture
checks call pure domain/repository helpers only. The end-to-end driver tests can
only request connections no server accepts.
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
from sqlalchemy.exc import NoSuchModuleError, OperationalError

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


def _clear_fixture_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "RUNTIME_STORE_DATABASE_URL",
        "DATABASE_URL",
        "EUROGAS_NEXUS_DB_DSN",
        "EUROGAS_NEXUS_ENV",
        "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED",
    ):
        monkeypatch.delenv(name, raising=False)


def _forbid_database_access(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace engine/session entry points with a spy that fails if reached."""

    calls: list[str] = []

    def _unexpected(**_: Any) -> Any:
        calls.append("database access")
        raise AssertionError("the refusal must happen before any database access")

    monkeypatch.setattr(FIXTURE, "get_engine", _unexpected)
    monkeypatch.setattr(FIXTURE, "get_session_factory", _unexpected)
    return calls


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


def test_environment_gate_refuses_everything_except_development_and_test() -> None:
    for allowed in ("development", "DEVELOPMENT", "  Test  ", "\tdevelopment\n"):
        assert FIXTURE.environment_refusal(allowed) is None
    for refused in (
        None,
        "",
        "   ",
        "production",
        "staging",
        "trial",
        "release",
        "prod",
        "dev",
        "preview",
        "development2",
        "test-environment",
    ):
        refusal = FIXTURE.environment_refusal(refused)
        assert refusal is not None, refused
        assert "'development'" in refusal and "'test'" in refusal
        assert "Nothing was written" in refusal


@pytest.mark.parametrize(
    "environment",
    [None, "", "   ", "production", "staging", "trial", "release", "arbitrary-value"],
)
def test_fixture_refuses_environment_before_reading_the_database_url(
    environment: str | None,
) -> None:
    env = {
        "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
        "RUNTIME_STORE_DATABASE_URL": _url("eurogas_uat_payment_visual"),
    }
    if environment is not None:
        env["EUROGAS_NEXUS_ENV"] = environment
    result = _run(env)
    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "EUROGAS_NEXUS_ENV" in output
    assert "'development'" in output and "'test'" in output
    assert "fixture-secret" not in output
    assert "postgresql://" not in output


@pytest.mark.parametrize(
    "environment",
    ["development", "Development", "  DEVELOPMENT  ", "test", "TEST", "\tTest\n"],
)
def test_fixture_accepts_only_normalized_development_or_test(environment: str) -> None:
    # With no URL the run must pass the environment gate and stop at the URL gate.
    result = _run({"EUROGAS_NEXUS_ENV": environment, "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1"})
    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "RUNTIME_STORE_DATABASE_URL" in output
    assert "must be set explicitly to 'development' or 'test'" not in output


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


@pytest.mark.parametrize(
    ("env", "arguments", "fragment"),
    [
        ({}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": ""}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": "   "}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": "production"}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": "staging"}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": "trial"}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": "release"}, (), "EUROGAS_NEXUS_ENV"),
        ({"EUROGAS_NEXUS_ENV": "arbitrary"}, (), "EUROGAS_NEXUS_ENV"),
        (
            {
                "EUROGAS_NEXUS_ENV": "development",
                "RUNTIME_STORE_DATABASE_URL": _url("eurogas_uat_payment_visual"),
            },
            (),
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED",
        ),
        (
            {"EUROGAS_NEXUS_ENV": "test", "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1"},
            (),
            "RUNTIME_STORE_DATABASE_URL",
        ),
        (
            {
                "EUROGAS_NEXUS_ENV": "test",
                "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
                "RUNTIME_STORE_DATABASE_URL": _url("eurogas_nexus"),
            },
            (),
            "default runtime database",
        ),
        (
            {
                "EUROGAS_NEXUS_ENV": "test",
                "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
                "RUNTIME_STORE_DATABASE_URL": "sqlite:///never_used.sqlite3",
            },
            (),
            "PostgreSQL",
        ),
        (
            {
                "EUROGAS_NEXUS_ENV": "test",
                "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
                "RUNTIME_STORE_DATABASE_URL": _url("eurogas_nexus_uat"),
            },
            (),
            FIXTURE.DATABASE_NAME_PREFIX,
        ),
        (
            {
                "EUROGAS_NEXUS_ENV": "test",
                "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
                "RUNTIME_STORE_DATABASE_URL": "mysql://fixture-user:fixture-secret@127.0.0.1/eurogas",
            },
            (),
            "PostgreSQL",
        ),
        (
            {
                "EUROGAS_NEXUS_ENV": "test",
                "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
                "RUNTIME_STORE_DATABASE_URL": "not a database url",
            },
            (),
            "could not be parsed",
        ),
        (
            {
                "EUROGAS_NEXUS_ENV": "test",
                "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
                "RUNTIME_STORE_DATABASE_URL": _url("eurogas_uat_payment_visual"),
            },
            ("--unexpected",),
            "Unexpected command-line arguments",
        ),
    ],
)
def test_configuration_refusals_return_before_any_database_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    env: dict[str, str],
    arguments: tuple[str, ...],
    fragment: str,
) -> None:
    calls = _forbid_database_access(monkeypatch)
    _clear_fixture_environment(monkeypatch)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    result = FIXTURE.main(list(arguments))

    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert result == FIXTURE.EXIT_CONFIGURATION_REFUSAL
    assert fragment in text
    assert calls == []
    assert "fixture-user" not in text
    assert "fixture-secret" not in text
    assert "postgresql://" not in text
    assert "Traceback" not in text


@pytest.mark.parametrize(
    "driver_error",
    [
        ModuleNotFoundError("No module named 'psycopg2'"),
        NoSuchModuleError("Can't load plugin: sqlalchemy.dialects:postgresql.notadriver"),
        OperationalError(
            "BEGIN",
            {},
            OSError(
                "connection failed for postgresql://fixture-user:fixture-secret@127.0.0.1"
                ":5432/eurogas_uat_payment_visual"
            ),
        ),
    ],
    ids=["unavailable-driver", "invalid-driver", "connection-failure"],
)
def test_engine_and_connection_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    driver_error: Exception,
) -> None:
    _clear_fixture_environment(monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "test")
    monkeypatch.setenv("EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED", "1")
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", _url("eurogas_uat_payment_visual"))

    def _raise(**_: Any) -> Any:
        raise driver_error

    monkeypatch.setattr(FIXTURE, "get_engine", _raise)

    result = FIXTURE.main([])

    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert result == FIXTURE.EXIT_DATABASE_FAILURE
    assert "could not be reached or written" in text
    assert "fixture-user" not in text
    assert "fixture-secret" not in text
    assert "postgresql://" not in text
    assert "No module named" not in text
    assert "Can't load plugin" not in text
    assert "connection failed" not in text
    assert "Traceback" not in text


@pytest.mark.parametrize(
    "driver_url",
    [
        "postgresql+notadriver://fixture-user:fixture-secret@127.0.0.1:5432/eurogas_uat_payment_visual",
        # Whether or not psycopg2 is installed, this cannot reach a database: an
        # unavailable DBAPI fails at engine creation and an installed one finds
        # no server on this port.
        "postgresql+psycopg2://fixture-user:fixture-secret@127.0.0.1:54329/eurogas_uat_payment_visual",
    ],
    ids=["invalid-driver", "unavailable-driver"],
)
def test_fixture_reports_driver_failures_without_echoing_url_or_exception(
    driver_url: str,
) -> None:
    result = _run(
        {
            "EUROGAS_NEXUS_ENV": "test",
            "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
            "RUNTIME_STORE_DATABASE_URL": driver_url,
        }
    )
    output = result.stdout + result.stderr
    assert result.returncode == 4
    assert "fixture-user" not in output
    assert "fixture-secret" not in output
    assert "postgresql://" not in output
    assert "No module named" not in output
    assert "Can't load plugin" not in output
    assert "Traceback" not in output


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


def test_owner_guard_accepts_only_the_two_exact_fixture_ids() -> None:
    owned = sorted(FIXTURE.OWNED_CONTRACT_IDS)
    assert owned == [
        "uat-declared-payment-anchored-rules-v1",
        "uat-declared-payment-explicit-dates-v1",
    ]
    assert owned == sorted(fixture.contract_id for fixture in FIXTURE.fixture_contracts())
    assert FIXTURE.target_owner_refusal([]) is None
    assert FIXTURE.target_owner_refusal(owned) is None
    assert FIXTURE.target_owner_refusal([*reversed(owned), *owned]) is None

    for foreign in (
        # Similar ids that merely share the prefix are foreign, not fixture data.
        "uat-declared-payment-explicit-dates-v2",
        "uat-declared-payment-anchored-rules-v1-extra",
        "uat-declared-payment-",
        "uat-declared-payment",
        "customer-supply-contract-2025",
    ):
        refusal = FIXTURE.target_owner_refusal([*owned, foreign])
        assert refusal is not None, foreign
        assert foreign not in refusal
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
