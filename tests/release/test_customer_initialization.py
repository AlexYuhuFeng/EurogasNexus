"""Customer bootstrap contracts; no container, database or real .env is touched."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from eurogas_nexus.core.config_contract import CONFIG_VARS
from eurogas_nexus.core.preflight import check_environment

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts/install/windows/Install-EurogasNexusServerRuntime.ps1"
WRAPPER = ROOT / "scripts/install/windows/Deploy-EurogasNexus.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
requires_powershell = pytest.mark.skipif(
    sys.platform != "win32" or not POWERSHELL, reason="Windows bootstrap command plan"
)


def quote(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run_powershell(body: str) -> dict:
    script = f"""
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    {quote(INSTALLER)}, [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ throw 'Installer syntax error' }}
function Load-Function([string]$Name) {{
    $node = $tree.FindAll({{ param($item)
        $item -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $item.Name -eq $Name
    }}, $true) | Select-Object -First 1
    if (-not $node) {{ throw "Missing installer function $Name" }}
    return [scriptblock]::Create($node.Extent.Text)
}}
{body}
"""
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script],
        cwd=ROOT, capture_output=True, text=True, timeout=40,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@requires_powershell
@pytest.mark.parametrize("action", ["Install", "Repair"])
@pytest.mark.parametrize("skip_public", [False, True])
@pytest.mark.parametrize("config_fails", [False, True])
def test_customer_command_plan(action, skip_public, config_fails) -> None:
    result = run_powershell(f"""
. (Load-Function 'Install-OrRepairRuntime')
. (Load-Function 'Invoke-Compose')
function Initialize-RuntimeFiles {{}}
function Import-ApiImageArchive {{}}
function Wait-ApiReady {{ return @{{ status='ok'; version='test' }} }}
function Wait-PublicApiReady {{ return @{{ status='ok'; version='test' }} }}
$global:Calls = [System.Collections.Generic.List[object]]::new()
function docker {{
    $call = @($args | ForEach-Object {{ [string]$_ }})
    $global:Calls.Add($call)
    $global:LASTEXITCODE = if ({'$true' if config_fails else '$false'} -and $call[-1] -eq 'config-check') {{ 17 }} else {{ 0 }}
}}
$Action={quote(action)}; $UseLocalHttp=$false; $DeploymentRole='Server'
$ApiImageArchivePath=''; $EnvironmentFile='synthetic.env'; $ComposeFile='synthetic.yaml'
$SkipPublicData={'$true' if skip_public else '$false'}; $ApiBaseUrl='https://example.invalid/api'
$failure=$null; $report=$null
try {{ $report=Install-OrRepairRuntime }} catch {{ $failure=$_.Exception.Message }}
@{{ calls=@($global:Calls.ToArray()); failure=$failure; report=$report }} | ConvertTo-Json -Depth 12 -Compress
""")
    calls = [call[5:] for call in result["calls"]]
    assert calls[:3] == [
        ["pull", "postgres", "migrate", "api"],
        ["up", "-d", "postgres"],
        ["run", "--rm", "--no-deps", "config-check"],
    ]
    assert all("simulated-prices" not in call and "preview-seed" not in call for call in calls)
    if config_fails:
        assert len(calls) == 3
        assert "config-check" in result["failure"]
        assert result["report"] is None
    else:
        assert calls[3:5] == [
            ["run", "--rm", "--no-deps", "migrate"],
            ["up", "-d", "--no-deps", "api"],
        ]
        assert result["failure"] is None
        assert result["report"]["simulated_prices_enabled"] is False
        assert result["report"]["public_data_workers_enabled"] is not skip_public


@requires_powershell
@pytest.mark.parametrize("script", [INSTALLER, WRAPPER])
@pytest.mark.parametrize("action", ["Install", "Repair"])
def test_obsolete_simulation_switch_refused_before_any_work(script, action, tmp_path) -> None:
    # A copied script without bundle identity cannot install; the explicit refusal
    # must occur even before identity/path resolution. No real install root is used.
    copied = tmp_path / script.name
    copied.write_bytes(script.read_bytes())
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(copied),
         "-Action", action, "-EnableSimulatedPrices"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "CUSTOMER_SIMULATION_FORBIDDEN" in result.stderr
    assert sorted(path.name for path in tmp_path.iterdir()) == [script.name]


@requires_powershell
def initialize_synthetic_runtime(tmp_path: Path, oidc: dict[str, str]) -> dict[str, str]:
    runtime = tmp_path / "synthetic-runtime"
    runtime.mkdir()
    existing = {
        "POSTGRES_PASSWORD": "test-only-postgres-secret",
        "EUROGAS_NEXUS_SECRET_KEY": "1mDk0Q0m9K4pXc2rWb7tLzYvHsAeNfRgUjOiPlMnQ4E=",
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN": "test-only-public-token",
        "EUROGAS_NEXUS_INTERNAL_API_TOKEN": "test-only-internal-token",
        **oidc,
    }
    environment = runtime / ".env"
    environment.write_text("\n".join(f"{key}={value}" for key, value in existing.items()), encoding="utf-8")
    result = run_powershell(f"""
. (Load-Function 'Initialize-RuntimeFiles')
function Protect-EnvironmentFile {{}}
function New-HexSecret {{ throw 'Existing synthetic credentials must be preserved' }}
$InstallRoot={quote(runtime)}; $EnvironmentFile={quote(environment)}
$SourceComposeFile={quote(ROOT / 'deploy/runtime/compose.yaml')}
$ComposeFile={quote(runtime / 'compose.yaml')}; $DeploymentFile={quote(runtime / 'deployment.json')}
$UseLocalHttp=$true; $DeploymentRole='Server'; $SkipPublicData=$true
$ApiImage='example.invalid/customer:test'; $PackageVersion='0.0.0'; $ReleaseChannel='preview'
$ApiPort=8765; $PostgresPort=55432; $HttpsPort=8443; $HttpsBindAddress='127.0.0.1'
$ServerName='example.invalid'; $ApiBaseUrl='http://127.0.0.1:8765/api'
Initialize-RuntimeFiles
@{{ ok=$true }} | ConvertTo-Json -Compress
""")
    assert result["ok"]
    values = dict(line.split("=", 1) for line in environment.read_text(encoding="utf-8").splitlines())
    assert all(values[key] == value for key, value in existing.items())
    return values


def effective_compose_environment(values: dict[str, str]) -> dict[str, str]:
    """Resolve the limited interpolation used by the actual shared environment."""
    compose = yaml.safe_load((ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8"))
    shared = compose["x-runtime-environment"]
    for service in ["config-check", "migrate", "api"]:
        assert compose["services"][service]["environment"] == shared

    def replace(match):
        name, default = match.group(1), match.group(2)
        return values.get(name) or default or ""

    return {key: re.sub(r"\$\{([A-Z_]+)(?::-([^}]*))?\}", replace, value) for key, value in shared.items()}


def resolve_actual_compose(tmp_path: Path) -> dict[str, str]:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI required for actual dotenv resolution")
    # Only temporary synthetic values reach Compose. Ambient deployment values
    # must not override the fixture or enter captured configuration output.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("EUROGAS_NEXUS_", "POSTGRES_"))
        and key not in {"FORWARDED_ALLOW_IPS", "API_PORT", "HTTPS_PORT", "HTTPS_BIND_ADDRESS", "SERVER_NAME"}
    }
    runtime = tmp_path / "synthetic-runtime"
    result = subprocess.run(
        [docker, "compose", "--env-file", str(runtime / ".env"),
         "-f", str(runtime / "compose.yaml"), "--profile", "*", "config", "--format", "json"],
        cwd=runtime, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, "Synthetic Compose resolution failed (output withheld)"
    services = json.loads(result.stdout)["services"]
    effective = services["config-check"]["environment"]
    assert services["api"]["environment"] == services["migrate"]["environment"] == effective
    # Canonical Compose output escapes literal dollars for another Compose read.
    # The optional immutable-image probe below verifies actual container values.
    return {key: value.replace("$$", "$") for key, value in effective.items()}


@requires_powershell
@pytest.mark.parametrize("shape", ["absent", "partial", "complete", "allow_http"])
def test_repair_preserves_oidc_and_container_preflight_sees_it(tmp_path, shape) -> None:
    oidc = {} if shape == "absent" else {"EUROGAS_NEXUS_OIDC_ISSUER": "https://idp.example.invalid"}
    if shape in {"complete", "allow_http"}:
        oidc.update({
            "EUROGAS_NEXUS_OIDC_CLIENT_ID": "test-only-client",
            "EUROGAS_NEXUS_OIDC_CLIENT_SECRET": "'test-only$UNDEFINED_TOKEN#\"quoted\"'",
            "EUROGAS_NEXUS_OIDC_REDIRECT_URI": "https://customer.example.invalid/api/auth/oidc/callback",
            "EUROGAS_NEXUS_OIDC_ROLE_CLAIM": "custom_roles",
            "EUROGAS_NEXUS_OIDC_SCOPE_CLAIM": "custom_scopes",
            "EUROGAS_NEXUS_OIDC_PROVISIONING_MODE": "preprovisioned",
            "EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP": "'{\"desk\": [\"READ\"]}'",
            "EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP": "'{\"desk\": [\"public\"]}'",
        })
    if shape == "allow_http":
        oidc["EUROGAS_NEXUS_OIDC_ALLOW_HTTP"] = "1"
    values = initialize_synthetic_runtime(tmp_path, oidc)
    assert {key: value for key, value in values.items() if key.startswith("EUROGAS_NEXUS_OIDC_")} == oidc
    effective = resolve_actual_compose(tmp_path)
    assert effective["EUROGAS_NEXUS_SECRET_KEY"] == values["EUROGAS_NEXUS_SECRET_KEY"]
    assert all(effective[key] == value.strip("'") for key, value in oidc.items()), "OIDC values changed during Compose resolution"
    assert effective["EUROGAS_NEXUS_OIDC_PROVISIONING_MODE"] == "preprovisioned"
    assert effective["EUROGAS_NEXUS_ENV"] == effective["EUROGAS_NEXUS_API_PROFILE"] == "release"
    report = check_environment(effective)
    assert report.ok is (shape in {"absent", "complete"})
    if shape == "partial":
        assert any(item.code == "oidc_partially_configured" for item in report.findings)
    if shape == "allow_http":
        assert any(item.variable == "EUROGAS_NEXUS_OIDC_ALLOW_HTTP" and item.severity == "error" for item in report.findings)


@requires_powershell
def test_compose_literal_credentials_reach_isolated_immutable_image(tmp_path) -> None:
    image_id = os.environ.get("EUROGAS_TEST_CUSTOMER_IMAGE_ID", "")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        pytest.skip("Explicit existing immutable customer image required for container probe")
    docker = shutil.which("docker")
    assert docker, "Docker CLI required for requested container probe"
    literal = {
        "EUROGAS_NEXUS_OIDC_CLIENT_SECRET": 'test-only$UNDEFINED_TOKEN#"quoted"',
        "EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP": '{"desk": ["READ"]}',
        "EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP": '{"desk": ["public"]}',
    }
    initialize_synthetic_runtime(tmp_path, {key: "'" + value + "'" for key, value in literal.items()})
    runtime = tmp_path / "synthetic-runtime"
    source = yaml.safe_load((runtime / "compose.yaml").read_text(encoding="utf-8"))
    expected = {key: hashlib.sha256(value.encode()).hexdigest() for key, value in literal.items()}
    code = (
        "import hashlib,json,os; expected=" + repr(expected) + "; "
        "print(json.dumps({'values_match':all(hashlib.sha256(os.environ[k].encode()).hexdigest()==v "
        "for k,v in expected.items()),'nonroot':os.getuid()!=0}))"
    )
    probe = runtime / "probe.yaml"
    probe.write_text(yaml.safe_dump({"services": {"probe": {
        "image": image_id, "pull_policy": "never", "network_mode": "none", "read_only": True,
        "environment": source["x-runtime-environment"], "entrypoint": ["python", "-c", code],
    }}}), encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("EUROGAS_NEXUS_")}
    result = subprocess.run(
        [docker, "compose", "-p", "eurogas-customer-env-gate", "--env-file", str(runtime / ".env"),
         "-f", str(probe), "run", "--rm", "--no-deps", "probe"],
        cwd=runtime, env=environment, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, "Isolated synthetic environment probe failed (output withheld)"
    assert json.loads(result.stdout) == {"values_match": True, "nonroot": True}


def test_all_canonical_oidc_values_reach_customer_containers() -> None:
    canonical = {item.name for item in CONFIG_VARS if item.name.startswith("EUROGAS_NEXUS_OIDC_")}
    values = {key: "synthetic-test-value" for key in canonical}
    effective = effective_compose_environment(values)
    assert all(effective[key] == value for key, value in values.items())


def test_customer_postgres_has_no_fixture_initialization_and_migrations_do_not_seed() -> None:
    compose = yaml.safe_load((ROOT / "deploy/runtime/compose.yaml").read_text(encoding="utf-8"))
    postgres = compose["services"]["postgres"]
    assert postgres["image"] == "postgres:16-alpine"
    assert postgres["volumes"] == ["runtime-postgres:/var/lib/postgresql/data"]
    assert not set(postgres) & {"command", "entrypoint"}
    assert compose["volumes"]["runtime-postgres"]["name"] == "eurogas-nexus-runtime-postgres"
    for path in sorted((ROOT / "alembic/versions").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", getattr(node.func, "id", ""))
                assert not re.search(r"seed|fixture|bulk_insert|^insert$", name, re.I), path.name
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not re.match(r"\s*(INSERT|COPY|UPDATE|DELETE)\s", node.value, re.I), path.name
            if isinstance(node, ast.ImportFrom):
                assert not re.search(r"simulated|seed|fixture", node.module or "", re.I), path.name
