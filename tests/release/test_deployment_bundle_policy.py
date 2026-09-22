"""Packaging contract for the customer Server deployment bundle.

The bundle ships to customers, so selection is driven by one explicit versioned
allowlist (`scripts/release/package_deployment_bundle.policy.json`) instead of
recursive directory copies: whatever happens to sit next to an approved file in
the repository must never be able to enter the archive. These tests build real
archives and inspect their members.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.release import package_deployment_bundle as packager

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts" / "release" / "package_deployment_bundle.policy.json"
INSTALLER = ROOT / "scripts" / "install" / "windows" / "Install-EurogasNexusServerRuntime.ps1"
ARCHIVE_NAME = "Eurogas-Nexus-Server-Windows.zip"
BUNDLE_ROOT = "Eurogas-Nexus-Server-Windows"

# Files an unapproved or secret-bearing repository could contain. None of them
# is in the allowlist, so none of them may reach the archive.
INJECTED_FILES = {
    ".env": "POSTGRES_PASSWORD=injected-secret\n",
    "deploy/runtime/.env": "EUROGAS_NEXUS_SECRET_KEY=injected-secret\n",
    ".automation/scripts/supervisor.py": "# automation harness\n",
    "docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md": "# internal state\n",
    "tests/release/test_leakage.py": "# internal test\n",
    "deploy/runtime/Dockerfile.api": "FROM python:3.11-slim\n",
    "logs/runtime.log": "injected-secret\n",
    "runtime.sqlite": "injected-secret\n",
    "scripts/ops/notes.py": "print('internal')\n",
}

UNSAFE_RELATIVE_PATHS = [
    "../escape.txt",
    "/etc/passwd",
    "docs\\evil.md",
    "docs//evil.md",
    "docs/../../evil.txt",
    "./evil.txt",
    "C:/windows/system32/evil.txt",
    "trailing/",
]


def policy_json() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def write_policy(tmp_path: Path, raw: dict) -> Path:
    path = tmp_path / "package_deployment_bundle.policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def expected_members(policy: packager.Policy | None = None) -> list[str]:
    resolved = policy or packager.load_policy()
    return sorted(f"{resolved.bundle_root}/{entry.destination}" for entry in resolved.entries)


def archive_members(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as bundle:
        return sorted(bundle.namelist())


def payload_fixture(tmp_path: Path) -> Path:
    """Reconstitute the allowlisted payload as a small repository-shaped tree."""

    repo = tmp_path / "repo"
    for entry in packager.load_policy().entries:
        source = ROOT / entry.source
        assert source.is_file(), entry.source
        target = repo / entry.source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return repo


def inject(repo: Path, relative: str, text: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def require_symlink_support(tmp_path: Path) -> None:
    target = tmp_path / "symlink-target.txt"
    target.write_text("target\n", encoding="utf-8")
    try:
        (tmp_path / "symlink-probe.txt").symlink_to(target)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("creating symlinks is not permitted on this platform")


def require_junction_support(tmp_path: Path, link: Path, target: Path) -> None:
    """Create an NTFS junction, which needs no administrator privilege."""

    if sys.platform != "win32":  # pragma: no cover - platform dependent
        pytest.skip("NTFS junctions are a Windows-only reparse point")
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:  # pragma: no cover - platform dependent
        pytest.skip(f"could not create an NTFS junction: {result.stderr.strip()}")


def test_real_repository_packages_exactly_the_allowlisted_members(tmp_path: Path) -> None:
    archive = packager.package(tmp_path / "out")

    assert archive.name == ARCHIVE_NAME
    members = archive_members(archive)
    assert members == expected_members()
    for required in (
        "START-HERE.txt",
        "deploy/runtime/compose.yaml",
        "deploy/runtime/Caddyfile",
        "deploy/runtime/README-EN.md",
        "deploy/runtime/README-CN.md",
        "scripts/install/windows/Deploy-EurogasNexus.ps1",
        "scripts/install/windows/Install-EurogasNexusServerRuntime.ps1",
        "docs/deployment/DEPLOYMENT_ROLES-EN.md",
        "docs/deployment/DEPLOYMENT_ROLES-CN.md",
        "docs/deployment/HANDOVER_INDEX.md",
    ):
        assert f"{BUNDLE_ROOT}/{required}" in members
    assert not any(member.endswith("Dockerfile.api") for member in members)
    assert not any(member.split("/")[-1].startswith(".env") for member in members)


def test_selection_is_stable_across_runs(tmp_path: Path) -> None:
    first = archive_members(packager.package(tmp_path / "first"))
    second = archive_members(packager.package(tmp_path / "second"))

    assert first == second
    assert len(first) == len(set(first))


def test_unapproved_and_secret_files_never_enter_the_archive(tmp_path: Path) -> None:
    repo = payload_fixture(tmp_path)
    for relative, text in INJECTED_FILES.items():
        inject(repo, relative, text)

    archive = packager.package(tmp_path / "out", repo_root=repo)

    members = archive_members(archive)
    assert members == expected_members()
    for relative in INJECTED_FILES:
        assert f"{BUNDLE_ROOT}/{relative}" not in members
    with zipfile.ZipFile(archive) as bundle:
        contents = b"\n".join(bundle.read(name) for name in bundle.namelist())
    assert b"injected-secret" not in contents


@pytest.mark.parametrize(
    "relative",
    [
        "deploy/runtime/compose.yaml",
        "deploy/runtime/Caddyfile",
        "scripts/install/windows/Deploy-EurogasNexus.ps1",
        "docs/deployment/HANDOVER_INDEX.md",
        "scripts/release/package_deployment_bundle.START-HERE.txt",
    ],
)
def test_missing_required_file_fails_closed(tmp_path: Path, relative: str) -> None:
    repo = payload_fixture(tmp_path)
    (repo / relative).unlink()
    output = tmp_path / "out"

    with pytest.raises(packager.PackagingError) as error:
        packager.package(output, repo_root=repo)

    assert relative in str(error.value)
    assert "missing" in str(error.value)
    assert not (output / ARCHIVE_NAME).exists()
    assert not list(output.glob("*.partial"))


@pytest.mark.parametrize("destination", UNSAFE_RELATIVE_PATHS)
def test_unsafe_bundle_destinations_are_rejected(tmp_path: Path, destination: str) -> None:
    raw = policy_json()
    raw["entries"][0]["destination"] = destination

    with pytest.raises(packager.PackagingError):
        packager.load_policy(write_policy(tmp_path, raw))


@pytest.mark.parametrize("source", UNSAFE_RELATIVE_PATHS)
def test_unsafe_bundle_sources_are_rejected(tmp_path: Path, source: str) -> None:
    raw = policy_json()
    raw["entries"][0]["source"] = source

    with pytest.raises(packager.PackagingError):
        packager.load_policy(write_policy(tmp_path, raw))


def test_duplicate_destinations_are_rejected(tmp_path: Path) -> None:
    raw = policy_json()
    raw["entries"].append(dict(raw["entries"][0]))

    with pytest.raises(packager.PackagingError, match="duplicate bundle destination"):
        packager.load_policy(write_policy(tmp_path, raw))


def test_duplicate_sources_are_rejected(tmp_path: Path) -> None:
    raw = policy_json()
    duplicate = dict(raw["entries"][0])
    duplicate["destination"] = "START-HERE-COPY.txt"
    raw["entries"].append(duplicate)

    with pytest.raises(packager.PackagingError, match="duplicate bundle source"):
        packager.load_policy(write_policy(tmp_path, raw))


def test_unknown_policy_and_entry_keys_are_rejected(tmp_path: Path) -> None:
    raw = policy_json()
    raw["entries"][0]["requierd"] = True
    with pytest.raises(packager.PackagingError, match="unknown keys"):
        packager.load_policy(write_policy(tmp_path, raw))

    raw = policy_json()
    raw["recursive_copy"] = True
    with pytest.raises(packager.PackagingError, match="unknown keys"):
        packager.load_policy(write_policy(tmp_path, raw))


def test_symlinked_repository_root_is_refused(tmp_path: Path) -> None:
    require_symlink_support(tmp_path)
    repo = payload_fixture(tmp_path)
    linked_root = tmp_path / "linked-repo"
    linked_root.symlink_to(repo, target_is_directory=True)

    with pytest.raises(packager.PackagingError, match="symlinked repository root"):
        packager.package(tmp_path / "out", repo_root=linked_root)


def test_symlinked_source_file_is_refused(tmp_path: Path) -> None:
    require_symlink_support(tmp_path)
    repo = payload_fixture(tmp_path)
    outside = tmp_path / "outside-handover.md"
    outside.write_text("# outside the repository\n", encoding="utf-8")
    victim = repo / "docs" / "deployment" / "HANDOVER_INDEX.md"
    victim.unlink()
    victim.symlink_to(outside)

    with pytest.raises(packager.PackagingError, match="refusing to follow a symlink"):
        packager.package(tmp_path / "out", repo_root=repo)


def test_symlinked_directory_escaping_the_repository_is_refused(tmp_path: Path) -> None:
    require_symlink_support(tmp_path)
    repo = payload_fixture(tmp_path)
    outside_runtime = tmp_path / "outside-runtime"
    outside_runtime.mkdir()
    for name in ("compose.yaml", "Caddyfile", "README-EN.md", "README-CN.md"):
        (outside_runtime / name).write_text("outside the repository\n", encoding="utf-8")
    runtime = repo / "deploy" / "runtime"
    shutil.rmtree(runtime)
    runtime.symlink_to(outside_runtime, target_is_directory=True)

    with pytest.raises(packager.PackagingError, match="refusing to follow a symlink"):
        packager.package(tmp_path / "out", repo_root=repo)


def test_windows_junction_escaping_the_repository_is_refused(tmp_path: Path) -> None:
    repo = payload_fixture(tmp_path)
    outside_runtime = tmp_path / "outside-runtime"
    outside_runtime.mkdir()
    for name in ("compose.yaml", "Caddyfile", "README-EN.md", "README-CN.md"):
        (outside_runtime / name).write_text("outside the repository\n", encoding="utf-8")
    runtime = repo / "deploy" / "runtime"
    shutil.rmtree(runtime)
    require_junction_support(tmp_path, runtime, outside_runtime)
    try:
        with pytest.raises(packager.PackagingError, match="refusing to follow a symlink"):
            packager.package(tmp_path / "out", repo_root=repo)
    finally:
        # Drop the junction itself; the target directory is left untouched.
        os.rmdir(runtime)


def test_windows_junction_repository_root_is_refused(tmp_path: Path) -> None:
    repo = payload_fixture(tmp_path)
    linked_root = tmp_path / "junctioned-repo"
    require_junction_support(tmp_path, linked_root, repo)

    with pytest.raises(packager.PackagingError, match="symlinked repository root"):
        packager.package(tmp_path / "out", repo_root=linked_root)


def test_policy_retains_every_installer_required_runtime_file() -> None:
    policy = packager.load_policy()
    entries = {entry.destination: entry for entry in policy.entries}
    installer = INSTALLER.read_text(encoding="utf-8-sig")

    # The runtime primitive resolves these two paths three levels above its own
    # directory inside the extracted bundle, so the destinations are load-bearing.
    assert '"deploy\\runtime\\compose.yaml"' in installer
    assert '"deploy\\runtime\\Caddyfile"' in installer
    for destination in (
        "deploy/runtime/compose.yaml",
        "deploy/runtime/Caddyfile",
        "scripts/install/windows/Deploy-EurogasNexus.ps1",
        "scripts/install/windows/Install-EurogasNexusServerRuntime.ps1",
        "docs/deployment/DEPLOYMENT_ROLES-EN.md",
        "docs/deployment/DEPLOYMENT_ROLES-CN.md",
        "docs/deployment/HANDOVER_INDEX.md",
        "START-HERE.txt",
    ):
        assert destination in entries, destination
        assert entries[destination].required is True


def test_policy_never_denies_its_own_payload_and_keeps_the_archive_contract() -> None:
    policy = packager.load_policy()

    assert policy.schema_version == packager.SUPPORTED_POLICY_SCHEMA
    assert policy.archive_name == ARCHIVE_NAME
    assert policy.bundle_root == BUNDLE_ROOT
    for entry in policy.entries:
        assert packager.forbidden_match(entry.destination, policy) is None, entry.destination
        assert packager.forbidden_match(entry.source, policy) is None, entry.source
        assert "Dockerfile" not in entry.source


def test_forbidden_globs_still_catch_injected_names() -> None:
    policy = packager.load_policy()

    for member in (
        ".env",
        "deploy/runtime/.env",
        ".automation/scripts/supervisor.py",
        "docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md",
        "tests/release/test_leakage.py",
        "deploy/runtime/Dockerfile.api",
        "logs/runtime.log",
        "certs/nexus.key",
    ):
        assert packager.forbidden_match(member, policy) is not None, member
    for member in (
        "deploy/runtime/compose.yaml",
        "docs/deployment/DEPLOYMENT_ROLES-EN.md",
        "scripts/install/windows/Deploy-EurogasNexus.ps1",
        "START-HERE.txt",
    ):
        assert packager.forbidden_match(member, policy) is None, member


def test_start_here_preserves_the_documented_preflight(tmp_path: Path) -> None:
    archive = packager.package(tmp_path / "out")
    with zipfile.ZipFile(archive) as bundle:
        text = bundle.read(f"{BUNDLE_ROOT}/START-HERE.txt").decode("utf-8")

    for phrase in (
        "EUROGAS NEXUS SERVER FOR WINDOWS",
        "This package installs the backend runtime only",
        "PowerShell 5.1+",
        "Docker Compose v2",
        "powershell -ExecutionPolicy Bypass -File "
        ".\\scripts\\install\\windows\\Deploy-EurogasNexus.ps1",
        "-Action Preflight",
        "-Role Server",
        "-PrivateNetworkOnly",
        "Then replace Preflight with Install",
        "docs\\deployment\\DEPLOYMENT_ROLES-EN.md",
        "not a desktop Client",
    ):
        assert phrase in text, phrase
    assert not text.startswith("\ufeff")


def test_wrappers_delegate_selection_to_the_python_packager() -> None:
    shell = (ROOT / "scripts" / "release" / "package_deployment_bundle.sh").read_text(
        encoding="utf-8"
    )
    powershell = (ROOT / "scripts" / "release" / "package_deployment_bundle.ps1").read_text(
        encoding="utf-8"
    )

    for text in (shell, powershell):
        assert "package_deployment_bundle.py" in text
        for drift in (
            "cp -R",
            "Copy-Item",
            "Compress-Archive",
            "copytree",
            "docs/deployment",
            "deploy/runtime",
            "START-HERE",
            ARCHIVE_NAME,
        ):
            assert drift not in text, drift
