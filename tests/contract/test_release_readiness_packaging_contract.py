"""Contract tests for release packaging documentation."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_READINESS = ROOT / "docs" / "release" / "RELEASE_READINESS.md"


def test_release_readiness_documents_linux_architecture_specific_packages() -> None:
    """Release readiness docs should distinguish Linux x64 and Linux ARM64 assets."""

    text = RELEASE_READINESS.read_text(encoding="utf-8-sig")
    for phrase in [
        "Linux desktop release packaging is architecture-specific",
        "release-desktop-linux-x64",
        "release-desktop-linux-arm64",
        "Linux DEB package for x64 Linux users",
        "Linux DEB package for ARM64 Linux users",
        "ARM Linux users do not receive the x64 DEB by mistake",
    ]:
        assert phrase in text
