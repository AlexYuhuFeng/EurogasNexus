"""Client release-surface contracts for Web and Windows shells."""



from __future__ import annotations

import json
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



    assert 'const DEFAULT_BROWSER_BASE = "/api";' in api_client

    assert 'const DEFAULT_DESKTOP_BASE = "http://127.0.0.1:8000/api";' in api_client

    assert "VITE_EUROGAS_API_BASE_URL" in api_client

    assert "__TAURI_INTERNALS__" in api_client

    assert "tauri.localhost" in api_client

    assert "VITE_EUROGAS_API_BASE_URL" in vite_env

    assert "__TAURI_INTERNALS__" in vite_env

    assert "postgres" not in api_client.lower()

    assert "RUNTIME_STORE_DATABASE_URL" not in api_client

    assert zh["nav.sources"] == "\u6570\u636e\u6e90\u4e2d\u5fc3"

    assert zh["theme.dark"] == "\u6df1\u8272"

    assert '<option value="zh-CN">{t("settings.chinese")}</option>' in app





def test_web_client_matches_design_reference_cockpit() -> None:

    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    css = (ROOT / "clients" / "web" / "src" / "styles" / "app.css").read_text(encoding="utf-8")

    en = json.loads(

        (ROOT / "clients" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")

    )

    zh = json.loads(

        (ROOT / "clients" / "web" / "src" / "i18n" / "zh.json").read_text(encoding="utf-8")

    )



    assert "cockpit-topbar" in app

    assert "workflow-strip" not in app

    assert "scenario-rail" in app

    assert "decision-rail" in app

    assert "trade-result-panel" in app

    assert "topbar-search" in app
    assert "topbar-icon-button" not in app
    assert "workspace-nav" not in app
    assert "workspace-menu" in app
    assert "workspaceMenuOpen" in app
    assert "workspace-pill-copy" in app
    assert "topbar-menu-glyph" in app
    assert "workspace-page" in app
    assert 'activeWorkspace === "market"' in app
    assert 'activeWorkspace === "contracts"' in app
    assert 'activeWorkspace === "glossary"' in app
    assert "resourcePoolOptimizationRequest" in app
    assert "optimizeResourcePool(resourcePoolOptimizationRequest)" in app
    assert "efet-section-grid" in app
    assert "map-overlay" not in app
    assert "topology-status-panel" not in app
    assert "network-operations-panel" not in app
    assert "data-health-panel" not in app
    assert "networkGeometryMissing" not in app
    assert "approximateNodeCount" not in app
    assert "map-node-legend" not in app
    assert "decision-signal-panel" in app
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
    assert "Resource-pool home cleanup" in css
    assert ".workspace-network .map-price-strip" in css
    assert "source-runtime-panel" in app

    assert "tile.openstreetmap.org" in map_component

    assert "osm-raster" in map_component

    assert "--eg-ink: #171717" in css

    assert "--eg-canvas-soft: #fafafa" in css

    assert en["scenario.title"] == "Scenario Builder"

    assert zh["scenario.title"] == "\u60c5\u666f\u6784\u5efa\u5668"
    assert en["nav.contracts"] == "Contracts"
    assert zh["nav.contracts"] == "\u5408\u540c"
    assert en["home.resource_pool"] == "Resource pool"
    assert zh["home.resource_pool"] == "\u8d44\u6e90\u6c60"

    assert en["result.route_alpha"] == "Route alpha ladder"

    assert zh["result.route_alpha"] == "\u8def\u5f84\u6536\u76ca\u9636\u68af"
    assert en["map.network_warning_title"] == "Pipeline geometry not loaded"
    assert zh["map.network_warning_title"] == "\u7ba1\u7ebf\u51e0\u4f55\u672a\u52a0\u8f7d"
    assert en["map.coordinate_quality"] == "Coordinate quality"
    assert zh["map.coordinate_quality"] == "\u5750\u6807\u8d28\u91cf"
    assert en["map.approximate_points"] == "Approx. coords"
    assert zh["map.approximate_points"] == "\u8fd1\u4f3c\u5750\u6807"


def test_web_client_sources_page_is_categorized_source_center() -> None:
    app = (ROOT / "clients" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")
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

    assert "source-category-rail" in app
    assert "source-health-grid" in app
    assert "source-diagnostics" in app
    assert "selectedSource" in app
    assert "credential_state" in app
    assert "last_success_at_utc" in app
    assert "connectivity_status" in app
    assert (
        'const sourceCategoryOrder = ["price", "fx", "infrastructure", "tariff", "weather", "ai"]'
        in app
    )
    assert "categoryProviderSummary" in app
    assert "normalizeSourceSystem" in api_client
    assert "SOURCE_CATEGORY_BY_SYSTEM" in api_client
    assert (
        'sources: () => get<SourceSystemWire[]>("/sources").then(normalizeSourcesResponse)'
        in api_client
    )
    assert "source-center" in css
    assert en["nav.sources"] == "Data Sources"
    assert en["sources.title"] == "Data Source Center"
    assert zh["sources.title"] == "\u6570\u636e\u6e90\u4e2d\u5fc3"


def test_release_workflow_publishes_web_windows_and_linux_assets() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    ps1 = (ROOT / "scripts" / "release" / "build_v1_release.ps1").read_text(encoding="utf-8")
    sh = (ROOT / "scripts" / "release" / "build_v1_release.sh").read_text(encoding="utf-8")

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
    assert "npm --prefix $WebDir run build" in ps1
    assert "npm --prefix $DesktopDir run build -- --bundles $Bundle" in ps1
    assert 'npm --prefix "${WEB_DIR}" run build' in sh
    assert 'npm --prefix "${DESKTOP_DIR}" run build -- --bundles "${BUNDLE}"' in sh
