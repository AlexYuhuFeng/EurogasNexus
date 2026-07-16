"""Repository-wide product terminology contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TERMINOLOGY_DOC = ROOT / "docs" / "architecture" / "TERMINOLOGY.md"
CLEANUP_SCRIPT = ROOT / "scripts" / "ops" / "apply_terminology_cleanup.py"
ROUTE_COST = ROOT / "src" / "eurogas_nexus" / "api" / "routes" / "public" / "route_cost.py"
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"
LEGACY_FIELD = "research" + "_only"
COMPATIBILITY_LINE = f'            "{LEGACY_FIELD}": True,'
BUSINESS_DATA_LINE = f'                "{LEGACY_FIELD}": True,'


def test_canonical_product_positioning_is_documented() -> None:
    text = TERMINOLOGY_DOC.read_text(encoding="utf-8-sig")
    assert (
        "Eurogas Nexus is a European natural gas market intelligence, optimization, "
        "and decision-support platform."
    ) in text
    assert "human_review_required" in text
    assert "temporarily retains `meta.research_only`" in text


def test_cleanup_verifier_covers_backend_and_frontend_payload_surfaces() -> None:
    text = CLEANUP_SCRIPT.read_text(encoding="utf-8-sig")
    assert "src/eurogas_nexus/api/routes/public/route_cost.py" in text
    assert "clients/web/src/App.tsx" in text
    assert 'LEGACY_FIELD = "research" + "_only"' in text
    assert "Terminology compatibility boundary verified." in text


def test_frontend_no_longer_contains_legacy_payload_field() -> None:
    assert LEGACY_FIELD not in APP_TSX.read_text(encoding="utf-8-sig")


def test_backend_keeps_only_the_shared_envelope_compatibility_field() -> None:
    text = ROUTE_COST.read_text(encoding="utf-8-sig")
    assert text.count(COMPATIBILITY_LINE) == 1
    assert BUSINESS_DATA_LINE not in text


def test_new_app_modules_do_not_use_legacy_payload_field() -> None:
    app_modules = ROOT / "clients" / "web" / "src" / "app"
    offenders = []
    for path in app_modules.rglob("*.ts*"):
        if LEGACY_FIELD in path.read_text(encoding="utf-8-sig"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
