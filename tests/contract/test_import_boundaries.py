"""Import boundary contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "eurogas_nexus"


def test_domain_modules_do_not_import_fastapi() -> None:
    domain_root = SRC / "domain"
    offenders: list[str] = []

    for path in domain_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "fastapi" in text.lower():
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_sdk_and_cli_do_not_import_internal_domain_modules() -> None:
    boundary_roots = [SRC / "sdk", SRC / "cli"]
    offenders: list[str] = []

    for root in boundary_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "eurogas_nexus.domain" in text:
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
