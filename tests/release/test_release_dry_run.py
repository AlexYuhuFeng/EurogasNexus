"""The dry run may never fabricate a published image identity.

`run_release_dry_run.py --build-container` builds a local image and can only
observe that build's local config id (`docker image inspect .Id`). That value
identifies local build state; it is not the digest of a published repository
manifest and must never become operator-bundle identity or release-manifest
image digests. These tests fake only the docker CLI so the rest of the dry run
runs for real, and inspect the resulting archive and manifest.
"""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts.release import run_release_dry_run as dry_run

ROOT = Path(__file__).resolve().parents[2]

# Test-only identity fixtures: never a real commit, digest or release.
LOCAL_BUILD_ID = "sha256:" + "ab" * 32
PUBLISHED_DIGEST = "sha256:" + "9f" * 32


def fake_cli(monkeypatch: pytest.MonkeyPatch, manifest_output: Path) -> list[list[str]]:
    """Stub docker build/inspect and record every command the dry run issues.

    The dry run's manifest step defaults `--output` to a repo-relative path;
    the harness appends an explicit sandbox path so tests never write release
    artifacts into the working tree. The identity input itself
    (`--image-digest`) is passed through exactly as the dry run produced it.
    """

    real_run = dry_run._run
    commands: list[list[str]] = []

    def wrapper(command, cwd=None, check=True):
        recorded = [str(part) for part in command]
        commands.append(recorded)
        if recorded[0] == "docker":
            if recorded[1:2] == ["build"]:
                return subprocess.CompletedProcess(command, 0, "", "")
            if recorded[1:3] == ["image", "inspect"]:
                return subprocess.CompletedProcess(command, 0, f"{LOCAL_BUILD_ID}\n", "")
            raise AssertionError(f"unexpected docker command: {command}")
        if any(part.endswith("build_release_manifest.py") for part in recorded):
            command = [*command, "--output", str(manifest_output)]
        return real_run(command, cwd=cwd, check=check)

    monkeypatch.setattr(dry_run, "_run", wrapper)
    return commands


def run_dry_run(tmp_path: Path, *extra_arguments: str) -> tuple[int, Path, dict]:
    output = tmp_path / "release-assets"
    exit_code = dry_run.main(
        ["--channel", "preview", "--output-dir", str(output), *extra_arguments]
    )
    report = json.loads((output / "release-dry-run-report.json").read_text(encoding="utf-8"))
    return exit_code, output, report


def report_step(report: dict, name: str) -> dict:
    return next(item for item in report["steps"] if item["name"] == name)


def command_running(commands: list[list[str]], marker: str) -> list[str]:
    matches = [command for command in commands if any(marker in part for part in command)]
    assert len(matches) == 1, matches
    return matches[0]


def flag_value(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def test_published_image_digest_requires_an_explicit_manifest_digest() -> None:
    assert dry_run.published_image_digest("") == ""
    assert dry_run.published_image_digest(f"  {PUBLISHED_DIGEST} ") == PUBLISHED_DIGEST
    for value in (
        "eurogas-nexus-api:dry-run",  # a floating tag is not a digest
        "sha256:" + "9F" * 32,  # uppercase hex
        "sha256:" + "9f" * 31,  # short digest
        LOCAL_BUILD_ID.upper(),
    ):
        with pytest.raises(ValueError):
            dry_run.published_image_digest(value)


def test_dry_run_source_never_assigns_the_local_build_id_to_image_digest() -> None:
    """Contract on the source: the inspect id feeds one diagnostic only."""

    text = (ROOT / "scripts" / "release" / "run_release_dry_run.py").read_text(encoding="utf-8")

    assert "local_build_id = inspect.stdout.strip()" in text
    assert "image_digest = published_image_digest(args.image_digest)" in text
    assert "image_digest = inspect.stdout" not in text
    assert "image_digest = inspect" not in text


def test_dry_run_never_packages_a_bundle_from_a_local_build_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "release-assets"
    commands = fake_cli(monkeypatch, output / "release-manifest.json")

    exit_code, output, report = run_dry_run(tmp_path, "--build-container")

    # The local build happened and its config id is recorded as a diagnostic.
    docker_commands = [command for command in commands if command[0] == "docker"]
    assert docker_commands[0][1] == "build"
    assert docker_commands[1][1:3] == ["image", "inspect"]
    build_container = report_step(report, "build-container")
    assert build_container["ok"] is True
    assert LOCAL_BUILD_ID in build_container["detail"]
    assert "diagnostic" in build_container["detail"]

    # No operator bundle may be produced from that diagnostic value ...
    assert not any(
        "package_deployment_bundle.py" in part for command in commands for part in command
    )
    assert not list(output.glob("Eurogas-Nexus-Server-*.zip"))
    assert not list(output.glob("*.partial"))
    package_deployment = report_step(report, "package-deployment")
    assert package_deployment["ok"] is False
    assert "--image-digest" in package_deployment["detail"]

    # ... and the local config id never reaches an identity input or artifact.
    manifest_command = command_running(commands, "build_release_manifest.py")
    assert flag_value(manifest_command, "--image-digest") == ""
    for command in commands:
        if command[0] != "docker":
            assert LOCAL_BUILD_ID not in " ".join(command)
    manifest = json.loads((output / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_images"][0]["digest"] == ""
    assert exit_code != 0


def test_dry_run_bundle_uses_the_explicit_published_digest_not_the_local_build_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "release-assets"
    commands = fake_cli(monkeypatch, output / "release-manifest.json")

    _, output, report = run_dry_run(
        tmp_path, "--build-container", "--image-digest", PUBLISHED_DIGEST
    )

    assert report_step(report, "build-container")["ok"] is True
    assert report_step(report, "package-deployment")["ok"] is True
    archives = list(output.glob("Eurogas-Nexus-Server-*-Windows.zip"))
    assert len(archives) == 1, sorted(path.name for path in output.glob("*.zip"))
    with zipfile.ZipFile(archives[0]) as bundle:
        identity = json.loads(
            bundle.read("Eurogas-Nexus-Server-Windows/release-identity.json").decode("utf-8")
        )
    assert identity["api_image_digest"] == PUBLISHED_DIGEST
    assert identity["api_image_reference"].endswith(f"@{PUBLISHED_DIGEST}")
    assert LOCAL_BUILD_ID not in json.dumps(identity)
    manifest_command = command_running(commands, "build_release_manifest.py")
    assert flag_value(manifest_command, "--image-digest") == PUBLISHED_DIGEST
    manifest = json.loads((output / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_images"][0]["digest"] == PUBLISHED_DIGEST
