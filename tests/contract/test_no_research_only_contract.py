"""Guard against reintroducing the old research-only payload flag."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "clients" / "web" / "src"


def test_new_frontend_modules_do_not_reintroduce_research_only_payload_flag() -> None:
    """The product should use decision-support / shadow-run language, not research-only payload flags."""

    allowed_legacy_files = {
        FRONTEND_SRC / "App.tsx",
    }
    offenders: list[str] = []
    for path in FRONTEND_SRC.rglob("*.ts*"):
        if path in allowed_legacy_files:
            continue
        text = path.read_text(encoding="utf-8-sig")
        if "research_only" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []
