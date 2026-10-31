"""Contract tests for the internal weather-model numerical CI gate.

These tests are deliberately small and structural. They assert the properties a
reviewer depends on (exact wheel hash, read-only reusable workflow, pinned
actions, zero-skip enforcement, exact module identity, caller shape) rather than
mirroring the workflow line by line. The zero-skip parser is also executed
against synthetic JUnit XML so a workflow edit that turns skips, failures,
errors, or a testcase name into a pass fails here, not in a green run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "weather-model-acceptance.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
LOCK = ROOT / "requirements-scientific-ci.lock"
PG_SCRIPT = ROOT / "scripts" / "ci" / "run_postgres_ci.sh"
DOC = ROOT / "docs" / "engineering" / "WEATHER_MODEL_CI_CONTRACT.md"
REGISTRATION_DOC = (
    ROOT / "docs" / "engineering" / "ARCHIVE_LABEL_CI_REGISTRATION.md"
)

NUMPY_HASH = "8cba086a43d54ca804ce711b2a940b16e452807acebe7852ff327f1ecd49b0d4"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
UPLOAD_ARTIFACT = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
WEATHER_CALL = "./.github/workflows/weather-model-acceptance.yml"
# Eleven explicit focused modules plus the four actual-PostgreSQL modules. The
# workflow selects these files by name; it never runs a directory or a glob.
FOCUSED_MODULES = {
    "weather_core": "tests/unit/test_weather_demand.py",
    "weather_bridge": "tests/unit/test_weather_demand_inputs.py",
    "target_inputs": "tests/unit/test_demand_target_inputs.py",
    "demand_target_label_mapper": "tests/unit/test_demand_target_label_mapper.py",
    "weather_runtime": "tests/unit/test_weather_demand_runtime.py",
    "weather_operator": "tests/unit/test_weather_demand_operator_cli.py",
    "weather_prediction": "tests/unit/test_weather_demand_prediction_runtime.py",
    "weather_archive_persistence": "tests/unit/test_weather_archive_persistence.py",
    "weather_label_basis": "tests/unit/test_weather_demand_label_basis.py",
    "weather_forecast_contract": "tests/unit/test_weather_forecast_contract.py",
    "weather_db_bridge": "tests/db/test_ecmwf_weather_feature_bridge.py",
}
POSTGRES_MODULES = {
    "pg_weather_runtime": "tests/integration/test_weather_demand_runtime_postgres.py",
    "pg_weather_operator": "tests/integration/test_weather_demand_operator_postgres.py",
    "pg_weather_prediction": "tests/integration/test_weather_demand_prediction_runtime_postgres.py",
    "pg_weather_archive_persistence": (
        "tests/integration/test_weather_archive_persistence_postgres.py"
    ),
}
REQUIRED_MODULES = {**FOCUSED_MODULES, **POSTGRES_MODULES}
ARCHIVE_LABEL_MODULES = {
    "weather_archive_persistence",
    "weather_label_basis",
    "demand_target_label_mapper",
    "pg_weather_archive_persistence",
}


def _load(path: Path) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), f"{path} is not a YAML mapping"
    return document


def _triggers(document: dict) -> dict:
    # PyYAML's YAML 1.1 resolver turns the unquoted key ``on`` into True.
    triggers = document.get("on")
    if triggers is None:
        triggers = document.get(True)
    assert isinstance(triggers, dict), "workflow has no trigger mapping"
    return triggers


def _single_job(document: dict) -> dict:
    jobs = document.get("jobs")
    assert isinstance(jobs, dict) and len(jobs) == 1, "expected exactly one shared job"
    return next(iter(jobs.values()))


def _runs(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def _uses(job: dict) -> list[str]:
    return [str(step["uses"]) for step in job.get("steps", []) if "uses" in step]


def _gate_script() -> str:
    job = _single_job(_load(WORKFLOW))
    for step in job.get("steps", []):
        if "zero-skipped" in str(step.get("name", "")).lower():
            match = re.search(r"python - <<'PY'\n(.*?)\n\s*PY\b", str(step["run"]), re.S)
            assert match is not None, "zero-skip step does not expose its Python parser"
            return textwrap.dedent(match.group(1))
    pytest.fail("workflow has no zero-skipped JUnit step")


def _case(
    module: str,
    file: str,
    *,
    name: str = "test_ok",
    outcome: str | None = None,
) -> str:
    child = f"<{outcome}/>" if outcome else ""
    return (
        f'<testcase classname="{module}" name="{name}" '
        f'file="{file}">{child}</testcase>'
    )


def _suite(
    cases: list[str],
    *,
    skipped: int = 0,
    failures: int = 0,
    errors: int = 0,
) -> str:
    return (
        f'<testsuite tests="{len(cases)}" failures="{failures}" errors="{errors}" '
        f'skipped="{skipped}">{"".join(cases)}</testsuite>'
    )


def _valid_cases() -> list[str]:
    return [
        _case(path.removesuffix(".py").replace("/", "."), path)
        for path in REQUIRED_MODULES.values()
    ]


def _run_gate(
    tmp_path: Path, unit_xml: str, postgres_xml: str
) -> subprocess.CompletedProcess[str]:
    junit = tmp_path / "artifacts" / "weather-model-ci" / "junit"
    junit.mkdir(parents=True)
    (junit / "unit.xml").write_text(unit_xml, encoding="utf-8")
    (junit / "postgres.xml").write_text(postgres_xml, encoding="utf-8")
    environment = {
        **os.environ,
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REPOSITORY": "example/repository",
        "GITHUB_RUN_ID": "1",
        "GITHUB_RUN_ATTEMPT": "1",
        "RUNNER_OS": "Linux",
        "PYTHON_VERSION": "3.11.12",
    }
    return subprocess.run(
        [sys.executable, "-"],
        input=_gate_script(),
        text=True,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
    )


def test_science_lock_is_exactly_the_approved_numpy_wheel() -> None:
    text = LOCK.read_text(encoding="utf-8")
    requirements = re.findall(r"^[A-Za-z0-9_.-]+==", text, re.M)
    assert requirements == ["numpy=="], f"science lock must contain only NumPy: {requirements}"
    assert "numpy==2.3.5" in text
    assert (
        "numpy-2.3.5-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
        in text
    )
    assert f"--hash=sha256:{NUMPY_HASH}" in text
    assert text.count("--hash=sha256:") == 1
    assert not re.search(r"(https?://|git\+|file:|--index-url|--extra-index-url)", text)
    assert "INTERNAL CI-ONLY" in text
    assert "NOT a customer runtime" in text


def test_workflow_is_read_only_pinned_and_has_no_source_input() -> None:
    document = _load(WORKFLOW)
    text = WORKFLOW.read_text(encoding="utf-8")
    assert document["permissions"] == {"contents": "read"}
    assert "contents: write" not in text
    assert "permissions: write" not in text
    assert "pull-requests: write" not in text

    triggers = _triggers(document)
    assert {"workflow_call", "workflow_dispatch"} <= set(triggers)
    for trigger in ("workflow_call", "workflow_dispatch"):
        body = triggers.get(trigger) or {}
        assert "inputs" not in body, f"{trigger} must not accept a ref/source input"

    job = _single_job(document)
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] <= 20
    assert document["env"]["PYTHON_VERSION"] == "3.11.12"

    uses = _uses(job)
    assert set(uses) == {CHECKOUT, SETUP_PYTHON, UPLOAD_ARTIFACT}
    for action in uses:
        assert re.fullmatch(r"actions/[a-z-]+@[0-9a-f]{40}", action), action

    checkout = next(step for step in job["steps"] if step.get("uses") == CHECKOUT)
    assert checkout["with"]["ref"] == "${{ github.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    setup = next(step for step in job["steps"] if step.get("uses") == SETUP_PYTHON)
    assert setup["with"]["python-version"] == "${{ env.PYTHON_VERSION }}"
    assert "secrets:" not in text
    assert "ref: ${{ inputs." not in text


def test_workflow_uses_the_existing_pg_job_settings_and_exact_installs() -> None:
    job = _single_job(_load(WORKFLOW))
    postgres = job["services"]["postgres"]
    assert postgres["image"] == "postgres:16" or re.fullmatch(
        r"postgres:16@sha256:[0-9a-f]{64}", postgres["image"]
    )
    assert postgres["env"] == {
        "POSTGRES_USER": "nexus",
        "POSTGRES_PASSWORD": "nexus",
        "POSTGRES_DB": "nexus_test",
    }
    assert postgres["ports"] == ["5432:5432"]
    assert "pg_isready -U nexus" in postgres["options"]
    assert postgres["options"].count("--health-") >= 4
    assert "nexus_test" in job["env"]["RUNTIME_STORE_DATABASE_URL"]

    runs = _runs(job)
    assert (
        "python -m pip install --require-hashes -r requirements-build.lock -r requirements.lock"
        in runs
    )
    assert "python -m pip install --no-deps --no-build-isolation -e ." in runs
    assert (
        "python -m pip install --require-hashes --only-binary=:all: --no-deps "
        "-r requirements-scientific-ci.lock" in runs
    )
    assert "numpy.__version__" in runs and "2.3.5" in runs
    assert "bash scripts/ci/run_postgres_ci.sh" in runs
    assert "pytest.importorskip" not in runs


def test_junit_gate_accepts_complete_reports(tmp_path: Path) -> None:
    cases = _valid_cases()
    split = len(FOCUSED_MODULES)
    valid = _run_gate(tmp_path, _suite(cases[:split]), _suite(cases[split:]))
    assert valid.returncode == 0, valid.stdout + valid.stderr
    counts_path = tmp_path / "artifacts" / "weather-model-ci" / "counts.json"
    counts = json.loads(counts_path.read_text(encoding="utf-8"))
    assert counts["tests"] == len(REQUIRED_MODULES)
    assert counts["skipped"] == 0
    assert counts["failures"] == 0
    assert counts["errors"] == 0
    assert counts["missing_evidence"] == []
    assert counts["identity_conflicts"] == 0
    assert counts["result"] == "pass"


def test_junit_gate_rejects_skips_failures_errors_and_zero_cases(
    tmp_path: Path,
) -> None:
    cases = _valid_cases()
    split = len(FOCUSED_MODULES)
    unit_cases, postgres_cases = cases[:split], cases[split:]
    postgres_xml = _suite(postgres_cases)

    skipped_case = _case(
        "tests.unit.test_weather_demand",
        "tests/unit/test_weather_demand.py",
        outcome="skipped",
    )
    skipped = _run_gate(
        tmp_path / "skipped",
        _suite([skipped_case, *unit_cases[1:]], skipped=1),
        postgres_xml,
    )
    assert skipped.returncode != 0
    assert "skipped" in (skipped.stdout + skipped.stderr).lower()

    # pytest normally writes both the suite aggregate and the testcase child.
    # Either form alone must fail, so deleting the child cannot hide a skip.
    aggregate_skip = _run_gate(
        tmp_path / "aggregate-skip",
        _suite(unit_cases, skipped=1),
        postgres_xml,
    )
    assert aggregate_skip.returncode != 0
    assert "skipped" in (aggregate_skip.stdout + aggregate_skip.stderr).lower()

    failure_case = _case(
        "tests.unit.test_weather_demand",
        "tests/unit/test_weather_demand.py",
        outcome="failure",
    )
    failed = _run_gate(
        tmp_path / "failure",
        _suite([failure_case, *unit_cases[1:]], failures=1),
        postgres_xml,
    )
    assert failed.returncode != 0
    assert "failed" in (failed.stdout + failed.stderr).lower()

    error_case = _case(
        "tests.unit.test_weather_demand",
        "tests/unit/test_weather_demand.py",
        outcome="error",
    )
    errored = _run_gate(
        tmp_path / "error",
        _suite([error_case, *unit_cases[1:]], errors=1),
        postgres_xml,
    )
    assert errored.returncode != 0
    assert "errored" in (errored.stdout + errored.stderr).lower()

    aggregate_failure = _run_gate(
        tmp_path / "aggregate-failure",
        _suite(unit_cases, failures=1),
        postgres_xml,
    )
    assert aggregate_failure.returncode != 0
    assert "failed" in (aggregate_failure.stdout + aggregate_failure.stderr).lower()

    aggregate_error = _run_gate(
        tmp_path / "aggregate-error",
        _suite(unit_cases, errors=1),
        postgres_xml,
    )
    assert aggregate_error.returncode != 0
    assert "errored" in (aggregate_error.stdout + aggregate_error.stderr).lower()

    empty = _run_gate(tmp_path / "empty", _suite([]), _suite([]))
    assert empty.returncode != 0
    assert "zero" in (empty.stdout + empty.stderr).lower()


def test_junit_gate_uses_exact_module_identity_not_testcase_names(
    tmp_path: Path,
) -> None:
    script = _gate_script()
    assert 'case.get("name")' not in script
    assert 'case.get("classname")' in script
    assert 'case.get("file")' in script

    cases = _valid_cases()
    split = len(FOCUSED_MODULES)
    postgres_xml = _suite(cases[split:])

    # A name is not evidence. Even when every required path is written only in
    # testcase names, the gate must report every module as missing.
    name_only = _run_gate(
        tmp_path / "name-only",
        _suite(
            [
                _case(
                    "",
                    "",
                    name=(
                        f"{path}::"
                        f"{path.removesuffix('.py').replace('/', '.')}"
                    ),
                )
                for path in REQUIRED_MODULES.values()
            ]
        ),
        _suite([]),
    )
    assert name_only.returncode != 0
    name_only_output = (name_only.stdout + name_only.stderr).lower()
    assert "missing required module evidence" in name_only_output

    # The actual regression: one module is absent, but another testcase's name
    # contains its exact path. The concatenating parser accepted that spoof.
    missing_key = "weather_bridge"
    missing_path = REQUIRED_MODULES[missing_key]
    spoof_name = (
        f"{missing_path}::{missing_path.removesuffix('.py').replace('/', '.')}"
    )
    spoofed_unit = [
        _case(
            path.removesuffix(".py").replace("/", "."),
            path,
            name=spoof_name if key == "weather_core" else "test_ok",
        )
        for key, path in FOCUSED_MODULES.items()
        if key != missing_key
    ]
    missing = _run_gate(
        tmp_path / "missing",
        _suite(spoofed_unit),
        postgres_xml,
    )
    assert missing.returncode != 0
    missing_output = (missing.stdout + missing.stderr).lower()
    assert missing_key in missing_output

    # A longer path containing the required path is not the exact file identity.
    prefixed_unit = [
        _case(path.removesuffix(".py").replace("/", "."), path)
        for key, path in FOCUSED_MODULES.items()
        if key != missing_key
    ]
    prefixed = _run_gate(
        tmp_path / "prefixed",
        _suite([*prefixed_unit, _case("", f"vendor/{missing_path}")]),
        postgres_xml,
    )
    assert prefixed.returncode != 0
    assert missing_key in (prefixed.stdout + prefixed.stderr).lower()

    # A classname that names the missing module but a file that names another
    # module is inconsistent evidence, not a second provider of that module.
    conflicting_unit = []
    for key, path in FOCUSED_MODULES.items():
        if key == missing_key:
            continue
        classname = path.removesuffix(".py").replace("/", ".")
        if key == "weather_core":
            classname = missing_path.removesuffix(".py").replace("/", ".")
        conflicting_unit.append(_case(classname, path))
    conflict = _run_gate(
        tmp_path / "conflict",
        _suite(conflicting_unit),
        postgres_xml,
    )
    assert conflict.returncode != 0
    assert "conflicting classname/file identities" in (conflict.stdout + conflict.stderr).lower()


def test_callers_use_one_shared_definition_and_keep_existing_pipelines() -> None:
    for caller in (CI,):
        document = _load(caller)
        calls = [
            job
            for job in document["jobs"].values()
            if job.get("uses") == WEATHER_CALL
        ]
        assert len(calls) == 1, f"{caller.name} must call the shared workflow once"
        assert "with" not in calls[0]
        assert "secrets" not in calls[0]
        shared = {
            str(job["uses"])
            for job in document["jobs"].values()
            if "uses" in job
        }
        assert {
            WEATHER_CALL,
            "./.github/workflows/native-acceptance.yml",
            "./.github/workflows/sdk-acceptance.yml",
        } <= shared


def test_science_audit_is_added_to_the_existing_audit_job_only() -> None:
    document = _load(CI)
    audit = document["jobs"]["dependency-audit"]
    runs = _runs(audit)
    assert "python -m pip_audit -r requirements-runtime.lock" in runs
    assert "python -m pip_audit -r requirements.lock" in runs
    assert "python -m pip_audit -r requirements-scientific-ci.lock" in runs
    assert "audit_dependencies.py" in runs
    assert "--ignore-vuln" not in runs
    license_steps = [
        step
        for step in audit["steps"]
        if "License policy audit" in str(step.get("name", ""))
    ]
    assert license_steps
    assert "requirements-scientific-ci.lock" not in str(license_steps[0].get("run", ""))


def test_registered_pg_weather_actual_fit_modules_and_document_remain() -> None:
    pg = PG_SCRIPT.read_text(encoding="utf-8")
    assert "tests/integration/test_weather_demand_runtime_postgres.py" in pg
    assert "tests/integration/test_weather_demand_operator_postgres.py" in pg
    assert "tests/integration/test_weather_archive_persistence_postgres.py" in pg

    document = _single_job(_load(WORKFLOW))
    runs = _runs(document)
    pytest_runs = "\n".join(
        str(step.get("run", ""))
        for step in document.get("steps", [])
        if "python -m pytest" in str(step.get("run", ""))
    )
    selected = set(re.findall(r"tests/[A-Za-z0-9_./-]+\.py", pytest_runs))
    assert selected == set(REQUIRED_MODULES.values()), (
        "workflow must select exactly the explicit focused modules, not a "
        f"directory or glob: {sorted(selected)}"
    )
    assert runs.count("--junitxml") == 2

    script = _gate_script()
    for path in REQUIRED_MODULES.values():
        assert path in script, f"parser does not require {path}"

    doc = DOC.read_text(encoding="utf-8")
    assert "internal ci computation only" in doc.lower()
    assert "OPEN" in doc
    assert "not" in doc.lower() and "customer" in doc.lower()
    registration = REGISTRATION_DOC.read_text(encoding="utf-8")
    assert "internal numerical ci" in registration.lower()
    assert "not a hosted ci" in registration.lower()
    assert "windows skips are not numerical evidence" in registration.lower()
    for key, path in REQUIRED_MODULES.items():
        if key in ARCHIVE_LABEL_MODULES:
            assert path in registration, (
                f"archive/label registration document does not list {path}"
            )
        else:
            assert path in doc, f"contract document does not list {path}"
