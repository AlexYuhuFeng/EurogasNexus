"""Focused tests for the native build-only evidence writer.

The workflow itself is reviewed statically because this repository's local
execution shell can be unavailable. These tests exercise the input boundary that
the workflow relies on: source identity, canonical toolchain, lock hashes,
expected build outputs, staged-byte hashes and unsafe output refusal.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "native-acceptance.yml"
CANONICAL = {"python": "3.11.12", "node": "24.13.1", "rust": "1.94.0"}
SOURCE_SHA = "a" * 40
REPOSITORY = "AlexYuhuFeng/EurogasNexus"


def _load_module():
    path = ROOT / "scripts" / "uat" / "write_native_build_evidence.py"
    spec = importlib.util.spec_from_file_location("write_native_build_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


native = _load_module()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _git_runner(*, head: str = SOURCE_SHA, status: str = ""):
    def run(_repo_root: Path, arguments: tuple[str, ...]) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return head + "\n"
        if arguments[0] == "status":
            return status
        raise AssertionError(f"unexpected git arguments: {arguments}")

    return run


def _package_paths(platform: str) -> tuple[str, str]:
    if platform == "windows-x64":
        return (
            "clients/desktop/src-tauri/target/release/bundle/nsis/*.exe",
            "clients/desktop/src-tauri/target/release/eurogas-nexus-desktop.exe",
        )
    return (
        "clients/desktop/src-tauri/target/release/bundle/deb/*.deb",
        "clients/desktop/src-tauri/target/release/eurogas-nexus-desktop",
    )


def _make_repo(tmp_path: Path, platform: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in native.LOCK_FILES:
        _write_text(repo / relative, f"synthetic lock content for {relative}\n")
    for relative in native.BUILD_INPUT_FILES:
        _write_text(repo / relative, f"synthetic build input for {relative}\n")
    _write_text(repo / ".python-version", f"{CANONICAL['python']}\n")
    _write_text(repo / ".nvmrc", f"{CANONICAL['node']}\n")
    _write_text(
        repo / "rust-toolchain.toml",
        f'[toolchain]\nchannel = "{CANONICAL["rust"]}"\n',
    )

    if platform == "windows-x64":
        package = (
            repo
            / "clients/desktop/src-tauri/target/release/bundle/nsis"
            / "Eurogas Nexus_0.5.0_x64-setup.exe"
        )
        portable = (
            repo
            / "clients/desktop/src-tauri/target/release"
            / "eurogas-nexus-desktop.exe"
        )
    else:
        architecture = "amd64" if platform == "linux-x64" else "arm64"
        package = (
            repo
            / "clients/desktop/src-tauri/target/release/bundle/deb"
            / f"eurogas-nexus-desktop_0.5.0_{architecture}.deb"
        )
        portable = (
            repo
            / "clients/desktop/src-tauri/target/release"
            / "eurogas-nexus-desktop"
        )
    _write_bytes(package, f"synthetic {platform} package bytes".encode())
    _write_bytes(portable, f"synthetic {platform} native binary bytes".encode())
    return repo


def _version_runner(**overrides: str):
    versions = {**CANONICAL, **overrides}

    def run(tool: str) -> str:
        if tool == "python":
            return versions["python"] + "\n"
        if tool == "node":
            return "v" + versions["node"] + "\n"
        if tool == "rust":
            return f"rustc {versions['rust']} (synthetic 2026-01-01)\n"
        raise AssertionError(f"unexpected toolchain probe: {tool}")

    return run


def _invoke(
    tmp_path: Path,
    *,
    platform: str = "windows-x64",
    git_runner=None,
    version_runner=None,
    expected: dict[str, str] | None = None,
    stage_dir: str | None = None,
    output: str | None = None,
    mutate=None,
):
    repo = _make_repo(tmp_path, platform)
    if mutate is not None:
        mutate(repo)
    spec = native.PLATFORMS[platform]
    package_glob, portable_source = _package_paths(platform)
    stage = stage_dir if stage_dir is not None else f"artifacts/native-acceptance/{platform}"
    evidence_output = (
        output
        if output is not None
        else f"{stage}/evidence/native-build-evidence.json"
    )
    evidence = native.build_evidence(
        repo_root=repo,
        source_sha=SOURCE_SHA,
        platform_label=platform,
        runner_os=spec.runner_os,
        runner_arch=spec.runner_arch,
        bundle=spec.bundle,
        package_glob=package_glob,
        portable_source=portable_source,
        stage_dir=stage,
        output=evidence_output,
        expected_toolchain=expected or dict(CANONICAL),
        run_id="1234567890",
        run_attempt="1",
        ref="refs/heads/main",
        event_name="workflow_dispatch",
        repository=REPOSITORY,
        git_runner=git_runner or _git_runner(),
        version_runner=version_runner or _version_runner(),
    )
    return repo, stage, evidence


def test_workflow_is_manual_read_only_and_has_no_publish_surface() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "inputs:" not in text
    assert "secrets." not in text
    assert "environment:" not in text
    assert "permissions:\n  contents: read" in text
    for forbidden in (
        "contents: write",
        "packages: write",
        "id-token: write",
        "gh release",
        "npm publish",
        "docker/login-action",
        "attest-build-provenance",
        "git tag",
        "git push",
    ):
        assert forbidden not in text

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            reference = stripped.split("@", 1)[1].split()[0]
            assert re.fullmatch(r"[0-9a-f]{40}", reference), stripped

    assert "windows-2025" in text
    assert "ubuntu-24.04-arm" in text
    assert "bundle: nsis" in text
    assert "bundle: deb" in text
    assert "bash scripts/ci/install_linux_tauri_dependencies.sh" in text
    assert "if: runner.os != 'Windows'" in text
    assert "if: runner.os == 'Windows'" in text
    assert "pwsh -File scripts/ci/install_windows_canonical_python.ps1" in text
    assert "cargo check --manifest-path src-tauri/Cargo.toml --locked" in text
    assert "npm run build -- --bundles ${{ matrix.bundle }} -- --locked" in text
    assert "python scripts/ci/check_toolchain_versions.py" in text
    assert "npm ci" in text
    assert "write_native_build_evidence.py" in text
    assert "eurogas-nexus-unsigned-native-acceptance" in text


def test_portable_binary_preserves_tauri_production_embedding() -> None:
    manifest_path = ROOT / "clients/desktop/src-tauri/Cargo.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["features"]["custom-protocol"] == ["tauri/custom-protocol"]
    assert "clients/desktop/src-tauri/Cargo.toml" in native.BUILD_INPUT_FILES

    text = WORKFLOW.read_text(encoding="utf-8")
    assert "npm run build -- --bundles ${{ matrix.bundle }} -- --locked" in text
    assert "Build portable native binary with locked dependencies" not in text

    # A future standalone Cargo build is allowed only when it explicitly opts
    # into the production feature; otherwise it can overwrite the Tauri binary.
    cargo_build_lines = [
        line.strip()
        for line in text.splitlines()
        if "cargo build" in line and not line.lstrip().startswith("#")
    ]
    assert all("--features custom-protocol" in line for line in cargo_build_lines)


def test_windows_python_installer_is_a_hash_bound_build_input(tmp_path: Path) -> None:
    relative = "scripts/ci/install_windows_canonical_python.ps1"
    assert relative in native.BUILD_INPUT_FILES

    repo, _stage, evidence = _invoke(tmp_path)
    record = evidence["build_inputs"][relative]
    assert record["sha256"] == _sha(repo / relative)
    assert record["bytes"] == (repo / relative).stat().st_size


def test_workflow_passes_ref_through_quoted_environment_expansion() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "shell: bash" in text
    assert '"$GITHUB_REF"' in text
    assert '"$GITHUB_SHA"' in text
    assert "${{ github.ref }}" not in text
    assert "${{ github.event_name }}" not in text


def test_evidence_binds_actual_artifacts_source_toolchain_and_locks(tmp_path: Path) -> None:
    repo, stage, evidence = _invoke(tmp_path)
    document = json.loads(
        (repo / stage / "evidence/native-build-evidence.json").read_text(encoding="utf-8")
    )

    assert document == evidence
    declarations = document["declarations"]
    assert declarations["scope"] == "native-build-only"
    assert declarations["status"] == "BUILT_NOT_ACCEPTED"
    assert declarations["unsigned"] is True
    assert declarations["unreviewed"] is True
    assert declarations["customer_release"] is False
    assert declarations["release_published"] is False
    assert declarations["native_ui_executed"] is False
    assert declarations["installed_launch_verified"] is False

    assert document["source"] == {
        "git_sha": SOURCE_SHA,
        "git_head": SOURCE_SHA,
        "tracked_worktree_clean": True,
    }
    assert document["toolchain"]["canonical"] == CANONICAL
    assert document["toolchain"]["expected"] == CANONICAL

    for relative in native.LOCK_FILES:
        assert document["locks"][relative]["sha256"] == _sha(repo / relative)

    for label in ("package", "portable"):
        artifact = document["artifacts"][label]
        staged = repo / artifact["staged_path"]
        assert staged.is_file()
        assert artifact["sha256"] == _sha(staged)
        assert artifact["bytes"] == staged.stat().st_size
        assert artifact["source_sha256"] == artifact["sha256"]

    checksums = repo / stage / "checksums.sha256"
    assert document["checksums"]["sha256"] == _sha(checksums)
    lines = checksums.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert digest == _sha(repo / stage / relative)


def test_missing_package_output_is_refused(tmp_path: Path) -> None:
    def remove(repo: Path) -> None:
        bundle = repo / "clients/desktop/src-tauri/target/release/bundle/nsis"
        next(bundle.glob("*.exe")).unlink()

    with pytest.raises(native.EvidenceError, match="exactly one"):
        _invoke(tmp_path, mutate=remove)


def test_ambiguous_package_output_is_refused(tmp_path: Path) -> None:
    def duplicate(repo: Path) -> None:
        directory = repo / "clients/desktop/src-tauri/target/release/bundle/nsis"
        shutil.copy2(next(directory.glob("*.exe")), directory / "second.exe")

    with pytest.raises(native.EvidenceError, match="exactly one"):
        _invoke(tmp_path, mutate=duplicate)


def test_source_sha_must_match_the_checked_out_commit(tmp_path: Path) -> None:
    mismatch = _git_runner(head="b" * 40)
    with pytest.raises(
        native.EvidenceError, match="does not match the dispatched source SHA"
    ):
        _invoke(tmp_path, git_runner=mismatch)


def test_tracked_worktree_changes_are_refused_before_staging(tmp_path: Path) -> None:
    with pytest.raises(native.EvidenceError, match="tracked worktree changes"):
        _invoke(
            tmp_path,
            git_runner=_git_runner(status=" M src/eurogas_nexus/core/config.py\n"),
        )
    assert not (tmp_path / "repo" / "artifacts").exists()


def test_source_check_uses_tracked_only_status(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(_repo_root: Path, arguments: tuple[str, ...]) -> str:
        calls.append(arguments)
        if arguments == ("rev-parse", "HEAD"):
            return SOURCE_SHA + "\n"
        if arguments[0] == "status":
            return ""
        raise AssertionError(f"unexpected git arguments: {arguments}")

    _invoke(tmp_path, git_runner=runner)
    assert ("status", "--porcelain=v1", "--untracked-files=no") in calls


def test_expected_toolchain_must_match_the_canonical_files(tmp_path: Path) -> None:
    expected = dict(CANONICAL)
    expected["python"] = "3.12.0"
    with pytest.raises(native.EvidenceError, match="python toolchain"):
        _invoke(tmp_path, expected=expected)


def test_missing_lock_file_is_refused(tmp_path: Path) -> None:
    def remove_lock(repo: Path) -> None:
        (repo / "requirements-build.lock").unlink()

    with pytest.raises(native.EvidenceError, match="required lock file is missing"):
        _invoke(tmp_path, mutate=remove_lock)


@pytest.mark.parametrize(
    ("stage_dir", "output"),
    [
        ("../outside", "../outside/evidence/native-build-evidence.json"),
        (
            "artifacts/native-acceptance/windows-x64",
            "C:/outside/native-build-evidence.json",
        ),
        (
            "artifacts/native-acceptance/windows-x64",
            "artifacts/native-acceptance/windows-x64/evidence/../../escape.json",
        ),
        ("tmp/native", "tmp/native/evidence/native-build-evidence.json"),
    ],
)
def test_unsafe_stage_or_output_paths_are_refused(
    tmp_path: Path, stage_dir: str, output: str
) -> None:
    with pytest.raises(native.EvidenceError):
        _invoke(tmp_path, stage_dir=stage_dir, output=output)
    assert not (tmp_path / "tmp" / "native").exists()


def test_output_must_be_the_stage_evidence_file(tmp_path: Path) -> None:
    with pytest.raises(native.EvidenceError, match="evidence output must be"):
        _invoke(
            tmp_path,
            output="artifacts/native-acceptance/windows-x64/native-build-evidence.json",
        )


def test_cli_refuses_an_unsafe_stage_without_writing(tmp_path: Path) -> None:
    code = native.main(
        [
            "--repo-root",
            str(tmp_path),
            "--source-sha",
            SOURCE_SHA,
            "--platform-label",
            "windows-x64",
            "--runner-os",
            "Windows",
            "--runner-arch",
            "X64",
            "--bundle",
            "nsis",
            "--package-glob",
            "clients/desktop/src-tauri/target/release/bundle/nsis/*.exe",
            "--portable-source",
            "clients/desktop/src-tauri/target/release/eurogas-nexus-desktop.exe",
            "--stage-dir",
            "tmp/native",
            "--output",
            "tmp/native/evidence/native-build-evidence.json",
            "--python-version",
            CANONICAL["python"],
            "--node-version",
            CANONICAL["node"],
            "--rust-version",
            CANONICAL["rust"],
            "--run-id",
            "1",
            "--run-attempt",
            "1",
            "--ref",
            "refs/heads/main",
            "--event-name",
            "workflow_dispatch",
            "--repository",
            REPOSITORY,
        ]
    )
    assert code == 2
    assert not (tmp_path / "tmp" / "native").exists()


def test_non_empty_stage_directory_is_not_overwritten(tmp_path: Path) -> None:
    stale = (
        tmp_path
        / "repo"
        / "artifacts/native-acceptance/windows-x64/package/old.exe"
    )

    def leave_stale(repo: Path) -> None:
        _write_bytes(stale, b"stale artifact")

    with pytest.raises(native.EvidenceError, match="not empty"):
        _invoke(tmp_path, mutate=leave_stale)
    assert stale.read_bytes() == b"stale artifact"


def test_linux_portable_archive_has_one_executable_member(tmp_path: Path) -> None:
    repo, stage, evidence = _invoke(tmp_path, platform="linux-arm64")
    artifact = evidence["artifacts"]["portable"]
    assert artifact["packaging"] == "tar.gz"
    assert artifact["archive_member"] == "eurogas-nexus-desktop"

    archive_path = repo / artifact["staged_path"]
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == 1
        assert members[0].name == "eurogas-nexus-desktop"
        assert members[0].mode & 0o777 == 0o755
        extracted = archive.extractfile(members[0])
        assert extracted is not None
        payload = extracted.read()

    source = repo / "clients/desktop/src-tauri/target/release/eurogas-nexus-desktop"
    assert payload == source.read_bytes()
    assert artifact["sha256"] == _sha(archive_path)
    assert artifact["source_sha256"] == _sha(source)
    assert (
        "portable/eurogas-nexus-desktop-linux-arm64.tar.gz"
        in (repo / stage / "checksums.sha256").read_text(encoding="utf-8")
    )


def test_actual_toolchain_is_measured_and_recorded_separately(tmp_path: Path) -> None:
    probes: list[str] = []
    fake = _version_runner()

    def recording(tool: str) -> str:
        probes.append(tool)
        return fake(tool)

    _repo, _stage, evidence = _invoke(tmp_path, version_runner=recording)
    toolchain = evidence["toolchain"]
    assert probes == ["python", "node", "rust"]
    assert toolchain["canonical"] == CANONICAL
    assert toolchain["expected"] == CANONICAL
    assert toolchain["actual"] == CANONICAL


@pytest.mark.parametrize(
    ("tool", "drifted"),
    [("python", "3.12.0"), ("node", "24.13.0"), ("rust", "1.93.0")],
)
def test_actual_toolchain_drift_is_refused_before_staging(
    tmp_path: Path, tool: str, drifted: str
) -> None:
    with pytest.raises(native.EvidenceError, match=rf"actual {tool} version"):
        _invoke(tmp_path, version_runner=_version_runner(**{tool: drifted}))
    assert not (tmp_path / "repo" / "artifacts").exists()


def test_actual_python_comes_from_the_running_interpreter() -> None:
    expected = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    assert native._run_version_command("python").strip() == expected
    source = (ROOT / "scripts/uat/write_native_build_evidence.py").read_text(
        encoding="utf-8"
    )
    assert "shell=True" not in source
    assert '("node", "--version")' in source
    assert '("rustc", "--version")' in source


def test_version_probes_use_fixed_argv_and_no_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    class Completed:
        returncode = 0
        stdout = "v24.13.1\n"

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return Completed()

    monkeypatch.setattr(native.subprocess, "run", fake_run)
    assert native._run_version_command("node") == "v24.13.1\n"
    assert native._run_version_command("rust") == "v24.13.1\n"
    assert [arguments for arguments, _ in calls] == [
        ("node", "--version"),
        ("rustc", "--version"),
    ]
    assert all(kwargs.get("shell", False) is False for _, kwargs in calls)


def test_version_probe_failure_is_refused_without_raw_output(tmp_path: Path) -> None:
    def broken(_tool: str) -> str:
        raise OSError("SECRET raw stdout/stderr payload")

    with pytest.raises(native.EvidenceError) as excinfo:
        _invoke(tmp_path, version_runner=broken)
    message = str(excinfo.value)
    assert "python version probe failed: OSError" in message
    assert "SECRET" not in message
    assert not (tmp_path / "repo" / "artifacts").exists()


def test_version_probe_exit_code_is_reported_without_raw_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Failed:
        returncode = 9
        stdout = "SECRET stdout payload"
        stderr = "SECRET stderr payload"

    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: Failed())
    fake = _version_runner()

    def runner(tool: str) -> str:
        if tool == "python":
            return fake(tool)
        return native._run_version_command(tool)

    with pytest.raises(native.EvidenceError) as excinfo:
        _invoke(tmp_path, version_runner=runner)
    message = str(excinfo.value)
    assert "node version probe failed with exit code 9" in message
    assert "SECRET" not in message
    assert not (tmp_path / "repo" / "artifacts").exists()


def test_malformed_actual_version_output_is_refused_without_echoing_it(
    tmp_path: Path,
) -> None:
    fake = _version_runner()

    def runner(tool: str) -> str:
        if tool == "python":
            return fake(tool)
        return "SECRET not-a-version"

    with pytest.raises(native.EvidenceError) as excinfo:
        _invoke(tmp_path, version_runner=runner)
    message = str(excinfo.value)
    assert "node version output is not a full X.Y.Z version" in message
    assert "SECRET" not in message
