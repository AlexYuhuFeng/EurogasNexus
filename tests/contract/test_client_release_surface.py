"""Client release-surface contracts for Web and Windows shells."""



from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]





def test_windows_client_wraps_shared_web_workspace() -> None:

    config = json.loads(

        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(

            encoding="utf-8"

        )

    )



    assert config["build"]["frontendDist"] == "../../web/dist"

    assert config["build"]["beforeBuildCommand"] == "npm --prefix ../web run build"

    assert config["build"]["devUrl"] == "http://127.0.0.1:3000"

    assert config["app"]["windows"][0]["label"] == "main"

    assert config["app"]["windows"][0]["decorations"] is False

    assert config["app"]["windows"][0]["fullscreen"] is True

    assert config["app"]["windows"][0]["visible"] is False

    assert config["bundle"]["active"] is True





def test_windows_client_uses_startup_splash_window() -> None:

    config = json.loads(

        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(

            encoding="utf-8"

        )

    )

    main_rs = (

        ROOT / "clients" / "desktop" / "src-tauri" / "src" / "main.rs"

    ).read_text(encoding="utf-8")



    windows = {window["label"]: window for window in config["app"]["windows"]}

    assert windows["splashscreen"]["visible"] is True

    assert windows["splashscreen"]["decorations"] is False

    assert windows["splashscreen"]["fullscreen"] is False

    assert 'get_webview_window("main")' in main_rs

    assert 'get_webview_window("splashscreen")' in main_rs

    assert "main_window.show()" in main_rs

    assert "splashscreen.close()" in main_rs





def test_windows_client_has_minimal_safe_permissions() -> None:

    capability = json.loads(

        (ROOT / "clients" / "desktop" / "src-tauri" / "capabilities" / "default.json")

        .read_text(encoding="utf-8")

    )

    config_text = (

        ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json"

    ).read_text(encoding="utf-8")



    assert capability["permissions"] == ["core:default"]

    assert "postgres" not in config_text.lower()

    assert "DATABASE_URL" not in config_text

    assert ".env" not in config_text

    assert (

        "connect-src 'self' http://localhost:* http://127.0.0.1:* "

        "https://tile.openstreetmap.org" in config_text

    )

    assert "img-src 'self' data: blob: https://tile.openstreetmap.org" in config_text





def test_client_dependency_policy_excludes_disallowed_frameworks() -> None:

    web_package = json.loads(

        (ROOT / "clients" / "web" / "package.json").read_text(encoding="utf-8")

    )

    desktop_package = json.loads(

        (ROOT / "clients" / "desktop" / "package.json").read_text(encoding="utf-8")

    )

    names = set(web_package.get("dependencies", {}))

    names |= set(web_package.get("devDependencies", {}))

    names |= set(desktop_package.get("dependencies", {}))

    names |= set(desktop_package.get("devDependencies", {}))



    forbidden = {

        "electron",

        "next",

        "tailwindcss",

        "@mui/material",

        "antd",

        "bootstrap",

        "redux",

    }

    assert names.isdisjoint(forbidden)

    assert "@tauri-apps/cli" in names





def test_ci_builds_web_windows_and_linux_clients() -> None:

    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")



    assert "web-client-build" in workflow

    assert "desktop-client-build" in workflow

    assert "windows-latest" in workflow

    assert "ubuntu-latest" in workflow
    assert "ubuntu-24.04-arm" in workflow
    assert "linux-arm64" in workflow

    assert "--bundles ${{ matrix.bundle }}" in workflow

    assert "clients/desktop/src-tauri/target/release/bundle/nsis/*.exe" in workflow

    assert "clients/desktop/src-tauri/target/release/bundle/deb/*.deb" in workflow





def test_web_client_uses_api_only_and_supports_mandarin_theme() -> None:

    api_client = (

        ROOT / "clients" / "web" / "src" / "api" / "client.ts"

    ).read_text(encoding="utf-8")

    vite_env = (

        ROOT / "clients" / "web" / "src" / "vite-env.d.ts"

    ).read_text(encoding="utf-8")

    zh = json.loads(

        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")

    )

    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    topbar = (
        ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.tsx"
    ).read_text(encoding="utf-8")
    settings_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SettingsCenter.tsx"
    ).read_text(encoding="utf-8")
    app_and_settings = app + topbar + settings_center



    assert 'const DEFAULT_BROWSER_BASE = "/api";' in api_client

    assert 'const DEFAULT_DESKTOP_BASE = "http://127.0.0.1:8000/api";' in api_client

    assert "VITE_EUROGAS_API_BASE_URL" in api_client

    assert "__TAURI_INTERNALS__" in api_client

    assert "tauri.localhost" in api_client

    assert "VITE_EUROGAS_API_BASE_URL" in vite_env

    assert "__TAURI_INTERNALS__" in vite_env

    vite_config = (ROOT / "clients" / "web" / "vite.config.ts").read_text(
        encoding="utf-8"
    )

    assert '"/api": "http://127.0.0.1:8000"' in vite_config

    assert "http://localhost:8000" not in vite_config

    assert "postgres" not in api_client.lower()

    assert "RUNTIME_STORE_DATABASE_URL" not in api_client

    assert zh["nav.sources"] == "\u6570\u636e\u6e90\u4e2d\u5fc3"

    assert zh["theme.dark"] == "\u6df1\u8272"

    assert '<option value="zh-CN">{t("settings.chinese")}</option>' in app_and_settings





def test_web_client_matches_design_reference_cockpit() -> None:

    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    topbar = (
        ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.tsx"
    ).read_text(encoding="utf-8")
    source_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SourceCenter.tsx"
    ).read_text(encoding="utf-8")
    contract_workbench = (
        ROOT / "clients" / "web" / "src" / "components" / "ContractWorkbench.tsx"
    ).read_text(encoding="utf-8")
    network_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "NetworkWorkspace.tsx"
    ).read_text(encoding="utf-8")
    capacity_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "CapacityWorkspace.tsx"
    ).read_text(encoding="utf-8")
    app_and_topbar = app + topbar
    app_and_components = (
        app + topbar + source_center + contract_workbench + network_workspace + capacity_workspace
    )

    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    en = json.loads(

        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")

    )

    zh = json.loads(

        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")

    )



    assert "cockpit-topbar" in app_and_topbar

    assert "workflow-strip" not in app

    assert "scenario-rail" in network_workspace

    assert "decision-rail" in network_workspace

    assert "trade-result-panel" in network_workspace

    assert "topbar-search" in app_and_topbar
    assert "topbar-icon-button" not in app
    assert "workspace-nav" not in app
    assert "workspace-menu" in topbar
    assert "workspaceMenuOpen" not in app
    assert "groupedMenuOpen" in topbar
    assert "workspace-pill-copy" in app_and_topbar
    assert "topbar-menu-glyph" in app_and_topbar
    assert "workspace-page" in app
    assert '"capacity"' in app
    assert '"orders"' in app
    assert '"manual"' in app
    assert 'activeWorkspace === "capacity"' in app
    assert 'activeWorkspace === "market"' in app
    assert 'activeWorkspace === "contracts"' in app
    assert 'activeWorkspace === "review"' in app
    assert 'activeWorkspace === "orders"' in app
    assert 'activeWorkspace === "glossary"' in app
    assert 'activeWorkspace === "manual"' in app
    assert "resourcePoolOptimizationRequest" in app
    assert "optimizeResourcePool(resourcePoolOptimizationRequest)" in app
    assert "lastAutoOptimizerSignatureRef" in app
    assert "autoOptimizerSignature" in app
    assert "void optimizeResourcePool(resourcePoolOptimizationRequest)" in app
    assert "canRunPoolOptimizer" in app
    assert "poolInputBlockers" in app
    assert "runtimeDbReady" in app
    assert "blocker_runtime_db" in app
    assert "efet-section-grid" in app_and_components
    assert "map-overlay" not in app
    assert "topology-status-panel" not in app
    assert "network-operations-panel" not in app
    assert "data-health-panel" not in app
    assert "networkGeometryMissing" not in app
    assert "approximateNodeCount" not in app
    assert "map-node-legend" not in app
    assert "decision-signal-panel" in network_workspace
    assert "capacity-page" in capacity_workspace
    assert "review-page" in app
    assert "orders-page" in app
    assert "manual-page" in app
    assert "review-report-panel" in app
    assert "manual-step-list" in css
    map_component = (

        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"

    ).read_text(encoding="utf-8")

    assert "fallback-network-map map-ready" in map_component
    assert 'NavigationControl({ visualizePitch: true }), "top-right"' in map_component
    assert "coordinate_quality" in map_component
    assert "data_quality" in map_component
    assert "node-color-legend" in css
    assert "map-network-warning" in css
    assert "filter: grayscale" not in css
    assert "fallback-network-map.map-ready" in css
    assert "cockpit-app:not(.workspace-network) .decision-rail" in css
    assert "cockpit-app:not(.workspace-network) .scenario-rail" in css
    assert "mobile-cockpit-qa" in css
    assert "grid-template-areas" in css
    assert "topbar-controls" in css
    assert "max-height: min(44vh, 360px)" in css
    assert "Resource-pool home cleanup" in css
    assert ".workspace-network .map-price-strip" in css
    assert "source-runtime-panel" in app_and_components
    assert "map-data-panel" in network_workspace
    assert "map-network-state" in network_workspace
    assert "networkGeometryState" in app

    assert "tile.openstreetmap.org" in map_component

    assert "osm-raster" in map_component

    assert "--eg-ink: #171717" in css

    assert "--eg-canvas-soft: #fafafa" in css

    assert en["scenario.title"] == "Scenario Builder"

    assert zh["scenario.title"] == "\u60c5\u666f\u6784\u5efa\u5668"
    assert en["nav.capacity"] == "Capacity"
    assert zh["nav.capacity"] == "\u7ba1\u5bb9"


def test_web_client_release_cockpit_chrome_is_clean_and_color_coded() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    network_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "NetworkWorkspace.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    assert "release-cockpit-override" in css
    assert "workspace-topbar-only" in css
    assert "map-layer-chip compact" in network_workspace
    assert "aria-pressed={activeLayers.includes(layer)}" in network_workspace
    assert "MapLibre controls sit outside both decision rails" in css
    assert "route_candidate" in map_component
    assert 'edge.source_system === "route_candidate"' in map_component
    assert 'metadata.materialization === "route_candidate_edge"' in map_component
    assert "line-opacity" in map_component
    assert "--eg-map-pipeline" in css
    assert "--eg-map-lng" in css
    assert "--eg-map-interconnector" in css
    assert "--eg-map-hub" in css
    assert "Network, Market, Scenario" not in app
    assert en["nav.contracts"] == "Contracts"
    assert zh["nav.contracts"] == "\u5408\u540c"
    assert en["nav.orders"] == "Market Positioning"
    assert zh["nav.orders"] == "\u5e02\u573a\u5b9a\u4f4d"
    assert en["nav.manual"] == "Manual"
    assert zh["nav.manual"] == "\u7528\u6237\u624b\u518c"
    assert en["home.resource_pool"] == "Resource pool"
    assert zh["home.resource_pool"] == "\u8d44\u6e90\u6c60"

    assert en["result.route_alpha"] == "Route alpha ladder"

    assert zh["result.route_alpha"] == "\u8def\u5f84\u6536\u76ca\u9636\u68af"
    assert en["map.network_warning_title"] == "Pipeline geometry not loaded"
    assert zh["map.network_warning_title"] == "\u7ba1\u7ebf\u51e0\u4f55\u672a\u52a0\u8f7d"
    assert en["map.runtime_missing_body"].startswith("Runtime PostgreSQL")
    assert zh["map.runtime_missing_body"].startswith("\u8fd0\u884c PostgreSQL")
    assert en["map.coordinate_quality"] == "Coordinate quality"
    assert zh["map.coordinate_quality"] == "\u5750\u6807\u8d28\u91cf"
    assert en["map.approximate_points"] == "Approx. coords"
    assert zh["map.approximate_points"] == "\u8fd1\u4f3c\u5750\u6807"


def test_web_client_separates_market_capacity_orders_and_review_pages() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    capacity_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "CapacityWorkspace.tsx"
    ).read_text(encoding="utf-8")
    navigation = (
        ROOT / "clients" / "web" / "src" / "workspaceNavigation.ts"
    ).read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "export const workspacePageIds" in navigation
    for page in [
        "network", "capacity", "market", "scenario", "contracts", "strategy",
        "review", "orders", "sources", "glossary", "runtime", "settings", "manual",
    ]:
        assert f'"{page}"' in navigation
    assert "function workspaceFromLocation(): WorkspacePageId" in app
    assert 'new URLSearchParams(window.location.search).get("workspace")' in app
    assert "coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID)" in app
    assert "const WORKSPACE_PAGES" not in app
    assert 'nextUrl.searchParams.set("workspace", page)' in app
    assert "window.history.pushState({ workspace: page }, \"\", nextUrl)" in app
    assert 'window.addEventListener("popstate", syncWorkspaceFromUrl)' in app
    assert app.index('activeWorkspace === "capacity"') < app.index('activeWorkspace === "market"')
    assert app.index('activeWorkspace === "review"') < app.index('activeWorkspace === "orders"')
    assert app.index('className="data-table orders-table"') > app.index(
        'activeWorkspace === "orders"'
    )
    assert "capacity.tso_coverage" in capacity_workspace
    assert "capacity.tariffs" in capacity_workspace
    assert "capacity-operating-table" in capacity_workspace
    assert "capacity-point-inspector" in capacity_workspace
    assert "const PAGE_SIZE = 100" in capacity_workspace
    assert "capacity-pagination" in capacity_workspace
    assert "capacity-readiness-note" in capacity_workspace
    assert "Company TSO access and executable booking availability" in en[
        "capacity.readiness_available"
    ]
    assert "\u516c\u53f8 TSO \u51c6\u5165" in zh["capacity.readiness_available"]
    assert "reviewWarnings" in app
    assert "review-report-panel" in app
    assert "manual.no_client_db" in app
    assert en["market.subtitle"].startswith("Terminal view")
    assert zh["market.subtitle"].startswith("\u9762\u5411\u6b27\u6d32\u4e3b\u8981")
    assert en["orders.subtitle"].startswith("Read-only")
    assert zh["orders.subtitle"].startswith("\u53ea\u8bfb")


def test_web_client_market_page_is_trader_terminal_surface() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    store = (ROOT / "clients" / "web" / "src" / "stores" / "api.ts").read_text(
        encoding="utf-8"
    )
    market_terminal_path = ROOT / "clients" / "web" / "src" / "components" / "MarketTerminal.tsx"
    market_terminal = market_terminal_path.read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert 'import { MarketTerminal } from "@/components/MarketTerminal";' in app
    assert (
        "<MarketTerminal\n"
        in app
    )
    assert "marketLastUpdatedAtUtc" in app
    assert "refreshMarketData" in app
    assert "MARKET_REFRESH_INTERVAL_MS" in app
    assert "marketLastUpdatedAtUtc: string | null" in store
    assert "refreshMarketData: () => Promise<void>" in store
    assert "api.marketObservations()" in store
    assert "api.fxRates()" in store
    assert "market-terminal-board" in market_terminal
    assert "market-price-ticker" in market_terminal
    assert "market-region-comparison" in market_terminal
    assert "market-sparkline" in market_terminal
    assert "market-source-quality" in market_terminal
    assert "activeTenor" in market_terminal
    assert "setActiveTenor" in market_terminal
    assert "market-tenor-tab active" in market_terminal
    assert "market-source-matrix" in market_terminal
    assert "sourceMatrixRows" in market_terminal
    assert "update_interval_seconds" in market_terminal
    assert "market-live-status" in market_terminal
    assert "lastUpdatedAtUtc" in market_terminal
    assert "marketMajorHubs" in market_terminal
    assert "TTF" in market_terminal
    assert "NBP" in market_terminal
    assert "THE" in market_terminal
    assert "PEG" in market_terminal
    assert "ZTP" in market_terminal
    assert "PSV" in market_terminal
    assert "priceSourceSummary" in market_terminal
    assert "marketUnavailableRows" in market_terminal
    assert "market-terminal-board" in css
    assert "market-price-ticker" in css
    assert "market-region-comparison" in css
    assert "market-sparkline" in css
    assert "market-source-quality" in css
    assert ".market-tenor-tab.active" in css
    assert ".market-source-matrix" in css
    assert ".market-live-status" in css
    assert en["market.title"] == "Gas Market Terminal"
    assert en["market.terminal"] == "Major European gas markets"
    assert en["market.region_comparison"] == "Regional comparison"
    assert en["market.source_matrix"] == "Source matrix"
    assert en["market.live_polling"] == "Live polling"
    assert en["market.live_exchange_prices"].startswith("Exchange and broker")
    assert zh["market.terminal"] == "\u6b27\u6d32\u4e3b\u8981\u5929\u7136\u6c14\u5e02\u573a"


def test_web_client_strategy_page_is_shadow_run_terminal() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    strategy_terminal_path = (
        ROOT / "clients" / "web" / "src" / "components" / "StrategyShadowRunTerminal.tsx"
    )
    strategy_sections_path = (
        ROOT
        / "clients"
        / "web"
        / "src"
        / "components"
        / "strategy"
        / "StrategyShadowRunSections.tsx"
    )
    strategy_terminal = strategy_terminal_path.read_text(encoding="utf-8")
    strategy_sections = strategy_sections_path.read_text(encoding="utf-8")
    strategy_surface = strategy_terminal + strategy_sections
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(
        encoding="utf-8"
    )

    assert (
        'import { StrategyShadowRunTerminal } from "@/components/StrategyShadowRunTerminal";'
        in app
    )
    assert "<StrategyShadowRunTerminal" in app
    assert "strategyScenario={strategyScenario}" in app
    assert "strategyResult={strategyResult}" in app
    assert "portfolioResources={portfolioResources}" in app
    assert "marketObservations={contextMarkets}" in app
    assert "fxRates={fxRates}" in app
    assert "language={i18n.language}" in app
    assert "onEvaluate={() => evaluateStrategyLab(strategyScenario)}" in app
    assert "strategy-shadow-run-terminal" in strategy_terminal
    assert (
        'from "@/components/strategy/StrategyShadowRunSections"'
        in strategy_terminal
    )
    assert "strategy-command-deck" in strategy_terminal
    assert "strategy-price-basis-board" in strategy_surface
    assert "strategy-price-basis-selector" in strategy_surface
    assert "strategy-basis-option" in strategy_surface
    assert "strategy-price-basis-card" in strategy_surface
    assert "strategy-basis-exposure-ladder" in strategy_surface
    assert "strategy-basis-exposure-row" in strategy_surface
    assert "strategy-pnl-curve" in strategy_surface
    assert "strategy-pnl-scenario-comparison" in strategy_terminal
    assert "strategy-pnl-curve-row" in strategy_surface
    assert "strategy-contract-pnl-attribution" in strategy_surface
    assert "strategy-contract-pnl-row" in strategy_surface
    assert "strategy-data-quality-banner" in strategy_surface
    assert "strategy-data-quality-flags" in strategy_terminal
    assert 'useState<PriceBasisId>("WITHIN_DAY")' in strategy_terminal
    assert "onSelectBasis={setActiveBasis}" in strategy_terminal
    assert "onSelectBasis(row.basis)" in strategy_sections
    assert "aria-pressed={activeBasis === row.basis}" in strategy_surface
    assert "priceBasisRows" in strategy_terminal
    assert "pnlCurveRows" in strategy_terminal
    assert "basisExposureRows" in strategy_terminal
    assert "basisMarginVsPoolCost" in strategy_terminal
    assert "poolQuantityMwhPerDay" in strategy_terminal
    assert "weightedPoolCostGbpMwh" in strategy_terminal
    assert "activeBasisRow" in strategy_terminal
    assert 'activeBasis === "FX" ? null' in strategy_terminal
    assert "activePnlRow" in strategy_terminal
    assert "contractPnlRows" in strategy_terminal
    assert "hasSelectedContractPnl" in strategy_terminal
    assert "simulatedBasisCount" in strategy_terminal
    assert "staleBasisCount" in strategy_terminal
    assert "unavailableBasisCount" in strategy_terminal
    assert "classifyPriceBasis" in strategy_terminal
    assert "isSimulatedSource" in strategy_terminal
    assert "isStaleObservation" in strategy_terminal
    assert "language: string" in strategy_terminal
    assert "Intl.DateTimeFormat(language.startsWith" in strategy_terminal
    assert "fxRates" in strategy_terminal
    assert "WITHIN_DAY" in strategy_terminal
    assert "DAY_AHEAD" in strategy_terminal
    assert "MONTHLY" in strategy_terminal
    assert "ICIS_ASSESSMENT" in strategy_terminal
    assert "ICE_OCM_MARK" in strategy_terminal
    assert "EEX_CURVE" in strategy_terminal
    assert "FX" in strategy_terminal
    assert "strategy-market-tape" in strategy_terminal
    assert "strategy-paper-state" in strategy_terminal
    assert "strategy-allocation-ladder" in strategy_terminal
    assert "strategy-risk-stack" in strategy_terminal
    assert "strategy-source-evidence" in strategy_terminal
    assert "strategy-warning-stack" in strategy_terminal
    assert "strategy-candidate-action" in strategy_terminal
    assert "source_refs" in strategy_terminal
    assert "candidate_action_for_review" in strategy_terminal
    assert "portfolioResources" in strategy_terminal
    assert "marketObservations" in strategy_terminal
    assert "human_review_required" in strategy_terminal
    assert "sourceSystems.join" in strategy_sections
    assert "StrategyBasisExposureLadder" in strategy_sections
    assert "StrategyPriceBasisBoard" in strategy_sections
    assert "StrategyPnlCurvePanel" in strategy_sections
    assert "StrategyContractPnlAttribution" in strategy_sections
    assert "strategy-shadow-run-terminal" in css
    assert "strategy-price-basis-board" in css
    assert "strategy-price-basis-selector" in css
    assert "strategy-basis-option" in css
    assert "strategy-basis-exposure-ladder" in css
    assert "strategy-basis-exposure-row" in css
    assert "strategy-pnl-curve" in css
    assert "strategy-pnl-scenario-comparison" in css
    assert "strategy-contract-pnl-attribution" in css
    assert "strategy-contract-pnl-row" in css
    assert "strategy-data-quality-banner" in css
    assert "strategy-data-quality-flags" in css
    assert "strategy-market-tape" in css
    assert "strategy-allocation-ladder" in css
    assert "strategy-candidate-action" in css
    assert en["strategy.shadow_terminal"] == "Strategy shadow-run terminal"
    assert en["strategy.price_basis_board"] == "Price-basis comparison"
    assert en["strategy.basis_exposure_ladder"] == "Basis exposure ladder"
    assert en["strategy.pool_pnl_at_risk"] == "Pool PnL at risk"
    assert en["strategy.margin_vs_pool_cost"] == "Margin vs pool cost"
    assert en["strategy.pnl_curve"] == "Resource-pool PnL curve"
    assert en["strategy.selected_price_basis"] == "Selected price basis"
    assert en["strategy.contract_pnl_attribution"] == "Contract PnL attribution"
    assert en["strategy.unavailable_basis_count"] == "Unavailable bases"
    assert en["strategy.simulated_data"] == "Simulated data"
    assert en["strategy.stale_data"] == "Stale data"
    assert en["strategy.market_tape"] == "Market tape"
    assert en["strategy.paper_state"] == "Paper state"
    assert en["strategy.no_execution"] == "No execution"
    assert zh["strategy.shadow_terminal"] == "\u7b56\u7565\u5f71\u5b50\u8fd0\u884c\u7ec8\u7aef"
    assert zh["strategy.price_basis_board"] == "\u4ef7\u683c\u57fa\u51c6\u5bf9\u6bd4"
    assert zh["strategy.basis_exposure_ladder"] == "\u57fa\u51c6\u66b4\u9732\u9636\u68af"
    assert zh["strategy.pool_pnl_at_risk"] == "\u8d44\u6e90\u6c60\u98ce\u9669 PnL"
    assert zh["strategy.margin_vs_pool_cost"] == (
        "\u76f8\u5bf9\u8d44\u6e90\u6c60\u6210\u672c\u5229\u5dee"
    )
    assert zh["strategy.pnl_curve"] == "\u8d44\u6e90\u6c60 PnL \u66f2\u7ebf"
    assert zh["strategy.selected_price_basis"] == "\u9009\u5b9a\u4ef7\u683c\u57fa\u51c6"
    assert zh["strategy.contract_pnl_attribution"] == "\u5408\u7ea6 PnL \u5f52\u56e0"
    assert "shadow-run terminal" in web_spec
    assert "market tape, paper state, allocation ladder" in web_spec
    assert "price-basis comparison board" in web_spec
    assert "basis exposure ladder" in web_spec
    assert "selected price-basis control" in web_spec
    assert "contract-level PnL attribution" in web_spec
    assert "stale/simulated/unavailable data banner" in web_spec
    assert "resource-pool PnL curve" in web_spec
    assert (
        "within-day, day-ahead, monthly, ICIS assessments, ICE OCM marks, "
        "EEX curves, and ECB FX"
    ) in web_spec


def test_web_client_settings_page_is_trader_preference_center() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    settings_center_path = ROOT / "clients" / "web" / "src" / "components" / "SettingsCenter.tsx"
    settings_center = settings_center_path.read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert 'import { SettingsCenter } from "@/components/SettingsCenter";' in app
    assert "<SettingsCenter" in app
    assert "settings-preference-center" in settings_center
    assert "settings-unit-panel" in settings_center
    assert "settings-service-panel" in settings_center
    assert "settings-boundary-panel" in settings_center
    assert "default_currency" in settings_center
    assert "energy_unit" in settings_center
    assert "session_timezone" in settings_center
    assert "price_basis" in settings_center
    assert "eurogas.settings.preferences" in settings_center
    assert "credentialProviders" in settings_center
    assert "onOpenSources" in settings_center
    assert "settings-preference-center" in css
    assert "settings-service-row" in css
    assert en["settings.default_currency"] == "Default currency"
    assert en["settings.energy_unit"] == "Energy unit"
    assert en["settings.service_access"] == "Service access"
    assert zh["settings.default_currency"] == "\u9ed8\u8ba4\u8d27\u5e01"
    assert zh["settings.energy_unit"] == "\u80fd\u91cf\u5355\u4f4d"


def test_web_client_network_page_shows_resource_pool_paths_on_map() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    network_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "NetworkWorkspace.tsx"
    ).read_text(encoding="utf-8")
    resource_pool_paths = (
        ROOT / "clients" / "web" / "src" / "app" / "resourcePoolMapPaths.ts"
    ).read_text(encoding="utf-8")
    overlay_path = ROOT / "clients" / "web" / "src" / "components" / "ResourcePoolPathOverlay.tsx"
    overlay = overlay_path.read_text(encoding="utf-8")
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(
        encoding="utf-8"
    )

    assert 'ResourcePoolPathOverlay,' in network_workspace
    assert "buildResourcePoolMapPaths" in app
    assert "<ResourcePoolPathOverlay" in network_workspace
    assert "resourcePoolMapPaths" in app
    assert "highlightedRoute={resourcePoolHighlightedRoute" in app
    assert "highlightedRoute={highlightedRoute}" in network_workspace
    assert "resource-pool-map-overlay" in overlay
    assert "resource-path-card" in overlay
    assert "resource-path-flow" in overlay
    assert "sourcePointName" in overlay
    assert "targetPointName" in overlay
    assert "availableQuantityMwhPerDay" in overlay
    assert "routeCostGbpMwh" in overlay
    assert "capacityLimitMwhPerDay" in overlay
    assert "resource-pool-allocation-summary" in overlay
    assert "resource-route-status-legend" in overlay
    assert "resource-path-allocation-evidence" in overlay
    assert "resource-path-capacity-warning" in overlay
    assert "resource-path-recommendation-evidence" in overlay
    assert "resource-route-state-pill" in overlay
    assert "routeRank" in overlay
    assert "recommendationReason" in overlay
    assert "capacityUtilizationPct" in overlay
    assert "requiredTsoAccess" in overlay
    assert "home.route_rank" in overlay
    assert "home.recommendation_reason" in overlay
    assert "home.capacity_utilization" in overlay
    assert "home.required_tso_access" in overlay
    assert "paths.slice(0, 3)" in overlay
    assert "hiddenPathCount" in overlay
    assert "home.more_route_paths" in overlay
    assert "weightedNetMargin" in overlay
    assert "capacityHeadroomMwhPerDay" in overlay
    assert "poolSharePct" in overlay
    assert "pnlGbpPerDay" in overlay
    assert "saleOptions.map((option)" in resource_pool_paths
    assert "rankedResourcePoolMapPaths" in resource_pool_paths
    assert "statePriority" in resource_pool_paths
    assert "indicativeNetMarginGbpMwh" in resource_pool_paths
    assert "resource.contract_cost_gbp_mwh" in resource_pool_paths
    assert "resolveRouteGeometryState" in resource_pool_paths
    assert "resolveRouteGeometryWarning" in resource_pool_paths
    assert "buildNodeIdByPointName" in resource_pool_paths
    assert "buildHighlightedResourcePoolRoute" in resource_pool_paths
    assert "saleOptions.slice(0, 3).map" not in app
    assert "rankedResourcePoolMapPaths" not in app
    assert "resource-pool-map-overlay" in css
    assert "resource-path-card" in css
    assert ".resource-pool-allocation-summary" in css
    assert ".resource-route-status-legend" in css
    assert ".resource-path-allocation-evidence" in css
    assert ".resource-path-recommendation-evidence" in css
    assert ".resource-path-capacity-warning" in css
    assert ".resource-route-state-pill" in css
    assert ".resource-path-more" in css
    assert "max-height: min(42vh, 380px)" in css
    assert "verifiedEdgeGeometryCoordinates" in map_component
    assert "fallback-flow-path direct-corridor" not in map_component
    assert en["home.resource_paths"] == "Resource paths"
    assert en["home.pool_allocation"] == "Pool allocation"
    assert en["home.route_status_legend"] == "Route status"
    assert en["home.capacity_bottleneck"] == "Capacity bottleneck"
    assert en["home.route_rank"] == "Route rank"
    assert en["home.recommendation_reason"] == "Recommendation reason"
    assert en["home.capacity_utilization"] == "Capacity utilization"
    assert en["home.required_tso_access"] == "Required TSO access"
    assert en["home.more_route_paths"] == "more route candidates in decision rail"
    assert en["home.pnl_per_day"] == "PnL/day"
    assert en["home.route_state.allocated"] == "Allocated"
    assert en["home.route_state.candidate"] == "Candidate"
    assert en["home.route_state.blocked"] == "Blocked"
    assert en["home.path_unavailable"].startswith("No persisted resource")
    assert zh["home.resource_paths"] == "\u8d44\u6e90\u8def\u5f84"
    assert zh["home.pool_allocation"] == "\u8d44\u6e90\u6c60\u5206\u914d"
    assert zh["home.route_status_legend"] == "\u8def\u5f84\u72b6\u6001"
    assert zh["home.capacity_bottleneck"] == "\u5bb9\u91cf\u74f6\u9888"
    assert zh["home.route_rank"] == "\u8def\u5f84\u6392\u540d"
    assert zh["home.recommendation_reason"] == "\u63a8\u8350\u7406\u7531"
    assert zh["home.capacity_utilization"] == "\u5bb9\u91cf\u4f7f\u7528\u7387"
    assert zh["home.required_tso_access"] == "\u6240\u9700 TSO \u51c6\u5165"
    assert zh["home.more_route_paths"] == (
        "\u6761\u66f4\u591a\u5019\u9009\u8def\u5f84\u5728\u53f3\u4fa7\u51b3\u7b56\u680f"
    )
    assert "pool allocation summary" in web_spec
    assert "route status legend" in web_spec
    assert "route ranking evidence" in web_spec
    assert "capacity utilization" in web_spec
    assert "required TSO access" in web_spec
    assert "capacity bottleneck" in web_spec
    assert "path-level PnL/day" in web_spec


def test_web_client_map_fallback_prioritizes_labels_for_trader_readability() -> None:
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )

    assert "MAX_MAP_LABELS" in map_component
    assert "MAJOR_HUB_PRIORITY" in map_component
    assert "priorityLabelNodes" in map_component
    assert "map-node-label" in map_component
    assert "fallbackLabelPriorityIds" in map_component
    assert "shouldShowFallbackNodeLabel" in map_component
    assert "isSearchLabelMatch" in map_component
    assert "highlightedRoutePoints.from.id" in map_component
    assert "highlightedRoutePoints.to.id" in map_component
    assert "node.node_type === \"hub\"" in map_component
    assert "fallback-node-label priority" in map_component
    assert "{shouldShowFallbackNodeLabel(node, index) && (" in map_component
    assert ".fallback-node-label" in css
    assert ".fallback-node-label.priority" in css
    assert ".fallback-node.approximate .fallback-node-label" in css


def test_web_client_map_renders_resource_paths_as_route_segments_not_direct_lines() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    resource_pool_paths = (
        ROOT / "clients" / "web" / "src" / "app" / "resourcePoolMapPaths.ts"
    ).read_text(encoding="utf-8")
    map_path_surface = app + resource_pool_paths
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    overlay = (
        ROOT / "clients" / "web" / "src" / "components" / "ResourcePoolPathOverlay.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    web_spec = (ROOT / "docs" / "clients" / "MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md").read_text(
        encoding="utf-8"
    )

    assert "routeId: option.option_id" in resource_pool_paths
    assert "resolveRouteGeometryState" in resource_pool_paths
    assert "buildRouteGeometryEdgesByRouteId" in resource_pool_paths
    assert "geometry_quality" in resource_pool_paths
    assert "unmatched_route_leg_count" in resource_pool_paths
    assert "buildHighlightedResourcePoolRoute" in map_path_surface
    assert "routeId" in overlay
    assert "routeGeometryState" in overlay
    assert "routeGeometryLabel" in overlay
    assert "routeGeometryWarning" in overlay
    assert "routeLegSummary" in overlay
    assert "routeSegmentsForHighlight" in map_component
    assert "highlightedRouteSegmentFeatures" in map_component
    assert "route_leg_sequence" in map_component
    assert "route_geometry_state" in map_component
    assert "geometry_quality" in map_component
    assert "routeGeometryStateLabel" in map_component
    assert "not surveyed pipeline geometry" in map_component
    assert "highlighted-route-segments" in map_component
    assert "fallback-flow-segment" in map_component
    assert "fallback-flow-path direct-corridor" not in map_component
    assert "verifiedEdgeGeometryCoordinates" in map_component
    assert "geometryCoordinates" in map_component
    assert "geometryWarning" in map_component
    assert "source_derived_leg_sequence" in map_component
    assert "directLineFallback" in map_component
    assert ".fallback-flow-segment" in css
    assert ".fallback-flow-path.direct-corridor" in css
    assert ".fallback-flow.segmented.corridor" in css
    assert ".resource-path-geometry.warning" in css
    assert "route geometry" in css
    assert "successful geometry" in web_spec
    assert "does not draw a source-to-target" in web_spec


def test_web_client_glossary_page_is_term_wiki_surface() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    glossary_wiki_path = ROOT / "clients" / "web" / "src" / "components" / "GlossaryWiki.tsx"
    glossary_wiki = glossary_wiki_path.read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(
        encoding="utf-8"
    )

    assert 'import { GlossaryWiki } from "@/components/GlossaryWiki";' in app
    assert "<GlossaryWiki" in app
    assert "selectedGlossaryTerm" in app
    assert "setSelectedGlossaryTerm" in app
    assert "onSelectGlossaryTerm" in app
    assert "visibleGlossaryCategories" in app
    assert "glossary-codex-shell" in glossary_wiki
    assert "glossary-left-rail" in glossary_wiki
    assert "glossary-wiki-shell" in glossary_wiki
    assert 't("glossary.all")' in glossary_wiki
    assert "glossary-category-tabs" in glossary_wiki
    assert "glossary-term-list" in glossary_wiki
    assert "glossary-term-card" in glossary_wiki
    assert "glossary-wiki-article" in glossary_wiki
    assert "glossary-wiki-context" in glossary_wiki
    assert "glossary-related-chip" in glossary_wiki
    assert "glossary-source-list" in glossary_wiki
    assert "context_sections" in glossary_wiki
    assert "matched_entities" in glossary_wiki
    assert "related_sources" in glossary_wiki
    assert "data_quality" in glossary_wiki
    assert "onSelectTerm(term)" in glossary_wiki
    assert "selectedTerm?.term_id === term.term_id" in glossary_wiki
    assert "consistent backend-served vocabulary" in web_spec
    assert "glossary-wiki-shell" in css
    assert "glossary-codex-shell" in css
    assert "glossary-left-rail" in css
    assert "glossary-wiki-article" in css
    assert "glossary-term-card.active" in css
    assert en["glossary.term_wiki"] == "Term wiki"
    assert en["glossary.all"] == "All"
    assert en["glossary.operational_context"] == "Operational context"
    assert en["glossary.source_refs"] == "Source references"
    assert zh["glossary.term_wiki"] == "\u672f\u8bed\u7ef4\u57fa"
    assert zh["glossary.all"] == "\u5168\u90e8"
    assert zh["glossary.operational_context"] == "\u8fd0\u884c\u4e0a\u4e0b\u6587"
    assert "wiki-style article" in web_spec
    assert "institutions, entities, venues, business models" in web_spec


def test_web_client_glossary_context_values_do_not_render_raw_objects() -> None:
    glossary_wiki = (
        ROOT / "clients" / "web" / "src" / "components" / "GlossaryWiki.tsx"
    ).read_text(encoding="utf-8")

    assert "function displayContextObject" in glossary_wiki
    assert "function objectRecord" in glossary_wiki
    assert '"entity_name"' in glossary_wiki
    assert '"point_name"' in glossary_wiki
    assert '"route_name"' in glossary_wiki
    assert '"contract_name"' in glossary_wiki
    assert '"source_reference"' in glossary_wiki
    assert '"source_system"' in glossary_wiki
    assert "entity.name ?? entity.term ?? entity.id ?? entity" not in glossary_wiki
    assert "item.label ?? item.name ?? item.source_reference ?? item" not in glossary_wiki


def test_web_client_glossary_keeps_article_visible_while_browsing_terms() -> None:
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )

    assert ".glossary-codex-shell" in css
    assert ".glossary-wiki-shell" in css
    assert (
        "grid-template-columns: minmax(320px, 0.82fr) minmax(620px, 1.58fr)"
    ) in css
    assert "max-height: calc(100vh - 150px)" in css
    assert "overflow-y: auto" in css
    assert "position: sticky" in css
    assert "top: calc(var(--eg-topbar-height) + 32px)" in css
    assert "@media (max-width: 1200px)" in css
    assert ".glossary-wiki-shell {" in css
    assert (
        "grid-template-columns: minmax(300px, 0.78fr) minmax(520px, 1.42fr)"
    ) in css
    assert "@media (max-width: 900px)" in css
    assert "max-height: none" in css
    assert "position: static" in css


def test_web_client_contracts_page_is_upload_and_manual_intake_workbench() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    workbench_path = ROOT / "clients" / "web" / "src" / "components" / "ContractWorkbench.tsx"
    workbench = workbench_path.read_text(encoding="utf-8")
    contract_import = (
        ROOT / "clients" / "web" / "src" / "app" / "contractImport.ts"
    ).read_text(encoding="utf-8")
    contract_payload = (
        ROOT / "clients" / "web" / "src" / "app" / "contractPayload.ts"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(
        encoding="utf-8"
    )

    assert 'import { ContractWorkbench } from "@/components/ContractWorkbench";' in app
    assert "<ContractWorkbench" in app
    assert 'import type { ContractDraft } from "@/app/index";' in app
    app_and_workbench = app + workbench
    assert "counterparty" in app_and_workbench
    assert "title_transfer_point" in app_and_workbench
    assert "beach_delivery_point" in app_and_workbench
    assert "index_basis" in app_and_workbench
    assert "terminal_access" in app_and_workbench
    assert "capacity_expiry" in app_and_workbench
    assert "document_name" in app_and_workbench
    assert "parseContractTextDraft" in contract_import
    assert "contractRecordFromImportedFile" in app
    assert "decision_support_only" in contract_payload
    assert "human_review_required" in contract_payload

    for token in [
        "contract-intake-workbench",
        "contract-upload-zone",
        "contract-manual-editor",
        "contract-library-panel",
        "contract-detail-preview",
        "efet-clause-map",
        "beach-delivery-strip",
        "contract-source-evidence",
        "contract-warning-stack",
        "contractImportRef",
        "importContractDraftFile",
        "loadPersistedContract",
        "saveDraftContract(contractPayload)",
        ".json,.txt,.pdf,.doc,.docx",
        't("contracts.upload_contract")',
        't("contracts.beach_delivery")',
        't("contracts.title_transfer_point")',
        't("contracts.document_status")',
    ]:
        assert token in workbench

    for token in [
        ".contract-intake-workbench",
        ".contract-upload-zone",
        ".contract-manual-editor",
        ".contract-library-panel",
        ".contract-detail-preview",
        ".efet-clause-map",
        ".beach-delivery-strip",
        ".contract-source-evidence",
        ".contract-warning-stack",
    ]:
        assert token in css

    assert en["contracts.upload_contract"] == "Upload contract"
    assert en["contracts.beach_delivery"] == "Beach delivery"
    assert en["contracts.counterparty"] == "Counterparty"
    assert en["contracts.title_transfer_point"] == "Title transfer point"
    assert en["contracts.document_status"] == "Document status"
    assert zh["contracts.upload_contract"] == "\u4e0a\u4f20\u5408\u540c"
    assert zh["contracts.beach_delivery"] == "\u6d77\u5cb8\u4ea4\u4ed8"
    assert zh["contracts.counterparty"] == "\u5bf9\u624b\u65b9"
    assert zh["contracts.title_transfer_point"] == "\u6743\u5c5e\u8f6c\u79fb\u70b9"
    assert zh["contracts.document_status"] == "\u6587\u4ef6\u72b6\u6001"
    assert "upload zone" in web_spec
    assert "title-transfer point" in web_spec
    assert "beach delivery point" in web_spec


def test_web_client_sources_page_is_categorized_source_center() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    source_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SourceCenter.tsx"
    ).read_text(encoding="utf-8")
    app_and_source_center = app + source_center
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    derived_data = (
        ROOT / "clients" / "web" / "src" / "app" / "workspaceDerivedData.ts"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "source-category-filter" in app_and_source_center
    assert "source-operations-table" in app_and_source_center
    assert "source-diagnostics" in app_and_source_center
    assert "source-next-action" in app_and_source_center
    assert "source-diagnostic-action" in app_and_source_center
    assert "sourceNextAction" in app_and_source_center
    assert "selectedSource" in app_and_source_center
    assert "credential_state" in app_and_source_center
    assert "last_success_at_utc" in app_and_source_center
    assert "connectivity_status" in app_and_source_center
    assert "SOURCE_CATEGORY_ORDER" in derived_data
    for category in ["price", "fx", "infrastructure", "tariff", "weather", "ai"]:
        assert f'"{category}"' in derived_data
    assert "buildSourcePostureRows" in app
    assert "categoryProviderSummary" in app
    assert "normalizeSourceSystem" in api_client
    assert "SOURCE_CATEGORY_BY_SYSTEM" in api_client
    assert (
        'sources: () => get<SourceSystemWire[]>("/sources").then(normalizeSourcesResponse)'
        in api_client
    )
    assert "source-center" in css
    assert "runtime-blocker-list" in css
    assert en["nav.sources"] == "Data Sources"
    assert en["sources.title"] == "Data Source Center"
    assert en["sources.next_action"] == "Next action"
    assert en["sources.action.run_ingestion"].startswith("Run the source ingestion")
    assert zh["sources.title"] == "\u6570\u636e\u6e90\u4e2d\u5fc3"
    assert zh["sources.next_action"] == "\u4e0b\u4e00\u6b65\u52a8\u4f5c"


def test_web_client_market_terminal_surfaces_simulated_source_and_tenor_context() -> None:
    market_terminal = (
        ROOT / "clients" / "web" / "src" / "components" / "MarketTerminal.tsx"
    ).read_text(encoding="utf-8")
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "metadata_json?: Record<string, unknown>" in api_client
    assert "source_record_id?: string | null" in api_client
    assert "EEX_Sim" in api_client
    assert "ICE_OCM_Sim" in api_client
    assert "Trayport_Sim" in api_client
    assert "ICIS_Sim" in api_client
    assert "market-tenor-tabs" in market_terminal
    assert "market-source-pill" in market_terminal
    assert "market-curve-lanes" in market_terminal
    assert "marketTenorOrder" in market_terminal
    assert "price_timing" in market_terminal
    assert "metadata_json" in market_terminal
    assert ".market-tenor-tabs" in css
    assert ".market-source-pill.simulated" in css
    assert ".market-curve-lanes" in css
    assert en["market.tenor_within_day"] == "Within-day"
    assert en["market.tenor_day_ahead"] == "Day-ahead"
    assert en["market.tenor_month_ahead"] == "Month-ahead"
    assert en["market.simulated_source"] == "Simulated source"
    assert zh["market.tenor_within_day"] == "\u65e5\u5185"
    assert zh["market.tenor_day_ahead"] == "\u65e5\u524d"
    assert zh["market.tenor_month_ahead"] == "\u6708\u524d"
    assert zh["market.simulated_source"] == "\u4eff\u771f\u6570\u636e\u6e90"


def test_source_center_surfaces_preview_substitute_feeds() -> None:
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    source_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SourceCenter.tsx"
    ).read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "preview_substitute_source_system: string | null" in api_client
    assert "preview_substitute_status: string | null" in api_client
    assert "preview_substitute_record_count: number" in api_client
    assert "selectedSource.preview_substitute_source_system" in source_center
    assert "sources.preview_substitute" in source_center
    assert "sources.preview_substitute_active" in source_center
    assert "sources.diagnostic.preview_substitute_active" in en
    assert en["sources.preview_substitute"] == "Preview substitute"
    assert zh["sources.preview_substitute"] == "\u9884\u89c8\u66ff\u4ee3\u6e90"


def test_source_center_shows_category_operational_posture_board() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    source_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SourceCenter.tsx"
    ).read_text(encoding="utf-8")
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "source_posture_summary" in api_client
    assert "SourceCategoryPostureDTO" in api_client
    assert "sourcePostureRows" in app
    assert "sourcePostureRows={sourcePostureRows}" in app
    assert "source-posture-board" in source_center
    assert "source-posture-row" in source_center
    assert "sources_needing_attention" in source_center
    assert "sources.posture_board" in source_center
    assert "source-operations-table" in source_center
    assert "source-posture-board" in css
    assert "source-posture-row" in css
    assert en["sources.posture_board"] == "Operational source posture"
    assert en["sources.preview_substitutes_active"] == "Preview substitutes"
    assert zh["sources.posture_board"] == "\u8fd0\u884c\u6570\u636e\u6e90\u6001\u52bf"
    assert zh["sources.preview_substitutes_active"] == "\u9884\u89c8\u66ff\u4ee3\u6e90"


def test_web_client_mobile_topbar_constrains_controls_to_viewport() -> None:
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(
        encoding="utf-8"
    )

    assert "@media (max-width: 900px)" in css
    assert ".cockpit-app .cockpit-topbar > *" in css
    assert "max-width: 100%" in css
    assert "min-width: 0" in css
    assert "flex-wrap: wrap" in css
    assert "minmax(0, 1fr)" in css


def test_web_client_resource_pool_options_are_backend_owned() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
    network_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "NetworkWorkspace.tsx"
    ).read_text(encoding="utf-8")
    contract_workbench = (
        ROOT / "clients" / "web" / "src" / "components" / "ContractWorkbench.tsx"
    ).read_text(encoding="utf-8")
    app_and_contracts = app + contract_workbench
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    store = (ROOT / "clients" / "web" / "src" / "stores" / "api.ts").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert (
        'resourcePoolOptions: () => get<ResourcePoolOptionsDTO>'
        '("/route-cost/resource-pool/options")'
    ) in api_client
    assert "resourcePoolOptions: ResourcePoolOptionsDTO | null" in store
    assert "resourcePoolOptions?.sale_options ?? []" in app
    assert "resourcePoolOptions?.portfolio_resources ?? []" in app
    assert "resourcePoolOptions?.blockers ?? []" in app
    assert "sale_price_source_system?: string | null" in api_client
    assert "sale_price_simulated?: boolean" in api_client
    assert "sale_price_source_family?: string | null" in api_client
    assert "sale_price_simulated ? t(\"market.simulated_source\")" in network_workspace
    assert "saveUpstreamContract" in api_client
    assert "saveDraftContract" in store
    assert "saveDraftContract(contractPayload)" in app_and_contracts
    assert "contractSaveMessage" in app
    assert "contract-library-panel" in app_and_contracts
    assert "contract-library-row" in app_and_contracts
    assert "contract-import-input" in app_and_contracts
    assert "importContractDraftFile" in app_and_contracts
    assert "loadPersistedContract" in app_and_contracts
    assert "contractDraftFromRecord" in app
    assert en["contracts.library"] == "Contract library"
    assert en["contracts.import_json"] == "Import JSON"
    assert zh["contracts.library"] == "\u5408\u540c\u5e93"
    assert zh["contracts.import_json"] == "\u5bfc\u5165 JSON"
    assert "nbp-via-bbl" not in app
    assert "cheap-nbp-route" not in app
    assert "alternate-cross-border" not in app
    assert "operator-test" not in app
    assert "operator-sale-option" not in app


def test_local_seed_uses_preview_provenance_not_operator_test_names() -> None:
    legacy_seed_script = ROOT / "scripts" / "ops" / "seed_operator_test_data.py"
    legacy_demo_seed_script = ROOT / "scripts" / "ops" / "seed_demo_runtime_data.py"
    seed_script_path = ROOT / "scripts" / "ops" / "seed_preview_runtime_data.py"

    assert not legacy_seed_script.exists()
    assert not legacy_demo_seed_script.exists()
    seed_script = seed_script_path.read_text(
        encoding="utf-8"
    )

    assert "demo_market_price" not in seed_script
    assert "upsert_simulated_market_observations" in seed_script
    assert "EEX_Sim" in seed_script
    assert "ICE_OCM_Sim" in seed_script
    assert "Trayport_Sim" in seed_script
    assert "ICIS_Sim" in seed_script
    assert "preview-portfolio-contract-ttf-pool-2025" in seed_script
    assert "LEGACY_FIXTURE_CONTRACT_IDS" in seed_script
    assert "demo-portfolio-contract-ttf-pool-2025" in seed_script
    assert "_clear_previous_preview_rows" in seed_script
    assert "_seed_preview_contract" in seed_script
    assert "public-route-ttf-bbl-nbp" in seed_script
    assert "public_route_template" in seed_script
    assert "materialize_route_candidate_edges" in seed_script
    assert "_clear_previous_demo_rows" not in seed_script
    assert "_seed_demo_contract" not in seed_script
    assert "demo-route" not in seed_script
    assert "demo_route_template" not in seed_script
    assert "operator-owned test" not in seed_script
    assert "operator-entered-test" not in seed_script
    assert "operator test contract" not in seed_script


def test_seed_preview_runtime_script_runs_directly_without_db_url() -> None:
    env = os.environ.copy()
    env.pop("RUNTIME_STORE_DATABASE_URL", None)
    env.pop("DATABASE_URL", None)
    env.pop("EUROGAS_NEXUS_DB_DSN", None)

    result = subprocess.run(
        [sys.executable, "scripts/ops/seed_preview_runtime_data.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Runtime DB URL missing" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_release_workflow_publishes_web_windows_and_linux_assets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "on:" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow
    assert "contents: write" in workflow
    assert "gh release create" in workflow
    assert "eurogas-nexus-web-${GITHUB_SHA::7}.tar.gz" in workflow
    assert "bundle: nsis" in workflow
    assert "bundle: deb" in workflow
    assert "*.exe" in workflow
    assert "*.deb" in workflow
    assert (
        "pytest -q tests/api tests/contract tests/integration tests/sdk "
        "tests/cli tests/release tests/security"
    ) in workflow
    build_ps1 = (ROOT / "scripts" / "release" / "build_release.ps1").read_text(
        encoding="utf-8"
    )
    assert "npm --prefix $WebDir run build" in build_ps1
    assert "npm --prefix $DesktopDir run build -- --bundles $Bundle" in build_ps1
    build_sh = (ROOT / "scripts" / "release" / "build_release.sh").read_text(
        encoding="utf-8"
    )
    assert 'npm --prefix "${WEB_DIR}" run build' in build_sh
    assert 'npm --prefix "${DESKTOP_DIR}" run build -- --bundles "${BUNDLE}"' in build_sh
