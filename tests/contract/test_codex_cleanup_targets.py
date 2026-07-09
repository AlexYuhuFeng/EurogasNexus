"""Contract tests for Codex/local cleanup target documentation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLEANUP_TARGETS = ROOT / ".agent" / "patches" / "CODEX_CLEANUP_TARGETS.md"
APP_NAVIGATION_MIGRATION = (
    ROOT / ".agent" / "patches" / "app_workspace_navigation_source_migration.md"
)
LEGACY_MENU_REMOVAL = ROOT / ".agent" / "patches" / "remove_legacy_workspace_menu.md"

REQUIRED_TARGETS = [
    "Target 1: App workspace source migration",
    "Target 2: App-owned legacy workspace menu state",
    "Target 3: Legacy props passed into WorkspaceTopBar",
    "Target 4: Old flat App workspace menu block",
    "Target 5: Temporary TopBar compatibility index",
    "Target 6: Transitional App parity test",
]

REQUIRED_PHRASES = [
    "Do not rewrite `App.tsx` wholesale.",
    "Do not change route ids",
    "@/workspaceNavigation",
    "coerceWorkspacePageId",
    "DEFAULT_WORKSPACE_PAGE_ID",
    "WorkspaceTopBarProps",
    "workspace-menu",
    "pytest -q tests/contract/test_workspace_navigation_contract.py",
    "npm --prefix clients/web run build",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_codex_cleanup_targets_document_exists() -> None:
    """The Codex cleanup checklist should be present as the single cleanup entrypoint."""

    assert CLEANUP_TARGETS.exists()
    assert APP_NAVIGATION_MIGRATION.exists()
    assert LEGACY_MENU_REMOVAL.exists()


def test_codex_cleanup_targets_cover_all_legacy_navigation_work() -> None:
    """The checklist should explicitly cover all known temporary navigation cleanup targets."""

    text = _read(CLEANUP_TARGETS)
    for target in REQUIRED_TARGETS:
        assert target in text
    for phrase in REQUIRED_PHRASES:
        assert phrase in text


def test_codex_cleanup_targets_reference_patch_guides() -> None:
    """The checklist should link to focused patch guides instead of encouraging broad rewrites."""

    text = _read(CLEANUP_TARGETS)
    assert ".agent/patches/app_workspace_navigation_source_migration.md" in text
    assert ".agent/patches/remove_legacy_workspace_menu.md" in text
    assert "clients/web/src/App.tsx" in text
    assert "clients/web/src/components/WorkspaceTopBar.tsx" in text
    assert "tests/contract/test_workspace_navigation_contract.py" in text
