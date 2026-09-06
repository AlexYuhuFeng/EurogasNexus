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
        "Eurogas-Nexus-Client-{release_version}-linux-x64.deb",
        "Eurogas-Nexus-Client-{release_version}-linux-arm64.deb",
        "Linux DEB package for x64 Linux users",
        "Linux DEB package for ARM64 Linux users",
        "ARM Linux users must not receive the x64 DEB by mistake",
    ]:
        assert phrase in text
