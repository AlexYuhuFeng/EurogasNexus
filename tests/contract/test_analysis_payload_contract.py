"""Contract tests for the extracted analysis payload builder.

The builder sends only what the analysis pipeline reads. The request's selection and
filter fields are refused by the platform when non-empty (`422
analysis_selection_not_supported`), so no client request builder may fill one in: a
selection the platform cannot apply would otherwise describe a narrowing the analyst
never received.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
ANALYSIS_PAYLOAD_TS = ROOT / "clients" / "web" / "src" / "app" / "analysisPayload.ts"
REVIEW_HOOK_TS = ROOT / "clients" / "web" / "src" / "app" / "hooks" / "useReviewAnalysis.ts"
APP_INDEX_TS = ROOT / "clients" / "web" / "src" / "app" / "index.ts"
COPILOT_MODEL_TS = ROOT / "clients" / "web" / "src" / "app" / "model" / "copilotModel.ts"
API_CLIENT_TS = ROOT / "clients" / "web" / "src" / "api" / "client.ts"

# The selection and filter fields both analysis routes refuse, from the backend models in
# `eurogas_nexus/domain/analysis/contracts.py`.
REFUSED_SELECTION_FIELDS = (
    "selected_terms",
    "selected_assets",
    "selected_contracts",
    "selected_strategies",
    "selected_resources",
    "include_sections",
    "portfolio_id",
)


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
        'model: "deepseek-v4-flash"',
        'language.startsWith("zh") ? "zh-CN" : "en"',
    ]:
        assert phrase in module_text


def test_the_report_run_takes_no_resource_list() -> None:
    """A report is not scoped by a selection, so the resource list is not an input."""

    hook_text = REVIEW_HOOK_TS.read_text(encoding="utf-8-sig")
    controller_text = (ROOT / "clients" / "web" / "src" / "app" / "hooks" / "useAppController.ts").read_text(
        encoding="utf-8-sig"
    )
    # The hook takes the language and the cited snapshot; the controller no longer has to
    # gather portfolio resources to build the payload.
    assert re.search(
        r"export function useReviewAnalysis\(\s*language: string,.*analysisSnapshotId: string \| null = null,\s*\)",
        hook_text,
        re.S,
    )
    assert "useReviewAnalysis(i18n.language, api.reviewSnapshotId)" in controller_text
    assert "portfolioResources" not in hook_text


def test_no_client_request_builder_sends_a_refused_selection_field() -> None:
    """No field is sent that the platform refuses, and none is declared as sendable."""

    sources = {
        "analysisPayload.ts": ANALYSIS_PAYLOAD_TS.read_text(encoding="utf-8-sig"),
        "copilotModel.ts": COPILOT_MODEL_TS.read_text(encoding="utf-8-sig"),
    }
    for name, text in sources.items():
        for field in REFUSED_SELECTION_FIELDS:
            assert field not in text, f"{name} sends the refused field {field}"

    # The request DTO the client types against declares only fields the platform accepts.
    dto = API_CLIENT_TS.read_text(encoding="utf-8-sig")
    block = dto.split("export interface AnalysisRequestDTO {", 1)[1].split("}", 1)[0]
    for field in REFUSED_SELECTION_FIELDS:
        assert field not in block, f"AnalysisRequestDTO declares the refused field {field}"
    assert "analysis_snapshot_id" in block


def test_app_barrel_exports_analysis_payload_builder() -> None:
    """The App extraction barrel should expose the analysis payload builder for future wiring."""

    barrel_text = APP_INDEX_TS.read_text(encoding="utf-8-sig")
    assert 'export { buildAnalysisPayload } from "./analysisPayload";' in barrel_text
