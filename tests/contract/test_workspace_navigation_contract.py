"""Workspace navigation product-contract tests for CR-01 / P1A."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
NAVIGATION_HOOK_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "hooks" / "useWorkspaceNavigation.ts"
)
TOPBAR_TSX = ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.tsx"
TOPBAR_CSS = ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.css"
WORKSPACE_NAVIGATION_TS = ROOT / "clients" / "web" / "src" / "workspaceNavigation.ts"
PRODUCT_NAVIGATION_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "navigation" / "productNavigation.ts"
)
RENDERER_TSX = ROOT / "clients" / "web" / "src" / "app" / "workspaces" / "WorkspaceRenderer.tsx"
I18N_EN = ROOT / "clients" / "web" / "src" / "i18n" / "en.json"
I18N_ZH = ROOT / "clients" / "web" / "src" / "i18n" / "zh.json"

EXPECTED_PAGES = [
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
    "access",
    "research",
]

#: Page ids removed by CP-00 (design basis 2, I.1); their addresses redirect to Research → Reports.
RETIRED_PAGES = ["strategy", "agents"]

EXPECTED_PRIMARY_CHILDREN = {
    "market": ["market", "network", "capacity"],
    "portfolio": ["contracts", "orders"],
    "strategy": ["research"],
    "decision": ["scenario", "review"],
    "system": ["settings", "manual", "glossary"],
    "administration": ["sources", "runtime", "access"],
}

EXPECTED_DEFAULTS = {
    "market": "market",
    "portfolio": "contracts",
    "strategy": "research",
    "decision": "scenario",
    "system": "manual",
    "administration": "sources",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _quoted_values(text: str) -> list[str]:
    return re.findall(r'"([a-z][a-z-]*)"', text)


def _product_children(text: str) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {}
    for primary_id, expected_pages in EXPECTED_PRIMARY_CHILDREN.items():
        match = re.search(
            rf'id:\s*"{primary_id}".*?pages:\s*\[(.*?)\]',
            text,
            flags=re.DOTALL,
        )
        assert match, f"Missing primary workspace: {primary_id}"
        actual_pages = _quoted_values(match.group(1))
        assert actual_pages == expected_pages
        children[primary_id] = actual_pages
    return children


def test_technical_page_registry_preserves_all_route_ids() -> None:
    navigation_text = _read(WORKSPACE_NAVIGATION_TS)
    assert "export const workspacePageIds: WorkspacePageId[] = [" in navigation_text
    for page in EXPECTED_PAGES:
        assert f'"{page}"' in navigation_text
    for page in RETIRED_PAGES:
        assert f'| "{page}"' not in navigation_text
    assert "workspaceGroups" not in navigation_text


def test_route_guard_helpers_remain_centralized() -> None:
    navigation_text = _read(WORKSPACE_NAVIGATION_TS)
    assert "export function isWorkspacePageId" in navigation_text
    assert "value is WorkspacePageId" in navigation_text
    assert "workspacePageIds.includes" in navigation_text
    assert "export function coerceWorkspacePageId" in navigation_text
    assert "fallback: WorkspacePageId = DEFAULT_WORKSPACE_PAGE_ID" in navigation_text
    assert 'export const DEFAULT_WORKSPACE_PAGE_ID: WorkspacePageId = "market"' in navigation_text


def test_primary_workspace_model_owns_child_and_default_mapping() -> None:
    product_text = _read(PRODUCT_NAVIGATION_TS)
    children = _product_children(product_text)
    all_children = [page for pages in children.values() for page in pages]
    assert sorted(all_children) == sorted(EXPECTED_PAGES)
    for primary, default_page in EXPECTED_DEFAULTS.items():
        assert f'id: "{primary}"' in product_text
        assert f'defaultPage: "{default_page}"' in product_text
    assert "export function primaryWorkspaceForPage" in product_text
    assert "export function defaultWorkspacePageForPrimary" in product_text
    assert "export function isPrimaryWorkspaceId" in product_text


def test_technical_view_to_primary_mapping_is_complete_and_unique() -> None:
    product_text = _read(PRODUCT_NAVIGATION_TS)
    mapped = []
    for primary, pages in EXPECTED_PRIMARY_CHILDREN.items():
        primary_match = re.search(
            rf'id:\s*"{primary}".*?defaultPage:',
            product_text,
            flags=re.DOTALL,
        )
        assert primary_match
        for page in pages:
            assert f'"{page}"' in product_text
        mapped.extend(pages)
    assert sorted(mapped) == sorted(EXPECTED_PAGES)
    assert len(mapped) == len(set(mapped))


def test_navigation_hook_derives_primary_and_opens_default_views() -> None:
    hook_text = _read(NAVIGATION_HOOK_TS)
    assert "primaryWorkspaceForPage(activeWorkspace)" in hook_text
    assert "function openPrimaryWorkspace(primary: PrimaryWorkspaceId)" in hook_text
    assert "defaultWorkspacePageForPrimary(primary)" in hook_text
    assert "coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID)" in hook_text
    assert 'window.addEventListener("popstate", syncWorkspaceFromUrl)' in hook_text


def test_topbar_composes_primary_tabs_without_a_grouped_dropdown() -> None:
    topbar_text = _read(TOPBAR_TSX)
    # The tablist stays owned by the shared primitive; the import may carry other
    # primitives from the same barrel (the status badge joined it for the
    # data-plane state, which §13 of the UI constitution keeps as a badge).
    assert re.search(r'import \{[^}]*\bWorkspaceTabs\b[^}]*\} from "@/components/ui"', topbar_text)
    assert "workspace-primary-tabs" in topbar_text
    assert "workspace-primary" in topbar_text
    # WF-05: the primary row is the four working modes from the mode registry, filtered by the
    # caller's identity; the utilities (Help & Settings, Administration) still come from the
    # primary registry, filtered by the Architecture V2 control-plane boundary, and live in the
    # account area and the compact drawer rather than the primary row.
    assert "visibleModes(currentUser)" in topbar_text
    assert "tabs={modeTabs}" in topbar_text
    assert "onOpenMode" in topbar_text
    assert "primaryWorkspaces" in topbar_text
    assert "visiblePrimaries.filter" in topbar_text
    assert "onOpenPrimaryWorkspace" in topbar_text
    assert "groupedMenuOpen" not in topbar_text
    assert "workspaceGroups" not in topbar_text
    assert "workspace-menu" not in topbar_text


def test_control_plane_boundary_is_declared_and_gated() -> None:
    """Architecture V2 Wave 3: administration is a separate, gated surface."""

    product_text = _read(PRODUCT_NAVIGATION_TS)
    topbar_text = _read(TOPBAR_TSX)
    shell_text = _read(
        ROOT / "clients" / "web" / "src" / "app" / "shell" / "AppShell.tsx"
    )
    restricted = ROOT / "clients" / "web" / "src" / "components" / "RestrictedSurface.tsx"

    assert 'id: "administration"' in product_text
    assert "controlPlane: true" in product_text
    assert "export function isControlPlanePage" in product_text

    # The tab row is filtered by the server composition, and a deep link into a
    # control-plane page renders the restricted notice instead of the workspace.
    assert "compositionSeesAdministration" in topbar_text
    assert "visiblePrimaries" in topbar_text
    assert "isControlPlanePage(" in shell_text
    assert "<RestrictedSurface" in shell_text

    assert restricted.exists()
    restricted_text = _read(restricted)
    assert "data-restricted-surface" in restricted_text
    assert "<button" not in restricted_text


def test_topbar_styles_are_externalized_and_keyboard_primitive_owned() -> None:
    topbar_text = _read(TOPBAR_TSX)
    css_text = _read(TOPBAR_CSS)
    assert 'import "./WorkspaceTopBar.css";' in topbar_text
    assert "<style>" not in topbar_text
    assert ".workspace-primary-tabs" in css_text
    assert ".workspace-local-task" in css_text
    assert "groupedWorkspaceMenuCss" not in topbar_text


def test_workspace_renderer_uses_local_task_tabs_not_group_page_tabs() -> None:
    renderer_text = _read(RENDERER_TSX)
    assert "primaryWorkspaceForPage(activeWorkspace)" in renderer_text
    assert "<WorkspaceTabs" in renderer_text
    assert "localTabs.length > 1" in renderer_text
    assert "workspace-page-tabs" in renderer_text
    assert "workspaceGroups" not in renderer_text


def test_primary_labels_are_i18n_backed_and_parity_aligned() -> None:
    en = json.loads(_read(I18N_EN))
    zh = json.loads(_read(I18N_ZH))
    for key in [
        "nav.primary.market",
        "nav.primary.market.description",
        "nav.primary.portfolio",
        "nav.primary.portfolio.description",
        "nav.primary.strategy",
        "nav.primary.strategy.description",
        "nav.primary.decision",
        "nav.primary.decision.description",
        "nav.primary.system",
        "nav.primary.system.description",
        "nav.primary.administration",
        "nav.primary.administration.description",
        "topbar.primary_navigation",
        "topbar.current_task",
        "topbar.task_label",
    ]:
        assert en[key].strip()
        assert zh[key].strip()
        assert en[key] != key
        assert zh[key] != key


MODE_NAVIGATION_TS = ROOT / "clients" / "web" / "src" / "app" / "navigation" / "modeNavigation.ts"


def test_four_modes_are_the_primary_row_and_decision_center_is_dissolved() -> None:
    """WF-05: Desk, Deals, Book, Research; every Decision Center task has a home."""

    modes_text = _read(MODE_NAVIGATION_TS)
    assert 'export const MODE_IDS = ["desk", "deals", "book", "research"] as const;' in modes_text
    # Review sits with the deals it approves; nomination and storage planning are the two views
    # of Book → Planning. Scenario and Optimise left with CP-00 and redirect to Deals → Contracts.
    # The page addresses stay, so old links keep working.
    for task_id, page, page_task in [
        ("review", "scenario", "review"),
        ("planning", "scenario", "nomination"),
    ]:
        assert re.search(
            rf'id: "{task_id}", labelKey: "[^"]+",(?: shortLabelKey: "[^"]+",)? '
            rf'page: "{page}", pageTask: "{page_task}"',
            modes_text,
        ), task_id
    assert 'alsoPageTasks: ["dispatch"]' in modes_text
    assert '"scenario:optimize": { page: "contracts", task: "resources" }' in modes_text
    assert "export function redirectSearch" in modes_text
    en = json.loads(_read(I18N_EN))
    zh = json.loads(_read(I18N_ZH))
    for mode in ["desk", "deals", "book", "research"]:
        for key in (f"nav.mode.{mode}", f"nav.mode.{mode}.description"):
            assert en[key].strip() and zh[key].strip() and en[key] != zh[key]


def test_old_glossary_and_manual_routes_are_rehomed_not_deleted() -> None:
    product_text = _read(PRODUCT_NAVIGATION_TS)
    assert '"glossary"' in product_text
    assert '"manual"' in product_text
    system_match = re.search(r'id:\s*"system".*?pages:\s*\[(.*?)\]', product_text, flags=re.DOTALL)
    assert system_match
    system_pages = _quoted_values(system_match.group(1))
    assert system_pages == EXPECTED_PRIMARY_CHILDREN["system"]
