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


def test_strategy_prices_consume_backend_normalized_market_view() -> None:
    scenario = _read(WEB / "app" / "strategyScenario.ts")
    terminal = _read(WEB / "components" / "StrategyShadowRunTerminal.tsx")
    market_terminal = _read(WEB / "components" / "MarketTerminal.tsx")
    store = _read(WEB / "stores" / "api.ts")
    app = _read_application()

    # the client-side re-implementation of FX/tenor/hub normalization is gone
    assert not (WEB / "app" / "marketPriceNormalization.ts").exists()

    # the store consumes the backend-normalized view and backend spreads
    assert '["normalizedMarkets", api.normalizedMarketObservations]' in store
    assert "loadEndpointWithRetry(api.normalizedMarketObservations, 0)" in store
    assert '["marketSpreads", api.marketSpreads]' in store
    assert "loadEndpointWithRetry(api.marketSpreads, 0)" in store

    # scenario assembly reads backend-owned fields only (no FX math)
    assert "observation.price_gbp_mwh" in scenario
    assert "observation.is_gas_price" in scenario
    assert 'observation.hub.toUpperCase() === "NBP"' in scenario
    assert "latestPositiveObservation" in scenario
    assert "const nbpPrice" not in scenario
    assert "Math.max(nbpPrice - 0.4, 0)" not in scenario

    # strategy terminal consumes backend-owned normalized prices
    assert "item.price_gbp_mwh" in terminal
    assert "item.is_gas_price" in terminal

    # market terminal consumes backend hub/tenor and backend-owned spreads
    assert "row.tenor" in market_terminal
    assert "row.hub" in market_terminal
    assert "spreadToTtfFor" in market_terminal
    assert "latest.price - ttfLatest.price" not in market_terminal

    # no client-side FX conversion graph anywhere in the web client
    client_sources = "\n".join(_read(path) for path in sorted(WEB.rglob("*.ts*")))
    assert "buildLatestCurrencyGraph" not in client_sources
    assert "1 / rate" not in client_sources

    assert "buildStrategyScenario(" in app
    assert "api.normalizedMarkets.filter(" in app
    assert "api.fxRates" in app


def test_review_workspace_records_persisted_decisions_with_page_memory_actor() -> None:
    review_workspace = _read(WEB / "components" / "ReviewWorkspace.tsx")
    client = _read(WEB / "api" / "client.ts")
    store = _read(WEB / "stores" / "api.ts")
    renderer = _read(WEB / "app" / "workspaces" / "WorkspaceRenderer.tsx")

    assert "reviewDecisions: (params" in client
    assert 'get<ReviewDecisionDTO[]>("/review/decisions"' in client
    assert "recordReviewDecision: (body" in client
    assert 'post<ReviewDecisionDTO>("/review/decisions"' in client
    assert "reviewDecisions" in store
    assert "recordReviewDecision: async" in store
    # actor identity is page-memory only, never persisted in the browser
    assert 'useState("operator")' in review_workspace
    assert "localStorage" not in review_workspace
    assert "onRecordDecision={api.recordReviewDecision}" in renderer
    assert "latestStrategyRunId={api.strategyRuns[0]?.run_id ?? null}" in renderer
    assert "review.decision_recorder" in review_workspace
    assert "review.decision_history" in review_workspace


def test_runtime_workspace_shows_pipeline_health_and_stream_mode() -> None:
    runtime_workspace = _read(WEB / "components" / "RuntimeWorkspace.tsx")
    renderer = _read(WEB / "app" / "workspaces" / "WorkspaceRenderer.tsx")
    css = _read(WEB / "styles" / "app.css")
    topbar = _read(WEB / "components" / "WorkspaceTopBar.tsx")
    shell = _read(WEB / "app" / "shell" / "AppShell.tsx")
    client = _read(WEB / "api" / "client.ts")
    store = _read(WEB / "stores" / "api.ts")
    en = json.loads(_read(WEB / "i18n" / "en.json"))
    zh = json.loads(_read(WEB / "i18n" / "zh.json"))

    assert 'get<PipelineHealthDTO>("/runtime/pipeline-health"' in client
    assert "api.pipelineHealth()" in store
    assert "pipelineHealth" in runtime_workspace
    assert "quote_freshness" in runtime_workspace
    assert "consecutive_failures" in runtime_workspace
    assert "streamingActive" in topbar
    assert "stream.live" in topbar
    assert "streamingActive={api.streamingActive}" in shell
    assert "SourceSystemDTO" in runtime_workspace
    assert "sources: SourceSystemDTO[]" in runtime_workspace
    assert "streamingActive: boolean" in runtime_workspace
    assert "endpointErrors: Record<string, string>" in runtime_workspace
    assert "sources={api.sources}" in renderer
    assert "streamingActive={api.streamingActive}" in renderer
    assert "endpointErrors={api.endpointErrors}" in renderer
    assert "releaseReadinessRows" in runtime_workspace
    assert "runtime-release-readiness" in runtime_workspace
    assert "runtime-readiness-row" in runtime_workspace
    assert "runtime-readiness-state" in runtime_workspace
    assert "runtime-commercial-sources" in runtime_workspace
    assert "commercialSourceRows" in runtime_workspace
    assert "commercialSourceRows.length === 0" in runtime_workspace
    assert "credentialBlockers" in runtime_workspace
    assert "certificationBlockers" in runtime_workspace
    assert 'key: "external_security_acceptance"' in runtime_workspace
    assert 'key: "no_execution_boundary"' in runtime_workspace
    assert 'streamingActive ? t("stream.live") : t("stream.polling_fallback")' in runtime_workspace
    assert ".runtime-release-readiness" in css
    assert ".runtime-readiness-row" in css
    assert ".runtime-readiness-state.blocked" in css
    assert ".runtime-commercial-sources" in css
    assert en["runtime.release_readiness"] == "Commercial release readiness"
    assert en["runtime.release_blockers"] == "Release blockers"
    assert en["runtime.security_acceptance"] == "Security acceptance"
    assert en["runtime.security_acceptance_detail"].startswith("External security acceptance")
    assert zh["runtime.release_readiness"] == "\u5546\u4e1a\u53d1\u5e03\u5c31\u7eea"
    assert zh["runtime.release_blockers"] == "\u53d1\u5e03\u963b\u65ad\u9879"
    assert zh["runtime.security_acceptance"] == "\u5b89\u5168\u9a8c\u6536"


def test_source_center_shows_certification_gate_status() -> None:
    client = _read(WEB / "api" / "client.ts")
    source_center = _read(WEB / "components" / "SourceCenter.tsx")
    derived = _read(WEB / "app" / "workspaceDerivedData.ts")

    assert "certification_stage" in client
    assert "certification_allows_live" in client
    assert "source-cert" in source_center
    assert "certification_stage" in source_center
    assert 'sources.action.certify' in derived
    assert 'operational_status === "active_uncertified"' in derived


def test_frontend_runtime_business_data_is_api_owned() -> None:
    app = _read_application()
    store = _read(WEB / "stores" / "api.ts")
    network = _read(WEB / "components" / "NetworkWorkspace.tsx")

    assert "useApiStore()" in app
    assert "resourcePoolOptions?.sale_options ?? []" in app
    assert "resourcePoolOptions?.portfolio_resources ?? []" in app
    trading_context = _read(WEB / "app" / "tradingContext.ts")
    assert "api.normalizedMarkets.filter(" in app
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
    line_model = _read(WEB / "app" / "networkMapLines.ts")
    resource_pool_paths = _read(WEB / "app" / "resourcePoolMapPaths.ts")

    # Verification gate stays strict and is the only path into the solid layer.
    assert '"corridors_only"' in derived
    assert 'edge.source_system === "route_candidate"' in derived
    assert 'metadata.materialization === "route_candidate_edge"' in derived
    assert 'metadata.verification_status !== "verified"' in derived
    assert "VERIFIED_GEOMETRY_AUTHORITIES" in derived
    assert "geometry_coordinates" in derived
    assert "verifiedEdgeGeometryCoordinates(edge)" in line_model
    assert 'displayKind: "verified_pipeline"' in line_model
    assert 'displayKind: "indicative_route"' in line_model
    assert "verifiedCoordinates" in line_model
    assert "isRouteCandidateEdge" in line_model
    assert "metadata.route_id && metadata.route_geometry_state" not in line_model
    assert "buildSchematicRouteCoordinates" in line_model
    assert "routeLegSequence" in line_model

    # The resource-path overlay must use the same verified gate as the map.
    assert "verifiedEdgeGeometryCoordinates(edge)" in resource_pool_paths
    assert "routeEdges.some((edge) => verifiedEdgeGeometryCoordinates(edge) !== null)" in resource_pool_paths

    # Unverified evidence must be rendered, but explicitly as schematic/indicative.
    assert "buildVisibleMapNetworkLines" in line_model
    assert "buildSyntheticSelectedRouteLine" in line_model
    assert '"schematic_endpoint_curve"' in line_model
    assert 't("map.indicative_route_warning")' in map_component
    assert 'geometry_classification: "indicative_schematic_corridor"' in map_component
    assert 'geometry_verification: "unverified"' in map_component
    assert 'id: "verified-pipeline-lines"' in map_component
    assert 'id: "indicative-route-lines"' in map_component

    # The map must not be empty when backend route evidence exists.
    assert "buildVisibleMapNetworkLines({ nodes, edges, activeLayers, searchTerm, highlightedRoute })" in map_component
    assert "visibleLines.map((line)" in map_component
    assert "routeDrawingSuppressed" not in map_component
    assert "route_geometry_suppressed_body" not in map_component
    assert "fallback-flow endpoint-link" not in map_component
    assert "fallback-flow-path endpoint-link" not in map_component
    assert 't("map.route_corridors_only")' in network_workspace
    assert 't("map.visual_legend")' in network_workspace
    assert 't("map.verified_pipeline_lines")' in network_workspace
    assert 't("map.indicative_route_lines")' in network_workspace
    assert 't("map.suppressed_route_lines")' not in network_workspace
    assert "unmatchedRouteLegsWarning" in resource_pool_paths
    assert 't("map.unmatched_route_legs_warning", { count })' in resource_pool_paths
    assert 't("map.source_derived_leg_sequence_warning")' in resource_pool_paths
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


def test_strategy_performance_chart_uses_persisted_runs_without_fabricated_fallback() -> None:
    strategy_sections = _read(
        WEB / "components" / "strategy" / "StrategyShadowRunSections.tsx"
    )

    assert "runs: StrategyRunDTO[]" in strategy_sections
    assert "run.cumulative_pnl_gbp !== null" in strategy_sections
    assert "Date.parse(left.started_at_utc)" in strategy_sections
    assert ".slice(-30)" in strategy_sections
    assert "plottedRuns.length > 0" in strategy_sections
    assert 'className="strategy-performance-empty"' in strategy_sections
    assert '<polyline className="strategy-chart-line"' in strategy_sections
    assert 'className="strategy-chart-point"' in strategy_sections
    assert "Math.random" not in strategy_sections


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
