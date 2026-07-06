"""Contract tests for extracted workspace derived data helpers."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
DERIVED_DATA_TS = ROOT / "clients" / "web" / "src" / "app" / "workspaceDerivedData.ts"
APP_INDEX_TS = ROOT / "clients" / "web" / "src" / "app" / "index.ts"


def test_workspace_derived_data_helpers_match_app_contract() -> None:
    """Derived helper functions should preserve current App.tsx list slicing and warning logic."""

    app_text = APP_TSX.read_text(encoding="utf-8-sig")
    helper_text = DERIVED_DATA_TS.read_text(encoding="utf-8-sig")
    for app_phrase in [
        "const latestOfficialFlows = useMemo(() => flows",
        "const latestCapacityRows = useMemo(() => capacity.slice(0, 5), [capacity]);",
        "const latestTsoAccessRows = useMemo(() => tsoAccess.slice(0, 6), [tsoAccess]);",
        "const latestTariffRows = useMemo(() => tsoTariffs.slice(0, 6), [tsoTariffs]);",
        "const latestStorageRows = useMemo(() => storage.slice(0, 4), [storage]);",
        "const latestLngRows = useMemo(() => lng.slice(0, 4), [lng]);",
        "const reviewWarnings = useMemo(",
        "const sourceStats = useMemo(() => {",
    ]:
        assert app_phrase in app_text
    for helper_phrase in [
        "export function latestRows",
        "export function latestOfficialFlows",
        "export function buildReviewWarnings",
        "export function buildSourceStats",
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
    ]:
        assert export_name in barrel_text
