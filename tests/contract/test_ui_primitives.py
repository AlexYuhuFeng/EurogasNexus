"""Contract test: shared Web UI primitives are owned and consumed consistently."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = ROOT / "clients" / "web" / "src"
UI_DIR = WEB_SRC / "components" / "ui"
SOURCE_CENTER = WEB_SRC / "components" / "SourceCenter.tsx"
RUNTIME_WORKSPACE = WEB_SRC / "components" / "RuntimeWorkspace.tsx"

PRIMITIVES = (
    "MetricStrip",
    "PanelHeader",
    "StatusBadge",
    "WorkspaceTabs",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shared_ui_primitives_have_one_home() -> None:
    """Primitive components live under components/ui and are exported there."""
    index = _read(UI_DIR / "index.ts")
    for primitive in PRIMITIVES:
        assert (UI_DIR / f"{primitive}.tsx").exists(), primitive
        assert f'export {{ {primitive} }}' in index


def test_source_and_runtime_use_shared_primitives() -> None:
    """Source Center and Runtime consume the shared primitive boundary."""
    source = _read(SOURCE_CENTER)
    runtime = _read(RUNTIME_WORKSPACE)

    for primitive in PRIMITIVES:
        assert f'<{primitive}' in source
        assert f'<{primitive}' in runtime

    assert 'from "@/components/ui"' in source
    assert 'from "@/components/ui"' in runtime


def test_duplicated_tab_markup_removed_from_migrated_workspaces() -> None:
    """Task tabs are delegated to WorkspaceTabs, not duplicated inline."""
    source = _read(SOURCE_CENTER)
    runtime = _read(RUNTIME_WORKSPACE)

    assert re.search(r'<WorkspaceTabs.*?role="tablist"', source, re.DOTALL)
    assert re.search(r'<WorkspaceTabs.*?role="tablist"', runtime, re.DOTALL)
    assert not re.search(r'<button.*?role="tab"', source, re.DOTALL)
    assert not re.search(r'<button.*?role="tab"', runtime, re.DOTALL)
    assert "handleViewKeyDown" not in source
    assert "handleViewKeyDown" not in runtime
    assert "Tab semantics are owned" not in source
    assert "Tab semantics are owned" not in runtime
    assert "StatusBadge owns" not in runtime
    assert 'variant="runtime-readiness-state"' in runtime


def test_no_ui_framework_dependency_added() -> None:
    """This baseline keeps the approved plain React/CSS stack."""
    package = ROOT / "clients" / "web" / "package.json"
    dependencies = _read(package)

    for banned in ("@mui/", "@radix-ui/", "@chakra-ui/", "antd", "bootstrap"):
        assert banned not in dependencies
