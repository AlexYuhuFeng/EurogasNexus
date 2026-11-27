"""The parallel validate job still runs every check the single job ran, exactly once.

``validate`` in ``.github/workflows/ci.yml`` used to be one job running ruff, the repository
checks, ``pytest -q tests`` and the smokes in sequence (40-53 minutes). It is now the non-test
checks in one job, the suite in shards with parallel workers, and a ``validate`` job that keeps
the required check's name and passes only when every part passed. These tests keep that split
from losing a test directory, a check, or the meaning of the required check.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _ci() -> dict:
    return yaml.safe_load((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))


def test_the_test_shards_together_run_the_whole_suite() -> None:
    job = _ci()["jobs"]["validate-tests"]
    matrix = job["strategy"]["matrix"]["include"]
    assert job["strategy"]["fail-fast"] is False

    *named, rest = matrix
    named_paths = {path for entry in named for path in shlex.split(entry["paths"])}
    rest_args = shlex.split(rest["paths"])
    # The last shard is everything the others do not name, so a new directory is never orphaned.
    assert rest_args[0] == "tests"
    ignored = {arg.removeprefix("--ignore=") for arg in rest_args[1:]}
    assert all(arg.startswith("--ignore=") for arg in rest_args[1:])
    assert ignored == named_paths
    for path in named_paths:
        assert path.startswith("tests/") and (ROOT / path).is_dir(), path

    tests_step = next(step for step in job["steps"] if step.get("name") == "Tests")
    assert tests_step["run"] == "pytest -q -n auto $SHARD_PATHS"
    assert tests_step["env"] == {"SHARD_PATHS": "${{ matrix.paths }}"}


def test_every_non_test_check_runs_exactly_once() -> None:
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    checks_job = _ci()["jobs"]["validate-checks"]
    runs = [str(step.get("run", "")) for step in checks_job["steps"]]
    for command in (
        "ruff check .",
        "python scripts/ci/check_markdown_links.py",
        "python scripts/ci/check_config_contract.py",
        "python scripts/ci/generate_env_template.py --check",
        "python scripts/ci/check_toolchain_versions.py",
        "python scripts/ops/check_config.py --env-file scripts/ci/fixtures/release.env --strict",
        "python scripts/ops/load_smoke.py --requests 200 --concurrency 8 --p95-threshold-ms 1000",
        "bash scripts/ops/run_served_load_smoke.sh",
        "python -m eurogas_nexus.mcp.server",
        "from apps.api.main import app",
    ):
        assert sum(command in run for run in runs) == 1, command
        assert text.count(command) == 1, command
    # The checks run on docs-only changes too: the markdown link check above all.
    assert "if" not in checks_job


def test_validate_keeps_its_name_and_passes_only_when_every_part_passed() -> None:
    jobs = _ci()["jobs"]
    gate = jobs["validate"]
    assert gate["name"] == "validate"
    assert gate["if"] == "always()"
    assert set(gate["needs"]) == {
        "changes",
        "validate-checks",
        "validate-tests",
        "validate-docs-tests",
    }
    check = gate["steps"][0]["run"]
    assert 'test "$CHECKS" = "success"' in check
    assert 'test "$TESTS" = "success"' in check
    assert 'test "$CHANGES" = "success"' in check
    assert "|| true" not in check


def test_only_a_docs_only_pull_request_skips_the_heavy_jobs() -> None:
    jobs = _ci()["jobs"]
    scope = next(step for step in jobs["changes"]["steps"] if step.get("id") == "scope")
    assert 'test "$GITHUB_EVENT_NAME" = "pull_request"' in scope["run"]
    assert "git diff --name-only HEAD^1 HEAD" in scope["run"]
    assert "'^docs/|\\.md$'" in scope["run"]
    skipped = {
        name
        for name, job in jobs.items()
        if job.get("if") == "needs.changes.outputs.docs_only != 'true'"
    }
    assert skipped == {
        "validate-tests",
        "dependency-audit",
        "integration-postgres",
        "web-client-build",
        "browser-acceptance-build",
        "browser-acceptance-shard",
    }
    assert jobs["validate-docs-tests"]["if"] == "needs.changes.outputs.docs_only == 'true'"


def test_main_runs_are_never_cancelled_and_others_are_superseded() -> None:
    concurrency = _ci()["concurrency"]
    assert "github.ref == 'refs/heads/main' && github.sha || github.ref" in concurrency["group"]
    assert concurrency["cancel-in-progress"] == "${{ github.ref != 'refs/heads/main' }}"


def test_every_action_is_pinned_by_commit() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = re.search(r"uses:\s*([^\s#]+)", line)
            if not match or match.group(1).startswith("./"):
                continue
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", match.group(1)), (
                workflow.name,
                line,
            )


def test_release_validate_and_the_pre_push_gate_run_in_parallel_workers() -> None:
    release = yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))
    tests_step = next(
        step for step in release["jobs"]["validate"]["steps"] if step.get("name") == "Tests"
    )
    assert tests_step["run"] == "pytest -q -n auto tests"

    gate = (ROOT / "scripts" / "ci" / "pre_push_check.sh").read_text(encoding="utf-8")
    assert "python -m pytest -q -x -n auto -p no:cacheprovider tests/contract" in gate

    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    assert re.search(r"^pytest-xdist==\d", lock, re.MULTILINE)
    assert re.search(r"^execnet==\d", lock, re.MULTILINE)
