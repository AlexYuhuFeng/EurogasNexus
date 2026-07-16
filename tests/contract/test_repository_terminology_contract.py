"""Repository-wide product terminology contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMINOLOGY_DOC = ROOT / "docs" / "architecture" / "TERMINOLOGY.md"
CLEANUP_SCRIPT = ROOT / "scripts" / "ops" / "apply_terminology_cleanup.py"


def test_canonical_product_positioning_is_documented() -> None:
    text = TERMINOLOGY_DOC.read_text(encoding="utf-8-sig")
    assert (
        "Eurogas Nexus is a European natural gas market intelligence, optimization, "
        "and decision-support platform."
    ) in text
    assert "Do not add a `research_only` field" in text
    assert "human_review_required" in text


def test_cleanup_script_targets_known_legacy_payload_fields() -> None:
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8-sig")
    assert "src/eurogas_nexus/api/routes/public/route_cost.py" in text
    assert "clients/web/src/App.tsx" in text
    assert '"research_only": True' in text
    assert "research_only: true" in text
    assert "Expected exactly one legacy block" in text
    assert "research_only remains in" in text


def test_new_app_modules_do_not_use_research_only_payload_field() -> None:
    app_modules = ROOT / "clients" / "web" / "src" / "app"
    offenders = []
    for path in app_modules.rglob("*.ts*"):
        if "research_only" in path.read_text(encoding="utf-8-sig"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
