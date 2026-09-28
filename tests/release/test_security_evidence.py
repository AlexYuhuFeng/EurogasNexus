"""G8 security-tests evidence producer contract tests.

G8 may only be evidenced by an actual pytest execution of the fixed
``tests/security`` suite: ``scripts/release/run_security_evidence.py`` runs the
suite itself and derives the status from the executed JUnit report plus the
structured selection evidence written by its minimal pytest plugin. These
tests drive the producer with injected runners and tiny real subprocess suites
for every failure shape (non-zero exit, empty suite, failures/errors, skips,
missing/malformed report, count mismatch, timeout, launch error, any
deselection), run the real suite end to end, and check that the shipped policy,
the generic writer and the release workflow wiring cannot bypass the executed
result.

The producer tests inject the git resolver (commit binding) and the workspace
factory (owner-only production temp dirs are not usable inside this sandboxed
test environment), so every commit SHA, run id and case name in this module is
a test-only fixture. No test dispatches a workflow, publishes, tags, touches a
database or uses a credential.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from scripts.release.run_security_evidence import (
    GATE_ID,
    JUNIT_REPORT_NAME,
    SELECTION_EVIDENCE_ENV,
    SELECTION_EVIDENCE_NAME,
    SELECTION_PLUGIN_MODULE,
    SELECTION_PLUGIN_SOURCE,
    SELECTION_SCHEMA,
    SUITE_DIRECTORY,
    TIMEOUT_SECONDS,
    GitState,
)
from scripts.release.run_security_evidence import main as producer_main
from scripts.release.run_security_evidence import run_pytest as producer_run_pytest
from scripts.release.validate_stable_release import evaluate_gates

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "release" / "run_security_evidence.py"
WRITER = ROOT / "scripts" / "release" / "write_gate_evidence.py"
POLICY_PATH = ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json"
EVIDENCE_NAME = "security-tests.json"
COMPANION_NAME = JUNIT_REPORT_NAME
RELEASE_SHA = "1" * 40
RUN_ID = "1234567890"
RUN_URL = f"https://github.com/AlexYuhuFeng/EurogasNexus/actions/runs/{RUN_ID}"
LOCAL_WORKFLOW = "run_release_dry_run.py"
LOCAL_ENVIRONMENT = "local-dry-run"
AUTO = object()


def shipped_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def junit_report(
    *,
    passed: int = 3,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
    declared_tests: int | None = None,
    declared_failures: int | None = None,
) -> str:
    """Build a pytest-shaped JUnit report for the injected runner fixtures."""

    cases = []
    for index in range(errors):
        cases.append(
            f'<testcase classname="tests.security.fixture" name="test_error_{index}">'
            '<error message="fixture error"/></testcase>'
        )
    for index in range(failures):
        cases.append(
            f'<testcase classname="tests.security.fixture" name="test_fail_{index}">'
            '<failure message="fixture failure"/></testcase>'
        )
    for index in range(skipped):
        cases.append(
            f'<testcase classname="tests.security.fixture" name="test_skip_{index}">'
            '<skipped type="pytest.skip" message="fixture skip"/></testcase>'
        )
    for index in range(passed):
        cases.append(f'<testcase classname="tests.security.fixture" name="test_pass_{index}"/>')
    total = len(cases) if declared_tests is None else declared_tests
    declared_failure_count = failures if declared_failures is None else declared_failures
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<testsuites name="pytest tests"><testsuite name="pytest" errors="{errors}" '
        f'failures="{declared_failure_count}" skipped="{skipped}" tests="{total}" '
        'time="0.1" timestamp="2026-09-28T00:00:00+00:00" hostname="fixture">'
        + "".join(cases)
        + "</testsuite></testsuites>"
    )


def case_count(report: str) -> int:
    return report.count("<testcase")


def selection_evidence(
    *,
    selected: int,
    deselected: int = 0,
    removed: int = 0,
    initial_items: int | None = None,
    schema: str = SELECTION_SCHEMA,
) -> dict:
    return {
        "schema": schema,
        "initial_items": (
            selected + max(deselected, removed) if initial_items is None else initial_items
        ),
        "selected": selected,
        "deselected": deselected,
        "net_removed_by_collection_hooks": removed,
        "keyword": "",
        "markexpr": "",
        "exitstatus": 0,
    }


class FakeGit:
    """Injectable git resolver: success, drifting HEAD, or an error state."""

    def __init__(
        self,
        *,
        heads: tuple[str, ...] = (RELEASE_SHA,),
        clean: bool = True,
        error: str = "",
    ) -> None:
        self.heads = list(heads)
        self.clean = clean
        self.error = error
        self.calls = 0

    def __call__(self) -> GitState:
        self.calls += 1
        head = self.heads[min(self.calls - 1, len(self.heads) - 1)]
        return GitState(head_sha=head, tracked_worktree_clean=self.clean, error=self.error)


class SandboxWorkspaces:
    """Sandbox-safe workspace factory: default-mode dirs the child can write."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.paths: list[Path] = []

    @contextmanager
    def __call__(self) -> Iterator[Path]:
        path = self.root / f"g8-workspace-{uuid.uuid4().hex[:8]}"
        path.mkdir()
        self.paths.append(path)
        yield path


def producer_arguments(output: Path, *, local: bool = False) -> list[str]:
    arguments = [
        "--commit-sha",
        RELEASE_SHA,
        "--workflow",
        LOCAL_WORKFLOW if local else "release.yml",
        "--job",
        "security-tests" if local else "validate",
        "--environment",
        LOCAL_ENVIRONMENT if local else "github-actions/linux/x64",
        "--run-id",
        RUN_ID,
        "--run-url",
        RUN_URL,
        "--output",
        str(output),
    ]
    if local:
        arguments.append("--local-dry-run")
    return arguments


def fake_runner(
    *,
    report: str | None,
    selection=AUTO,
    returncode: int = 0,
    calls: list[tuple[Path, Path, int]] | None = None,
):
    """Injected runner: writes the report/selection fixture and an exit code."""

    def runner(
        suite_dir: Path, report_path: Path, timeout_seconds: int
    ) -> subprocess.CompletedProcess:
        if calls is not None:
            calls.append((suite_dir, report_path, timeout_seconds))
        if report is not None:
            report_path.write_text(report, encoding="utf-8")
        payload = selection
        if payload is AUTO:
            payload = selection_evidence(selected=case_count(report or ""))
        if isinstance(payload, dict) or payload is None:
            text = None if payload is None else json.dumps(payload, sort_keys=True)
        else:
            text = str(payload)
        if text is not None:
            (report_path.parent / SELECTION_EVIDENCE_NAME).write_text(text, encoding="utf-8")
        return subprocess.CompletedProcess([], returncode, "fixture stdout", "fixture stderr")

    return runner


def run_producer(
    tmp_path: Path,
    *,
    report: str | None,
    selection=AUTO,
    returncode: int = 0,
    runner=None,
    suite_dir: Path | None = None,
    git: FakeGit | None = None,
    local: bool = False,
    output: Path | None = None,
) -> tuple[int, Path]:
    output = output or tmp_path / "release-evidence" / EVIDENCE_NAME
    execute = runner if runner is not None else fake_runner(
        report=report, selection=selection, returncode=returncode
    )
    exit_code = producer_main(
        producer_arguments(output, local=local),
        runner=execute,
        suite_dir=suite_dir,
        git_resolver=git or FakeGit(),
        workspace_factory=SandboxWorkspaces(tmp_path),
    )
    return exit_code, output


def load_envelope(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def companion_for(output: Path) -> Path:
    return output.with_name(COMPANION_NAME)


def row_for_g8(evidence_dir: Path, *, local: bool = False) -> tuple[dict, bool]:
    """Evaluate exactly the shipped G8 gate so row assertions are unambiguous."""

    policy = copy.deepcopy(shipped_policy())
    policy["gates"] = [gate for gate in policy["gates"] if gate["id"] == GATE_ID]
    context = {
        "schema_version": 1,
        "app_version": "0.5.0",
        "release_version": "v0.5.0-rc.4",
        "channel": "rc",
        "git_sha": RELEASE_SHA,
        "git_short_sha": RELEASE_SHA[:12],
        "git_ref": "refs/tags/v0.5.0-rc.4",
        "source_repository": "https://github.com/AlexYuhuFeng/EurogasNexus",
    }
    rows, failed = evaluate_gates(
        policy, evidence_dir, "rc", context=context, local_dry_run=local
    )
    return rows[0], failed


# ---------------------------------------------------------------------------
# The executed suite is the only source of a PASS
# ---------------------------------------------------------------------------


def test_pass_evidence_comes_from_the_executed_suite_report(tmp_path: Path) -> None:
    report_text = junit_report(passed=3)
    calls: list[tuple[Path, Path, int]] = []
    exit_code, output = run_producer(
        tmp_path, report=report_text, runner=fake_runner(report=report_text, calls=calls)
    )
    assert exit_code == 0

    # The runner executed the fixed suite and wrote into the scratch workspace,
    # not into the evidence directory.
    assert len(calls) == 1
    suite_dir, report_path, timeout_seconds = calls[0]
    assert suite_dir == SUITE_DIRECTORY
    assert report_path.name == COMPANION_NAME
    assert report_path.parent != output.parent
    assert timeout_seconds == TIMEOUT_SECONDS > 0

    # The executed JUnit XML is retained beside the envelope with a matching
    # hash, so the recorded digest stays auditable.
    companion = companion_for(output)
    assert companion.read_text(encoding="utf-8") == report_text

    envelope = load_envelope(output)
    assert envelope["schema_version"] == 2
    assert envelope["gate_id"] == GATE_ID
    assert envelope["status"] == "PASS"
    assert envelope["commit_sha"] == RELEASE_SHA
    assert envelope["subject"] == {"kind": "source", "digests": {}}
    assert envelope["producer"] == {
        "workflow": "release.yml",
        "job": "validate",
        "environment": "github-actions/linux/x64",
        "run_id": RUN_ID,
        "run_url": RUN_URL,
    }
    datetime.fromisoformat(envelope["produced_at_utc"])
    report = envelope["report"]
    assert report["report_type"] == "pytest-security-suite"
    assert report["suite"] == "tests/security"
    assert report["counts"] == {
        "tests": 3,
        "passed": 3,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert report["pytest_exit_code"] == 0
    assert report["timeout_seconds"] == TIMEOUT_SECONDS
    assert report["junit_report"] == COMPANION_NAME
    assert report["junit_report_sha256"] == hashlib.sha256(
        report_text.encode("utf-8")
    ).hexdigest()
    assert report["selection"] == selection_evidence(selected=3)

    # Source identity is recorded and clearly separated from crypto provenance.
    identity = report["source_identity"]
    assert identity["requested_commit_sha"] == RELEASE_SHA
    assert identity["head_sha_before"] == RELEASE_SHA
    assert identity["head_sha_after"] == RELEASE_SHA
    assert identity["head_matched_before"] is True
    assert identity["head_matched_after"] is True
    assert identity["tracked_worktree_clean_before"] is True
    assert identity["release_context"] is True
    assert identity["release_eligible"] is True
    assert "not signed attestation" in identity["basis"]


def test_producer_has_no_status_switch_and_no_report_input(tmp_path: Path) -> None:
    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    existing = tmp_path / "existing.xml"
    existing.write_text(junit_report(passed=3), encoding="utf-8")

    with pytest.raises(SystemExit) as refused:
        producer_main([*producer_arguments(output), "--status", "PASS"])
    assert refused.value.code == 2
    with pytest.raises(SystemExit) as reused:
        producer_main([*producer_arguments(output), "--junit-report", str(existing)])
    assert reused.value.code == 2
    assert not output.exists()


def test_non_zero_pytest_exit_is_explicit_fail_evidence(tmp_path: Path) -> None:
    exit_code, output = run_producer(
        tmp_path, report=junit_report(passed=3), returncode=1
    )
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert envelope["detail"] == "pytest exited with code 1"
    assert envelope["report"]["pytest_exit_code"] == 1


def test_report_failures_and_errors_are_fail_evidence_even_on_exit_zero(tmp_path: Path) -> None:
    report_text = junit_report(passed=1, failures=1, errors=1)
    exit_code, output = run_producer(tmp_path, report=report_text)
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert "1 failure(s) and 1 error(s)" in envelope["detail"]
    assert envelope["report"]["failed_cases"] == ["tests.security.fixture::test_fail_0"]
    assert envelope["report"]["error_cases"] == ["tests.security.fixture::test_error_0"]
    assert envelope["report"]["counts"] == {
        "tests": 3,
        "passed": 1,
        "failures": 1,
        "errors": 1,
        "skipped": 0,
    }


def test_empty_suite_is_fail_evidence(tmp_path: Path) -> None:
    exit_code, output = run_producer(tmp_path, report=junit_report(passed=0), returncode=5)
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert envelope["report"]["counts"]["tests"] == 0


def test_skipped_required_case_is_fail_evidence(tmp_path: Path) -> None:
    exit_code, output = run_producer(tmp_path, report=junit_report(passed=2, skipped=1))
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert "skipped 1 required case(s)" in envelope["detail"]
    assert envelope["report"]["skipped_cases"] == ["tests.security.fixture::test_skip_0"]


def test_missing_and_malformed_reports_are_fail_evidence(tmp_path: Path) -> None:
    # A stale companion from an earlier run must not survive a run that
    # produced no report: the envelope records no digest and no companion.
    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    output.parent.mkdir(parents=True)
    stale = companion_for(output)
    stale.write_text("<testsuites><testsuite/></testsuites>", encoding="utf-8")
    exit_code, output = run_producer(tmp_path, report=None, output=output)
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["detail"] == "pytest produced no JUnit XML report"
    assert envelope["report"]["junit_report"] == ""
    assert envelope["report"]["junit_report_sha256"] == ""
    assert not stale.exists()

    malformed = "<testsuites><testsuite"
    exit_code, output = run_producer(tmp_path, report=malformed)
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["detail"].startswith("JUnit XML report is malformed")
    # The raw bytes are retained for inspection and hashed as retained.
    companion = companion_for(output)
    assert companion.read_text(encoding="utf-8") == malformed
    assert envelope["report"]["junit_report_sha256"] == hashlib.sha256(
        malformed.encode("utf-8")
    ).hexdigest()

    exit_code, output = run_producer(tmp_path, report='{"status": "PASS"}')
    assert exit_code == 1
    assert load_envelope(output)["detail"].startswith("JUnit XML report is malformed")


def test_declared_counts_must_match_the_testcase_elements(tmp_path: Path) -> None:
    exit_code, output = run_producer(tmp_path, report=junit_report(passed=2, declared_tests=3))
    assert exit_code == 1
    assert "declares 3 tests but contains 2 testcase elements" in load_envelope(output)["detail"]

    exit_code, output = run_producer(
        tmp_path, report=junit_report(passed=1, failures=1, declared_failures=0)
    )
    assert exit_code == 1
    assert "declares 0 failures but contains 1 matching testcase elements" in (
        load_envelope(output)["detail"]
    )


def test_timeout_and_launch_errors_are_explicit_fail_evidence(tmp_path: Path) -> None:
    def timeout_runner(suite_dir: Path, report_path: Path, timeout_seconds: int):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=timeout_seconds)

    exit_code, output = run_producer(tmp_path, report=None, runner=timeout_runner)
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert envelope["detail"] == f"the security suite timed out after {TIMEOUT_SECONDS} seconds"

    def broken_runner(suite_dir: Path, report_path: Path, timeout_seconds: int):
        raise OSError("pytest is not installed")

    exit_code, output = run_producer(tmp_path, report=None, runner=broken_runner)
    assert exit_code == 1
    assert load_envelope(output)["detail"].startswith("pytest could not be launched")


def test_output_name_must_be_the_policy_evidence_file(tmp_path: Path) -> None:
    output = tmp_path / "release-evidence" / "not-the-policy-name.json"
    exit_code = producer_main(producer_arguments(output), runner=fake_runner(report=junit_report()))
    assert exit_code == 2
    assert not output.exists()


def test_default_runner_pins_the_fixed_command_and_plugin_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real runner is the fixed suite plus plugin, report and bound."""

    from scripts.release import run_security_evidence as producer

    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((list(command), dict(kwargs)))
        report_token = next(part for part in command if str(part).startswith("--junitxml="))
        report_path = Path(str(report_token).split("=", 1)[1])
        report_path.write_text(junit_report(passed=2), encoding="utf-8")
        (report_path.parent / SELECTION_EVIDENCE_NAME).write_text(
            json.dumps(selection_evidence(selected=2)), encoding="utf-8"
        )
        return subprocess.CompletedProcess(list(command), 0, "", "")

    monkeypatch.setattr(producer.subprocess, "run", fake_run)
    workspaces = SandboxWorkspaces(tmp_path)
    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    exit_code = producer_main(
        producer_arguments(output),
        runner=producer.run_pytest,
        git_resolver=FakeGit(),
        workspace_factory=workspaces,
    )
    assert exit_code == 0

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:3] == [sys.executable, "-m", "pytest"]
    assert Path(command[3]) == SUITE_DIRECTORY
    # A fixed command-line override and the environment guard together mean no
    # repository configuration or ambient pytest option can filter the suite.
    assert ["-o", "addopts="] == command[command.index("-o") : command.index("-o") + 2]
    assert "--import-mode=importlib" in command
    assert "-p" in command and "no:cacheprovider" in command
    assert SELECTION_PLUGIN_MODULE in command
    assert kwargs["timeout"] == TIMEOUT_SECONDS > 0
    assert kwargs["cwd"] == ROOT
    assert kwargs["check"] is False

    report_path = Path(command[-1].split("=", 1)[1])
    assert report_path.name == COMPANION_NAME
    assert report_path.parent == workspaces.paths[0]
    environment = kwargs["env"]
    assert str(report_path.parent) in environment["PYTHONPATH"].split(os.pathsep)
    assert environment[SELECTION_EVIDENCE_ENV] == str(
        report_path.parent / SELECTION_EVIDENCE_NAME
    )
    assert "PYTEST_ADDOPTS" not in environment
    assert "PYTEST_PLUGINS" not in environment
    # The plugin module written into the scratch workspace is the shipped one.
    assert (report_path.parent / f"{SELECTION_PLUGIN_MODULE}.py").read_text(
        encoding="utf-8"
    ) == SELECTION_PLUGIN_SOURCE


def test_secure_workspace_is_owner_only_and_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production scratch space uses mkdtemp (mode 0o700) and is removed."""

    from scripts.release import run_security_evidence as producer

    recorded: list[str] = []
    root = tmp_path / "sandbox-root"
    root.mkdir()

    def fake_mkdtemp(*, prefix: str) -> str:
        recorded.append(prefix)
        directory = root / f"{prefix}fixture"
        directory.mkdir()
        return str(directory)

    monkeypatch.setattr(producer.tempfile, "mkdtemp", fake_mkdtemp)
    with producer.secure_workspace() as workspace:
        assert workspace == root / f"{producer.WORKSPACE_PREFIX}fixture"
        assert workspace.is_dir()
    assert recorded == [producer.WORKSPACE_PREFIX]
    assert not workspace.exists()


# ---------------------------------------------------------------------------
# The executed suite must be the whole collected suite
# ---------------------------------------------------------------------------


def test_deselected_cases_are_fail_evidence(tmp_path: Path) -> None:
    report_text = junit_report(passed=1)
    exit_code, output = run_producer(
        tmp_path,
        report=report_text,
        selection=selection_evidence(selected=1, deselected=2, removed=2),
    )
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert "did not execute every collected case" in envelope["detail"]
    assert "deselected=2" in envelope["detail"]
    assert envelope["report"]["counts"]["tests"] == 1


def test_cases_removed_by_collection_hooks_are_fail_evidence(tmp_path: Path) -> None:
    report_text = junit_report(passed=1)
    exit_code, output = run_producer(
        tmp_path,
        report=report_text,
        selection=selection_evidence(selected=1, removed=2),
    )
    assert exit_code == 1
    assert "removed/changed by collection hooks=2" in load_envelope(output)["detail"]


def test_missing_malformed_or_inconsistent_selection_evidence_is_fail(tmp_path: Path) -> None:
    exit_code, output = run_producer(
        tmp_path, report=junit_report(passed=2), selection=None
    )
    assert exit_code == 1
    assert "no selection evidence" in load_envelope(output)["detail"]

    exit_code, output = run_producer(
        tmp_path, report=junit_report(passed=2), selection="{not json"
    )
    assert exit_code == 1
    assert load_envelope(output)["detail"].startswith("selection evidence is malformed")

    exit_code, output = run_producer(
        tmp_path,
        report=junit_report(passed=2),
        selection=selection_evidence(selected=2, schema="something-else"),
    )
    assert exit_code == 1
    assert "is not a eurogas-g8-selection-v1 document" in load_envelope(output)["detail"]

    exit_code, output = run_producer(
        tmp_path, report=junit_report(passed=2), selection=selection_evidence(selected=3)
    )
    assert exit_code == 1
    detail = load_envelope(output)["detail"]
    assert "records 3 selected case(s) but the JUnit report contains 2" in detail


def test_real_suite_deselection_is_refused_end_to_end(tmp_path: Path) -> None:
    """A collection hook that silently drops cases must never read as PASS."""

    suite = tiny_suite(
        tmp_path,
        "tiny-deselecting",
        "def test_allowed():\n    assert True\n\n"
        "def test_dropped_one():\n    assert True\n\n"
        "def test_dropped_two():\n    assert True\n",
        conftest=(
            "def pytest_collection_modifyitems(config, items):\n"
            "    items[:] = [item for item in items if 'allowed' in item.name]\n"
        ),
    )
    exit_code, output = run_producer(
        tmp_path, report=None, runner=producer_run_pytest, suite_dir=suite
    )
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert "removed/changed by collection hooks=2" in envelope["detail"]
    assert envelope["report"]["counts"]["tests"] == 1


def test_suite_pytest_ini_addopts_cannot_filter_the_run(tmp_path: Path) -> None:
    """The fixed -o addopts= override neutralises suite/repo pytest config."""

    suite = tiny_suite(
        tmp_path,
        "tiny-filtered-by-ini",
        "def test_one():\n    assert True\n\n"
        "def test_two():\n    assert True\n\n"
        "def test_three():\n    assert True\n",
        pytest_ini="[pytest]\naddopts = -k test_one\n",
    )
    exit_code, output = run_producer(
        tmp_path, report=None, runner=producer_run_pytest, suite_dir=suite
    )
    assert exit_code == 0, load_envelope(output)["detail"]
    envelope = load_envelope(output)
    assert envelope["status"] == "PASS"
    assert envelope["report"]["counts"]["tests"] == 3
    assert envelope["report"]["selection"]["deselected"] == 0


def test_environment_pytest_options_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    calls: list[tuple[Path, Path, int]] = []
    for variable in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        monkeypatch.setenv(variable, "-k one_test")
        exit_code = producer_main(
            producer_arguments(output),
            runner=fake_runner(report=junit_report(), calls=calls),
            suite_dir=tmp_path,
            git_resolver=FakeGit(),
            workspace_factory=SandboxWorkspaces(tmp_path),
        )
        assert exit_code == 2
        assert not output.exists()
        assert calls == []
        monkeypatch.delenv(variable)

    # Empty values are not a selection and must not break normal runs.
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    monkeypatch.setenv("PYTEST_PLUGINS", "")
    exit_code, output = run_producer(tmp_path, report=junit_report(passed=1))
    assert exit_code == 0


# ---------------------------------------------------------------------------
# The requested commit is bound to the checkout
# ---------------------------------------------------------------------------


def test_wrong_commit_sha_is_refused_before_execution(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path, int]] = []
    git = FakeGit(heads=("2" * 40,))
    exit_code, output = run_producer(
        tmp_path,
        report=junit_report(passed=3),
        runner=fake_runner(report=junit_report(passed=3), calls=calls),
        git=git,
    )
    assert exit_code == 1
    envelope = load_envelope(output)
    assert envelope["status"] == "FAIL"
    assert "is not the checked-out git HEAD" in envelope["detail"]
    assert envelope["report"]["source_identity"]["head_matched_before"] is False
    assert calls == [], "a mismatched checkout must not execute the suite"
    assert git.calls == 1


def test_release_context_requires_a_clean_tracked_worktree(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path, int]] = []
    exit_code, output = run_producer(
        tmp_path,
        report=junit_report(passed=3),
        runner=fake_runner(report=junit_report(passed=3), calls=calls),
        git=FakeGit(clean=False),
    )
    assert exit_code == 1
    envelope = load_envelope(output)
    assert "tracked worktree is dirty" in envelope["detail"]
    assert envelope["report"]["source_identity"]["release_eligible"] is False
    assert calls == [], "a dirty release checkout must not execute the suite"


def test_tracked_changes_during_run_refuse_release_evidence(tmp_path: Path) -> None:
    git = FakeGit()
    execute = fake_runner(report=junit_report(passed=3))

    def changing_runner(suite, report, timeout):
        result = execute(suite, report, timeout)
        git.clean = False
        return result

    code, output = run_producer(
        tmp_path, report=junit_report(passed=3), runner=changing_runner, git=git
    )
    envelope = load_envelope(output)
    assert code == 1
    assert envelope["status"] == "FAIL"
    assert "tracked worktree is dirty" in envelope["detail"]
    assert envelope["report"]["source_identity"]["release_eligible"] is False


def test_git_identity_failure_is_fail_evidence(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path, int]] = []
    exit_code, output = run_producer(
        tmp_path,
        report=junit_report(passed=3),
        runner=fake_runner(report=junit_report(passed=3), calls=calls),
        git=FakeGit(error="git rev-parse HEAD failed with code 128"),
    )
    assert exit_code == 1
    assert "source identity could not be verified" in load_envelope(output)["detail"]
    assert calls == []


def test_head_moving_during_the_run_is_fail_evidence(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path, int]] = []
    exit_code, output = run_producer(
        tmp_path,
        report=junit_report(passed=3),
        runner=fake_runner(report=junit_report(passed=3), calls=calls),
        git=FakeGit(heads=(RELEASE_SHA, "3" * 40)),
    )
    assert exit_code == 1
    envelope = load_envelope(output)
    assert "git HEAD changed while the security suite ran" in envelope["detail"]
    assert envelope["report"]["source_identity"]["head_matched_after"] is False
    assert len(calls) == 1


def test_local_dry_run_records_dirty_state_and_is_not_release_eligible(tmp_path: Path) -> None:
    exit_code, output = run_producer(
        tmp_path, report=junit_report(passed=2), git=FakeGit(clean=False), local=True
    )
    assert exit_code == 0
    envelope = load_envelope(output)
    assert envelope["status"] == "PASS"
    assert envelope["producer"]["workflow"] == LOCAL_WORKFLOW
    assert envelope["producer"]["environment"] == LOCAL_ENVIRONMENT
    identity = envelope["report"]["source_identity"]
    assert identity["release_context"] is False
    assert identity["release_eligible"] is False
    assert identity["tracked_worktree_clean_before"] is False
    assert "not release-eligible" in envelope["detail"]

    # The local-only identity is accepted by the maintainer dry-run validator
    # and rejected by strict validation, exactly like every dry-run envelope.
    row, failed = row_for_g8(output.parent, local=True)
    assert row["state"] == "PASS"
    assert failed is False
    row, failed = row_for_g8(output.parent)
    assert row["state"] == "FAIL"
    assert failed is True
    assert "local dry-run evidence cannot authorise a release" in row["detail"]


def test_local_dry_run_requires_the_local_only_producer_identity(tmp_path: Path) -> None:
    output = tmp_path / "release-evidence" / EVIDENCE_NAME

    # A release producer identity may never claim the dirty-tree relaxation.
    exit_code = producer_main(
        [*producer_arguments(output), "--local-dry-run"],
        runner=fake_runner(report=junit_report()),
        git_resolver=FakeGit(clean=False),
        workspace_factory=SandboxWorkspaces(tmp_path),
    )
    assert exit_code == 2
    assert not output.exists()

    # The local-only identity requires the explicit local dry-run mode.
    exit_code = producer_main(
        [arg for arg in producer_arguments(output, local=True) if arg != "--local-dry-run"],
        runner=fake_runner(report=junit_report()),
        git_resolver=FakeGit(),
        workspace_factory=SandboxWorkspaces(tmp_path),
    )
    assert exit_code == 2
    assert not output.exists()


# ---------------------------------------------------------------------------
# Real pytest subprocesses
# ---------------------------------------------------------------------------


def tiny_suite(
    tmp_path: Path,
    name: str,
    body: str,
    *,
    pytest_ini: str = "",
    conftest: str = "",
) -> Path:
    suite = tmp_path / name
    suite.mkdir()
    (suite / "test_tiny_security_case.py").write_text(body, encoding="utf-8")
    if pytest_ini:
        (suite / "pytest.ini").write_text(pytest_ini, encoding="utf-8")
    if conftest:
        (suite / "conftest.py").write_text(conftest, encoding="utf-8")
    return suite


def test_tiny_suites_execute_through_the_real_pytest_subprocess(tmp_path: Path) -> None:
    passing = tiny_suite(
        tmp_path,
        "tiny-pass",
        "def test_allowed():\n    assert True\n",
    )
    # No runner is injected here: the producer launches the real pytest
    # subprocess through its default runner.
    output = tmp_path / "pass-evidence" / EVIDENCE_NAME
    exit_code = producer_main(
        producer_arguments(output),
        suite_dir=passing,
        git_resolver=FakeGit(),
        workspace_factory=SandboxWorkspaces(tmp_path),
    )
    assert exit_code == 0
    envelope = load_envelope(output)
    assert envelope["status"] == "PASS"
    assert envelope["report"]["counts"] == {
        "tests": 1,
        "passed": 1,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert envelope["report"]["selection"]["selected"] == 1
    assert envelope["report"]["selection"]["deselected"] == 0
    assert envelope["report"]["selection"]["net_removed_by_collection_hooks"] == 0
    assert envelope["report"]["selection"]["initial_items"] == 1
    assert Path(envelope["report"]["suite"]).name == "tiny-pass"

    failing = tiny_suite(
        tmp_path,
        "tiny-fail",
        "import pytest\n\ndef test_denied():\n    assert False, 'fixture failure'\n"
        "\ndef test_skipped():\n    pytest.skip('fixture skip')\n",
    )
    failed_output = tmp_path / "fail-evidence" / EVIDENCE_NAME
    exit_code = producer_main(
        producer_arguments(failed_output),
        suite_dir=failing,
        git_resolver=FakeGit(),
        workspace_factory=SandboxWorkspaces(tmp_path),
    )
    assert exit_code == 1
    envelope = load_envelope(failed_output)
    assert envelope["status"] == "FAIL"
    assert envelope["report"]["counts"]["failures"] == 1
    assert envelope["report"]["counts"]["skipped"] == 1
    assert "test_denied" in envelope["report"]["failed_cases"][0]


def test_actual_security_suite_runs_and_produces_pass_evidence(tmp_path: Path) -> None:
    """The shipped tests/security suite is executed independently end to end."""

    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    exit_code = producer_main(
        producer_arguments(output),
        git_resolver=FakeGit(),
        workspace_factory=SandboxWorkspaces(tmp_path),
    )
    assert exit_code == 0, load_envelope(output)["detail"]
    envelope = load_envelope(output)
    counts = envelope["report"]["counts"]
    assert envelope["status"] == "PASS"
    assert envelope["report"]["suite"] == "tests/security"
    assert counts["tests"] >= 100, counts
    assert counts == {
        "tests": counts["tests"],
        "passed": counts["tests"],
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    selection = envelope["report"]["selection"]
    assert selection["selected"] == counts["tests"]
    assert selection["deselected"] == 0
    assert selection["net_removed_by_collection_hooks"] == 0
    assert selection["initial_items"] == counts["tests"]
    companion = companion_for(output)
    assert envelope["report"]["junit_report"] == COMPANION_NAME
    assert envelope["report"]["junit_report_sha256"] == hashlib.sha256(
        companion.read_bytes()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Policy, writer and workflow wiring cannot bypass the executed result
# ---------------------------------------------------------------------------


def test_shipped_policy_binds_g8_to_the_validate_producer_and_its_runner() -> None:
    policy = shipped_policy()
    gate = next(item for item in policy["gates"] if item["id"] == GATE_ID)
    assert gate["name"] == "Security tests"
    assert gate["type"] == "internal"
    assert gate["required_for"] == "all"
    assert gate["evidence"] == EVIDENCE_NAME
    assert gate["subject_kind"] == "source"
    assert gate["not_applicable_allowed"] is False
    assert gate["producers"] == ["validate", "dry-run"]
    assert gate["evidence_runner"] == "scripts/release/run_security_evidence.py"
    profile = policy["producers"]["validate"]
    assert profile["workflow"] == "release.yml"
    assert profile["job"] == "validate"
    assert profile["environment_prefix"] == "github-actions/"
    assert profile["require_run_identity"] is True


def test_producer_requires_its_policy_link(tmp_path: Path) -> None:
    policy = shipped_policy()
    for gate in policy["gates"]:
        if gate["id"] == GATE_ID:
            gate.pop("evidence_runner")
    unlinked = tmp_path / "policy.json"
    unlinked.write_text(json.dumps(policy), encoding="utf-8")

    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    exit_code = producer_main(
        [*producer_arguments(output), "--gate-policy", str(unlinked)],
        runner=fake_runner(report=junit_report()),
    )
    assert exit_code == 2
    assert not output.exists()


def test_generic_writer_refuses_the_executed_result_gate(tmp_path: Path) -> None:
    output = tmp_path / "security-tests.json"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITER),
            "--gate-id",
            GATE_ID,
            "--status",
            "PASS",
            "--detail",
            "status-only claim",
            "--commit-sha",
            RELEASE_SHA,
            "--workflow",
            "release.yml",
            "--job",
            "validate",
            "--environment",
            "github-actions/linux/x64",
            "--run-id",
            RUN_ID,
            "--run-url",
            RUN_URL,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "run_security_evidence.py" in result.stderr
    assert not output.exists()


def test_executed_evidence_passes_the_shipped_gate_validator(tmp_path: Path) -> None:
    exit_code, output = run_producer(tmp_path, report=junit_report(passed=3))
    assert exit_code == 0

    row, failed = row_for_g8(output.parent)
    assert row["state"] == "PASS"
    assert failed is False

    # The same executed result from an unauthorised producer identity is refused.
    envelope = load_envelope(output)
    envelope["producer"]["job"] = "assemble"
    output.write_text(json.dumps(envelope), encoding="utf-8")
    row, failed = row_for_g8(output.parent)
    assert row["state"] == "FAIL"
    assert failed is True
    assert "not an authorised producer" in row["detail"]

    # Local dry-run evidence is not the executed CI producer.
    envelope = load_envelope(output)
    envelope["producer"] = {
        "workflow": LOCAL_WORKFLOW,
        "job": "security-tests",
        "environment": LOCAL_ENVIRONMENT,
        "run_id": "",
        "run_url": "",
    }
    output.write_text(json.dumps(envelope), encoding="utf-8")
    row, failed = row_for_g8(output.parent)
    assert row["state"] == "FAIL"
    assert failed is True


def test_release_validate_job_runs_the_runner_before_the_evidence_upload() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["validate"]["steps"]
    names = [str(step.get("name", "")) for step in steps]

    runner_index = next(
        index
        for index, step in enumerate(steps)
        if "run_security_evidence.py" in str(step.get("run") or "")
    )
    tests_index = names.index("Tests")
    upload_index = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    )
    # The real suite runs after the existing tests and before the evidence
    # upload, so a failing or unevidenced security suite stops the job early
    # and the upload never sees a fabricated PASS.
    assert tests_index < runner_index < upload_index

    runner = steps[runner_index]
    assert runner["shell"] == "bash"
    assert "if" not in runner
    assert not runner.get("continue-on-error", False)
    run = runner["run"]
    assert f"release-assets/release-evidence/{EVIDENCE_NAME}" in run
    assert '--commit-sha "$GITHUB_SHA"' in run
    assert "--workflow release.yml --job validate" in run
    assert "--run-id \"$GITHUB_RUN_ID\"" in run
    assert "|| true" not in run
    assert "--status" not in run
    # The release workflow can never take the local dry-run path.
    assert "--local-dry-run" not in run
    assert "--allow-local-dry-run-evidence" not in run

    upload = steps[upload_index]
    assert upload["with"]["name"] == "release-validate-evidence"
    # The upload carries the whole evidence directory, so the retained JUnit
    # companion travels with the envelope whose hash names it.
    assert upload["with"]["path"] == "release-assets/release-evidence"
    assert upload["with"]["if-no-files-found"] == "error"

    # The assembled bundle merges every release-* artifact (including
    # release-validate-evidence) into release-assets, and the gate validator
    # reads the policy-declared file from release-assets/release-evidence.
    assemble_download = next(
        step
        for step in workflow["jobs"]["assemble"]["steps"]
        if str(step.get("with", {}).get("pattern", "")) == "release-*"
    )
    assert assemble_download["with"]["path"] == "release-assets"
    assert assemble_download["with"]["merge-multiple"] is True
    gate_step = next(
        step
        for step in workflow["jobs"]["publish-stable"]["steps"]
        if "validate_stable_release.py" in str(step.get("run") or "")
    )
    assert "--evidence-dir release-assets/release-evidence" in gate_step["run"]

    # The workflow contains exactly one G8 producer and never the generic
    # writer for G8: the executed runner is the only wiring (comment lines
    # describing it are not producer steps).
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert code.count("run_security_evidence.py") == 1
    assert "--gate-id G8" not in code


def test_shipped_cli_refuses_environment_pytest_options(tmp_path: Path) -> None:
    """The shipped entry point refuses ambient pytest selection fail-closed."""

    output = tmp_path / "release-evidence" / EVIDENCE_NAME
    environment = dict(os.environ)
    environment["PYTEST_ADDOPTS"] = "-k one_test"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *producer_arguments(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode == 2
    assert "PYTEST_ADDOPTS" in result.stderr
    assert not output.exists()


def test_shipped_cli_exposes_the_local_dry_run_mode(tmp_path: Path) -> None:
    """Guard the module import surface used by the local dry-run invocation."""

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "--local-dry-run" in completed.stdout


def test_report_companion_is_deterministic_beside_the_envelope(tmp_path: Path) -> None:
    """The companion file name is fixed; scratch state never leaks to output."""

    exit_code, output = run_producer(
        tmp_path,
        report=junit_report(passed=1),
        runner=fake_runner(report=junit_report(passed=1)),
    )
    assert exit_code == 0
    files = sorted(path.name for path in output.parent.iterdir())
    assert files == [EVIDENCE_NAME, COMPANION_NAME]
