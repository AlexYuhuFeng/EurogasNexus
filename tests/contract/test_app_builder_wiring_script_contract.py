"""Contract tests for the App builder wiring script."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "apply_app_builder_wiring.py"


def test_app_builder_wiring_script_is_conservative() -> None:
    """The wiring script should fail closed and verify the final App.tsx contract."""

    script_text = SCRIPT.read_text(encoding="utf-8-sig")
    for phrase in [
        "Expected exactly one",
        "refusing to edit App.tsx",
        "refusing to write",
        "buildContractPayload(contract)",
        "buildResourcePoolOptimizationRequest(contract, portfolioResources, saleOptions, upstreamContracts)",
        "buildRouteRecommendationRequest(portfolioResources, saleOptions, totalPoolVolume, upstreamContracts)",
        "buildStrategyScenario(contract, liveMark, markets, portfolioResources)",
        "APP_IMPORT",
        "codecs.BOM_UTF8",
    ]:
        assert phrase in script_text


def test_app_builder_wiring_script_targets_expected_app_blocks() -> None:
    """The script should cover the four extracted request/builder blocks."""

    script_text = SCRIPT.read_text(encoding="utf-8-sig")
    for pattern_name in [
        "RESOURCE_POOL_PATTERN",
        "CONTRACT_PAYLOAD_PATTERN",
        "STRATEGY_SCENARIO_PATTERN",
        "ROUTE_RECOMMENDATION_PATTERN",
    ]:
        assert pattern_name in script_text
