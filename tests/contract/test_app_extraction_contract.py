"""Contract tests for gradual App.tsx extraction work."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
DEFAULT_CONTRACT_DRAFT_TS = ROOT / "clients" / "web" / "src" / "app" / "defaultContractDraft.ts"
ROUTE_METADATA_TS = ROOT / "clients" / "web" / "src" / "app" / "routeMetadata.ts"
CONTRACT_IMPORT_TS = ROOT / "clients" / "web" / "src" / "app" / "contractImport.ts"
CONTRACT_PAYLOAD_TS = ROOT / "clients" / "web" / "src" / "app" / "contractPayload.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_default_contract_draft_module_exists_before_app_wiring() -> None:
    """The default contract draft should be ready as an extracted module before App imports it."""

    app_text = _read(APP_TSX)
    module_text = _read(DEFAULT_CONTRACT_DRAFT_TS)
    assert "const defaultContractDraft" in app_text
    assert "export const defaultContractDraft" in module_text
    assert "export function cloneDefaultContractDraft" in module_text
    assert "allowed_exit_points: [...defaultContractDraft.allowed_exit_points]" in module_text
    assert "eligible_sale_modes: [...defaultContractDraft.eligible_sale_modes]" in module_text


def test_route_metadata_module_exists_before_app_wiring() -> None:
    """Route metadata helpers should be ready as extracted pure helpers before App imports them."""

    app_text = _read(APP_TSX)
    module_text = _read(ROUTE_METADATA_TS)
    for helper in [
        "normalizePointName",
        "metadataText",
        "routeLegLabel",
        "routeEdgeRouteId",
        "routeEdgeMetadataText",
    ]:
        assert f"function {helper}" in app_text
        assert f"export function {helper}" in module_text


def test_contract_import_module_exists_before_app_wiring() -> None:
    """Contract import parsing should be ready as extracted pure helpers before App imports it."""

    app_text = _read(APP_TSX)
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
        assert f"function {helper}" in app_text
        assert f"export function {helper}" in module_text
    assert 'document_status: "STAGED_REVIEW_REQUIRED"' in module_text
    assert 'document_status: "IMPORTED_JSON_DRAFT"' in module_text


def test_contract_payload_builder_exists_before_app_wiring() -> None:
    """Contract payload construction should be ready as an extracted pure builder before App imports it."""

    app_text = _read(APP_TSX)
    module_text = _read(CONTRACT_PAYLOAD_TS)
    assert "const contractPayload = useMemo" in app_text
    assert "export function buildContractPayload" in module_text
    for phrase in [
        'resource_type: "PIPELINE_IMPORT"',
        'source: "web_contract_capture"',
        "decision_support_only: true",
        "human_review_required: true",
        "notes: JSON.stringify",
    ]:
        assert phrase in module_text
