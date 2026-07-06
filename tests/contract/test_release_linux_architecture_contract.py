"""Contract tests for release desktop architecture coverage."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def test_release_builds_linux_deb_for_x64_and_arm64() -> None:
    """Desktop release workflow should publish separate Linux DEB artifacts by architecture."""

    workflow_text = RELEASE_WORKFLOW.read_text(encoding="utf-8-sig")
    for phrase in [
        "Also build Windows and Linux x64/ARM64 desktop packages.",
        "artifact_label: linux-x64",
        "artifact_label: linux-arm64",
        "os: ubuntu-latest",
        "os: ubuntu-24.04-arm",
        "Linux x64 DEB package",
        "Linux ARM64 DEB package",
    ]:
        assert phrase in workflow_text


def test_release_does_not_use_ambiguous_linux_desktop_artifact_label() -> None:
    """The release matrix should not publish a single ambiguous Linux artifact label."""

    workflow_text = RELEASE_WORKFLOW.read_text(encoding="utf-8-sig")
    assert "artifact_label: linux\n" not in workflow_text
