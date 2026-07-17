"""Web client structure contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "clients" / "web" / "src"
APP_SHELL = WEB_SRC / "app" / "shell" / "AppShell.tsx"
WORKSPACE_RENDERER = WEB_SRC / "app" / "workspaces" / "WorkspaceRenderer.tsx"
PORTFOLIO_MODEL = WEB_SRC / "app" / "model" / "usePortfolioDecisionModel.ts"


def test_source_center_and_topbar_are_extracted_from_app() -> None:
    app = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")
    shell = APP_SHELL.read_text(encoding="utf-8")
    renderer = WORKSPACE_RENDERER.read_text(encoding="utf-8")
    source_center = WEB_SRC / "components" / "SourceCenter.tsx"
    topbar = WEB_SRC / "components" / "WorkspaceTopBar.tsx"

    assert source_center.exists()
    assert topbar.exists()
    assert 'from "@/components/SourceCenter"' in renderer
    assert 'from "@/components/WorkspaceTopBar"' in shell
    assert "Data Source Center" not in app + shell + renderer
    assert "source-category-list" not in app + shell + renderer


def test_network_cockpit_exposes_warning_evidence_stack() -> None:
    model = PORTFOLIO_MODEL.read_text(encoding="utf-8")
    shell = APP_SHELL.read_text(encoding="utf-8")
    en = (WEB_SRC / "i18n" / "en.json").read_text(encoding="utf-8")
    zh = (WEB_SRC / "i18n" / "zh.json").read_text(encoding="utf-8")

    assert "reviewEvidenceItems" in model
    assert "reviewEvidenceItems={portfolio.reviewEvidenceItems}" in shell
    assert "home.evidence_stack" in en
    assert "home.evidence_stack" in zh
    assert "home.review_warnings" in en
    assert "home.review_warnings" in zh


def test_app_is_a_small_composition_root() -> None:
    app = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")

    assert len(app.splitlines()) <= 20
    assert "useAppController" in app
    assert "<AppShell" in app
    assert "activeWorkspace ===" not in app
    assert "useEffect(" not in app
