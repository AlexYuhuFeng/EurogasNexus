"""Contract tests for the Windows canonical Python installer.

Static checks run on every platform. The subprocess checks only run when
``pwsh`` is available and stop in the installer's preflight, before any network
access or archive extraction.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "ci" / "install_windows_canonical_python.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "native-acceptance.yml"
EXPECTED_VERSION = "3.11.12"
EXPECTED_SHA256 = "f794b1e74349a989d1b9a466d2207527d4e16a36c92a1277802458293bc4be31"
ARCHIVE_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    "20250529/cpython-3.11.12%2B20250529-x86_64-pc-windows-msvc-"
    "install_only_stripped.tar.gz"
)
INSTALL_ROOT_NAME = f"eurogas-nexus-python-{EXPECTED_VERSION}"
PWSH = shutil.which("pwsh")


def _run_installer(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    assert PWSH is not None
    return subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-File", str(script)],
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=env,
        errors="replace",
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=60,
    )


def _combined_output(completed: subprocess.CompletedProcess) -> str:
    return (completed.stdout or "") + (completed.stderr or "")


def _validation_repo(tmp_path: Path, canonical: str | None) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    script = repo / "scripts" / "ci" / INSTALLER.name
    script.parent.mkdir(parents=True)
    shutil.copy2(INSTALLER, script)
    if canonical is not None:
        (repo / ".python-version").write_text(canonical + "\n", encoding="utf-8")

    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    github_path = tmp_path / "github_path"
    github_path.write_text("", encoding="utf-8")
    return script, runner_temp


def test_installer_pins_reviewed_version_url_hash_and_archive_shape() -> None:
    text = INSTALLER.read_text(encoding="utf-8")

    canonical = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert canonical == EXPECTED_VERSION
    assert f"$ExpectedPythonVersion = '{EXPECTED_VERSION}'" in text
    assert f"$ExpectedSha256 = '{EXPECTED_SHA256}'" in text
    assert f"$ArchiveUrl = '{ARCHIVE_URL}'" in text
    assert "Get-FileHash -LiteralPath $archivePath -Algorithm SHA256" in text
    assert "Get-FileHash" in text
    assert "if ($actualSha256 -cne $ExpectedSha256)" in text
    assert text.index("Get-FileHash") < text.index("& $tarPath $tarArguments")
    assert ".python-version" in text
    assert text.index("$canonicalVersionPath") < text.index("Invoke-WebRequest")
    assert "GetEnvironmentVariable('GITHUB_PATH')" in text
    assert text.index("GetEnvironmentVariable('GITHUB_PATH')") < text.index(
        "Invoke-WebRequest"
    )
    assert "python\\python.exe" in text
    assert 'if ($versionOutput -cne "Python $ExpectedPythonVersion")' in text
    assert "Add-Content -LiteralPath $githubPath -Value $pythonHome" in text


def test_installer_rejects_caller_inputs_and_security_downgrades() -> None:
    text = INSTALLER.read_text(encoding="utf-8")

    assert re.search(r"(?im)^\s*param\s*\(", text) is None
    assert "http://" not in text
    for forbidden in (
        "Invoke-Expression",
        "Set-ExecutionPolicy",
        "SecurityProtocol",
        "ServerCertificateValidationCallback",
        "-SkipCertificateCheck",
        "Remove-Item",
        "Start-BitsTransfer",
    ):
        assert forbidden not in text
    assert "refusing to overwrite an existing Windows Python install" in text
    assert "eurogas-nexus-python-$ExpectedPythonVersion" in text
    assert "New-Item -ItemType Directory" in text


def test_installer_reads_only_runner_infrastructure_environment() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    names = set(re.findall(r"GetEnvironmentVariable\('([^']+)'\)", text))

    assert names == {"RUNNER_TEMP", "GITHUB_PATH", "SystemRoot"}
    assert "$env:" not in text


def test_workflow_uses_the_fallback_only_on_windows() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    blocks = re.split(r"(?m)^      - name: ", text)
    steps = {block.splitlines()[0]: block for block in blocks[1:] if block.strip()}

    assert text.count("actions/setup-python@") == 1
    setup = steps["Set up Python"]
    windows = steps["Install verified canonical Python (Windows)"]
    assert "if: runner.os != 'Windows'" in setup
    assert "actions/setup-python@" in setup
    assert "if: runner.os == 'Windows'" in windows
    assert "shell: pwsh" in windows
    assert "pwsh -File scripts/ci/install_windows_canonical_python.ps1" in windows
    assert "actions/setup-python@" not in windows


def test_installer_is_a_hash_bound_build_input() -> None:
    evidence_writer = ROOT / "scripts" / "uat" / "write_native_build_evidence.py"
    text = evidence_writer.read_text(encoding="utf-8")
    assert '    "scripts/ci/install_windows_canonical_python.ps1",' in text


@pytest.mark.skipif(PWSH is None, reason="pwsh is not installed")
def test_missing_github_path_fails_before_download_or_install(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(tmp_path)
    env.pop("GITHUB_PATH", None)

    completed = _run_installer(INSTALLER, env)
    output = _combined_output(completed)

    assert completed.returncode != 0
    assert "GITHUB_PATH is required" in output
    assert not (tmp_path / INSTALL_ROOT_NAME).exists()


@pytest.mark.skipif(PWSH is None, reason="pwsh is not installed")
@pytest.mark.parametrize(
    ("canonical", "message"),
    [
        (None, "canonical Python version file is missing"),
        ("3.12.0", "not the reviewed 3.11.12 Windows asset"),
    ],
)
def test_missing_or_changed_canonical_fails_before_download(
    tmp_path: Path, canonical: str | None, message: str
) -> None:
    script, runner_temp = _validation_repo(tmp_path, canonical)
    github_path = tmp_path / "github_path"
    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(runner_temp)
    env["GITHUB_PATH"] = str(github_path)

    completed = _run_installer(script, env)
    output = _combined_output(completed)

    assert completed.returncode != 0
    assert message in output
    assert not (runner_temp / INSTALL_ROOT_NAME).exists()
    assert github_path.read_text(encoding="utf-8") == ""
