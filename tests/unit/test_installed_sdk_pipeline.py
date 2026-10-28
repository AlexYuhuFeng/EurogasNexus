"""Focused tests for the installed-wheel SDK acceptance pipeline.

These are boundary tests, not a second copy of the acceptance implementation:
they exercise the path/source guards, child cleanup, output redaction, the six
HTTP-case record contract, the shared-wheel manifest, and the reusable workflow's
read-only shape.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


def _load_helper() -> ModuleType:
    """Load scripts/ci/check_installed_sdk.py without requiring a package marker."""

    helper_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_installed_sdk.py"
    )
    spec = importlib.util.spec_from_file_location(
        "check_installed_sdk_for_tests", helper_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helper = _load_helper()


@pytest.mark.parametrize("expected", ["a" * 40, "A" * 40])
def test_source_binding_reads_the_actual_head(tmp_path: Path, expected: str) -> None:
    calls = []

    def git_runner(root, arguments):
        calls.append((root, arguments))
        return subprocess.CompletedProcess(arguments, 0, "a" * 40 + "\n", "")

    assert helper._bind_source_commit(tmp_path, expected, git_runner=git_runner) == "a" * 40
    assert calls == [(tmp_path, ("rev-parse", "HEAD"))]


@pytest.mark.parametrize(
    ("expected", "actual", "returncode", "code"),
    [
        ("abc1234", "a" * 40, 0, "source_commit_invalid"),
        ("a" * 40, "b" * 40, 0, "source_commit_mismatch"),
        ("a" * 40, "not-a-commit", 0, "source_commit_invalid_response"),
        ("a" * 40, "", 1, "source_commit_unavailable"),
    ],
)
def test_source_binding_refuses_unproven_identity(
    tmp_path: Path, expected: str, actual: str, returncode: int, code: str
) -> None:
    def git_runner(root, arguments):
        return subprocess.CompletedProcess(arguments, returncode, actual, "private diagnostic")

    with pytest.raises(helper.AcceptanceFailure) as failure:
        helper._bind_source_commit(tmp_path, expected, git_runner=git_runner)
    assert failure.value.code == code
    assert "private diagnostic" not in str(failure.value)


def test_source_binding_refuses_dirty_tracked_files(tmp_path: Path) -> None:
    def git_runner(root, arguments):
        assert arguments == ("status", "--porcelain=v1", "--untracked-files=no")
        return subprocess.CompletedProcess(arguments, 0, " M src/changed.py\n", "")

    with pytest.raises(helper.AcceptanceFailure) as failure:
        helper._require_clean_tracked_worktree(tmp_path, git_runner=git_runner)
    assert failure.value.code == "tracked_worktree_dirty"


def test_work_dir_inside_checkout_is_rejected(tmp_path: Path) -> None:
    """The isolated smoke must not run from inside the source checkout."""

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    with pytest.raises(helper.AcceptanceFailure) as failure:
        helper._validate_work_root(checkout, str(checkout / "runtime"))
    assert failure.value.stage == "configuration"
    assert failure.value.code == "work_dir_inside_checkout"


def test_work_dir_beside_checkout_is_allowed(tmp_path: Path) -> None:
    """A sibling temp root is outside the checkout and remains valid."""

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    work = tmp_path / "runtime"
    assert helper._validate_work_root(checkout, str(work)) == work.resolve()


def test_installed_origin_rejects_source_and_outside_venv(tmp_path: Path) -> None:
    """Only a file physically inside the isolated venv is accepted."""

    checkout = tmp_path / "checkout"
    venv = tmp_path / "venv"
    installed = venv / "Lib" / "site-packages" / "eurogas_nexus_sdk" / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("", encoding="utf-8")
    assert helper._assert_installed_origin(installed, venv, checkout) == installed.resolve()

    source = (
        checkout
        / "packages"
        / "python-sdk"
        / "src"
        / "eurogas_nexus_sdk"
        / "__init__.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")
    with pytest.raises(helper.AcceptanceFailure) as source_failure:
        helper._assert_installed_origin(source, venv, checkout)
    assert source_failure.value.code == "sdk_imported_from_checkout"

    outside = tmp_path / "outside" / "__init__.py"
    outside.parent.mkdir()
    outside.write_text("", encoding="utf-8")
    with pytest.raises(helper.AcceptanceFailure) as outside_failure:
        helper._assert_installed_origin(outside, venv, checkout)
    assert outside_failure.value.code == "sdk_outside_expected_venv"


def test_smoke_origin_path_escape_is_rejected(tmp_path: Path) -> None:
    """A relative origin that climbs out of the venv cannot pass the smoke contract."""

    checkout = tmp_path / "checkout"
    venv = tmp_path / "venv"
    source = (
        checkout
        / "packages"
        / "python-sdk"
        / "src"
        / "eurogas_nexus_sdk"
        / "__init__.py"
    )
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")
    venv.mkdir()
    relative = Path("..") / source.relative_to(tmp_path)

    summary = {
        "status": "passed",
        "sdk_origin": relative.as_posix(),
        "sdk_version": "0.5.0",
        "python_version": "3.11.12",
        "module_count": 2,
        "typed_validation_case_count": 2,
        "typed_error_fields": ["billing_start", "valuation_date"],
    }
    with pytest.raises(helper.AcceptanceFailure) as failure:
        helper._validate_smoke_summary(
            summary,
            venv_prefix=venv,
            checkout_root=checkout,
            installed_origin=source,
        )
    assert failure.value.code == "sdk_imported_from_checkout"


def test_terminate_process_reaps_the_child_it_started() -> None:
    """Process cleanup uses the owned child handle, with no port/PID discovery."""

    process = subprocess.Popen(
        [sys.executable, "-I", "-c", "import time; time.sleep(60)"]
    )
    try:
        helper._terminate_process(process, grace_seconds=10.0)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_child_output_is_not_exposed_on_failure(tmp_path: Path) -> None:
    """A failed child may print a credential-shaped value; it must not reach output."""

    secret = "sk-installed-sdk-test-secret"
    command = [
        sys.executable,
        "-I",
        "-c",
        (
            "import sys; "
            f"print({secret!r}); "
            f"print({secret!r}, file=sys.stderr); "
            "raise SystemExit(9)"
        ),
    ]
    with pytest.raises(helper.AcceptanceFailure) as failure:
        helper._run_json_process(
            command,
            cwd=tmp_path,
            env=helper._base_env(),
            timeout=10,
            stage="smoke",
        )
    assert failure.value.code == "process_failed"
    report = helper._failure_report(
        failure.value.stage,
        failure.value.code,
        source_commit="a" * 40,
        wheel_sha256=None,
    )
    assert secret not in str(failure.value)
    assert secret not in json.dumps(report)


def test_failure_report_rejects_unsafe_source_commit() -> None:
    """Free-form dispatch text is not copied into the evidence record."""

    report = helper._failure_report(
        "configuration",
        "source_commit_invalid",
        source_commit="secret\nnot-a-sha",
        wheel_sha256=None,
    )
    assert report["source_commit"] == "unverified"
    assert "secret" not in json.dumps(report)


def _example_summary() -> dict[str, object]:
    """Return one passing six-case example record in the shape the helper consumes."""

    return {
        "status": "passed",
        "synthetic_inputs": True,
        "sdk_mode": "installed",
        "checks": [
            {"check": check_id, "status": "pass"}
            for check_id in sorted(helper.EXPECTED_CHECK_IDS)
        ],
    }


def test_example_contract_requires_six_typed_http_cases() -> None:
    """The installed example must report exactly the expected six HTTP checks."""

    counts = helper._validate_example_summary(_example_summary())
    assert counts == {
        "http_case_count": 6,
        "capacity_http_case_count": 3,
        "lng_http_case_count": 1,
        "refusal_case_count": 2,
    }

    source_summary = _example_summary()
    source_summary["sdk_mode"] = "source"
    with pytest.raises(helper.AcceptanceFailure) as source_failure:
        helper._validate_example_summary(source_summary)
    assert source_failure.value.code == "example_used_source_sdk"

    short_summary = _example_summary()
    short_summary["checks"] = list(short_summary["checks"])[:-1]
    with pytest.raises(helper.AcceptanceFailure) as short_failure:
        helper._validate_example_summary(short_summary)
    assert short_failure.value.code == "http_case_count_changed"


def _write_wheel(path: Path, *, include_backend: bool, include_sdk: bool) -> None:
    """Write a minimal wheel-shaped archive for manifest guard tests."""

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "eurogas_nexus-0.5.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: eurogas-nexus\nVersion: 0.5.0\n\n",
        )
        if include_backend:
            archive.writestr("eurogas_nexus/__init__.py", "")
        if include_sdk:
            archive.writestr("eurogas_nexus_sdk/__init__.py", "")


def test_shared_wheel_contains_backend_and_sdk(tmp_path: Path) -> None:
    """One distribution must carry both packages, never a separate SDK wheel."""

    good = tmp_path / "eurogas_nexus-0.5.0-py3-none-any.whl"
    _write_wheel(good, include_backend=True, include_sdk=True)
    helper._verify_shared_wheel(good)

    missing_sdk = tmp_path / "eurogas_nexus-0.5.0-sdk-missing.whl"
    _write_wheel(missing_sdk, include_backend=True, include_sdk=False)
    with pytest.raises(helper.AcceptanceFailure) as failure:
        helper._verify_shared_wheel(missing_sdk)
    assert failure.value.code == "missing_sdk_package"


def test_reusable_workflow_is_read_only_and_uses_canonical_pins() -> None:
    """Workflow contract: manual/reusable entry, x64 matrix, pinned read-only actions."""

    workflow_path = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "sdk-acceptance.yml"
    )
    text = workflow_path.read_text(encoding="utf-8")

    assert "workflow_call:" in text
    assert "workflow_dispatch:" in text
    assert "permissions:\n  contents: read" in text
    assert "pull_request_target" not in text
    assert "secrets." not in text
    assert "ubuntu-24.04" in text
    assert "windows-2025" in text
    assert "source_commit:" not in text
    assert "inputs.source_commit" not in text
    assert "if-no-files-found: error" in text
    assert "install_windows_canonical_python.ps1" in text
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in text
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text
    assert "requirements-build.lock" in text
    assert "requirements-runtime.lock" in text
    assert "--require-hashes" in text
    assert "--no-build-isolation" in text
    assert "--no-index --no-deps" in text
