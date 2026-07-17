"""Contract tests for App.tsx extraction boundaries."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
API_STORE_TS = ROOT / "clients" / "web" / "src" / "stores" / "api.ts"
DEFAULT_CONTRACT_DRAFT_TS = ROOT / "clients" / "web" / "src" / "app" / "defaultContractDraft.ts"
ROUTE_METADATA_TS = ROOT / "clients" / "web" / "src" / "app" / "routeMetadata.ts"
RESOURCE_POOL_MAP_PATHS_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "resourcePoolMapPaths.ts"
)
CONTRACT_IMPORT_TS = ROOT / "clients" / "web" / "src" / "app" / "contractImport.ts"
CONTRACT_PAYLOAD_TS = ROOT / "clients" / "web" / "src" / "app" / "contractPayload.ts"
RESOURCE_POOL_REQUEST_TS = ROOT / "clients" / "web" / "src" / "app" / "resourcePoolRequest.ts"
STRATEGY_SCENARIO_TS = ROOT / "clients" / "web" / "src" / "app" / "strategyScenario.ts"
ROUTE_RECOMMENDATION_REQUEST_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "routeRecommendationRequest.ts"
)
CONTRACT_EDITOR_TS = ROOT / "clients" / "web" / "src" / "app" / "hooks" / "useContractEditor.ts"
PORTFOLIO_MODEL_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "usePortfolioDecisionModel.ts"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_default_contract_draft_module_is_wired_into_app() -> None:
    """The default contract draft should be imported from the extracted module."""

    app_text = _read(APP_TSX)
    owner_text = _read(CONTRACT_EDITOR_TS)
    module_text = _read(DEFAULT_CONTRACT_DRAFT_TS)
    assert "const defaultContractDraft" not in app_text
    assert "cloneDefaultContractDraft" in owner_text
    assert "export const defaultContractDraft" in module_text
    assert "export function cloneDefaultContractDraft" in module_text
    assert "allowed_exit_points: [...defaultContractDraft.allowed_exit_points]" in module_text
    assert "eligible_sale_modes: [...defaultContractDraft.eligible_sale_modes]" in module_text


def test_route_metadata_module_is_wired_into_app() -> None:
    """Route metadata helpers should be imported instead of duplicated in App.tsx."""

    app_text = _read(APP_TSX)
    module_text = _read(ROUTE_METADATA_TS)
    resource_pool_paths_text = _read(RESOURCE_POOL_MAP_PATHS_TS)
    for helper in [
        "normalizePointName",
        "metadataText",
        "routeLegLabel",
        "routeEdgeRouteId",
        "routeEdgeMetadataText",
    ]:
        assert f"function {helper}" not in app_text
        assert f"export function {helper}" in module_text
        assert helper in resource_pool_paths_text


def test_contract_import_module_is_wired_into_app() -> None:
    """Contract import parsing should be imported instead of duplicated in App.tsx."""

    app_text = _read(APP_TSX)
    owner_text = _read(CONTRACT_EDITOR_TS)
    module_text = _read(CONTRACT_IMPORT_TS)
    for helper in [
        "stringFromRecord",
        "numberFromRecord",
        "nullableNumberFromRecord",
        "stringArrayFromRecord",
        "notesRecordFromRecord",
        "contractDraftFromRecord",
        "contractRecordFromParsedJson",
        "parseContractTextDraft",
        "contractRecordFromImportedFile",
    ]:
        assert f"function {helper}" not in app_text
        assert f"export function {helper}" in module_text
    for helper in [
        "contractDraftFromRecord",
        "contractRecordFromImportedFile",
    ]:
        assert helper in owner_text
    assert 'document_status: "STAGED_REVIEW_REQUIRED"' in module_text
    assert 'document_status: "IMPORTED_JSON_DRAFT"' in module_text


def test_contract_payload_builder_is_wired_into_app() -> None:
    """Contract payload construction should be imported from the extracted builder."""

    owner_text = _read(CONTRACT_EDITOR_TS)
    module_text = _read(CONTRACT_PAYLOAD_TS)
    assert "buildContractPayload(contract)" in owner_text
    assert "export function buildContractPayload" in module_text
    for phrase in [
        'resource_type: "PIPELINE_IMPORT"',
        'source: "web_contract_capture"',
        "decision_support_only: true",
        "human_review_required: true",
        "notes: JSON.stringify",
    ]:
        assert phrase in module_text


def test_resource_pool_request_builder_is_wired_into_app() -> None:
    """Resource-pool optimization request construction should be imported from the builder."""

    owner_text = _read(PORTFOLIO_MODEL_TS)
    module_text = _read(RESOURCE_POOL_REQUEST_TS)
    assert "buildResourcePoolOptimizationRequest(" in owner_text
    assert "api.upstreamContracts" in owner_text
    assert "export function buildResourcePoolOptimizationRequest" in module_text
    for phrase in [
        'portfolio_id: "web-resource-pool"',
        'objective: "MAX_DAILY_PNL"',
        "annual_financing_rate_pct",
    ]:
        assert phrase in module_text
    assert "research_only" not in module_text


def test_strategy_scenario_builder_is_wired_into_app() -> None:
    """Strategy scenario construction should be imported from the extracted builder."""

    owner_text = _read(PORTFOLIO_MODEL_TS)
    module_text = _read(STRATEGY_SCENARIO_TS)
    assert "buildStrategyScenario(" in owner_text
    assert "api.fxRates" in owner_text
    assert "export function buildStrategyScenario" in module_text
    for phrase in [
        'run_mode: "SHADOW_RUN"',
        'strategy_id: "nbp-sap-icis-ocm-window"',
        'price_name: "ICE_OCM"',
        "marketPriceGbpMwh",
        "latestPositiveObservation",
        "require_tso_access: true",
    ]:
        assert phrase in module_text
    assert "research_only" not in module_text


def test_route_recommendation_request_builder_is_wired_into_app() -> None:
    """Route recommendation request construction should be imported from the builder."""

    owner_text = _read(PORTFOLIO_MODEL_TS)
    module_text = _read(ROUTE_RECOMMENDATION_REQUEST_TS)
    assert "buildRouteRecommendationRequest(" in owner_text
    assert "totalPoolVolume" in owner_text
    assert "export function buildRouteRecommendationRequest" in module_text
    for phrase in [
        'request_id: "web-db-backed-route-allocation"',
        'capacity_product: "ANNUAL"',
        'firmness: "FIRM"',
        'price_unit: option.sale_price_unit ?? "EUR/MWh"',
    ]:
        assert phrase in module_text
    assert "research_only" not in module_text


def test_api_store_does_not_send_research_only_payload_field() -> None:
    """The API store should not carry the old research-only payload field to backend calls."""

    store_text = _read(API_STORE_TS)
    assert "withoutLegacyFlag" in store_text
    assert "api.optimizeResourcePool(withoutLegacyFlag(request))" in store_text
    assert "api.evaluateStrategyLab(withoutLegacyFlag(scenario))" in store_text
    assert "research_only" not in store_text
