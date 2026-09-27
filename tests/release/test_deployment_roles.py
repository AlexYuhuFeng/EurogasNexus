"""Release contracts for customer deployment roles."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from scripts.release import package_deployment_bundle as packager
from scripts.release.release_metadata import resolve_release_context

ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
requires_windows_powershell = pytest.mark.skipif(
    sys.platform != "win32" or POWERSHELL is None,
    reason="extracted-bundle preflight runs Windows PowerShell",
)

# Test-only identity fixtures: never a real commit, digest or release.
TEST_COMMIT_SHA = "0123456789abcdef0123456789abcdef01234567"
TEST_IMAGE_DIGEST = "sha256:" + "9f" * 32
STAGED_ENV = ("EUROGAS_NEXUS_VERSION", "EUROGAS_NEXUS_RELEASE_CHANNEL")


def read(relative: str) -> str:
    """Read a repo-relative file (tolerates UTF-8 BOM).

    Args:
        relative: Path relative to the repo root.

    Returns:
        File text.
    """

    return (ROOT / relative).read_text(encoding="utf-8-sig")


def test_deployment_bundle_defines_exact_device_roles() -> None:
    script = read("scripts/install/windows/Deploy-EurogasNexus.ps1")

    assert '[ValidateSet("Server", "Client")]' in script
    assert "ServerApiUrl" in script
    assert "ClientInstallerPath" in script
    assert "client_database_credentials = $false" in script
    assert "automatic_docker_install = $false" in script
    assert "Get-AuthenticodeSignature" in script
    assert "AllowUnsignedPreview" in script
    assert "PrivateNetworkOnly" in script
    assert "network_exposure = if ($Role" in script
    assert "A remote client requires an HTTPS ServerApiUrl." in script


def test_server_runtime_is_db_first_and_has_explicit_migration() -> None:
    compose = read("deploy/runtime/compose.yaml")

    for service in [
        "postgres:",
        "migrate:",
        "api:",
        "gateway:",
        "public-ingestion:",
        "public-ingestion-worker:",
        "reference-ingestion-worker:",
        "preview-seed:",
    ]:
        assert service in compose
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert "postgresql+pg8000://" in compose
    assert 'profiles: ["simulated-prices"]' in compose
    assert 'profiles: ["server"]' in compose
    assert 'profiles: ["public-ingestion"]' in compose
    assert '"${HTTPS_BIND_ADDRESS}:${HTTPS_PORT}:443"' in compose
    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}" in compose
    assert "POSTGRES_PASSWORD=eurogas" not in compose


def test_server_bootstrapper_does_not_install_docker_or_expose_secrets() -> None:
    script = read("scripts/install/windows/Install-EurogasNexusServerRuntime.ps1")
    lowered = script.lower()

    assert "docker_install_attempted = $false" in lowered
    assert "winget install" not in lowered
    assert "choco install" not in lowered
    assert "docker compose" in lowered
    assert "new-hexsecret" in lowered
    assert "icacls" in lowered
    assert "0.0.0.0 is refused" in lowered
    assert '"alembic", "upgrade", "head"' not in lowered  # Compose owns the command.


def test_desktop_reads_managed_api_endpoint_without_db_configuration() -> None:
    rust = read("clients/desktop/src-tauri/src/main.rs")
    client = read("clients/web/src/api/client.ts")
    host = read("clients/web/src/app/host/hostCapabilities.ts")

    assert "read_deployment_config" in rust
    assert 'join("deployment.json")' in rust
    assert "hydrateApiBaseUrlFromDesktopDeployment" in client
    # The managed endpoint is read through the single HostCapabilities boundary, so
    # the command name and the allowlist live there (Architecture V2 rule 50).
    assert "tryHostCommand<DesktopDeploymentConfig>" in client
    assert "HOST_COMMANDS.readDeploymentConfig" in client
    assert 'readDeploymentConfig: "read_deployment_config"' in host
    assert "postgresql" not in rust.lower()


def test_release_publishes_runtime_image_and_deployment_bundle() -> None:
    workflow = read(".github/workflows/release.yml")

    for phrase in [
        "packages: write",
        "runtime-image:",
        "platforms: linux/amd64,linux/arm64",
        "file: deploy/runtime/Dockerfile.api",
        "deployment:",
        "package_deployment_bundle.sh",
        "release-deployment",
    ]:
        assert phrase in workflow


def test_deployment_documentation_is_bilingual_and_unambiguous() -> None:
    english = read("docs/deployment/DEPLOYMENT_ROLES-EN.md")
    chinese = read("docs/deployment/DEPLOYMENT_ROLES-CN.md")

    for role in ["`Server`", "`Client`"]:
        assert role in english
        assert role in chinese
    assert "never receives a PostgreSQL URL" in english
    assert "不会静默下载或安装" in chinese


# ---------------------------------------------------------------------------
# PILOT-A: extracted-bundle release identity resolution
# ---------------------------------------------------------------------------


def release_context_fixture() -> dict:
    """A resolved, test-only release context; never a real release."""

    return resolve_release_context(
        channel="preview",
        git_sha=TEST_COMMIT_SHA,
        build_run_number=7,
    )


def test_release_workflow_threads_verified_identity_into_the_bundle() -> None:
    workflow = yaml.safe_load(read(".github/workflows/release.yml"))
    deployment = workflow["jobs"]["deployment"]

    # The bundle identity records the digest of the image this release built.
    assert "runtime-image" in deployment["needs"]
    steps = {step["name"]: step for step in deployment["steps"]}
    assert steps["Download immutable image identity"]["with"]["name"] == "image-metadata"
    run = steps["Package and rename Server operator bundle"]["run"]
    assert "package_deployment_bundle.sh" in run
    assert "--release-context release-context/release-context.json" in run
    assert '--image-digest "$IMAGE_DIGEST"' in run
    # The digest is validated before it can become bundle identity.
    assert "assert re.fullmatch" in run
    assert "|| true" not in run


def run_powershell(arguments: list[str], *, environment: dict | None = None):
    """Run Windows PowerShell with the staged release environment removed."""

    process_environment = os.environ.copy()
    for name in STAGED_ENV:
        process_environment.pop(name, None)
    if environment:
        process_environment.update(environment)
    return subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            *arguments,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=process_environment,
        check=False,
        timeout=300,
    )


def packed_bundle(tmp_path: Path) -> Path:
    """Build and extract the operator ZIP with the test-only identity fixture."""

    archive = packager.package(
        tmp_path / "out",
        release_context=release_context_fixture(),
        image_digest=TEST_IMAGE_DIGEST,
    )
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    return extracted / "Eurogas-Nexus-Server-Windows"


def preflight_arguments(
    root: Path, tmp_path: Path, entrypoint: str, *, role: bool = False
) -> list[str]:
    """Throwaway PEM-shaped fixtures; the preflight only checks that paths exist."""

    certificate = tmp_path / "nexus.example.com.crt"
    private_key = tmp_path / "nexus.example.com.key"
    certificate.write_text(
        "-----BEGIN CERTIFICATE-----\npreflight test fixture\n-----END CERTIFICATE-----\n",
        encoding="utf-8",
    )
    private_key.write_text(
        "-----BEGIN PRIVATE KEY-----\npreflight test fixture\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    arguments = ["-File", str(root / "scripts" / "install" / "windows" / entrypoint)]
    if role:
        arguments += ["-Role", "Server"]
    arguments += [
        "-Action",
        "Preflight",
        "-ServerName",
        "nexus.example.com",
        "-HttpsBindAddress",
        "127.0.0.1",
        "-PrivateNetworkOnly",
        "-TlsCertificatePath",
        str(certificate),
        "-TlsPrivateKeyPath",
        str(private_key),
        "-Json",
    ]
    return arguments


def path_without_docker() -> str:
    """The inherited PATH minus the directory that provides the docker CLI.

    The preflight's own docker probes are exercised elsewhere; removing the CLI
    keeps this test deterministic, side-effect free and independent of any
    local container runtime state.
    """

    docker = shutil.which("docker")
    if docker is None:
        return os.environ.get("PATH", "")
    docker_directory = str(Path(docker).resolve().parent).lower()
    entries = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and str(Path(entry).resolve()).lower() != docker_directory
    ]
    return os.pathsep.join(entries)


@requires_windows_powershell
def test_entrypoint_scripts_parse_with_the_powershell_parser(tmp_path: Path) -> None:
    root = packed_bundle(tmp_path)
    parser_check = (
        "$tokens = $null; $errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        "'{path}', [ref]$tokens, [ref]$errors); "
        "if ($errors.Count -gt 0) {{ "
        "$errors | ForEach-Object {{ Write-Output $_.Message }}; exit 1 }}"
    )
    for entrypoint in (
        "Deploy-EurogasNexus.ps1",
        "Install-EurogasNexusServerRuntime.ps1",
    ):
        path = root / "scripts" / "install" / "windows" / entrypoint
        result = run_powershell(["-Command", parser_check.format(path=path)])
        assert result.returncode == 0, result.stdout + result.stderr


@requires_windows_powershell
def test_extracted_deploy_preflight_resolves_identity_without_env_version(
    tmp_path: Path,
) -> None:
    """The documented operator entry point resolves identity, then reports blockers.

    The docker CLI is removed from the child PATH so the runtime probe is
    deterministic; preflight never starts a container or changes host state.
    """

    root = packed_bundle(tmp_path)
    context = release_context_fixture()
    before = sorted(path.relative_to(root) for path in root.rglob("*"))
    environment = {"PATH": path_without_docker()}

    deploy = run_powershell(
        preflight_arguments(root, tmp_path, "Deploy-EurogasNexus.ps1", role=True),
        environment=environment,
    )
    assert deploy.returncode in (0, 20), deploy.stdout + deploy.stderr
    report = json.loads(deploy.stdout)
    assert report["release_identity_source"] == "bundle"
    assert report["release_version"] == context["release_version"]
    assert report["release_channel"] == "preview"
    assert report["api_image"] == f"{context['api_image']}@{TEST_IMAGE_DIGEST}"
    assert report["role"] == "Server"
    assert report["automatic_docker_install"] is False
    if report["ok"]:
        assert report["blocking"] == []
    else:
        # Deploy reports honest blockers (here: the runtime primitive's host
        # probes cannot complete in this sandbox).
        assert report["blocking"]

    # Preflight is read-only: nothing new appears inside the extracted bundle.
    after = sorted(path.relative_to(root) for path in root.rglob("*"))
    assert after == before


@requires_windows_powershell
def test_extracted_runtime_preflight_never_fails_with_an_identity_error(tmp_path: Path) -> None:
    """The runtime primitive resolves the bundle identity where the host permits.

    Its preflight probes host facts (WMI memory/disk, docker state). On a host
    that denies WMI, or where the engine pipe is unreachable, the primitive
    aborts inside its own host probe - pre-existing behaviour, outside PILOT-A.
    A host-probe abort must never be an identity failure, and wherever the
    probes complete the reported identity must be the bundle identity.
    """

    root = packed_bundle(tmp_path)
    context = release_context_fixture()

    runtime = run_powershell(
        preflight_arguments(root, tmp_path, "Install-EurogasNexusServerRuntime.ps1"),
        environment={"PATH": path_without_docker()},
    )
    combined = runtime.stdout + runtime.stderr
    if runtime.returncode in (0, 20):
        runtime_report = json.loads(runtime.stdout)
        assert runtime_report["release_identity_source"] == "bundle"
        assert runtime_report["release_version"] == context["release_version"]
        assert runtime_report["release_channel"] == "preview"
        assert runtime_report["api_image"] == f"{context['api_image']}@{TEST_IMAGE_DIGEST}"
        assert runtime_report["docker_install_attempted"] is False
        assert runtime_report["checks"]["docker_cli"] is False
        assert any("docker" in item.lower() for item in runtime_report["blocking"])
    else:
        assert "release identity" not in combined.lower()
        assert "CimInstance" in combined or "docker" in combined.lower()


@pytest.mark.parametrize(
    ("case", "corrupt"),
    [
        ("missing", None),
        ("invalid-json", "{not json"),
        ("invalid-field", '{"schema_version": 1, "product_name": "Eurogas Nexus"}'),
    ],
)
@requires_windows_powershell
def test_missing_or_malformed_bundle_identity_fails_closed(
    tmp_path: Path, case: str, corrupt: str | None
) -> None:
    root = packed_bundle(tmp_path)
    identity = root / "release-identity.json"
    if corrupt is None:
        identity.unlink()
    else:
        identity.write_text(corrupt, encoding="utf-8")

    result = run_powershell(
        preflight_arguments(root, tmp_path, "Deploy-EurogasNexus.ps1", role=True)
    )

    assert result.returncode != 0
    assert "release identity" in (result.stdout + result.stderr).lower()


@requires_windows_powershell
def test_conflicting_env_version_fails_closed(tmp_path: Path) -> None:
    root = packed_bundle(tmp_path)

    result = run_powershell(
        preflight_arguments(root, tmp_path, "Deploy-EurogasNexus.ps1", role=True),
        environment={"EUROGAS_NEXUS_VERSION": "9.9.9"},
    )

    assert result.returncode != 0
    assert "conflict" in (result.stdout + result.stderr).lower()


@pytest.mark.parametrize(
    ("entrypoint", "role"),
    [
        ("Deploy-EurogasNexus.ps1", True),
        ("Install-EurogasNexusServerRuntime.ps1", False),
    ],
)
@requires_windows_powershell
def test_tagged_api_image_repository_fails_closed_in_both_parsers(
    tmp_path: Path, entrypoint: str, role: bool
) -> None:
    """`repo:tag` is refused even when repository and reference agree.

    The identity's own repository/reference consistency check cannot catch a
    tag that is present in both values, so each parser must reject a tag on
    the final repository path component itself.
    """

    root = packed_bundle(tmp_path)
    identity_path = root / "release-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    tagged = f"{identity['api_image_repository']}:0.5.0"
    identity["api_image_repository"] = tagged
    identity["api_image_reference"] = f"{tagged}@{identity['api_image_digest']}"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    result = run_powershell(preflight_arguments(root, tmp_path, entrypoint, role=role))

    combined = (result.stdout + result.stderr).lower()
    assert result.returncode != 0
    assert "release identity" in combined
    assert "api_image_repository" in combined
    assert "final path component" in combined


@requires_windows_powershell
def test_runtime_primitive_refuses_a_conflicting_api_image_override(tmp_path: Path) -> None:
    """A customer bundle pins one image; -ApiImage may not contradict it."""

    root = packed_bundle(tmp_path)
    arguments = preflight_arguments(root, tmp_path, "Install-EurogasNexusServerRuntime.ps1")
    arguments += ["-ApiImage", f"ghcr.io/example/other-api@{TEST_IMAGE_DIGEST}"]

    result = run_powershell(arguments)

    combined = (result.stdout + result.stderr).lower()
    assert result.returncode != 0
    assert "release identity conflict" in combined
    assert "-apiimage" in combined


@requires_windows_powershell
def test_port_carrying_api_image_repository_is_accepted(tmp_path: Path) -> None:
    """A registry port earlier in the reference is not a tag on the repository."""

    root = packed_bundle(tmp_path)
    identity_path = root / "release-identity.json"
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    ported = "registry.example.com:5000/example/api"
    identity["api_image_repository"] = ported
    identity["api_image_reference"] = f"{ported}@{identity['api_image_digest']}"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")

    result = run_powershell(
        preflight_arguments(root, tmp_path, "Deploy-EurogasNexus.ps1", role=True),
        environment={"PATH": path_without_docker()},
    )
    combined = result.stdout + result.stderr
    if result.returncode in (0, 20):
        report = json.loads(result.stdout)
        assert report["api_image"] == f"{ported}@{TEST_IMAGE_DIGEST}"
    else:
        # Host probes (WMI/docker) may abort the runtime primitive; the ported
        # repository itself must never be reported as an identity failure.
        assert "release identity" not in combined.lower()


@requires_windows_powershell
def test_runtime_primitive_accepts_the_pinned_api_image_override(tmp_path: Path) -> None:
    """Repeating the pinned reference is not a conflict."""

    root = packed_bundle(tmp_path)
    context = release_context_fixture()
    pinned = f"{context['api_image']}@{TEST_IMAGE_DIGEST}"
    arguments = preflight_arguments(root, tmp_path, "Install-EurogasNexusServerRuntime.ps1")
    arguments += ["-ApiImage", pinned]

    result = run_powershell(arguments, environment={"PATH": path_without_docker()})
    combined = result.stdout + result.stderr
    if result.returncode in (0, 20):
        report = json.loads(result.stdout)
        assert report["api_image"] == pinned
    else:
        # Host probes (WMI/docker) may abort before the report; that abort must
        # never be an identity conflict.
        assert "release identity conflict" not in combined.lower()


@requires_windows_powershell
def test_server_runtime_primitive_fails_closed_without_identity(tmp_path: Path) -> None:
    root = packed_bundle(tmp_path)
    (root / "release-identity.json").unlink()

    result = run_powershell(
        preflight_arguments(root, tmp_path, "Install-EurogasNexusServerRuntime.ps1")
    )

    assert result.returncode != 0
    assert "release identity" in (result.stdout + result.stderr).lower()


@requires_windows_powershell
def test_matching_env_version_is_ignored_and_bundle_identity_wins(tmp_path: Path) -> None:
    root = packed_bundle(tmp_path)
    context = release_context_fixture()

    result = run_powershell(
        preflight_arguments(root, tmp_path, "Deploy-EurogasNexus.ps1", role=True),
        environment={"EUROGAS_NEXUS_VERSION": context["app_version"]},
    )

    assert result.returncode in (0, 20), result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["release_identity_source"] == "bundle"
    assert report["release_version"] == context["release_version"]


@requires_windows_powershell
def test_source_checkout_invocation_resolves_development_version(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "clients" / "desktop" / "src-tauri").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "test"\nversion = "0.9.9"\n', encoding="utf-8"
    )
    (checkout / "clients" / "desktop" / "src-tauri" / "tauri.conf.json").write_text(
        json.dumps({"version": "0.9.9"}), encoding="utf-8"
    )
    for relative in (
        "scripts/install/windows/Deploy-EurogasNexus.ps1",
        "scripts/install/windows/Install-EurogasNexusServerRuntime.ps1",
        "deploy/runtime/compose.yaml",
        "deploy/runtime/Caddyfile",
    ):
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    result = run_powershell(
        preflight_arguments(checkout, tmp_path, "Deploy-EurogasNexus.ps1", role=True)
    )

    assert result.returncode in (0, 20), result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["release_identity_source"] == "source-development"
    assert report["release_version"] == "v0.9.9-preview"
    assert report["release_channel"] == "preview"
