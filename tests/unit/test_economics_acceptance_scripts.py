"""Focused safety and fixture tests for the durable economics acceptance scripts.

These checks do not run a browser or an HTTP server. They prove that the typed
SDK example is importable, that its synthetic goldens are the documented exact
values, that its base-URL rules refuse implicit/unsafe access, and that its
refusal reporting never echoes free-text server messages. The browser script is
held to its no-mock/no-secret-file safety contract and syntax-checked when Node
is available.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_SCRIPT = ROOT / "scripts" / "examples" / "lng_capacity_economics.py"
BROWSER_SCRIPT = ROOT / "scripts" / "uat" / "economics_workflow_smoke.mjs"


def _load_example() -> ModuleType:
    """Load the example module by path without installing anything."""

    spec = importlib.util.spec_from_file_location(
        "eurogas_economics_example",
        EXAMPLE_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def example() -> ModuleType:
    """Return the imported SDK example module."""

    return _load_example()


def test_synthetic_capacity_goldens_are_exact(example: ModuleType) -> None:
    """The 23 h, 25 h and pence cases carry the documented exact expectations."""

    by_id = {case["id"]: case for case in example.CAPACITY_GOLDENS}
    assert by_id["capacity-23h"]["expected_total_cost"] == "460.0000"
    assert by_id["capacity-23h"]["expected_cost_per_delivered_mwh"] == "4.0000"
    assert by_id["capacity-23h"]["expected_duration_microseconds"] == 82_800_000_000
    assert by_id["capacity-25h"]["expected_total_cost"] == "500.0000"
    assert by_id["capacity-25h"]["expected_cost_per_delivered_mwh"] == "4.0000"
    assert by_id["capacity-25h"]["expected_duration_microseconds"] == 90_000_000_000
    assert by_id["capacity-pence-24h"]["expected_total_cost"] == "85.9848"
    assert by_id["capacity-pence-24h"]["expected_cost_per_delivered_mwh"] == "0.7165"
    assert by_id["capacity-pence-24h"]["currency"] == "GBP"
    assert by_id["capacity-pence-24h"]["tariff_unit"] == "p/(kWh/h)/h"


def test_lng_golden_money_and_energy_are_exact(example: ModuleType) -> None:
    """The LNG fixture keeps the 550/482.5 money and 7/3/10 energy split."""

    golden = example.LNG_GOLDEN
    assert golden["expected_purchase_outlay_eur"] == "2000.0000"
    assert golden["expected_sale_proceeds_eur"] == "2700.0000"
    assert golden["expected_downstream_costs_eur"] == "150.0000"
    assert golden["expected_cargo_margin_eur"] == "550.0000"
    assert golden["expected_net_present_value_eur"] == "482.5000"
    assert golden["expected_total_undiscounted_cash_eur"] == "550.0000"
    assert golden["expected_total_consumed_energy_mwh"] == "7"
    assert golden["expected_physical_loss_energy_mwh"] == "3"
    assert golden["expected_total_reduction_energy_mwh"] == "10"
    assert golden["expected_physical_readiness"] == "NOT_ASSESSED"


def test_lng_typed_request_preserves_fixture_exactness(example: ModuleType) -> None:
    """The typed request contains the explicit staged chain and discount factors."""

    request = example._lng_request()
    assert request.purchased_energy_mwh == "100"
    assert request.delivered_energy_mwh == "90"
    assert request.purchase_unit_price_eur_per_mwh == "20"
    assert request.sale_unit_price_eur_per_mwh == "30"
    assert len(request.energy_stages) == 2
    consumed = sum(
        Decimal(stage.consumed_energy_mwh) for stage in request.energy_stages
    )
    loss = sum(
        Decimal(stage.physical_loss_energy_mwh) for stage in request.energy_stages
    )
    assert consumed == Decimal("7")
    assert loss == Decimal("3")
    assert request.energy_stages[0].input_energy_mwh == "100"
    assert request.energy_stages[-1].output_energy_mwh == "90"
    assert len(request.discount_factors) == 2
    assert request.discount_factors[-1].factor == "0.975"
    assert request.downstream_costs[0].amount_eur == "150"

    broken = example._lng_request(break_conservation=True)
    assert broken.energy_stages[0].physical_loss_energy_mwh == "2"


def test_base_url_requires_explicit_loopback_or_https_uat(
    example: ModuleType,
) -> None:
    """No base URL is defaulted; remote access needs an explicit HTTPS opt-in."""

    with pytest.raises(example.ConfigurationError):
        example.resolve_api_base_url({})

    origin, remote = example.resolve_api_base_url(
        {"EUROGAS_UAT_API_BASE_URL": "http://127.0.0.1:8000"}
    )
    assert origin == "http://127.0.0.1:8000"
    assert remote is False

    with pytest.raises(example.ConfigurationError):
        example.resolve_api_base_url(
            {"EUROGAS_UAT_API_BASE_URL": "https://uat.example.invalid"}
        )
    with pytest.raises(example.ConfigurationError):
        example.resolve_api_base_url(
            {
                "EUROGAS_UAT_API_BASE_URL": "http://uat.example.invalid",
                "EUROGAS_UAT_ALLOW_NON_LOOPBACK": "1",
            }
        )
    with pytest.raises(example.ConfigurationError):
        example.resolve_api_base_url(
            {
                "EUROGAS_UAT_API_BASE_URL": "https://user:secret@uat.example.invalid",
                "EUROGAS_UAT_ALLOW_NON_LOOPBACK": "1",
            }
        )
    with pytest.raises(example.ConfigurationError):
        example.resolve_api_base_url(
            {"EUROGAS_UAT_API_BASE_URL": "http://127.0.0.1:8000/api"}
        )

    origin, remote = example.resolve_api_base_url(
        {
            "EUROGAS_UAT_API_BASE_URL": "https://uat.example.invalid",
            "EUROGAS_UAT_ALLOW_NON_LOOPBACK": "1",
        }
    )
    assert origin == "https://uat.example.invalid"
    assert remote is True


def test_refusal_summary_drops_free_text_and_keeps_stable_codes(
    example: ModuleType,
) -> None:
    """A refusal summary contains no echoed message, secret or raw response text."""

    request = httpx.Request(
        "POST",
        "http://127.0.0.1:8000/api/research/capacity-billing",
        headers={"Authorization": "Bearer secret-bearer-value"},
    )
    response = httpx.Response(
        422,
        request=request,
        json={
            "detail": {
                "code": "capacity_billing_refused",
                "message": "echo secret-bearer-value and raw detail",
                "codes": ["BILLED_CAPACITY_ENERGY_INCONSISTENT"],
                "violations": [
                    {
                        "code": "BILLED_CAPACITY_ENERGY_INCONSISTENT",
                        "detail": "secret-bearer-value",
                    }
                ],
            }
        },
    )
    summary = example.refusal_summary(response)
    assert summary == {
        "status": 422,
        "code": "capacity_billing_refused",
        "codes": ["BILLED_CAPACITY_ENERGY_INCONSISTENT"],
    }
    encoded = json.dumps(summary)
    assert "secret-bearer-value" not in encoded
    assert "echo" not in encoded
    assert "violations" not in encoded


def test_sdk_mode_is_explicit(example: ModuleType) -> None:
    """The example reports the imported SDK as source or installed, never blank."""

    assert example.sdk_mode() in {"source", "installed"}


def test_missing_config_emits_clean_json_without_traceback(
    example: ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing API base URL fails cleanly and sends no request."""

    assert example.main({}) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "CONFIG_INVALID"
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_browser_script_has_no_mock_money_or_secret_harness() -> None:
    """The browser script keeps timing-only interception and no secret-file assumptions."""

    source = BROWSER_SCRIPT.read_text(encoding="utf-8")
    assert "route.continue()" in source
    assert "route.fulfill" not in source
    assert "browser-runtime-secrets" not in source
    assert ".local-runtime" not in source
    assert "readFileSync(local" not in source
    assert "EUROGAS_NEXUS_DEV_LOGIN_USERNAME" in source
    assert "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD" in source
    assert "EUROGAS_UAT_BASE_URL" in source
    assert "EUROGAS_UAT_PLAYWRIGHT_PATH" in source
    assert "EUROGAS_UAT_OUTPUT_DIR" in source
    assert "EUROGAS_UAT_AXE_PATH" in source
    assert "Control+Enter" in source
    assert "zh-CN" in source
    assert "1440" in source
    assert "390" in source
    assert "STAGE_CONSERVATION_FAILED" in source
    assert "BILLED_CAPACITY_ENERGY_INCONSISTENT" in source


def test_browser_script_syntax_when_node_is_available() -> None:
    """Node parses the browser module when the repository's Node runtime exists."""

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available on PATH")
    completed = subprocess.run(
        [node, "--check", str(BROWSER_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
