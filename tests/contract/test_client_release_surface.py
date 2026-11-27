"""Client release-surface contracts for Web and Windows shells."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from eurogas_nexus.release.versioning import parse_app_version
from eurogas_nexus.version import APPLICATION_VERSION

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "clients" / "web" / "src"


def _read_application_source() -> str:
    """Read the composition root and its explicit application-layer owners."""

    paths = [WEB_SRC / "App.tsx"]
    paths.extend(sorted((WEB_SRC / "app" / "hooks").glob("*.ts")))
    paths.extend(sorted((WEB_SRC / "app" / "model").glob("*.ts")))
    paths.extend(sorted((WEB_SRC / "app" / "shell").glob("*.tsx")))
    paths.extend(sorted((WEB_SRC / "app" / "workspaces").glob("*.tsx")))
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_release_versions_are_aligned() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    cargo = tomllib.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    )
    tauri = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )
    web = json.loads((ROOT / "clients" / "web" / "package.json").read_text(encoding="utf-8"))
    desktop = json.loads(
        (ROOT / "clients" / "desktop" / "package.json").read_text(encoding="utf-8")
    )

    # pyproject holds the PEP 440 spelling (1.0.0b1) of the SemVer the others hold.
    assert parse_app_version(pyproject["project"]["version"]).semver == APPLICATION_VERSION
    assert {
        cargo["package"]["version"],
        tauri["version"],
        web["version"],
        desktop["version"],
    } == {APPLICATION_VERSION}


def test_desktop_workstation_shares_business_ui_with_native_window_controls() -> None:

    config = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )

    assert config["build"]["frontendDist"] == "../../web/dist"

    assert config["build"]["beforeBuildCommand"] == "npm --prefix ../web run build"

    assert config["build"]["devUrl"] == "http://127.0.0.1:3000"

    assert "--port 3000 --strictPort" in config["build"]["beforeDevCommand"]

    assert config["app"]["windows"][0]["label"] == "main"

    assert config["app"]["windows"][0]["decorations"] is True

    assert config["app"]["windows"][0]["fullscreen"] is False

    assert config["app"]["windows"][0]["visible"] is False

    assert config["bundle"]["active"] is True
    assert config["bundle"]["windows"]["webviewInstallMode"]["type"] == "downloadBootstrapper"
    assert config["bundle"]["windows"]["nsis"]["installMode"] == "perMachine"


def test_windows_client_uses_startup_splash_window() -> None:

    config = json.loads(
        (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )

    main_rs = (ROOT / "clients" / "desktop" / "src-tauri" / "src" / "main.rs").read_text(
        encoding="utf-8"
    )

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
        (ROOT / "clients" / "desktop" / "src-tauri" / "capabilities" / "default.json").read_text(
            encoding="utf-8"
        )
    )

    config_text = (ROOT / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
        encoding="utf-8"
    )

    assert capability["permissions"] == ["core:default"]

    assert "postgres" not in config_text.lower()

    assert "DATABASE_URL" not in config_text

    assert ".env" not in config_text

    assert "connect-src 'self' http://localhost:* http://127.0.0.1:* https:" in config_text

    # Map tiles come from the service the customer chooses (their own, or one they license),
    # so images may load from any HTTPS host; scripts still load only from the bundle, and
    # plugins, framing and foreign form targets are refused.
    assert "img-src 'self' data: blob: https:;" in config_text
    assert "script-src 'self';" in config_text
    assert "object-src 'none'" in config_text
    assert "frame-ancestors 'none'" in config_text


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
    import yaml

    workflows = ROOT / ".github" / "workflows"
    ci = yaml.safe_load((workflows / "ci.yml").read_text(encoding="utf-8"))
    jobs = ci["jobs"]

    # The Web build stays in ordinary CI and still installs/builds the shared
    # React/npm client from its lock file.
    web_steps = jobs["web-client-build"]["steps"]
    web_runs = {(step.get("working-directory"), step.get("run")) for step in web_steps}
    assert ("clients/web", "npm ci") in web_runs
    assert ("clients/web", "npm run build") in web_runs
    web_package = json.loads(
        (ROOT / "clients" / "web" / "package.json").read_text(encoding="utf-8")
    )
    web_dependencies = {
        **web_package.get("dependencies", {}),
        **web_package.get("devDependencies", {}),
    }
    assert "react" in web_dependencies

    # CI delegates the native build to the reviewed reusable workflow; the
    # caller is unconditional and carries no inline matrix, env or steps.
    desktop = jobs["desktop-client-build"]
    assert desktop["uses"] == "./.github/workflows/native-acceptance.yml"
    assert "if" not in desktop
    assert "strategy" not in desktop
    assert "env" not in desktop
    assert "secrets" not in desktop
    assert "steps" not in desktop

    sdk = jobs["sdk-installed"]
    assert sdk["uses"] == "./.github/workflows/sdk-acceptance.yml"
    assert (workflows / "sdk-acceptance.yml").is_file()

    native = yaml.safe_load((workflows / "native-acceptance.yml").read_text(encoding="utf-8"))
    native_job = native["jobs"]["native-build"]
    matrix = native_job["strategy"]["matrix"]["include"]
    expected_matrix = {
        "windows-x64": (
            "windows-2025",
            "nsis",
            "clients/desktop/src-tauri/target/release/bundle/nsis/*.exe",
        ),
        "linux-x64": (
            "ubuntu-24.04",
            "deb",
            "clients/desktop/src-tauri/target/release/bundle/deb/*.deb",
        ),
        "linux-arm64": (
            "ubuntu-24.04-arm",
            "deb",
            "clients/desktop/src-tauri/target/release/bundle/deb/*.deb",
        ),
    }
    actual_matrix = {
        entry["artifact_label"]: (
            entry["os"],
            entry["bundle"],
            entry["package_glob"],
        )
        for entry in matrix
    }
    assert len(matrix) == len(expected_matrix) == 3
    assert actual_matrix == expected_matrix

    steps = native_job["steps"]
    actions = [step["uses"] for step in steps if "uses" in step]
    assert actions
    for action in actions:
        if action.startswith("./"):
            continue
        _, separator, ref = action.rpartition("@")
        assert separator and len(ref) == 40, action
        assert all(character in "0123456789abcdef" for character in ref), action
    assert any(action.startswith("dtolnay/rust-toolchain@6c977a6") for action in actions)

    linux_setup = [
        step
        for step in steps
        if step.get("run") == "bash scripts/ci/install_linux_tauri_dependencies.sh"
    ]
    assert len(linux_setup) == 1
    assert linux_setup[0].get("if") == "runner.os == 'Linux'"

    runs = [step.get("run") for step in steps]
    assert runs.count("npm ci") == 2
    build_commands = [run for run in runs if isinstance(run, str) and "npm run build" in run]
    assert build_commands == ["npm run build -- --bundles ${{ matrix.bundle }} -- --locked"]
    assert not any(isinstance(run, str) and "cargo build --release" in run for run in runs)


def test_web_client_uses_api_only_and_supports_mandarin_theme() -> None:

    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )

    vite_env = (ROOT / "clients" / "web" / "src" / "vite-env.d.ts").read_text(encoding="utf-8")

    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    app = _read_application_source()
    topbar = (ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.tsx").read_text(
        encoding="utf-8"
    )
    settings_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SettingsCenter.tsx"
    ).read_text(encoding="utf-8")
    app_and_settings = app + topbar + settings_center

    assert 'const DEFAULT_BROWSER_BASE = "/api";' in api_client

    assert 'const DEFAULT_DESKTOP_BASE = "http://127.0.0.1:8000/api";' in api_client

    assert "VITE_EUROGAS_API_BASE_URL" in api_client

    # Host detection lives in the single HostCapabilities boundary (Architecture
    # V2 rule 50): the transport and the store read the resolved kind from there.
    host_capabilities = (
        ROOT / "clients" / "web" / "src" / "app" / "host" / "hostCapabilities.ts"
    ).read_text(encoding="utf-8")

    assert "__TAURI_INTERNALS__" in host_capabilities

    assert "tauri.localhost" in host_capabilities

    assert "resolveHostKind" in api_client

    assert "__TAURI_INTERNALS__" not in api_client

    assert "__TAURI_INTERNALS__" not in (
        ROOT / "clients" / "web" / "src" / "stores" / "api.ts"
    ).read_text(encoding="utf-8")

    assert "VITE_EUROGAS_API_BASE_URL" in vite_env

    assert "__TAURI_INTERNALS__" in vite_env

    vite_config = (ROOT / "clients" / "web" / "vite.config.ts").read_text(encoding="utf-8")

    assert '"/api": "http://127.0.0.1:8000"' in vite_config

    assert "http://localhost:8000" not in vite_config

    assert "postgres" not in api_client.lower()

    assert "RUNTIME_STORE_DATABASE_URL" not in api_client

    assert zh["nav.sources"] == "\u6570\u636e\u6e90\u4e2d\u5fc3"

    assert zh["theme.dark"] == "\u6df1\u8272"

    # Mandarin is offered through the locale registry every language picker reads.
    locales = (ROOT / "clients" / "web" / "src" / "i18n" / "locales.ts").read_text(encoding="utf-8")
    assert '{ code: "zh-CN", nativeName: "简体中文"' in locales
    assert "<PersonalPreferencesPanel" in app_and_settings


def test_web_client_matches_design_reference_cockpit() -> None:

    app = _read_application_source()
    topbar = (ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.tsx").read_text(
        encoding="utf-8"
    )
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
    extracted_pages = "".join(
        (ROOT / "clients" / "web" / "src" / "components" / filename).read_text(encoding="utf-8")
        for filename in [
            "ReviewWorkspace.tsx",
            "MarketPositioningWorkspace.tsx",
            "RuntimeWorkspace.tsx",
            "ManualWorkspace.tsx",
        ]
    )
    app_and_topbar = app + topbar
    app_and_components = (
        app
        + topbar
        + source_center
        + contract_workbench
        + network_workspace
        + capacity_workspace
        + extracted_pages
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

    # The Network page carries no optimiser rail any more (design basis 2, CP-21): the
    # decision stack left with the optimiser pages; the "Our book" tab keeps the book list and
    # the relevance lists (J.5).
    assert "scenario-rail" not in network_workspace
    assert "decision-rail" not in network_workspace
    assert "trade-result-panel" not in network_workspace
    assert "<MapBookRelevance" in network_workspace

    # Finding a place on the map is the map's own finder; the top bar no longer carries a
    # second map search (it duplicated the finder and pushed the account menu off screen).
    gas_network_map = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    assert "<MapFinder places={finderPlaces}" in gas_network_map
    assert "topbar-search" not in topbar
    assert "workspace-topbar-page" in topbar
    assert "topbar-icon-button" not in app
    assert "workspace-nav" not in app
    assert "workspace-primary-tabs" in topbar
    assert "workspaceMenuOpen" not in app
    assert "groupedMenuOpen" not in topbar
    assert "workspace-local-task" not in topbar  # went with the duplicate map search
    assert "topbar-menu-glyph" not in app_and_topbar
    assert "workspace-page" in app
    assert "workspace-page-tabs" in app
    # The shell composes every page through the workspace renderer and intercepts none of
    # them (conflicting register C9). The task resolver keeps naming the network page - it
    # is the composition that decides what a page shows, not the shell.
    shell_source = (WEB_SRC / "app" / "shell" / "AppShell.tsx").read_text(encoding="utf-8")
    assert "<WorkspaceRenderer controller={controller} />" in shell_source
    assert 'activeWorkspace === "network"' not in shell_source
    assert 'activeWorkspace === "network"' in app
    market_cockpit_for_contract = (
        ROOT / "clients" / "web" / "src" / "components" / "MarketCockpit.tsx"
    ).read_text(encoding="utf-8")
    portfolio_workspace_for_contract = (
        ROOT / "clients" / "web" / "src" / "components" / "PortfolioWorkspace.tsx"
    ).read_text(encoding="utf-8")
    # Outages and capacity are the Network task's panel beside the map (one task, not a page):
    # the Desk page shows the task's kept page (DeskNetworkTask), which builds that panel.
    network_task_for_contract = (
        ROOT / "clients" / "web" / "src" / "components" / "DeskNetworkTask.tsx"
    ).read_text(encoding="utf-8")
    assert "<KeptSlot id={DESK_NETWORK_KEPT} />" in market_cockpit_for_contract
    assert "capacity={{" in network_task_for_contract
    assert '"exposure"' in portfolio_workspace_for_contract
    assert '"manual"' in app
    assert 'activePrimaryWorkspace.id === "market"' in app
    assert 'import { MarketCockpit } from "@/components/MarketCockpit";' in app
    assert 'import { PortfolioWorkspace } from "@/components/PortfolioWorkspace";' in app
    assert 'import { DecisionWorkspace } from "@/components/DecisionWorkspace";' in app
    assert 'activePrimaryWorkspace.id === "portfolio"' in app
    assert 'activePrimaryWorkspace.id === "decision"' in app
    assert 'activeWorkspace === "glossary"' in app
    assert 'activeWorkspace === "manual"' in app
    assert "resourcePoolOptimizationRequest" in app
    # Every run carries the provenance key it was built under - the trading context plus the
    # canonical identity of the caller-known inputs (October 1 action-lifecycle repair plus the
    # input-identity follow-up; see COMMERCIAL_DECISION_WORKFLOW_SPEC.md sections 26 and 27), so
    # a result can be provenanced to the inputs it was actually computed for.
    assert "const optimizerProvenanceKey = useMemo(" in app
    assert "decisionInputIdentity({" in app
    assert (
        "api.optimizeResourcePool(resourcePoolOptimizationRequest, optimizerProvenanceKey)" in app
    )
    assert "api.recommendRouteAllocation(routeRecommendationRequest, compareProvenanceKey)" in app
    assert "lastAutoOptimizerSignatureRef" in app
    assert "autoOptimizerSignature" in app
    assert (
        "void api.optimizeResourcePool(resourcePoolOptimizationRequest, optimizerProvenanceKey)"
        in app
    )
    assert "canRunPoolOptimizer" in app
    assert "poolInputBlockers" in app
    assert "runtimeDbReady" in app
    assert "blocker_runtime_db" in app
    # Deals -> Contracts is the contract list with the open contract beside it (2026-11-19).
    assert "contract-list-command" in app_and_components
    assert "contract-terms-layout" in app_and_components
    assert "map-overlay" not in app
    assert "topology-status-panel" not in app
    assert "network-operations-panel" not in app
    assert "data-health-panel" not in app
    assert "networkGeometryMissing" not in app
    assert "approximateNodeCount" not in app
    assert "map-node-legend" not in app
    assert "decision-signal-panel" not in network_workspace
    assert "capacity-page" in capacity_workspace
    assert "review-page" in extracted_pages
    assert "orders-page" in extracted_pages
    assert "manual-page" in extracted_pages
    assert "review-report-panel" in extracted_pages
    assert "manual-step-list" in css
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")

    assert "fallback-network-map map-ready" in map_component
    # Zoom sits top-right with the map's own control stack under it (fit our positions, the
    # key); the toolbar is a row above the map and the finder its top left. The map is flat and
    # north-up: no compass, no rotation, no pitch, no 3D (owner, 2026-11-26).
    assert 'NavigationControl({ showCompass: false }), "top-right"' in map_component
    assert "dragRotate: false" in map_component
    assert "touchPitch: false" in map_component
    assert "fill-extrusion" not in map_component
    assert "map-control-stack" in (
        ROOT / "clients" / "web" / "src" / "components" / "mapScene" / "MapSceneControls.tsx"
    ).read_text(encoding="utf-8")
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

    map_tile_providers = (
        ROOT / "clients" / "web" / "src" / "app" / "mapTileProviders.ts"
    ).read_text(encoding="utf-8")
    # One basemap (owner review 2026-11-26): OpenStreetMap data through OpenFreeMap's vector
    # styles (ODbL, commercial use allowed, attribution shown), the bundled outline only as the
    # automatic offline / China fallback. No second provider, no custom URL, no "none".
    assert "tiles.openfreemap.org/styles/positron" in map_tile_providers
    assert "© OpenStreetMap contributors, © OpenMapTiles" in map_tile_providers
    assert 'export type MapTileProviderId = "openfreemap" | "outline";' in map_tile_providers
    assert "tianditu" not in map_tile_providers.lower()
    assert "VITE_EUROGAS_MAP_TILE_URL" not in map_tile_providers
    assert "basemap-raster" not in map_component
    # Public endpoints whose terms exclude a commercial product are not offered (owner review
    # 2026-11-26): OpenStreetMap's tile servers, CARTO's free tiles, AMap's public raster.
    assert "tile.openstreetmap.org/{z}" not in map_tile_providers
    assert "basemaps.cartocdn.com" not in map_tile_providers
    assert "is.autonavi.com" not in map_tile_providers

    assert "--eg-ink: #171717" in css

    assert "--eg-canvas-soft: #fafafa" in css

    assert en["scenario.title"] == "Scenario Builder"

    assert zh["scenario.title"] == "\u60c5\u666f\u6784\u5efa\u5668"
    assert en["nav.capacity"] == "Capacity"
    assert zh["nav.capacity"] == "\u7ba1\u5bb9"


def test_web_client_release_cockpit_chrome_is_clean_and_color_coded() -> None:
    app = _read_application_source()
    network_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "NetworkWorkspace.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    line_model = (ROOT / "clients" / "web" / "src" / "app" / "networkMapLines.ts").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    assert "release-cockpit-override" in css
    assert "workspace-topbar-only" in css
    # Network chips carry their words, not only a colour dot (unlabelled dots were unreadable).
    assert "chip map-layer-chip layer-${layer}" in network_workspace
    assert "map-layer-chip compact" not in network_workspace
    assert "aria-pressed={activeLayers.includes(layer)}" in network_workspace
    assert "MapLibre controls sit outside both decision rails" in css
    assert "route_candidate" in line_model
    assert 'edge.source_system === "route_candidate"' in line_model
    assert 'metadata.materialization === "route_candidate_edge"' in line_model
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

    assert en["result.route_alpha"] == "Route alpha ladder"

    assert zh["result.route_alpha"] == "\u8def\u5f84\u6536\u76ca\u9636\u68af"
    assert en["map.network_warning_title"] == "Pipeline geometry not loaded"
    assert zh["map.network_warning_title"] == "\u7ba1\u7ebf\u51e0\u4f55\u672a\u52a0\u8f7d"
    assert en["map.runtime_missing_body"].startswith("The data store is not connected")
    assert zh["map.runtime_missing_body"].startswith("\u6570\u636e\u5b58\u50a8")
    assert en["map.coordinate_quality"] == "Coordinate quality"
    assert zh["map.coordinate_quality"] == "\u5750\u6807\u8d28\u91cf"
    assert en["map.approximate_points"] == "Approx. coords"
    assert zh["map.approximate_points"] == "\u8fd1\u4f3c\u5750\u6807"


def test_web_client_separates_market_capacity_orders_and_review_pages() -> None:
    app = _read_application_source()
    capacity_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "CapacityWorkspace.tsx"
    ).read_text(encoding="utf-8")
    positioning_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "MarketPositioningWorkspace.tsx"
    ).read_text(encoding="utf-8")
    review_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "ReviewWorkspace.tsx"
    ).read_text(encoding="utf-8")
    manual_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "ManualWorkspace.tsx"
    ).read_text(encoding="utf-8")
    navigation = (ROOT / "clients" / "web" / "src" / "workspaceNavigation.ts").read_text(
        encoding="utf-8"
    )
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "export const workspacePageIds" in navigation
    for page in [
        "network",
        "capacity",
        "market",
        "scenario",
        "contracts",
        "review",
        "orders",
        "sources",
        "glossary",
        "runtime",
        "settings",
        "manual",
    ]:
        assert f'"{page}"' in navigation
    # The Strategies and Assistant pages left with CP-00 (design basis 2, I.1).
    for retired in ["strategy", "agents"]:
        assert f'| "{retired}"' not in navigation
    assert "function workspaceFromLocation(): WorkspacePageId" in app
    assert 'new URLSearchParams(window.location.search).get("workspace")' in app
    assert "coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID)" in app
    assert "const WORKSPACE_PAGES" not in app
    assert "nextUrl.search = workspaceTaskSearch(window.location.search, page, task)" in app
    assert 'window.history.pushState({ workspace: page }, "", nextUrl)' in app
    assert 'window.addEventListener("popstate", syncWorkspaceFromUrl)' in app
    assert app.index('activePrimaryWorkspace.id === "market"') < app.index(
        'activePrimaryWorkspace.id === "portfolio"'
    )
    assert app.index('activePrimaryWorkspace.id === "portfolio"') < app.index(
        'activePrimaryWorkspace.id === "decision"'
    )
    portfolio_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "PortfolioWorkspace.tsx"
    ).read_text(encoding="utf-8")
    assert "MarketPositioningWorkspace" in portfolio_workspace
    assert 'id="screen-orders"' in positioning_workspace
    assert '"data-record": "screen-order"' in positioning_workspace
    assert '["network", "storage", "lng"] as CapacityView[]' in capacity_workspace
    assert "capacity.view_${view}" in capacity_workspace
    assert "capacity.tariffs" in capacity_workspace
    assert "capacity-operating-table" in capacity_workspace
    assert "capacity-point-inspector" in capacity_workspace
    assert "const PAGE_SIZE = 50" in capacity_workspace
    assert "capacity-pagination" in capacity_workspace
    assert "capacity-readiness-note" in capacity_workspace
    assert 'normalized.includes("firm") && normalized.includes("technical")' in capacity_workspace
    assert 'normalized.includes("firm") && normalized.includes("booked")' in capacity_workspace
    assert "Math.abs(flowMcmD) / technicalCapacityMcmD * 100" in capacity_workspace
    assert "bookedCapacityMcmD / technicalCapacityMcmD * 100" in capacity_workspace
    assert "STALE_AFTER_HOURS = 24" in capacity_workspace
    assert "latestRowsByKey(storage" in capacity_workspace
    assert "latestRowsByKey(lng" in capacity_workspace
    assert "row.dtmi_twh" in capacity_workspace
    assert (
        "Company TSO access and executable booking availability"
        in en["capacity.readiness_available"]
    )
    assert "\u516c\u53f8 TSO \u51c6\u5165" in zh["capacity.readiness_available"]
    assert "reviewWarnings" in app
    assert "review-report-panel" in review_workspace
    assert "manual.no_client_db" in manual_workspace
    assert en["market.subtitle"].startswith("Terminal view")
    assert zh["market.subtitle"].startswith("\u9762\u5411\u6b27\u6d32\u4e3b\u8981")
    assert en["orders.subtitle"].startswith("Read-only")
    assert zh["orders.subtitle"].startswith("\u53ea\u8bfb")


def test_web_client_market_page_is_trader_terminal_surface() -> None:
    app = _read_application_source()
    store = (ROOT / "clients" / "web" / "src" / "stores" / "api.ts").read_text(encoding="utf-8")
    market_terminal_path = ROOT / "clients" / "web" / "src" / "components" / "MarketTerminal.tsx"
    market_terminal = market_terminal_path.read_text(encoding="utf-8")
    market_cockpit = (
        ROOT / "clients" / "web" / "src" / "components" / "MarketCockpit.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert 'import { MarketTerminal } from "@/components/MarketTerminal";' in market_cockpit
    assert "<MarketTerminal" in market_cockpit
    assert "marketLastUpdatedAtUtc" in market_cockpit
    assert "refreshMarketData" in market_cockpit
    assert "markets={api.normalizedMarkets}" in market_cockpit
    assert "MARKET_REFRESH_INTERVAL_MS" in app
    assert "marketLastUpdatedAtUtc: string | null" in store
    assert "refreshMarketData: () => Promise<void>" in store
    # The market lane reads one coherent projection through the same bounded
    # workspace loader (Architecture V2 Wave 5); the low-level reads still exist in
    # the workspace batch, so the terminal keeps real, timeout-bounded sources. The read
    # carries the query its pass was bound to - the published trading context - so the
    # payload declares the context it was asked about rather than one derived from the
    # backend's clock, and an answer that no longer owns its lane is not written.
    assert "const query = projectionRequestContext(get().tradingContext);" in store
    assert "api.marketContext(query, loaderOptions)" in store
    assert '["normalizedMarkets", api.normalizedMarketObservations]' in store
    assert '["marketSpreads", api.marketSpreads]' in store
    assert "loadWorkspaceEndpoint(api.fxRates" in store
    assert "market-terminal-board" in market_terminal
    # One hub board replaces the ticker cards, curve lanes, latest-marks table and regional
    # comparison that repeated the same prices; per-source detail sits behind a disclosure.
    assert "market-hub-board-table" in market_terminal
    assert "curve-${tenor}" in market_terminal
    assert "premiumOverTtf" in market_terminal
    assert "market-source-details" in market_terminal
    assert "market-sparkline" in market_terminal
    assert "market-region-comparison" not in market_terminal
    assert "market-source-quality" not in market_terminal
    assert "activeTenor" in market_terminal
    assert "setActiveTenor" in market_terminal
    assert 'className: "market-tenor-tab"' in market_terminal
    assert "market-source-matrix" in market_terminal
    assert "sourceMatrixRows" in market_terminal
    assert "update_interval_seconds" in market_terminal
    assert "market-live-status" in market_terminal
    assert "quoteHistoryByHubTenor" in market_terminal
    assert "quoteAgeSeconds" in market_terminal
    assert "quoteDelta" in market_terminal
    assert "quote.source_system" in market_terminal
    assert "lastUpdatedAtUtc" in market_terminal
    assert "marketTenorOrder" in market_terminal
    assert "market.tenor_weekend" in market_terminal
    assert 't("market.tenor_tabs")' in market_terminal
    assert 't("market.hub")' in market_terminal
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
    assert "market-sparkline" in css
    # The tenor choice is the Segmented primitive (UX-02); its look lives in controls.css.
    assert ".market-tenor-tab.active" not in css
    assert ".market-source-matrix" in css
    assert ".market-live-status" in css
    assert ".market-price-delta.up" in css
    assert "market-fx-strip" in market_terminal
    assert en["market.title"] == "Gas Market Terminal"
    assert en["market.terminal"] == "Major European gas markets"
    assert en["market.region_comparison"] == "Regional comparison"
    assert en["market.source_matrix"] == "Source matrix"
    assert en["market.live_polling"] == "Live polling"
    assert en["market.live_exchange_prices"].startswith("Exchange and broker")
    assert zh["market.terminal"] == "\u6b27\u6d32\u4e3b\u8981\u5929\u7136\u6c14\u5e02\u573a"


def test_web_client_settings_page_is_trader_preference_center() -> None:
    app = _read_application_source()
    settings_center_path = ROOT / "clients" / "web" / "src" / "components" / "SettingsCenter.tsx"
    settings_center = settings_center_path.read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert 'import { SettingsCenter } from "@/components/SettingsCenter";' in app
    assert "<SettingsCenter" in app
    assert "settings-preference-center" in settings_center
    # One basemap (owner review 2026-11-26): no map-provider panel in Settings.
    assert "settings-unit-panel" not in settings_center
    assert "map_tile" not in settings_center
    assert "settings-service-panel" in settings_center
    assert "settings-boundary-panel" in settings_center
    assert "settings-auth-grid" in settings_center
    assert "settings-auth-field" in settings_center
    assert "settings-auth-save" in settings_center
    assert 'autoComplete="new-password"' in settings_center
    assert ".settings-auth-grid" in css
    # Every setting on the page changes something. Currency, energy unit, volume unit,
    # price basis and session time zone were stored in the browser and read by nothing,
    # so they were removed; quotes keep their native units and the trader desk converts.
    dead_settings = (
        "default_currency",
        "energy_unit",
        "session_timezone",
        "eurogas.settings.preferences",
    )
    for dead in dead_settings:
        assert dead not in settings_center
    assert "<PersonalPreferencesPanel" in settings_center
    assert "<OrganisationDefaultsPanel" in settings_center
    assert "credentialProviders" in settings_center
    assert "onOpenSources" in settings_center
    assert "settings-preference-center" in css
    assert "settings-service-row" in css
    assert en["settings.service_access"] == "Service access"
    assert en["preferences.personal_title"] == "My preferences"
    assert zh["preferences.personal_title"] == "\u6211\u7684\u504f\u597d"


def test_web_client_network_page_shows_complete_resource_pool_path_ladder() -> None:
    app = _read_application_source()
    # The network surface is composed by the market primary, so the path ladder is wired
    # where the composition lives rather than in the shell (conflicting register C9).
    market_cockpit = (
        ROOT / "clients" / "web" / "src" / "components" / "MarketCockpit.tsx"
    ).read_text(encoding="utf-8")
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
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(encoding="utf-8")

    # The ladder stays with the optimiser surface; the Network page no longer carries it
    # (design basis 2, CP-21): its "Our book" view draws the contracts' priced paths instead.
    assert "buildResourcePoolMapPaths" in app
    assert "<ResourcePoolPathOverlay" not in network_workspace
    assert "resourcePoolMapPaths" not in market_cockpit
    assert "highlightedRoute=" not in market_cockpit
    assert "contractPathLines(" in network_workspace
    assert "resource-pool-map-overlay" in overlay
    assert "resource-path-geometry-notice" in overlay
    assert "firstIndicativeGeometryPath" in overlay
    assert 't("map.indicative_route_notice_title")' in overlay
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
    assert "const visiblePaths = paths;" in overlay
    assert "paths.slice(0, 3)" not in overlay
    assert "hiddenPathCount" not in overlay
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
    assert "map-visual-legend" in network_workspace
    assert "buildVisibleMapNetworkLines" in network_workspace
    assert ".map-visual-legend" in css
    assert ".line-swatch.verified" in css
    assert ".line-swatch.indicative" in css
    assert "resource-path-card" in css
    assert ".resource-pool-allocation-summary" in css
    assert ".resource-route-status-legend" in css
    assert ".resource-path-allocation-evidence" in css
    assert ".resource-path-recommendation-evidence" in css
    assert ".resource-path-capacity-warning" in css
    assert ".resource-route-state-pill" in css
    assert "max-height: min(42vh, 380px)" in css
    assert "buildVisibleMapNetworkLines" in map_component
    assert 'id: "verified-pipeline-lines"' in map_component
    assert 'id: "indicative-route-lines"' in map_component
    assert "fallback-flow-path direct-corridor" not in map_component
    assert en["home.resource_paths"] == "Resource paths"
    assert en["home.pool_allocation"] == "Pool allocation"
    assert en["home.route_status_legend"] == "Route status"
    assert en["home.capacity_bottleneck"] == "Capacity bottleneck"
    assert en["home.route_rank"] == "Route rank"
    assert en["home.recommendation_reason"] == "Recommendation reason"
    assert en["home.capacity_utilization"] == "Capacity utilization"
    assert en["home.required_tso_access"] == "Required TSO access"
    assert en["home.pnl_per_day"] == "PnL/day"
    assert en["home.route_state.allocated"] == "Allocated"
    assert en["home.route_state.candidate"] == "Candidate"
    assert en["home.route_state.blocked"] == "Blocked"
    assert en["home.path_unavailable"].startswith("No saved resource")
    assert en["map.visual_legend"] == "Map legend"
    assert en["map.verified_pipeline_lines"] == "Verified line geometry"
    assert en["map.indicative_route_lines"] == "Indicative route corridors"
    assert en["map.indicative_route_notice_title"] == "Indicative route corridor"
    assert "map.route_not_drawn" not in en
    assert "map.suppressed_route_lines" not in en
    assert zh["home.resource_paths"] == "\u8d44\u6e90\u8def\u5f84"
    assert zh["home.pool_allocation"] == "\u8d44\u6e90\u6c60\u5206\u914d"
    assert zh["home.route_status_legend"] == "\u8def\u5f84\u72b6\u6001"
    assert zh["home.capacity_bottleneck"] == "\u5bb9\u91cf\u74f6\u9888"
    assert zh["home.route_rank"] == "\u8def\u5f84\u6392\u540d"
    assert zh["home.recommendation_reason"] == "\u63a8\u8350\u7406\u7531"
    assert zh["home.capacity_utilization"] == "\u5bb9\u91cf\u4f7f\u7528\u7387"
    assert zh["home.required_tso_access"] == "\u6240\u9700 TSO \u51c6\u5165"
    assert zh["map.visual_legend"] == "地图图例"
    assert zh["map.verified_pipeline_lines"] == "已验证线几何"
    assert zh["map.indicative_route_lines"] == "指示性路线走廊"
    assert "map.route_not_drawn" not in zh
    assert "pool allocation summary" in web_spec
    assert "route status legend" in web_spec
    assert "indicative route corridors" in web_spec
    assert "not official pipeline geometry" in web_spec
    assert "never surveyed or authoritative pipeline geometry" in web_spec
    assert "route ranking evidence" in web_spec
    assert "capacity utilization" in web_spec
    assert "required TSO access" in web_spec
    assert "capacity bottleneck" in web_spec
    assert "path-level PnL/day" in web_spec


def test_network_workspace_is_map_first_with_non_overlapping_rails_and_ladder() -> None:
    network_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "NetworkWorkspace.tsx"
    ).read_text(encoding="utf-8")
    overlay = (
        ROOT / "clients" / "web" / "src" / "components" / "ResourcePoolPathOverlay.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )

    assert "network-workspace-shell" in network_workspace
    assert "network-map-column" in network_workspace
    # The resource and decision rails and the route ladder left the Network page with the
    # optimiser pages (design basis 2, CP-21).
    for gone in (
        "network-resource-rail",
        "network-decision-rail",
        "network-route-ladder",
        "network-rail-tabs",
        "network-rail-view",
    ):
        assert gone not in network_workspace
    workspace_tabs = (
        ROOT / "clients" / "web" / "src" / "components" / "ui" / "WorkspaceTabs.tsx"
    ).read_text(encoding="utf-8")
    assert 'idPrefix="network-rail-tab"' not in network_workspace
    assert 'role?: "tablist"' in workspace_tabs
    # WorkspaceTabs delegates to the Tabs primitive (UX-02), which owns the tab semantics.
    tabs_primitive = (
        ROOT / "clients" / "web" / "src" / "components" / "ui" / "Tabs.tsx"
    ).read_text(encoding="utf-8")
    assert "<Tabs" in workspace_tabs
    assert 'role="tablist"' in tabs_primitive
    assert "aria-selected={selected}" in tabs_primitive
    assert "activeRailView" not in network_workspace
    assert "<IntradayDecisionFeed" not in network_workspace
    assert "onOpenReview" not in network_workspace
    assert "defaultOpen" in overlay
    assert "useState(defaultOpen)" in overlay
    assert ".network-workspace-shell" in css
    # The rails' and the ladder's styles left with them (CP-21); the shell's grid stays.
    assert 'grid-template-areas: "left map right" "ladder ladder ladder"' in css
    for gone in (".network-route-ladder", ".network-decision-rail", ".network-rail-view"):
        assert gone not in css
    assert "position: static" in css
    assert "grid-auto-flow: column" in css
    assert ".cockpit-app .workspace-topbar-only.has-map-search" in css
    assert 'grid-template-areas: "workspace task search" "context context topbar-controls"' in css
    assert "const visiblePaths = paths;" in overlay
    assert "paths.slice(0, 3)" not in overlay
    assert en["network.map_column_label"] == "European gas map"
    assert en["network.rail_decision"] == "Decision"
    assert en["network.rail_pnl"] == "P&L"
    assert en["network.rail_warnings"] == "Warnings"
    assert en["network.rail_evidence"] == "Evidence"


def test_web_client_map_fallback_prioritizes_labels_for_trader_readability() -> None:
    map_component = (
        ROOT / "clients" / "web" / "src" / "components" / "GasNetworkMap.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    assert "MAX_MAP_LABELS" in map_component
    assert "MAJOR_HUB_PRIORITY" in map_component
    assert "priorityLabelNodes" in map_component
    # Names on the live map are one decluttered MapLibre symbol layer (no HTML label boxes);
    # the no-WebGL fallback keeps its own priority labels.
    assert '"map-labels"' in map_component
    assert '"symbol-sort-key": ["get", "rank"]' in map_component
    assert '"text-allow-overlap": false' in map_component
    assert "fallbackLabelPriorityIds" in map_component
    assert "shouldShowFallbackNodeLabel" in map_component
    assert "isSearchLabelMatch" in map_component
    assert "addWithinBudget(highlightedRoutePoints.from)" in map_component
    assert "addWithinBudget(highlightedRoutePoints.to)" in map_component
    assert 'node.node_type === "hub"' in map_component
    assert "fallback-node-label priority" in map_component
    assert "{shouldShowFallbackNodeLabel(node, index) && (" in map_component
    assert ".fallback-node-label" in css
    assert ".fallback-node-label.priority" in css
    assert ".fallback-node.approximate .fallback-node-label" in css


def test_web_client_map_renders_resource_paths_as_route_segments_not_direct_lines() -> None:
    app = _read_application_source()
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
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    web_spec = (ROOT / "docs" / "clients" / "MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md").read_text(
        encoding="utf-8"
    )

    assert "routeId: option.option_id" in resource_pool_paths
    assert "resolveRouteGeometryState" in resource_pool_paths
    assert "buildRouteGeometryEdgesByRouteId" in resource_pool_paths
    assert "verifiedEdgeGeometryCoordinates" in resource_pool_paths
    assert "unmatchedRouteLegsWarning" in resource_pool_paths
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
    assert "map.geometry_indicative_warning" in map_component
    assert "highlighted-route-segments" in map_component
    assert "fallback-flow-segment" in map_component
    assert "verified_pipeline" in map_component
    assert "indicative_route" in map_component
    assert 'id: "verified-pipeline-lines"' in map_component
    assert 'id: "indicative-route-lines"' in map_component
    assert "geometry_classification" in map_component
    assert "is_schematic_corridor: true" in map_component
    assert 't("map.indicative_route_warning")' in map_component
    assert "fallback-flow-path direct-corridor" not in map_component
    assert "fallback-flow endpoint-link" not in map_component
    assert "fallback-flow-path endpoint-link" not in map_component
    assert "routeDrawingSuppressed" not in map_component
    assert "route_geometry_suppressed_body" not in map_component
    assert "direct-${highlightedRoutePoints.routeId}" not in map_component
    assert "geometryCoordinates" in map_component
    assert "geometryWarning" in map_component
    assert "source_derived_leg_sequence" in map_component
    assert "directLineFallback" in overlay
    assert "directLineFallback" in resource_pool_paths
    assert 't("map.indicative_route_notice_title")' in overlay
    assert 't("map.indicative_route_warning")' in overlay
    assert "firstIndicativeGeometryPath" in overlay
    assert "Matched route legs are shown as an indicative schematic corridor" not in overlay
    assert "Only source and target corridor evidence is available" not in overlay
    assert ".fallback-flow-segment" in css
    assert ".fallback-flow-path.endpoint-link" not in css
    assert ".fallback-flow.segmented.corridor" in css
    assert ".fallback-flow.segmented.indicative-highlight" in css
    assert ".fallback-edge.indicative-route" in css
    assert ".resource-path-geometry.warning" in css
    assert ".resource-path-geometry-notice" in css
    assert ".map-visual-legend" in css
    assert ".line-swatch.verified" in css
    assert ".line-swatch.indicative" in css
    assert "route geometry" in css
    assert "Keep the six-item legend" in css
    assert "verified_pipeline" in web_spec
    assert "indicative_route" in web_spec
    assert "schematic, not surveyed or official pipeline geometry" in web_spec
    assert "unlabelled source-to-target shortcut" in web_spec


def test_web_client_glossary_page_is_term_wiki_surface() -> None:
    app = _read_application_source()
    glossary_wiki_path = ROOT / "clients" / "web" / "src" / "components" / "GlossaryWiki.tsx"
    glossary_wiki = glossary_wiki_path.read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(encoding="utf-8")

    assert 'import { GlossaryWiki } from "@/components/GlossaryWiki";' in app
    assert "<GlossaryWiki" in app
    assert "selectedTermRecord" in app
    assert "setSelectedTerm" in app
    assert "selectTerm" in app
    assert "const categories = useMemo" in app
    assert "glossary-codex-shell" in glossary_wiki
    assert "glossary-left-rail" in glossary_wiki
    assert "glossary-wiki-shell" in glossary_wiki
    assert 't("glossary.all")' in glossary_wiki
    assert "glossary-category-tabs" in glossary_wiki
    assert "glossary-term-list" in glossary_wiki
    assert "glossary-term-card" in glossary_wiki
    assert "glossary-wiki-article" in glossary_wiki
    assert "glossary-related-chip" in glossary_wiki
    # An entity's figures come from the shared entry model, not from a dump of the context read.
    assert "glossary-entity" in glossary_wiki
    assert "entryPrices(" in glossary_wiki
    assert "isEntityTerm(" in glossary_wiki
    assert "glossaryMapPlace(" in glossary_wiki
    assert "onSelectTerm(term)" in glossary_wiki
    assert "selectedTerm?.term_id === term.term_id" in glossary_wiki
    assert "consistent backend-served vocabulary" in web_spec
    assert "glossary-wiki-shell" in css
    assert "glossary-codex-shell" in css
    assert "glossary-left-rail" in css
    assert "glossary-wiki-article" in css
    assert "glossary-term-card.active" in css
    assert en["glossary.all"] == "All"
    assert en["glossary.gas_day"] == "Gas day"
    assert zh["glossary.all"] == "\u5168\u90e8"
    assert zh["glossary.gas_day"] == "\u71c3\u6c14\u65e5"
    assert "wiki-style article" in web_spec
    assert "institutions, entities, venues, business models" in web_spec
    assert "separate concepts from entities" in web_spec


def test_web_client_glossary_context_values_do_not_render_raw_objects() -> None:
    glossary_wiki = (
        ROOT / "clients" / "web" / "src" / "components" / "GlossaryWiki.tsx"
    ).read_text(encoding="utf-8")
    entry_model = (
        ROOT / "clients" / "web" / "src" / "app" / "model" / "glossaryEntry.ts"
    ).read_text(encoding="utf-8")

    # The page renders named figures (value, unit, source, as-of) from the entry model; the
    # context read's records, sections and warning codes are never printed as they come.
    assert "context_sections" not in glossary_wiki
    assert "matched_entities" not in glossary_wiki
    assert "data_quality" not in glossary_wiki
    assert "export function entryPrices" in entry_model
    assert "export function entryCapacity" in entry_model
    assert "route_name" in entry_model
    assert "contract_name" in entry_model
    assert "source_reference" in entry_model


def test_web_client_glossary_keeps_article_visible_while_browsing_terms() -> None:
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    assert ".glossary-codex-shell" in css
    assert ".glossary-wiki-shell" in css
    assert ("grid-template-columns: minmax(320px, 0.82fr) minmax(620px, 1.58fr)") in css
    assert "max-height: calc(100vh - 150px)" in css
    assert "overflow-y: auto" in css
    assert "position: sticky" in css
    assert "top: 32px" in css
    assert "@media (max-width: 1200px)" in css
    assert ".glossary-wiki-shell {" in css
    assert ("grid-template-columns: minmax(300px, 0.78fr) minmax(520px, 1.42fr)") in css
    assert "@media (max-width: 900px)" in css
    assert "max-height: none" in css
    assert "position: static" in css


def test_web_client_contracts_page_is_task_led_resource_terms_workbench() -> None:
    app = _read_application_source()
    workbench_path = ROOT / "clients" / "web" / "src" / "components" / "ContractWorkbench.tsx"
    workbench = workbench_path.read_text(encoding="utf-8")
    contract_import = (ROOT / "clients" / "web" / "src" / "app" / "contractImport.ts").read_text(
        encoding="utf-8"
    )
    contract_payload = (ROOT / "clients" / "web" / "src" / "app" / "contractPayload.ts").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )
    web_spec = (ROOT / "docs" / "clients" / "WEB_CLIENT_DESIGN_SPEC.md").read_text(encoding="utf-8")

    portfolio_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "PortfolioWorkspace.tsx"
    ).read_text(encoding="utf-8")
    assert "import { ContractWorkbench" in portfolio_workspace
    assert 'from "@/components/ContractWorkbench";' in portfolio_workspace
    assert "<ContractWorkbench" in portfolio_workspace
    # Writing the reviewed draft is a `persist` consequence: the workspace owns the action and
    # the panel only renders and reports it.
    # The tab row holds tabs only (UX_REFERENCE rule 26): the save is the draft's own action,
    # built by the workspace and rendered in the workbench's command row.
    assert "saveAction={saveAction}" in portfolio_workspace
    assert 'const saveAction =\n    task === "resources" ? (' in portfolio_workspace
    assert "primaryAction=" not in portfolio_workspace
    # The action performs the save through the shared rule; the hook owns the request so it
    # can fold the server's refreshed edit lease back into the draft (S1e precondition).
    assert (
        "contractSaveStateForDraft.canSave && void contractEditor.saveContract()"
        in portfolio_workspace
    )
    assert 't("contracts.action.save")' in portfolio_workspace
    assert 't("contracts.action.save")' not in workbench
    assert 'import type { ContractDraft } from "@/app/index";' in app
    app_and_workbench = app + workbench + portfolio_workspace
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

    # The page is the contract list (owner, 2026-11-19): the list's command row (count, search,
    # kind filter, New contract, Import PDF), the list, and the open contract beside it; the
    # supply editor's clause layout is kept for a supply agreement.
    for token in [
        "contract-task-workspace",
        "contract-list-command",
        'id="contract-list"',
        "contract-detail",
        "contract-terms-layout",
        "contract-clause-nav",
        "contract-clause-editor",
        "contract-decision-rail",
        "contractImportRef",
        "importContractDraftFile",
        "loadTerm",
        # The UI accepts PDF only since CP-00; JSON stays on the API (design basis 2, H).
        'accept=".pdf,application/pdf"',
        't("contracts.action.import")',
        't("contracts.beach_delivery_point")',
        't("contracts.title_transfer_point")',
    ]:
        assert token in workbench

    for token in [
        ".contract-task-workspace",
        ".contract-terms-layout",
        ".contract-clause-nav",
        ".contract-clause-editor",
        ".contract-decision-rail",
    ]:
        assert token in css

    # Desk words, not internal ones (owner, 2026-11-19).
    assert en["contracts.upload_contract"] == "Import a contract PDF"
    assert en["contracts.beach_delivery"] == "Beach delivery"
    assert en["contracts.counterparty"] == "Counterparty"
    assert en["contracts.title_transfer_point"] == "Title transfer point"
    assert en["contracts.document_status"] == "Document status"
    assert zh["contracts.upload_contract"] == "\u5bfc\u5165\u5408\u540c PDF"
    assert zh["contracts.beach_delivery"] == "\u6d77\u5cb8\u4ea4\u4ed8"
    assert zh["contracts.counterparty"] == "\u5bf9\u624b\u65b9"
    assert zh["contracts.title_transfer_point"] == "\u6743\u5c5e\u8f6c\u79fb\u70b9"
    assert zh["contracts.document_status"] == "\u6587\u4ef6\u72b6\u6001"
    assert "task-led" in web_spec
    assert "structured JSON drafts" in web_spec
    assert "plain-text evidence" in web_spec
    assert "title-transfer point" in web_spec
    assert "beach delivery point" in web_spec


def test_web_client_sources_page_is_categorized_source_center() -> None:
    app = _read_application_source()
    source_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SourceCenter.tsx"
    ).read_text(encoding="utf-8")
    app_and_source_center = app + source_center
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    derived_data = (ROOT / "clients" / "web" / "src" / "app" / "workspaceDerivedData.ts").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
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
        "sources: (options?: ApiRequestOptions) => "
        'get<SourceSystemWire[]>("/sources", undefined, options).then(normalizeSourcesResponse)'
        in api_client
    )
    assert "source-center" in css
    assert "source-view-tabs" in css
    assert "source-readiness-strip" in css
    assert "runtime-blocker-list" in css
    assert en["nav.sources"] == "Data Sources"
    assert en["sources.title"] == "Data Source Center"
    assert en["sources.next_action"] == "Next action"
    assert en["sources.action.run_ingestion"].startswith("Run the source ingestion")
    assert en["sources.attention_queue"] == "Priority action queue"
    assert en["sources.access_queue"] == "Licensed access queue"
    assert zh["sources.title"] == "\u6570\u636e\u6e90\u4e2d\u5fc3"
    assert zh["sources.next_action"] == "\u4e0b\u4e00\u6b65\u52a8\u4f5c"
    assert zh["sources.attention_queue"] == "\u4f18\u5148\u5904\u7406\u961f\u5217"


def test_web_client_market_terminal_surfaces_simulated_source_and_tenor_context() -> None:
    market_terminal = (
        ROOT / "clients" / "web" / "src" / "components" / "MarketTerminal.tsx"
    ).read_text(encoding="utf-8")
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
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
    assert "curve-${tenor}" in market_terminal
    assert '"Trayport_Sim"' in market_terminal
    assert "marketTenorOrder" in market_terminal
    assert "price_timing" in market_terminal
    assert "metadata_json" in market_terminal
    assert ".market-tenor-tabs {" not in css
    assert ".market-source-pill.simulated" in css
    assert ".market-curve-lanes" not in market_terminal
    assert en["market.tenor_within_day"] == "Within-day"
    assert en["market.tenor_day_ahead"] == "Day-ahead"
    assert en["market.tenor_weekend"] == "Weekend"
    assert en["market.tenor_month_ahead"] == "Month-ahead"
    assert en["market.simulated_source"] == "Simulated source"
    assert zh["market.tenor_within_day"] == "\u65e5\u5185"
    assert zh["market.tenor_day_ahead"] == "\u65e5\u524d"
    assert zh["market.tenor_weekend"] == "周末"
    assert zh["market.tenor_month_ahead"] == "\u6708\u524d"
    assert zh["market.simulated_source"] == "\u6a21\u62df\u6570\u636e\u6e90"


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
    app = _read_application_source()
    source_center = (
        ROOT / "clients" / "web" / "src" / "components" / "SourceCenter.tsx"
    ).read_text(encoding="utf-8")
    api_client = (ROOT / "clients" / "web" / "src" / "api" / "client.ts").read_text(
        encoding="utf-8"
    )
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert "source_posture_summary" in api_client
    assert "SourceCategoryPostureDTO" in api_client
    assert "sourcePostureRows" in app
    assert "sourcePostureRows={sources.sourcePostureRows}" in app
    assert "source-posture-board" in source_center
    assert "source-posture-row" in source_center
    # Issues per category are counted from the listed sources (#22): the server's posture
    # totals include the hidden test sources, which must not add issues.
    assert "sourcePriority(source) < 5).length" in source_center
    assert "sources.posture_board" in source_center
    assert "source-operations-table" in source_center
    assert "source-posture-board" in css
    assert "source-posture-row" in css
    assert en["sources.posture_board"] == "Operational source posture"
    assert en["sources.preview_substitutes_active"] == "Preview substitutes"
    assert zh["sources.posture_board"] == "\u8fd0\u884c\u6570\u636e\u6e90\u6001\u52bf"
    assert zh["sources.preview_substitutes_active"] == "\u9884\u89c8\u66ff\u4ee3\u6e90"


def test_web_client_review_evidence_pack_is_readable_and_responsive() -> None:
    review_workspace = (
        ROOT / "clients" / "web" / "src" / "components" / "ReviewWorkspace.tsx"
    ).read_text(encoding="utf-8")
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    assert "review-evidence-grid" in review_workspace
    assert "review-evidence-row" in review_workspace
    assert "review-evidence-row-full" in review_workspace
    assert "review-evidence-key" in review_workspace
    assert "review-evidence-value" in review_workspace
    assert "review-evidence-list" in review_workspace
    assert "review-evidence-item" in review_workspace
    assert '<ul className="review-evidence-list">' in review_workspace
    assert '<li className="review-evidence-item"' in review_workspace
    assert "overflow-wrap: anywhere" in css
    assert ".review-evidence-grid" in css
    assert ".review-evidence-row-full" in css


def test_web_client_mobile_topbar_constrains_controls_to_viewport() -> None:
    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    assert "@media (max-width: 900px)" in css
    assert ".cockpit-app .cockpit-topbar > *" in css
    assert "max-width: 100%" in css
    assert "min-width: 0" in css
    assert "flex-wrap: wrap" in css
    assert "minmax(0, 1fr)" in css
    assert 'grid-template-areas: "workspace" "context-disclosure"' in css
    assert 'grid-template-areas: "workspace" "task" "search" "context-disclosure"' in css
    assert ".topbar-context-disclosure" in css


def test_web_client_resource_pool_options_are_backend_owned() -> None:
    app = _read_application_source()
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
    store = (ROOT / "clients" / "web" / "src" / "stores" / "api.ts").read_text(encoding="utf-8")
    en = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    )
    zh = json.loads(
        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")
    )

    assert (
        "resourcePoolOptions: (options?: ApiRequestOptions) => "
        'get<ResourcePoolOptionsDTO>("/route-cost/resource-pool/options", undefined, options)'
    ) in api_client
    assert "resourcePoolOptions: ResourcePoolOptionsDTO | null" in store
    assert "resourcePoolOptions?.sale_options ?? []" in app
    assert "resourcePoolOptions?.portfolio_resources ?? []" in app
    assert "resourcePoolOptions?.blockers ?? []" in app
    assert "sale_price_source_system?: string | null" in api_client
    assert "sale_price_simulated?: boolean" in api_client
    assert "sale_price_source_family?: string | null" in api_client
    assert 'route_topology_kind?: "LOCAL_MARKET_DISPOSITION" | "NETWORK_ROUTE"' in api_client
    # The Network page shows no optimiser allocation any more (design basis 2, CP-21); its
    # book view marks a simulated price "sim" on the indicative spread.
    assert 'sale_price_simulated ? t("market.simulated_source")' not in network_workspace
    assert "saveUpstreamContract" in api_client
    assert "saveDraftContract" in store
    portfolio_workspace_source = (
        ROOT / "clients" / "web" / "src" / "components" / "PortfolioWorkspace.tsx"
    ).read_text(encoding="utf-8")
    # Wave 9 action geography: the workspace header performs the save through the shared
    # save rule, so the panel it acts on no longer carries the payload or the call.
    assert (
        "contractSaveStateForDraft.canSave && void contractEditor.saveContract()"
        in portfolio_workspace_source
    )
    assert "contractSaveStateForDraft.canSave" in portfolio_workspace_source
    assert "saveDraftContract(contractPayload)" not in app_and_contracts
    assert "contractSaveMessage" in portfolio_workspace_source
    assert 'data-record": "upstream-contract"' in app_and_contracts
    assert "contract-import-input" in app_and_contracts
    assert "importContractDraftFile" in app_and_contracts
    assert "loadTerm" in app_and_contracts
    assert "contractDraftFromRecord" in app
    assert en["contracts.library"] == "Contracts"
    assert en["contracts.import_json"] == "Import JSON"
    assert zh["contracts.library"] == "\u5408\u540c"
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
    seed_script = seed_script_path.read_text(encoding="utf-8")

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
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    assert "gh release create" in workflow
    assert "eurogas-nexus-web-${RELEASE_VERSION}.tar.gz" in workflow
    assert "bundle: nsis" in workflow
    assert "bundle: deb" in workflow
    assert "*.exe" in workflow
    assert "*.deb" in workflow
    assert "docker/setup-qemu-action@" in workflow and "# v4.3.0" in workflow
    assert "docker/setup-buildx-action@" in workflow and "# v4.3.0" in workflow
    assert "docker/login-action@" in workflow and "# v4.6.0" in workflow
    assert "docker/build-push-action@" in workflow and "# v7.3.0" in workflow
    # The full suite, in parallel worker processes (pytest-xdist).
    assert "pytest -q -n auto tests" in workflow
    linux_dependencies = (
        ROOT / "scripts" / "ci" / "install_linux_tauri_dependencies.sh"
    ).read_text(encoding="utf-8")
    assert "MAX_ATTEMPTS=4" in linux_dependencies
    assert "Acquire::Retries=3" in linux_dependencies
    assert "https://ports.ubuntu.com" in linux_dependencies
    assert "bash scripts/ci/install_linux_tauri_dependencies.sh" in workflow
    build_ps1 = (ROOT / "scripts" / "release" / "build_release.ps1").read_text(encoding="utf-8")
    assert "npm --prefix $WebDir run build" in build_ps1
    assert "npm --prefix $DesktopDir run build -- --bundles $Bundle" in build_ps1
    build_sh = (ROOT / "scripts" / "release" / "build_release.sh").read_text(encoding="utf-8")
    assert 'npm --prefix "${WEB_DIR}" run build' in build_sh
    assert 'npm --prefix "${DESKTOP_DIR}" run build -- --bundles "${BUNDLE}"' in build_sh
