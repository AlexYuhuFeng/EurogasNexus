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
    "strategy",
    "review",
    "orders",
    "sources",
    "glossary",
    "runtime",
    "settings",
    "manual",
    "access",
    "research",
    "agents",
]

EXPECTED_PRIMARY_CHILDREN = {
    "market": ["network", "market", "capacity"],
    "portfolio": ["contracts", "orders"],
    "strategy": ["strategy"],
    "decision": ["scenario", "review"],
    "system": [
        "sources",
        "runtime",
        "research",
        "agents",
        "settings",
        "manual",
        "glossary",
        "access",
    ],
}

EXPECTED_DEFAULTS = {
    "market": "network",
    "portfolio": "contracts",
    "strategy": "strategy",
    "decision": "scenario",
    "system": "sources",
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
    assert "workspaceGroups" not in navigation_text


def test_route_guard_helpers_remain_centralized() -> None:
    navigation_text = _read(WORKSPACE_NAVIGATION_TS)
    assert "export function isWorkspacePageId" in navigation_text
    assert "value is WorkspacePageId" in navigation_text
    assert "workspacePageIds.includes" in navigation_text
    assert "export function coerceWorkspacePageId" in navigation_text
    assert "fallback: WorkspacePageId = DEFAULT_WORKSPACE_PAGE_ID" in navigation_text
    assert 'export const DEFAULT_WORKSPACE_PAGE_ID: WorkspacePageId = "network"' in navigation_text


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


def test_topbar_uses_five_primary_tabs_and_no_grouped_dropdown() -> None:
    topbar_text = _read(TOPBAR_TSX)
    assert 'import { WorkspaceTabs } from "@/components/ui"' in topbar_text
    assert "workspace-primary-tabs" in topbar_text
    assert "workspace-primary" in topbar_text
    assert "primaryWorkspaces.map" in topbar_text
    assert "onOpenPrimaryWorkspace" in topbar_text
    assert "groupedMenuOpen" not in topbar_text
    assert "workspaceGroups" not in topbar_text
    assert "workspace-menu" not in topbar_text


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
        "topbar.primary_navigation",
        "topbar.current_task",
        "topbar.task_label",
    ]:
        assert en[key].strip()
        assert zh[key].strip()
        assert en[key] != key
        assert zh[key] != key


def test_old_glossary_and_manual_routes_are_rehomed_not_deleted() -> None:
    product_text = _read(PRODUCT_NAVIGATION_TS)
    assert '"glossary"' in product_text
    assert '"manual"' in product_text
    system_match = re.search(r'id:\s*"system".*?pages:\s*\[(.*?)\]', product_text, flags=re.DOTALL)
    assert system_match
    system_pages = _quoted_values(system_match.group(1))
    assert system_pages == EXPECTED_PRIMARY_CHILDREN["system"]
