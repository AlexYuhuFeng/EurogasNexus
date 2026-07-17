"""Contract tests for extracted workspace derived data helpers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
DERIVED_DATA_TS = ROOT / "clients" / "web" / "src" / "app" / "workspaceDerivedData.ts"
APP_INDEX_TS = ROOT / "clients" / "web" / "src" / "app" / "index.ts"
PORTFOLIO_MODEL_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "model" / "usePortfolioDecisionModel.ts"
)
SOURCE_CONTROLLER_TS = (
    ROOT / "clients" / "web" / "src" / "app" / "hooks" / "useSourceCenterController.ts"
)


def test_workspace_derived_data_helpers_match_app_contract() -> None:
    """App should consume shared derived-data helpers instead of duplicating them."""

    app_text = APP_TSX.read_text(encoding="utf-8-sig")
    owner_text = PORTFOLIO_MODEL_TS.read_text(encoding="utf-8-sig")
    source_text = SOURCE_CONTROLLER_TS.read_text(encoding="utf-8-sig")
    application_text = owner_text + source_text
    helper_text = DERIVED_DATA_TS.read_text(encoding="utf-8-sig")
    for app_phrase in [
        "buildWorkspaceLatestRows({",
        "buildReviewWarnings(",
        "buildSourceStats(sources)",
        "buildSourcePostureRows(",
        "buildSourceCategoryCounts(sources)",
        "buildSourcesByCategory(sources)",
        "filterSourcesByCategory(sources, sourceCategory)",
        "sourceNextActionKey(source)",
        "resolveNetworkGeometryState(runtimeDbReady, api.nodes, api.edges)",
    ]:
        assert app_phrase in application_text
    for removed_phrase in [
        "const sourceCategoryOrder =",
        "const issueStatuses = new Set([\"failed\"",
        "const latestCapacityRows = useMemo(() => capacity.slice",
    ]:
        assert removed_phrase not in app_text + application_text
    for helper_phrase in [
        "export function latestRows",
        "export function latestOfficialFlows",
        "export function buildReviewWarnings",
        "export function buildSourceStats",
        "export function buildSourcePostureRows",
        "export function buildSourceCategoryCounts",
        "export function buildSourcesByCategory",
        "export function filterSourcesByCategory",
        "export function sourceNextActionKey",
        "export function resolveNetworkGeometryState",
        "export function buildWorkspaceLatestRows",
        '"failed"',
        '"needs_credential"',
        '"credential_disabled"',
        '"runtime_unconfigured"',
        "latestCapacityRows: latestRows(params.capacity, 5)",
        "latestTsoAccessRows: latestRows(params.tsoAccess, 6)",
        "latestTariffRows: latestRows(params.tsoTariffs, 6)",
        "latestStorageRows: latestRows(params.storage, 4)",
        "latestLngRows: latestRows(params.lng, 4)",
    ]:
        assert helper_phrase in helper_text


def test_app_barrel_exports_workspace_derived_data_helpers() -> None:
    """The App extraction barrel should expose workspace derived data helpers."""

    barrel_text = APP_INDEX_TS.read_text(encoding="utf-8-sig")
    for export_name in [
        "buildReviewWarnings",
        "buildSourceStats",
        "buildWorkspaceLatestRows",
        "latestOfficialFlows",
        "latestRows",
        "SOURCE_ISSUE_STATUSES",
        "SOURCE_CATEGORIES",
        "resolveNetworkGeometryState",
    ]:
        assert export_name in barrel_text
