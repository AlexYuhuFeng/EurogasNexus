#!/usr/bin/env python
"""Record G8 security-test evidence from an executed pytest security suite.

The G8 envelope may only come from an actual run, so this script launches the
fixed suite with ``sys.executable -m pytest tests/security`` and a JUnit XML
report in a unique, owner-only scratch workspace, and derives the gate status
from that executed result:

* ``PASS`` only when pytest exited 0, the report proves a non-empty suite with
  zero failures, zero errors and zero skipped cases, and the structured
  selection evidence proves that no collected case was deselected or removed;
* ``FAIL`` evidence (and a non-zero exit) on a non-zero pytest exit, an empty
  suite, any failure/error/skip, a missing, malformed or count-inconsistent
  JUnit report, any deselection, a missing selection report, a timeout, or any
  other tool error.

The executed result cannot be declared or filtered:

* there is no ``--status`` argument and no flag that imports or reuses an
  existing report;
* a non-empty ``PYTEST_ADDOPTS``/``PYTEST_PLUGINS`` environment is refused, and
  the run pins ``-o addopts=`` (plus ``--import-mode=importlib``) so neither
  the environment nor repository configuration can silently filter the suite;
* a minimal pytest plugin records the collected/selected/deselected counts and
  catches cases removed by collection hooks, and the producer fails closed on
  any deselection or count drift - a partial suite is not an executed suite;
* ``write_gate_evidence.py`` refuses any gate that declares an
  ``evidence_runner``, which keeps this the only G8 producer in CI.

Source identity, not provenance: the requested commit is bound to the actual
git HEAD of the checkout before and after the run, and release-context runs
refuse a dirty tracked worktree. ``--local-dry-run`` records the dirty state
instead of attesting a clean SHA; it requires the local-only producer identity
declared in the gate policy, marks the evidence ``release_eligible: false`` and
is rejected by strict validation. This binding is checkout identity, not
cryptographic provenance: the envelope carries no digests and is not signed
attestation. The executed JUnit XML is retained beside the envelope as
``security-tests.junit.xml`` with a matching SHA-256, so the recorded hash
stays auditable after the scratch workspace is removed.

External gates (G15/G16) stay pending until real external evidence and an
authorised approval identity exist; this script can never satisfy them.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.evidence_envelope import (  # noqa: E402
    DEFAULT_GATE_POLICY,
    build_envelope,
    gate_entry,
    load_gate_policy,
    write_envelope,
)
from scripts.release.release_artifacts import sha256_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GATE_ID = "G8"
EVIDENCE_RUNNER = "scripts/release/run_security_evidence.py"
SUITE_DIRECTORY = ROOT / "tests" / "security"
# Bounded run: a hung suite must not consume the job's default timeout.
TIMEOUT_SECONDS = 1800
MAX_REPORTED_CASES = 20

# Scratch workspace identity: owner-only temporary directory (mode 0o700) that
# the pytest child process shares with the user that runs this producer.
WORKSPACE_PREFIX = "eurogas-nexus-security-evidence-"
JUNIT_REPORT_NAME = "security-tests.junit.xml"
SELECTION_EVIDENCE_NAME = "g8-selection.json"
SELECTION_PLUGIN_MODULE = "eurogas_g8_selection_plugin"
SELECTION_SCHEMA = "eurogas-g8-selection-v1"
SELECTION_EVIDENCE_ENV = "EUROGAS_G8_SELECTION_EVIDENCE"
# Fixed command-line override: repository/suite pytest configuration (addopts)
# must not be able to filter the suite. ``--import-mode=importlib`` mirrors the
# only addopt the repository configuration contributes.
ADDOPTS_OVERRIDE = "addopts="
IMPORT_MODE = "importlib"

# Minimal pytest plugin written into the scratch workspace and loaded with
# ``-p``: it records the selection structurally (no prose parsing) so the
# producer can prove that the executed suite was not filtered.
SELECTION_PLUGIN_SOURCE = '''"""Structured selection evidence for the G8 security-test producer.

Loaded by scripts/release/run_security_evidence.py with ``-p``. It writes the
collected/selected/deselected case counts and any cases removed by collection
hooks to the JSON file named by EUROGAS_G8_SELECTION_EVIDENCE. The producer
fails closed when the file is missing, malformed or reports deselection.
"""

from __future__ import annotations

import json
import os

import pytest

_STATE = {
    "schema": "eurogas-g8-selection-v1",
    "initial_items": 0,
    "selected": -1,
    "deselected": 0,
    "net_removed_by_collection_hooks": 0,
    "keyword": "",
    "markexpr": "",
    "exitstatus": -1,
}


def pytest_deselected(items) -> None:
    _STATE["deselected"] += len(items)


@pytest.hookimpl(wrapper=True)
def pytest_collection_modifyitems(config, items):
    _STATE["initial_items"] = len(items)
    result = yield
    _STATE["net_removed_by_collection_hooks"] = _STATE["initial_items"] - len(items)
    _STATE["keyword"] = str(getattr(config.option, "keyword", ""))
    _STATE["markexpr"] = str(getattr(config.option, "markexpr", ""))
    return result


def pytest_collection_finish(session) -> None:
    _STATE["selected"] = len(session.items)
    _write()


def pytest_sessionfinish(session, exitstatus) -> None:
    _STATE["exitstatus"] = int(exitstatus)
    _write()


def _write() -> None:
    path = os.environ.get("EUROGAS_G8_SELECTION_EVIDENCE", "")
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(_STATE, handle, indent=2, sort_keys=True)
'''

Runner = Callable[[Path, Path, int], subprocess.CompletedProcess]
WorkspaceFactory = Callable[[], AbstractContextManager[Path]]


class SecuritySuiteError(RuntimeError):
    """The executed suite did not produce a trustworthy executed-suite result."""


def _zero_counts() -> dict[str, int]:
    return {"tests": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0}


@dataclass(frozen=True)
class SuiteResult:
    """Counts and case identifiers parsed from the executed JUnit report."""

    counts: dict[str, int] = field(default_factory=_zero_counts)
    failed_cases: list[str] = field(default_factory=list)
    error_cases: list[str] = field(default_factory=list)
    skipped_cases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GitState:
    """The checked-out source identity the evidence must bind to."""

    head_sha: str = ""
    tracked_worktree_clean: bool = False
    error: str = ""


GitResolver = Callable[[], GitState]


@contextmanager
def secure_workspace() -> Iterator[Path]:
    """Owner-only scratch workspace for the executed suite.

    Production always uses ``tempfile.mkdtemp`` (mode 0o700) and a best-effort
    removal, so neither the creation nor the cleanup of scratch space can turn
    a real result into a crash or leave the report unauditable. Sandboxed test
    environments inject their own workspace factory through ``main`` instead of
    weakening these permissions.
    """

    directory = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def run_pytest(
    suite_dir: Path, report_path: Path, timeout_seconds: int
) -> subprocess.CompletedProcess:
    """Execute the fixed suite with a JUnit report and the selection plugin."""

    workspace = report_path.parent
    selection_path = workspace / SELECTION_EVIDENCE_NAME
    (workspace / f"{SELECTION_PLUGIN_MODULE}.py").write_text(
        SELECTION_PLUGIN_SOURCE, encoding="utf-8"
    )
    environment = os.environ.copy()
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTEST_PLUGINS", None)
    python_path = str(workspace)
    existing = environment.get("PYTHONPATH")
    if existing:
        python_path = f"{python_path}{os.pathsep}{existing}"
    environment["PYTHONPATH"] = python_path
    environment[SELECTION_EVIDENCE_ENV] = str(selection_path)

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(suite_dir),
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            SELECTION_PLUGIN_MODULE,
            "-o",
            ADDOPTS_OVERRIDE,
            f"--import-mode={IMPORT_MODE}",
            f"--junitxml={report_path}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
        env=environment,
    )


def resolve_git_state(root: Path = ROOT) -> GitState:
    """Read the checked-out HEAD and tracked-worktree state from git."""

    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        return GitState(error=f"git could not be executed: {error}")
    if head.returncode != 0:
        return GitState(
            error=f"git rev-parse HEAD failed with code {head.returncode}: "
            f"{head.stderr.strip()[:200]}"
        )
    head_sha = head.stdout.strip()
    try:
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        return GitState(head_sha=head_sha, error=f"git could not be executed: {error}")
    if status.returncode != 0:
        return GitState(
            head_sha=head_sha,
            error=f"git status failed with code {status.returncode}: "
            f"{status.stderr.strip()[:200]}",
        )
    return GitState(head_sha=head_sha, tracked_worktree_clean=not status.stdout.strip())


def _identity_problem(state: GitState, commit_sha: str, *, release_context: bool) -> str:
    """Return why the checkout cannot evidence ``commit_sha``, or ``""``."""

    if state.error:
        return f"the checked-out source identity could not be verified: {state.error}"
    if state.head_sha != commit_sha:
        return (
            f"the requested --commit-sha {commit_sha} is not the checked-out git HEAD "
            f"{state.head_sha!r}; evidence must bind the commit that was executed"
        )
    if release_context and not state.tracked_worktree_clean:
        return (
            "the tracked worktree is dirty; release-context evidence requires the "
            "committed source tree (--local-dry-run records the dirty state and is "
            "never release-eligible)"
        )
    return ""


def _local_only_identity(policy: dict, *, workflow: str, environment: str) -> bool:
    """True when the workflow/environment match a local-only producer profile."""

    for profile in (policy.get("producers") or {}).values():
        if not isinstance(profile, dict) or not profile.get("local_only"):
            continue
        prefix = str(profile.get("environment_prefix", ""))
        if workflow == str(profile.get("workflow", "")) and prefix:
            if environment.startswith(prefix):
                return True
    return False


def _declared_count(suite: ElementTree.Element, name: str) -> int:
    raw = suite.get(name)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise SecuritySuiteError(
            f"JUnit testsuite declares an invalid {name!r} count: {raw!r}"
        ) from None


def _case_id(case: ElementTree.Element) -> str:
    classname = case.get("classname") or ""
    name = case.get("name") or ""
    return f"{classname}::{name}" if classname else name


def inspect_junit_report(report_path: Path) -> SuiteResult:
    """Return the executed counts, refusing a missing/malformed/mislabelled report.

    A report is refused when the file is missing or unparseable, when it is not
    a pytest-style ``testsuites``/``testsuite`` document, or when a declared
    testsuite count disagrees with the ``testcase`` elements actually present -
    a mislabelled report must never read as an executed PASS.
    """

    if not report_path.is_file():
        raise SecuritySuiteError("pytest produced no JUnit XML report")
    try:
        root = ElementTree.parse(report_path).getroot()
    except ElementTree.ParseError as error:
        raise SecuritySuiteError(f"JUnit XML report is malformed: {error}") from error
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    else:
        raise SecuritySuiteError(
            f"JUnit XML root element is not testsuites/testsuite: {root.tag!r}"
        )
    if not suites:
        raise SecuritySuiteError("JUnit XML report declares no testsuite")

    result = SuiteResult(counts=_zero_counts())
    for suite in suites:
        cases = suite.findall("testcase")
        declared = {
            name: _declared_count(suite, name)
            for name in ("tests", "failures", "errors", "skipped")
        }
        if declared["tests"] != len(cases):
            raise SecuritySuiteError(
                f"JUnit testsuite declares {declared['tests']} tests but contains "
                f"{len(cases)} testcase elements"
            )
        outcomes = {
            "failures": [case for case in cases if case.find("failure") is not None],
            "errors": [case for case in cases if case.find("error") is not None],
            "skipped": [case for case in cases if case.find("skipped") is not None],
        }
        for name, observed in outcomes.items():
            if declared[name] != len(observed):
                raise SecuritySuiteError(
                    f"JUnit testsuite declares {declared[name]} {name} but contains "
                    f"{len(observed)} matching testcase elements"
                )
        result.counts["tests"] += declared["tests"]
        result.counts["failures"] += declared["failures"]
        result.counts["errors"] += declared["errors"]
        result.counts["skipped"] += declared["skipped"]
        result.failed_cases.extend(_case_id(case) for case in outcomes["failures"])
        result.error_cases.extend(_case_id(case) for case in outcomes["errors"])
        result.skipped_cases.extend(_case_id(case) for case in outcomes["skipped"])

    counted = result.counts["tests"] - result.counts["failures"] - result.counts["errors"]
    counted -= result.counts["skipped"]
    if counted < 0:
        raise SecuritySuiteError(
            "JUnit report outcome counts exceed the declared test count: "
            f"{result.counts}"
        )
    result.counts["passed"] = counted
    return result


def _selection_count(evidence: dict, name: str) -> int:
    value = evidence.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SecuritySuiteError(
            f"selection evidence {name!r} must be a non-negative integer: {value!r}"
        )
    return value


def inspect_selection_evidence(selection_path: Path, *, executed_tests: int) -> dict:
    """Return the structured selection evidence, refusing any partial suite.

    The plugin reports the collected/selected/deselected counts and any cases
    removed by collection hooks. A missing, malformed or inconsistent report,
    any deselection and any count drift against the JUnit report all refuse the
    result: an executed suite must be the whole collected suite.
    """

    if not selection_path.is_file():
        raise SecuritySuiteError(
            "pytest produced no selection evidence; the executed suite cannot be "
            "proven complete"
        )
    try:
        evidence = json.loads(selection_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SecuritySuiteError(f"selection evidence is malformed: {error}") from error
    except OSError as error:
        raise SecuritySuiteError(f"selection evidence could not be read: {error}") from error
    if not isinstance(evidence, dict) or evidence.get("schema") != SELECTION_SCHEMA:
        raise SecuritySuiteError(
            f"selection evidence is not a {SELECTION_SCHEMA} document"
        )
    selected = _selection_count(evidence, "selected")
    deselected = _selection_count(evidence, "deselected")
    removed = _selection_count(evidence, "net_removed_by_collection_hooks")
    if deselected or removed:
        raise SecuritySuiteError(
            "the security suite did not execute every collected case "
            f"(deselected={deselected}, removed/changed by collection hooks="
            f"{removed}); a partial suite is not accepted"
        )
    if selected != executed_tests:
        raise SecuritySuiteError(
            f"selection evidence records {selected} selected case(s) but the JUnit "
            f"report contains {executed_tests} testcase(s)"
        )
    return evidence


def _fail(message: str) -> int:
    print(f"run-security-evidence: {message}", file=sys.stderr)
    return 2


def _clear_stale_companion(companion: Path) -> None:
    """Best-effort removal of a companion no fresh run retained.

    The envelope only claims a digest it actually retained, so a leftover
    companion from an earlier run must never be mistaken for this run's report.
    """

    try:
        companion.unlink(missing_ok=True)
    except OSError:
        pass


def _report_diagnostic(completed: subprocess.CompletedProcess) -> None:
    """Print a bounded tail of the captured pytest output for the job log."""

    output = f"{completed.stdout or ''}{completed.stderr or ''}".strip()
    if output:
        print("run-security-evidence: pytest output (tail):", file=sys.stderr)
        print(output[-4000:], file=sys.stderr)


def _suite_label(suite: Path) -> str:
    """Record a repository-relative suite label when the suite is in this repo."""

    try:
        return suite.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return suite.as_posix()


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner | None = None,
    suite_dir: Path | None = None,
    git_resolver: GitResolver | None = None,
    workspace_factory: WorkspaceFactory | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--local-dry-run",
        action="store_true",
        help=(
            "record a local dry-run result: only the local-only producer identity "
            "declared in the gate policy is accepted, the tracked dirty state is "
            "recorded and the evidence is never release-eligible. Release CI never "
            "passes this flag."
        ),
    )
    parser.add_argument("--gate-policy", default=str(DEFAULT_GATE_POLICY))
    args = parser.parse_args(argv)

    polluted = sorted(
        name
        for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")
        if os.environ.get(name, "").strip()
    )
    if polluted:
        return _fail(
            f"{' and '.join(polluted)} is set in the environment; the security suite "
            "must execute with no external pytest options or plugins, so the "
            "evidence is refused rather than recorded from a filtered suite"
        )

    policy = load_gate_policy(args.gate_policy)
    gate = gate_entry(policy, GATE_ID)
    if gate is None:
        return _fail(f"gate {GATE_ID!r} is not declared in the gate policy")
    if gate.get("evidence_runner") != EVIDENCE_RUNNER:
        return _fail(
            f"gate {GATE_ID!r} does not declare {EVIDENCE_RUNNER!r} as its "
            "evidence_runner; the gate-to-runner link is required"
        )
    if gate.get("subject_kind") != "source":
        return _fail(f"gate {GATE_ID!r} must stay source-bound")
    if Path(args.output).name != str(gate.get("evidence", "")):
        return _fail(
            f"--output must be the policy evidence file name {gate.get('evidence')!r}"
        )

    local_identity = _local_only_identity(
        policy, workflow=args.workflow, environment=args.environment
    )
    if args.local_dry_run and not local_identity:
        return _fail(
            "--local-dry-run evidence must carry the local-only producer identity "
            "declared in the gate policy (the strict release validator rejects that "
            "identity, so local evidence can never authorise a release)"
        )
    if local_identity and not args.local_dry_run:
        return _fail(
            "the local-only producer identity requires --local-dry-run; local "
            "evidence is never recorded as release-eligible"
        )

    suite = Path(suite_dir) if suite_dir is not None else SUITE_DIRECTORY
    output = Path(args.output)
    companion = output.with_name(JUNIT_REPORT_NAME)
    execute = runner or run_pytest
    resolve_git = git_resolver or resolve_git_state
    create_workspace = workspace_factory or secure_workspace

    source_identity: dict[str, object] = {
        "requested_commit_sha": args.commit_sha,
        "head_sha_before": "",
        "head_sha_after": "",
        "head_matched_before": False,
        "head_matched_after": False,
        "tracked_worktree_clean_before": False,
        "release_context": not args.local_dry_run,
        "release_eligible": False,
        "basis": (
            "git rev-parse HEAD and git status in the local checkout; source "
            "identity only, not signed attestation or cryptographic provenance"
        ),
    }
    result = SuiteResult()
    selection: dict = {}
    exit_code = -1
    report_sha256 = ""
    completed: subprocess.CompletedProcess | None = None
    status = "FAIL"
    detail = ""

    try:
        before = resolve_git()
        source_identity["head_sha_before"] = before.head_sha
        source_identity["tracked_worktree_clean_before"] = before.tracked_worktree_clean
        source_identity["head_matched_before"] = bool(before.head_sha) and (
            before.head_sha == args.commit_sha
        )
        problem = _identity_problem(
            before, args.commit_sha, release_context=not args.local_dry_run
        )
        if problem:
            raise SecuritySuiteError(problem)
        try:
            with create_workspace() as workspace:
                workspace_path = Path(workspace)
                report_path = workspace_path / JUNIT_REPORT_NAME
                selection_path = workspace_path / SELECTION_EVIDENCE_NAME
                # Drop any companion from an earlier run before executing: the
                # envelope may only name a report this run actually produced.
                _clear_stale_companion(companion)
                try:
                    completed = execute(suite, report_path, TIMEOUT_SECONDS)
                    exit_code = int(completed.returncode)
                except subprocess.TimeoutExpired:
                    raise SecuritySuiteError(
                        f"the security suite timed out after {TIMEOUT_SECONDS} seconds"
                    ) from None
                except OSError as error:
                    raise SecuritySuiteError(
                        f"pytest could not be launched: {error}"
                    ) from error
                if report_path.is_file():
                    try:
                        companion.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(report_path, companion)
                        report_sha256 = sha256_file(companion)
                    except OSError as error:
                        raise SecuritySuiteError(
                            "the executed JUnit report could not be retained beside "
                            f"the evidence: {error}"
                        ) from error
                result = inspect_junit_report(companion)
                if exit_code != 0:
                    raise SecuritySuiteError(f"pytest exited with code {exit_code}")
                if result.counts["tests"] == 0:
                    raise SecuritySuiteError("the security suite executed no tests")
                if result.counts["failures"] or result.counts["errors"]:
                    raise SecuritySuiteError(
                        f"the security suite recorded {result.counts['failures']} "
                        f"failure(s) and {result.counts['errors']} error(s)"
                    )
                if result.counts["skipped"]:
                    raise SecuritySuiteError(
                        f"the security suite skipped {result.counts['skipped']} required "
                        "case(s); a skipped security case is not an executed case"
                    )
                selection = inspect_selection_evidence(
                    selection_path, executed_tests=result.counts["tests"]
                )
        except OSError as error:
            raise SecuritySuiteError(
                f"the security scratch workspace could not be created: {error}"
            ) from error
        after = resolve_git()
        source_identity["head_sha_after"] = after.head_sha
        if after.error:
            raise SecuritySuiteError(after.error)
        if after.head_sha != args.commit_sha:
            raise SecuritySuiteError(
                "git HEAD changed while the security suite ran "
                f"(before {source_identity['head_sha_before']!r}, after "
                f"{after.head_sha!r}); evidence must bind the executed commit "
                f"{args.commit_sha}"
            )
        source_identity["head_matched_after"] = True
        source_identity["tracked_worktree_clean_after"] = after.tracked_worktree_clean
        problem = _identity_problem(
            after, args.commit_sha, release_context=not args.local_dry_run
        )
        if problem:
            raise SecuritySuiteError(problem)
        source_identity["release_eligible"] = bool(
            not args.local_dry_run
            and source_identity["head_matched_before"]
            and source_identity["tracked_worktree_clean_before"]
        )
        status = "PASS"
        detail = (
            f"{_suite_label(suite)} executed: {result.counts['tests']} tests, "
            f"{result.counts['passed']} passed, 0 failed, 0 errors, 0 skipped"
        )
        if args.local_dry_run:
            detail = f"{detail} [local dry-run; not release-eligible]"
    except SecuritySuiteError as error:
        status = "FAIL"
        detail = str(error)
        if completed is not None:
            _report_diagnostic(completed)

    if not report_sha256:
        _clear_stale_companion(companion)
    report = {
        "report_type": "pytest-security-suite",
        "suite": _suite_label(suite),
        "pytest_exit_code": exit_code,
        "counts": result.counts,
        "failed_cases": result.failed_cases[:MAX_REPORTED_CASES],
        "error_cases": result.error_cases[:MAX_REPORTED_CASES],
        "skipped_cases": result.skipped_cases[:MAX_REPORTED_CASES],
        "selection": selection,
        "junit_report": companion.name if report_sha256 else "",
        "junit_report_sha256": report_sha256,
        "timeout_seconds": TIMEOUT_SECONDS,
        "source_identity": source_identity,
        "diagnostic": detail,
    }
    try:
        envelope = build_envelope(
            gate_id=GATE_ID,
            status=status,
            detail=detail,
            commit_sha=args.commit_sha,
            subject={"kind": "source", "digests": {}},
            producer={
                "workflow": args.workflow,
                "job": args.job,
                "environment": args.environment,
                "run_id": args.run_id,
                "run_url": args.run_url,
            },
        )
    except ValueError as error:
        return _fail(str(error))
    envelope["report"] = report

    try:
        output = write_envelope(args.output, envelope)
    except OSError as error:
        return _fail(f"evidence could not be written: {error}")
    print(
        json.dumps(
            {
                "ok": status == "PASS",
                "gate_id": GATE_ID,
                "status": status,
                "detail": detail,
                "counts": result.counts,
                "selection": selection,
                "output": str(output),
                "junit_report": companion.name if report_sha256 else "",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
