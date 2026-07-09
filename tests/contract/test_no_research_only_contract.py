"""Guard against reintroducing the old research-only payload flag."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAYLOAD_SURFACES = [
    ROOT / "clients" / "web" / "src" / "App.tsx",
    ROOT / "clients" / "web" / "src" / "app",
]


def test_new_frontend_modules_do_not_reintroduce_research_only_payload_flag() -> None:
    """Frontend code should not send or construct the legacy research-only payload flag."""

    offenders: list[str] = []
    paths: list[Path] = []
    for surface in PAYLOAD_SURFACES:
        if surface.is_dir():
            paths.extend(surface.rglob("*.ts*"))
        else:
            paths.append(surface)
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        if "research_only:" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
