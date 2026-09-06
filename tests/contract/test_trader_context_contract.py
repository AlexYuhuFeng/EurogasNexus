"""CR-02 trader-context and cross-workspace selection contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "clients" / "web" / "src"


def _read(*parts: str) -> str:
    return (WEB.joinpath(*parts)).read_text(encoding="utf-8-sig")


def _json(lang: str) -> dict:
    return json.loads(_read("i18n", f"{lang}.json"))


def test_context_subsystem_separates_trader_selection_persistence_and_evidence() -> None:
    trader = _read("app", "context", "traderContext.ts")
    selection = _read("app", "context", "selectionContext.ts")
    persistence = _read("app", "context", "contextPersistence.ts")
    invalidation = _read("app", "context", "contextInvalidation.ts")

    assert "gasDay" in trader
    assert "deliveryProduct" in trader
    assert "hubId" in trader
    assert "portfolioId" not in trader
    assert "routeId" in selection
    assert "resourceId" in selection
    assert "strategyRunId" in selection
    assert "TRADER_CONTEXT_STORAGE_KEY" in persistence
    assert "traderContextKey" in invalidation
    assert "resultContextMatches" in invalidation


def test_app_controller_uses_shared_context_and_no_longer_duplicates_gas_day() -> None:
    controller = _read("app", "hooks", "useAppController.ts")
    cockpit = _read("app", "hooks", "useCockpitControls.ts")
    assert "useTraderContext()" in controller
    assert "useSelectionContext()" in controller
    assert "trader.gasDay" in controller
    assert "trader.deliveryProduct" in controller
    assert "trader.hubId" in controller
    assert "selectedResourceId: selection.resourceId" in controller
    assert "gasDay" not in cockpit
    assert "deliveryProduct" not in cockpit


def test_context_url_precedence_and_legacy_workspace_links_are_explicit() -> None:
    url = _read("app", "context", "contextUrl.ts")
    hook = _read("app", "context", "useTraderContext.ts")
    navigation = _read("app", "hooks", "useWorkspaceNavigation.ts")

    for key in ["gasDay", "product", "hub"]:
        assert key in url
    assert "resolveTraderContext" in url
    assert "readPersistedTraderContext()" in hook
    assert "replaceState" in hook
    assert "pushState" in hook
    assert "new URLSearchParams(window.location.search).get(\"workspace\")" in navigation


def test_portfolio_model_consumes_hub_and_resource_selection_intentionally() -> None:
    model = _read("app", "model", "usePortfolioDecisionModel.ts")
    strategy = _read("app", "strategyScenario.ts")

    assert "hubId: SupportedHubId | null" in model
    assert "selectedResourceId: string | null" in model
    assert "(!hubId || observation.hub.toUpperCase() === hubId)" in model
    assert "selectedResourceId?: string | null" in strategy
    assert "candidate.resource_id === selectedResourceId" in strategy
    assert "optimizerContextMismatch" in model
    assert "strategyContextMismatch" in model
    assert "optimizeResourcePoolForCurrentContext" in model


def test_high_value_cross_workspace_handoffs_are_explicit_actions() -> None:
    network = _read("components", "NetworkWorkspace.tsx")
    contracts = _read("components", "ContractWorkbench.tsx")
    strategy = _read("components", "StrategyShadowRunTerminal.tsx")
    review = _read("components", "ReviewWorkspace.tsx")

    assert "onOpenScenario: () => void" in network
    assert 't("network.open_in_scenario")' in network
    assert "onOpenStrategyForResource" in contracts
    assert 't("contracts.open_in_strategy")' in contracts
    assert "onReviewRun: (runId: string) => void" in strategy
    assert 't("strategy.review_decision")' in strategy
    assert "carriedStrategyRunId" in review


def test_context_ui_is_compact_accessible_and_clearable() -> None:
    topbar = _read("components", "WorkspaceTopBar.tsx")
    market = _read("components", "MarketTerminal.tsx")

    assert 'aria-label={t("context.hub")}' in topbar
    assert 'onHubChange(event.target.value || null)' in topbar
    assert "SUPPORTED_HUB_IDS" in topbar
    assert 'aria-pressed={focusedHub === definition.hub}' in market
    assert "onHubChange(focusedHub === definition.hub ? null : definition.hub)" in market


def test_context_labels_have_en_zh_parity() -> None:
    en = _json("en")
    zh = _json("zh")
    keys = [
        "context.hub",
        "context.no_hub_focus",
        "context.result_mismatch",
        "context.result_mismatch_hint",
        "network.open_in_scenario",
        "scenario.carried_route",
        "strategy.carried_resource",
        "strategy.review",
        "strategy.review_decision",
        "review.carried_strategy_run",
        "contracts.open_in_strategy",
        "contracts.open_in_strategy_unavailable",
    ]
    for key in keys:
        assert en[key].strip()
        assert zh[key].strip()


def test_backend_evidence_state_is_not_mixed_into_trader_context() -> None:
    trader = _read("app", "context", "traderContext.ts")
    for backend_field in ["asOf", "freshness", "provenance", "entitlement", "runtime"]:
        assert backend_field not in trader
