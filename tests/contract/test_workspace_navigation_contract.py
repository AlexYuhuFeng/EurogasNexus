"""Workspace navigation product-contract tests."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
TOPBAR_TSX = ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.tsx"
TOPBAR_CSS = ROOT / "clients" / "web" / "src" / "components" / "WorkspaceTopBar.css"
WORKSPACE_NAVIGATION_TS = ROOT / "clients" / "web" / "src" / "workspaceNavigation.ts"
I18N_INDEX = ROOT / "clients" / "web" / "src" / "i18n" / "index.ts"

EXPECTED_GROUPS = {
    "decision": ["network", "scenario", "review"],
    "commercial": ["contracts", "market", "capacity", "orders"],
    "analytics": ["strategy", "glossary"],
    "operations": ["sources", "runtime", "settings", "manual"],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _quoted_values(text: str) -> list[str]:
    return re.findall(r'"([a-z][a-z-]*)"', text)


def test_workspace_groups_cover_all_workspace_pages_once() -> None:
    """Grouped navigation must cover the same route ids accepted by App.tsx."""

    app_text = _read(APP_TSX)
    navigation_text = _read(WORKSPACE_NAVIGATION_TS)

    pages_match = re.search(
        r"const\s+WORKSPACE_PAGES:\s*WorkspacePageId\[\]\s*=\s*\[(.*?)\];",
        app_text,
        flags=re.DOTALL,
    )
    assert pages_match, "App.tsx must expose WORKSPACE_PAGES for direct URL validation."
    app_pages = _quoted_values(pages_match.group(1))

    grouped_pages: list[str] = []
    for group_id, expected_pages in EXPECTED_GROUPS.items():
        group_match = re.search(
            rf'id:\s*"{group_id}".*?pages:\s*\[(.*?)\]',
            navigation_text,
            flags=re.DOTALL,
        )
        assert group_match, f"Missing workspace group: {group_id}"
        actual_pages = _quoted_values(group_match.group(1))
        assert actual_pages == expected_pages
        grouped_pages.extend(actual_pages)

    assert grouped_pages == [
        "network",
        "scenario",
        "review",
        "contracts",
        "market",
        "capacity",
        "orders",
        "strategy",
        "glossary",
        "sources",
        "runtime",
        "settings",
        "manual",
    ]
    assert set(grouped_pages) == set(app_pages)
    assert len(grouped_pages) == len(set(grouped_pages))


def test_workspace_group_labels_are_i18n_backed() -> None:
    """Group headings must be translated through i18n, not CSS language selectors."""

    i18n_text = _read(I18N_INDEX)
    for group_id in EXPECTED_GROUPS:
        assert f'"nav.group.{group_id}"' in i18n_text


def test_workspace_menu_does_not_use_nth_of_type_grouping() -> None:
    """The menu must not depend on visual nth-of-type ordering hacks."""

    topbar_text = _read(TOPBAR_TSX)
    assert "nth-of-type" not in topbar_text
    assert "html[lang=\"zh-CN\"]" not in topbar_text


def test_topbar_owns_menu_state_contract() -> None:
    """WorkspaceTopBar should not depend on legacy App-owned menu state props."""

    topbar_text = _read(TOPBAR_TSX)
    props_match = re.search(
        r"interface\s+WorkspaceTopBarProps\s*\{(.*?)\n\}",
        topbar_text,
        flags=re.DOTALL,
    )
    assert props_match, "WorkspaceTopBarProps interface must be explicit."
    props_body = props_match.group(1)
    assert "workspaceMenuOpen" not in props_body
    assert "onWorkspaceMenuToggle" not in props_body
    assert "useState(false)" in topbar_text
    assert "groupedMenuOpen" in topbar_text


def test_topbar_styles_are_externalized() -> None:
    """Workspace menu styles should live in a CSS file, not an injected style tag."""

    topbar_text = _read(TOPBAR_TSX)
    css_text = _read(TOPBAR_CSS)
    assert 'import "./WorkspaceTopBar.css";' in topbar_text
    assert "groupedWorkspaceMenuCss" not in topbar_text
    assert "<style>" not in topbar_text
    assert ".workspace-menu" in css_text
    assert ".workspace-menu-group-title" in css_text


def test_workspace_navigation_model_is_shared() -> None:
    """Navigation structure should live outside the rendering component."""

    topbar_text = _read(TOPBAR_TSX)
    navigation_text = _read(WORKSPACE_NAVIGATION_TS)
    assert "export const workspaceGroups" in navigation_text
    assert "export type WorkspacePageId" in navigation_text
    assert 'from "../workspaceNavigation"' in topbar_text
    assert "export const workspaceGroups" not in topbar_text
