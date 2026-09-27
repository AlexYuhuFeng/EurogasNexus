"""Packaging contract for the customer Server deployment bundle.

The bundle ships to customers, so selection is driven by one explicit versioned
allowlist (`scripts/release/package_deployment_bundle.policy.json`) instead of
recursive directory copies: whatever happens to sit next to an approved file in
the repository must never be able to enter the archive. These tests build real
archives and inspect their members.

PILOT-A: the archive also carries `release-identity.json`, generated from the
resolved release context plus an explicit API image digest. Every identity value
in this file is a test-only fixture, never a real release identity.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.release import package_deployment_bundle as packager
from scripts.release.release_metadata import resolve_release_context

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts" / "release" / "package_deployment_bundle.policy.json"
INSTALLER = ROOT / "scripts" / "install" / "windows" / "Install-EurogasNexusServerRuntime.ps1"
DEPLOY = ROOT / "scripts" / "install" / "windows" / "Deploy-EurogasNexus.ps1"
ARCHIVE_NAME = "Eurogas-Nexus-Server-Windows.zip"
BUNDLE_ROOT = "Eurogas-Nexus-Server-Windows"
IDENTITY_NAME = "release-identity.json"

# Test-only identity fixtures: never a real commit, digest or release.
TEST_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
TEST_IMAGE_DIGEST = "sha256:" + "9f" * 32
FIXTURE = object()

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


def expected_members_with_identity(policy: packager.Policy | None = None) -> list[str]:
    resolved = policy or packager.load_policy()
    return sorted(
        [
            *expected_members(resolved),
            f"{resolved.bundle_root}/{resolved.identity_destination}",
        ]
    )


def archive_members(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as bundle:
        return sorted(bundle.namelist())


def release_context_fixture() -> dict:
    """A resolved, test-only release context; never a real release."""

    return resolve_release_context(
        channel="preview",
        git_sha=TEST_COMMIT_SHA,
        build_run_number=7,
    )


def package_fixture(
    archive_dir: Path,
    *,
    context: object = FIXTURE,
    image_digest: object = TEST_IMAGE_DIGEST,
    repo_root: Path | None = None,
) -> Path:
    """Build an archive carrying the test-only identity fixture."""

    resolved_context = release_context_fixture() if context is FIXTURE else context
    return packager.package(
        archive_dir,
        repo_root=repo_root or ROOT,
        release_context=resolved_context,
        image_digest=image_digest,
    )


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
    archive = package_fixture(tmp_path / "out")

    assert archive.name == ARCHIVE_NAME
    members = archive_members(archive)
    assert members == expected_members_with_identity()
    for required in (
        "START-HERE.txt",
        IDENTITY_NAME,
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
    first = archive_members(package_fixture(tmp_path / "first"))
    second = archive_members(package_fixture(tmp_path / "second"))

    assert first == second
    assert len(first) == len(set(first))
    # Entries plus exactly one generated identity record.
    assert len(first) == len(packager.load_policy().entries) + 1


def test_unapproved_and_secret_files_never_enter_the_archive(tmp_path: Path) -> None:
    repo = payload_fixture(tmp_path)
    for relative, text in INJECTED_FILES.items():
        inject(repo, relative, text)

    archive = package_fixture(tmp_path / "out", repo_root=repo)

    members = archive_members(archive)
    assert members == expected_members_with_identity()
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
        package_fixture(output, repo_root=repo)

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
        package_fixture(tmp_path / "out", repo_root=linked_root)


def test_symlinked_source_file_is_refused(tmp_path: Path) -> None:
    require_symlink_support(tmp_path)
    repo = payload_fixture(tmp_path)
    outside = tmp_path / "outside-handover.md"
    outside.write_text("# outside the repository\n", encoding="utf-8")
    victim = repo / "docs" / "deployment" / "HANDOVER_INDEX.md"
    victim.unlink()
    victim.symlink_to(outside)

    with pytest.raises(packager.PackagingError, match="refusing to follow a symlink"):
        package_fixture(tmp_path / "out", repo_root=repo)


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
        package_fixture(tmp_path / "out", repo_root=repo)


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
            package_fixture(tmp_path / "out", repo_root=repo)
    finally:
        # Drop the junction itself; the target directory is left untouched.
        os.rmdir(runtime)


def test_windows_junction_repository_root_is_refused(tmp_path: Path) -> None:
    repo = payload_fixture(tmp_path)
    linked_root = tmp_path / "junctioned-repo"
    require_junction_support(tmp_path, linked_root, repo)

    with pytest.raises(packager.PackagingError, match="symlinked repository root"):
        package_fixture(tmp_path / "out", repo_root=linked_root)


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
    archive = package_fixture(tmp_path / "out")
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
        IDENTITY_NAME,
        "SHA256SUMS",
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
    # Both wrappers forward the verified release context and image digest.
    assert '"$@"' in shell
    assert "--release-context" in powershell
    assert "--image-digest" in powershell


# ---------------------------------------------------------------------------
# Release identity (PILOT-A)
# ---------------------------------------------------------------------------


def test_archive_carries_one_release_identity_without_a_self_checksum(tmp_path: Path) -> None:
    archive = package_fixture(tmp_path / "out")
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        identity = json.loads(bundle.read(f"{BUNDLE_ROOT}/{IDENTITY_NAME}").decode("utf-8"))

    assert f"{BUNDLE_ROOT}/{IDENTITY_NAME}" in names
    # Exact key set: no extra field may smuggle a floating tag, a default SHA
    # or a hash of the archive itself into the bundle identity.
    assert set(identity) == {
        "schema_version",
        "product_name",
        "app_version",
        "release_version",
        "channel",
        "commit_sha",
        "api_image_repository",
        "api_image_digest",
        "api_image_reference",
    }
    context = release_context_fixture()
    assert identity["schema_version"] == 1
    assert identity["product_name"] == "Eurogas Nexus"
    assert identity["app_version"] == context["app_version"]
    assert identity["release_version"] == context["release_version"]
    assert identity["channel"] == context["channel"]
    assert identity["commit_sha"] == TEST_COMMIT_SHA
    assert identity["api_image_repository"] == context["api_image"]
    assert identity["api_image_digest"] == TEST_IMAGE_DIGEST
    assert identity["api_image_reference"] == f"{context['api_image']}@{TEST_IMAGE_DIGEST}"

    # The ZIP checksum stays external (SHA256SUMS, release-manifest.json):
    # nothing inside the archive may be named or carry a checksum of the ZIP.
    assert not any(re.search(r"(?i)sha256|checksum", name) for name in names)
    assert identity == packager.build_release_identity(context, TEST_IMAGE_DIGEST)


def identity_context(**overrides: object) -> dict:
    context = release_context_fixture()
    context.update(overrides)
    return context


def identity_context_without(key: str) -> dict:
    context = release_context_fixture()
    del context[key]
    return context


IDENTITY_FAILURES: list[tuple[str, object, object, str]] = [
    ("non-object-context", ["not", "an", "object"], TEST_IMAGE_DIGEST, "release context"),
    ("null-context", None, TEST_IMAGE_DIGEST, "release context"),
    ("missing-git-sha", identity_context_without("git_sha"), TEST_IMAGE_DIGEST, "git_sha"),
    ("short-sha", identity_context(git_sha="0123456789ab"), TEST_IMAGE_DIGEST, "commit SHA"),
    (
        "uppercase-sha",
        identity_context(git_sha=TEST_COMMIT_SHA.upper()),
        TEST_IMAGE_DIGEST,
        "commit SHA",
    ),
    ("unknown-channel", identity_context(channel="beta"), TEST_IMAGE_DIGEST, "channel"),
    (
        "channel-version-mismatch",
        identity_context(channel="rc"),
        TEST_IMAGE_DIGEST,
        "release_version",
    ),
    (
        "version-core-mismatch",
        identity_context(release_version="v0.6.0-preview.7.0123456789ab"),
        TEST_IMAGE_DIGEST,
        "v0.5.0",
    ),
    # A prefix match would accept a longer core: channel suffixes must follow
    # the exact base version, not merely start with it.
    (
        "lengthened-core-stable",
        identity_context(channel="stable", release_version="v0.5.01"),
        TEST_IMAGE_DIGEST,
        "v0.5.0",
    ),
    (
        "lengthened-core-rc",
        identity_context(channel="rc", release_version="v0.5.01-rc.1"),
        TEST_IMAGE_DIGEST,
        "v0.5.0",
    ),
    (
        "lengthened-core-preview",
        identity_context(release_version="v0.5.01-preview.7.0123456789ab"),
        TEST_IMAGE_DIGEST,
        "v0.5.0",
    ),
    (
        "preview-suffix-mismatch",
        identity_context(release_version="v0.5.0-preview.7.ffffffffffff"),
        TEST_IMAGE_DIGEST,
        "preview suffix",
    ),
    ("missing-api-image", identity_context_without("api_image"), TEST_IMAGE_DIGEST, "api_image"),
    (
        "already-pinned-api-image",
        identity_context(api_image=f"ghcr.io/example/api@{TEST_IMAGE_DIGEST}"),
        TEST_IMAGE_DIGEST,
        "api_image",
    ),
    (
        "tagged-api-image-repository",
        identity_context(api_image="ghcr.io/example/api:0.5.0"),
        TEST_IMAGE_DIGEST,
        "api_image",
    ),
    (
        "floating-tag-api-image-repository",
        identity_context(api_image="ghcr.io/example/api:latest"),
        TEST_IMAGE_DIGEST,
        "api_image",
    ),
    (
        "registry-port-api-image-with-tag",
        identity_context(api_image="registry.example.com:5000/example/api:0.5.0"),
        TEST_IMAGE_DIGEST,
        "api_image",
    ),
    (
        "trailing-slash-api-image-repository",
        identity_context(api_image="ghcr.io/example/api/"),
        TEST_IMAGE_DIGEST,
        "api_image",
    ),
    (
        "single-component-api-image-repository",
        identity_context(api_image="eurogas-nexus-api"),
        TEST_IMAGE_DIGEST,
        "api_image",
    ),
    ("missing-digest", identity_context(), None, "image digest"),
    ("empty-digest", identity_context(), "", "image digest"),
    ("short-digest", identity_context(), "sha256:" + "9f" * 31, "image digest"),
    ("unprefixed-digest", identity_context(), "9f" * 32, "image digest"),
    ("uppercase-digest", identity_context(), "sha256:" + "9F" * 32, "image digest"),
]


@pytest.mark.parametrize(
    ("case", "context", "image_digest", "fragment"),
    IDENTITY_FAILURES,
    ids=[case for case, _, _, _ in IDENTITY_FAILURES],
)
def test_identity_inputs_fail_closed(
    tmp_path: Path, case: str, context: object, image_digest: object, fragment: str
) -> None:
    output = tmp_path / "out"

    with pytest.raises(packager.PackagingError) as error:
        package_fixture(output, context=context, image_digest=image_digest)

    assert fragment in str(error.value)
    assert not (output / ARCHIVE_NAME).exists()
    assert not list(output.glob("*.partial"))


def test_exact_base_versions_and_registry_ports_are_accepted() -> None:
    """The tightened checks must not reject valid releases or registry ports."""

    ported = packager.build_release_identity(
        identity_context(api_image="registry.example.com:5000/example/api"),
        TEST_IMAGE_DIGEST,
    )
    assert ported["api_image_repository"] == "registry.example.com:5000/example/api"
    assert ported["api_image_reference"] == (
        f"registry.example.com:5000/example/api@{TEST_IMAGE_DIGEST}"
    )
    for channel, release_version in (
        ("stable", "v0.5.0"),
        ("rc", "v0.5.0-rc.2"),
        ("preview", "v0.5.0-preview.7.0123456789ab"),
    ):
        identity = packager.build_release_identity(
            identity_context(channel=channel, release_version=release_version),
            TEST_IMAGE_DIGEST,
        )
        assert identity["channel"] == channel
        assert identity["release_version"] == release_version


@pytest.mark.parametrize("destination", [*UNSAFE_RELATIVE_PATHS, "nested/identity.json"])
def test_unsafe_identity_destinations_are_rejected(tmp_path: Path, destination: str) -> None:
    raw = policy_json()
    raw["identity"]["destination"] = destination

    with pytest.raises(packager.PackagingError):
        packager.load_policy(write_policy(tmp_path, raw))


def test_identity_destination_is_validated_and_never_collides(tmp_path: Path) -> None:
    raw = policy_json()
    raw["identity"]["destination"] = raw["entries"][0]["destination"]
    with pytest.raises(packager.PackagingError, match="duplicate"):
        packager.load_policy(write_policy(tmp_path, raw))

    raw = policy_json()
    raw["identity"] = {"destination": IDENTITY_NAME, "purpose": "hidden extra key"}
    with pytest.raises(packager.PackagingError, match="unknown keys"):
        packager.load_policy(write_policy(tmp_path, raw))

    raw = policy_json()
    del raw["identity"]
    with pytest.raises(packager.PackagingError, match="identity"):
        packager.load_policy(write_policy(tmp_path, raw))


def test_policy_identity_name_matches_the_shipped_entrypoints() -> None:
    policy = packager.load_policy()

    assert policy.identity_destination == IDENTITY_NAME
    assert policy.bundle_root == BUNDLE_ROOT
    for path in (DEPLOY, INSTALLER):
        assert f'"{IDENTITY_NAME}"' in path.read_text(encoding="utf-8-sig"), path.name


def test_shipped_entrypoints_are_tab_free_and_resolve_inside_the_bundle(tmp_path: Path) -> None:
    archive = package_fixture(tmp_path / "out")
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    root = extracted / BUNDLE_ROOT

    for path in (DEPLOY, INSTALLER):
        text = path.read_text(encoding="utf-8-sig")
        # The literal TAB defect (CA-10) must never come back.
        assert "\t" not in text, path.name
        # The bundle root is three levels above the shipped script directory.
        assert "..\\..\\.." in text, path.name

    entry_directory = root / "scripts" / "install" / "windows"
    assert (entry_directory / "Deploy-EurogasNexus.ps1").is_file()
    assert (entry_directory / "Install-EurogasNexusServerRuntime.ps1").is_file()
    # Every shipped path the entry points resolve exists inside the extraction.
    bundle_root_via_scripts = entry_directory.parent.parent.parent
    assert bundle_root_via_scripts == root
    assert (bundle_root_via_scripts / IDENTITY_NAME).is_file()
    assert (root / "deploy" / "runtime" / "compose.yaml").is_file()
    assert (root / "deploy" / "runtime" / "Caddyfile").is_file()
    assert (root / "START-HERE.txt").is_file()
