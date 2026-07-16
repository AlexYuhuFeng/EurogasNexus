"""Repository-wide product terminology contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMINOLOGY_DOC = ROOT / "docs" / "architecture" / "TERMINOLOGY.md"
CLEANUP_SCRIPT = ROOT / "scripts" / "ops" / "apply_terminology_cleanup.py"
ROUTE_COST = ROOT / "src" / "eurogas_nexus" / "api" / "routes" / "public" / "route_cost.py"
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"


def test_canonical_product_positioning_is_documented() -> None:
    text = TERMINOLOGY_DOC.read_text(encoding="utf-8-sig")
    assert (
        "Eurogas Nexus is a European natural gas market intelligence, optimization, "
        "and decision-support platform."
    ) in text
    assert "Do not add a `research_only` field" in text
    assert "human_review_required" in text


def test_cleanup_script_targets_only_remaining_backend_field() -> None:
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8-sig")
    assert "src/eurogas_nexus/api/routes/public/route_cost.py" in text
    assert "clients/web/src/App.tsx" not in text
    assert '"research_only": True' in text
    assert "research_only: true" not in text
    assert "Expected exactly one legacy block" in text


def test_frontend_no_longer_contains_research_only_payload_field() -> None:
    assert "research_only" not in APP_TSX.read_text(encoding="utf-8-sig")


def test_backend_route_response_no_longer_contains_research_only_field() -> None:
    assert '"research_only": True' not in ROUTE_COST.read_text(encoding="utf-8-sig")


def test_new_app_modules_do_not_use_research_only_payload_field() -> None:
    app_modules = ROOT / "clients" / "web" / "src" / "app"
    offenders = []
    for path in app_modules.rglob("*.ts*"):
        if "research_only" in path.read_text(encoding="utf-8-sig"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
