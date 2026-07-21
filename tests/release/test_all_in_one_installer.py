"""Release contracts for the Docker-only Windows AllInOne installer."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


def test_nsis_embeds_frontend_runtime_and_non_destructive_uninstaller() -> None:
    nsis = read("installer/windows/all-in-one/EurogasNexusAllInOne.nsi")

    for phrase in [
        'Name "Eurogas Nexus AllInOne"',
        "RequestExecutionLevel admin",
        "Eurogas-Nexus-Client-setup.exe",
        "eurogas-nexus-api-amd64.tar",
        "Install-EurogasNexusAllInOne.ps1",
        "Manage-EurogasNexusAllInOne.ps1",
        "-Action Install",
        "-Action Uninstall -UninstallClient",
        "The PostgreSQL data volume will be preserved",
        "-Action PurgeData -ConfirmPurge",
        "MB_DEFBUTTON2",
    ]:
        assert phrase in nsis
    assert "POSTGRES_PASSWORD" not in nsis


def test_all_in_one_bootstrap_requires_only_windows_and_docker_runtime() -> None:
    bootstrap = read("scripts/install/windows/Install-EurogasNexusAllInOne.ps1")
    runtime = read("scripts/install/windows/Install-EurogasNexusServerRuntime.ps1")

    for phrase in [
        "Wait-DockerReady",
        "Docker Desktop.exe",
        "docker compose version",
        'ApiBaseUrl = "http://127.0.0.1:8765/api"',
        "ApiImageArchivePath",
        "LocalHttpOnly = $true",
        "Install-DesktopClient",
        "Write-ClientDeployment",
    ]:
        assert phrase in bootstrap
    for forbidden in ["winget install", "choco install", "pip install", "npm install"]:
        assert forbidden not in bootstrap.lower()

    assert "docker load --input" in runtime
    assert 'network_exposure = if ($UseLocalHttp) { "loopback_only" }' in runtime
    assert (
        'Invoke-Compose @("--profile", "tools", "run", "--rm", "--no-deps", "preview-seed")'
        in runtime
    )
    assert "New-HexSecret" in runtime
    assert "icacls" in runtime
    assert "public_data_workers_enabled = -not [bool]$SkipPublicData" in runtime

    manager = read("scripts/install/windows/Manage-EurogasNexusAllInOne.ps1")
    assert "Get-ConfiguredProfiles" in manager
    assert "Start-ConfiguredRuntime" in manager
    assert 'configuration.simulated_prices_enabled' in manager
    assert 'configuration.public_data_workers_enabled' in manager


def test_compose_seeds_postgres_before_starting_simulated_feed() -> None:
    compose = read("deploy/runtime/compose.yaml")

    assert "preview-seed:" in compose
    assert 'command: ["python", "scripts/ops/seed_preview_runtime_data.py"]' in compose
    assert "simulated-prices:" in compose
    assert (
        'command: ["python", "scripts/ops/ingest_simulated_market_prices.py", "--loop"]'
        in compose
    )
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert '"127.0.0.1:${POSTGRES_PORT}:5432"' in compose
    assert '"127.0.0.1:${API_PORT}:8000"' in compose


def test_release_builds_distinct_client_and_all_in_one_assets() -> None:
    workflow = read(".github/workflows/release.yml")

    for phrase in [
        "all-in-one-windows:",
        "all-in-one-runtime-image-amd64",
        "build_all_in_one_installer.ps1",
        "Eurogas-Nexus-Client-0.5.0-x64-setup.exe",
        "release-all-in-one-windows",
        "Eurogas-Nexus-AllInOne-...-x64-setup.exe",
        "needs.all-in-one-windows.result == 'success'",
    ]:
        assert phrase in workflow
    assert "build_desktop:" not in workflow

    package_script = read("scripts/release/package_deployment_bundle.sh")
    assert 'Eurogas-Nexus-AllInOne-Windows.zip"' not in package_script
    assert "eurogas-nexus-deployment-windows.zip" not in package_script
    assert "Eurogas-Nexus-Server-Windows.zip" in package_script


def test_windows_client_bootstraps_webview_and_installs_machine_wide() -> None:
    config = json.loads(read("clients/desktop/src-tauri/tauri.conf.json"))
    windows = config["bundle"]["windows"]

    assert windows["webviewInstallMode"] == {"type": "downloadBootstrapper"}
    assert windows["nsis"]["installMode"] == "perMachine"


def test_all_in_one_documentation_is_bilingual_and_absolute() -> None:
    english = read("docs/deployment/ALL_IN_ONE_INSTALLER-EN.md")
    chinese = read("docs/deployment/ALL_IN_ONE_INSTALLER-CN.md")

    for document in [english, chinese]:
        assert "Eurogas-Nexus-AllInOne-" in document
        assert "Docker" in document
        assert "127.0.0.1:8765/api" in document
        assert "PostgreSQL" in document
        assert "PurgeData" in document
    assert "No Python, Node.js, Rust, Git" in english
    assert "不需要 Python、Node.js、Rust、Git" in chinese
