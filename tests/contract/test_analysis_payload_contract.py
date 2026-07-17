"""Contract tests for the extracted analysis payload builder."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
ANALYSIS_PAYLOAD_TS = ROOT / "clients" / "web" / "src" / "app" / "analysisPayload.ts"
REVIEW_HOOK_TS = ROOT / "clients" / "web" / "src" / "app" / "hooks" / "useReviewAnalysis.ts"
APP_INDEX_TS = ROOT / "clients" / "web" / "src" / "app" / "index.ts"


def test_analysis_payload_builder_matches_app_contract() -> None:
    """The extracted builder should preserve the App.tsx analysis request contract."""

    app_text = APP_TSX.read_text(encoding="utf-8-sig")
    hook_text = REVIEW_HOOK_TS.read_text(encoding="utf-8-sig")
    module_text = ANALYSIS_PAYLOAD_TS.read_text(encoding="utf-8-sig")
    assert "useAppController" in app_text
    assert "const analysisPayload = useMemo(" in hook_text
    assert "buildAnalysisPayload(" in hook_text
    assert "export function buildAnalysisPayload" in module_text
    for phrase in [
        'task: "PORTFOLIO_REPORT"',
        'provider_id: "DEEPSEEK"',
        'model: "deepseek-chat"',
        'selected_terms: ["TTF", "NBP", "ICE OCM"]',
        'selected_assets: ["TTF", "NBP", "BBL"]',
        'selected_contracts: portfolioResources.map((resource) => resource.resource_id)',
        'language.startsWith("zh") ? "zh-CN" : "en"',
    ]:
        assert phrase in module_text


def test_app_barrel_exports_analysis_payload_builder() -> None:
    """The App extraction barrel should expose the analysis payload builder for future wiring."""

    barrel_text = APP_INDEX_TS.read_text(encoding="utf-8-sig")
    assert 'export { buildAnalysisPayload } from "./analysisPayload";' in barrel_text
