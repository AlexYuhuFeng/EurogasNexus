"""Trader-facing client correctness and UX boundary contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "clients" / "web" / "src"
APPLICATION_FILES = [
    WEB / "App.tsx",
    *sorted((WEB / "app" / "hooks").glob("*.ts")),
    *sorted((WEB / "app" / "model").glob("*.ts")),
    *sorted((WEB / "app" / "shell").glob("*.tsx")),
    *sorted((WEB / "app" / "workspaces").glob("*.tsx")),
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _read_application() -> str:
    return "\n".join(_read(path) for path in APPLICATION_FILES)


def test_strategy_prices_are_currency_normalized_and_not_zero_fallbacks() -> None:
    normalization = _read(WEB / "app" / "marketPriceNormalization.ts")
    scenario = _read(WEB / "app" / "strategyScenario.ts")
    terminal = _read(WEB / "components" / "StrategyShadowRunTerminal.tsx")
    app = _read_application()

    assert "export function convertCurrency" in normalization
    assert "buildLatestCurrencyGraph" in normalization
    assert 'convertCurrency(observation.price, observation.currency, "GBP", rates)' in normalization
    assert "marketPriceGbpMwh(observation, fxRates)" in scenario
    assert "latestPositiveObservation" in scenario
    assert "Math.max(nbpPrice - 0.4, 0)" not in scenario
    assert "const nbpPrice" not in scenario
    assert "marketPriceGbpMwh(item, fxRates)" in terminal
    assert "isGasPriceObservation(item)" in terminal
    assert (
        "buildStrategyScenario(" in app
    )
    assert "api.fxRates" in app


def test_frontend_runtime_business_data_is_api_owned() -> None:
    app = _read_application()
    store = _read(WEB / "stores" / "api.ts")
    network = _read(WEB / "components" / "NetworkWorkspace.tsx")

    assert "useApiStore()" in app
    assert "resourcePoolOptions?.sale_options ?? []" in app
    assert "resourcePoolOptions?.portfolio_resources ?? []" in app
    trading_context = _read(WEB / "app" / "tradingContext.ts")
    assert "api.markets.filter(" in app
    assert "marketMatchesTradingContext" in trading_context
    assert "saleOptions = [" not in app
    assert "portfolioResources = [" not in app
    assert "marketObservations = [" not in app
    assert "fetchWorkspace" in store
    assert "sale_price_simulated" in network
    assert not list(WEB.rglob("*fixture*.json"))
    assert not list(WEB.rglob("*mock*.json"))


def test_route_overlay_is_compact_by_default_and_details_are_accessible() -> None:
    overlay = _read(WEB / "components" / "ResourcePoolPathOverlay.tsx")
    css = _read(WEB / "styles" / "app.css")

    assert "useState(false)" in overlay
    assert "aria-expanded={detailsOpen}" in overlay
    assert "detailsOpen && (" in overlay
    assert 't("home.show_path_details")' in overlay
    assert 't("home.hide_path_details")' in overlay
    assert ".resource-path-detail-stack" in css


def test_topbar_controls_and_source_credentials_have_accessible_names() -> None:
    topbar = _read(WEB / "components" / "WorkspaceTopBar.tsx")
    source_center = _read(WEB / "components" / "SourceCenter.tsx")

    assert 'aria-label={t("settings.language")}' in topbar
    assert 'aria-label={t("settings.appearance")}' in topbar
    assert 'aria-label={t("panel.credentials")}' in source_center
    assert 'aria-label={t("credentials.api_key")}' in source_center


def test_settings_distinguish_public_sources_from_missing_credentials() -> None:
    settings = _read(WEB / "components" / "SettingsCenter.tsx")

    assert "if (!provider.credential_required)" in settings
    assert 'return t("credentials.not_required")' in settings
    assert 'provider.configured ? t("settings.configured")' in settings


def test_visible_literal_translation_keys_exist_in_both_locales() -> None:
    component_text = "\n".join(_read(path) for path in WEB.rglob("*.tsx"))
    literal_keys = {
        match
        for match in re.findall(r'\bt\(["\']([^"\']+)["\']\)', component_text)
        if "${" not in match
    }
    for locale in ["en", "zh"]:
        translations = json.loads(_read(WEB / "i18n" / f"{locale}.json"))
        assert literal_keys <= translations.keys()
        assert not {
            key: value
            for key, value in translations.items()
            if isinstance(value, str) and ("?" in value or "\ufffd" in value)
        }


def test_network_geometry_does_not_overstate_route_corridor_coverage() -> None:
    derived = _read(WEB / "app" / "workspaceDerivedData.ts")
    app = _read_application()
    network_workspace = _read(WEB / "components" / "NetworkWorkspace.tsx")
    map_component = _read(WEB / "components" / "GasNetworkMap.tsx")

    assert '"corridors_only"' in derived
    assert 'edge.source_system === "route_candidate"' in derived
    assert 'metadata.materialization === "route_candidate_edge"' in derived
    assert 'metadata.verification_status !== "verified"' in derived
    assert "VERIFIED_GEOMETRY_AUTHORITIES" in derived
    assert "geometry_coordinates" in derived
    assert "verifiedEdgeGeometryCoordinates" in map_component
    assert "fallback-flow-path direct-corridor" not in map_component
    assert 't("map.route_corridors_only")' in network_workspace
    assert "<NetworkWorkspace" in app
    assert "MAJOR_HUB_PRIORITY" in map_component
    assert "map-node-label" in map_component
    assert "cluster: true" in map_component
    assert 'id: "node-clusters"' in map_component


def test_app_no_longer_owns_duplicate_workspace_menu() -> None:
    app = _read_application()
    topbar = _read(WEB / "components" / "WorkspaceTopBar.tsx")

    assert "workspaceMenuOpen" not in app
    assert "const WORKSPACE_PAGES" not in app
    assert 'from "@/workspaceNavigation"' in app
    assert "groupedMenuOpen" in topbar
    assert "[legacyProp: string]" not in topbar


def test_strategy_freshness_uses_latest_observation_per_basis() -> None:
    strategy_terminal = _read(WEB / "components" / "StrategyShadowRunTerminal.tsx")

    assert "staleCount: latest && isStaleObservation(" in strategy_terminal
    assert "staleCount: latestFx && isStaleObservation(" in strategy_terminal
    assert "staleCount: observations.filter" not in strategy_terminal
    assert "staleCount: fxRates.filter" not in strategy_terminal


def test_source_credentials_follow_selected_public_source() -> None:
    app = _read_application()

    assert "credentialProviderIdForSource(selectedSource, credentialProviders)" in app
    assert "provider.provider_id.toLocaleLowerCase() === sourceSystem" in app
    assert 'useState("")' in app


def test_network_workspace_is_extracted_from_app_shell() -> None:
    app = _read_application()
    network_workspace = _read(WEB / "components" / "NetworkWorkspace.tsx")

    assert "<NetworkWorkspace" in app
    assert "scenario-rail" not in app
    assert "decision-rail" not in app
    assert "scenario-rail" in network_workspace
    assert "decision-rail" in network_workspace
    assert len(_read(WEB / "App.tsx").splitlines()) <= 20


def test_secondary_workspaces_are_extracted_from_app_shell() -> None:
    app = _read_application()

    for component in [
        "ScenarioWorkspace",
        "ReviewWorkspace",
        "MarketPositioningWorkspace",
        "RuntimeWorkspace",
        "ManualWorkspace",
    ]:
        assert f"<{component}" in app
        assert (WEB / "components" / f"{component}.tsx").is_file()

    for page_class in [
        "scenario-page",
        "review-page",
        "orders-page",
        "runtime-page",
        "manual-page",
    ]:
        assert page_class not in app


def test_client_backend_url_is_runtime_configurable_and_safe() -> None:
    api_client = _read(WEB / "api" / "client.ts")
    settings = _read(WEB / "components" / "SettingsCenter.tsx")

    assert "normalizeApiBaseUrl" in api_client
    assert 'parsed.protocol !== "https:"' in api_client
    assert 'parsed.hostname === "127.0.0.1"' in api_client
    assert 'parsed.hostname === "localhost"' in api_client
    assert "expected JSON but received" in api_client
    assert "invalid JSON response" in api_client
    assert "testApiBaseUrl(value)" in settings
    assert "const health = await testApiBaseUrl(value)" in settings
    assert "saveApiBaseUrl(value)" in settings
    assert "settings.backend_api_url" in settings
    assert "DATABASE_URL" not in settings
