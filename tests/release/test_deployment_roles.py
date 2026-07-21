"""Release contracts for customer deployment roles."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


def test_deployment_bundle_defines_exact_device_roles() -> None:
    script = read("scripts/install/windows/Deploy-EurogasNexus.ps1")

    assert '[ValidateSet("Server", "Client", "AllInOne")]' in script
    assert "ServerApiUrl" in script
    assert "ClientInstallerPath" in script
    assert "client_database_credentials = $false" in script
    assert "automatic_docker_install = $false" in script
    assert "Get-AuthenticodeSignature" in script
    assert "AllowUnsignedPreview" in script
    assert "PrivateNetworkOnly" in script
    assert 'network_exposure = if ($Role' in script
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

    assert 'docker_install_attempted = $false' in lowered
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

    assert "read_deployment_config" in rust
    assert 'join("deployment.json")' in rust
    assert "hydrateApiBaseUrlFromDesktopDeployment" in client
    assert 'invoke<DesktopDeploymentConfig | null>("read_deployment_config")' in client
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
        "all-in-one-windows:",
        "release-all-in-one-windows",
    ]:
        assert phrase in workflow


def test_deployment_documentation_is_bilingual_and_unambiguous() -> None:
    english = read("docs/deployment/DEPLOYMENT_ROLES-EN.md")
    chinese = read("docs/deployment/DEPLOYMENT_ROLES-CN.md")

    for role in ["`Server`", "`Client`", "`AllInOne`"]:
        assert role in english
        assert role in chinese
    assert "never receives a PostgreSQL URL" in english
    assert "不会静默下载或安装" in chinese
