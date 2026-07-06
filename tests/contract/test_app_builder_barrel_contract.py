"""Contract tests for the App extraction export barrel."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_INDEX_TS = ROOT / "clients" / "web" / "src" / "app" / "index.ts"


def test_app_builder_barrel_exports_extracted_modules() -> None:
    """The App extraction barrel should expose every extracted builder/helper needed for App.tsx wiring."""

    barrel_text = APP_INDEX_TS.read_text(encoding="utf-8-sig")
    for export_line in [
        'export { buildContractPayload } from "./contractPayload";',
        'export { cloneDefaultContractDraft, defaultContractDraft } from "./defaultContractDraft";',
        'export type { ContractDraft } from "./defaultContractDraft";',
        'export { contractDraftFromRecord, contractRecordFromImportedFile } from "./contractImport";',
        'export { buildResourcePoolOptimizationRequest } from "./resourcePoolRequest";',
        'export { buildRouteRecommendationRequest } from "./routeRecommendationRequest";',
        'export { buildStrategyScenario } from "./strategyScenario";',
        'metadataText,',
        'normalizePointName,',
        'routeEdgeMetadataText,',
        'routeEdgeRouteId,',
        'routeLegLabel,',
    ]:
        assert export_line in barrel_text
