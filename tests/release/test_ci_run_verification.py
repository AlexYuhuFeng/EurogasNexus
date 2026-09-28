"""PILOT-B2 same-SHA CI acceptance verification contract tests.

The release gate may not infer CI success from an evidence file, a URL or a
JSON metadata blob: G1 PASS is only valid when the read-only GitHub API reports
a completed, successful ``ci.yml`` run for the exact release commit whose
required jobs (including bilingual browser acceptance) all succeeded. These
tests drive the verification with a scripted fixture transport - never the
network - covering wrong repository/workflow/SHA, unsuccessful, incomplete,
skipped and missing jobs, pagination, stale run attempts, malformed and failed
API responses, forged copies of a valid envelope, and the writer/validator
round trip, and the re-run race where the attempt changes between the run read
and the attempt-pinned jobs read. Transport tests also prove that redirects are
refused fail-closed: no second request is issued, so the credential is never
forwarded to a ``Location`` host.

Every commit SHA, run id and job result here is a test fixture. No test
dispatches, tags, publishes or deploys anything.
"""

from __future__ import annotations

import copy
import email.message
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.release import ci_run_verification as ci_verification
from scripts.release.ci_run_verification import (
    ApiResponse,
    StdlibGitHubApi,
    api_from_environment,
    load_ci_acceptance_spec,
    verify_same_sha_ci_run,
)
from scripts.release.evidence_envelope import build_envelope
from scripts.release.validate_stable_release import evaluate_gates
from scripts.release.write_ci_run_evidence import main as writer_main

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"

# Test-only identity fixtures: never a real commit, run or release.
RELEASE_SHA = "1" * 40
FOREIGN_SHA = "2" * 40
REPOSITORY = "AlexYuhuFeng/EurogasNexus"
CI_RUN_ID = 36345939410
RELEASE_RUN_ID = "9999999999"
RELEASE_RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/{RELEASE_RUN_ID}"
WORKFLOW_PATH = ".github/workflows/ci.yml"

CI_PRODUCER = {
    "workflow": "release.yml",
    "job": "validate",
    "environment": "github-actions/linux/x64",
    "run_id": RELEASE_RUN_ID,
    "run_url": RELEASE_RUN_URL,
}
DRY_RUN_PRODUCER = {
    "workflow": "run_release_dry_run.py",
    "job": "ci-run",
    "environment": "local-dry-run",
    "run_id": "",
    "run_url": "",
}


def shipped_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def gate_in(policy: dict, gate_id: str) -> dict:
    return next(gate for gate in policy["gates"] if gate["id"] == gate_id)


def required_jobs() -> list[str]:
    return list(shipped_policy()["ci_acceptance"]["required_jobs"])


def release_context(sha: str = RELEASE_SHA) -> dict:
    return {
        "schema_version": 1,
        "app_version": "0.5.0",
        "release_version": "v0.5.0-rc.4",
        "channel": "rc",
        "git_sha": sha,
        "git_short_sha": sha[:12],
        "git_ref": "refs/tags/v0.5.0-rc.4",
        "source_repository": f"https://github.com/{REPOSITORY}",
    }


def ci_run(
    *,
    run_id: int = CI_RUN_ID,
    head_sha: str = RELEASE_SHA,
    path: str = WORKFLOW_PATH,
    event: str = "push",
    status: str = "completed",
    conclusion: Any = "success",
    attempt: int = 1,
) -> dict:
    return {
        "id": run_id,
        "path": path,
        "head_sha": head_sha,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "html_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
        "repository": {"full_name": REPOSITORY},
    }


def ci_job(name: str, *, status: str = "completed", conclusion: Any = "success") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def all_required_jobs() -> list[dict]:
    return [ci_job(name) for name in required_jobs()]


class FakeGitHubApi:
    """Scripted read-only GitHub API stand-in; never touches the network."""

    def __init__(
        self,
        *,
        runs: list[dict] | None = None,
        jobs: list[dict] | None = None,
        run: dict | None = None,
        failure: ApiResponse | None = None,
        malformed: bool = False,
    ) -> None:
        self.runs = [ci_run()] if runs is None else runs
        self.jobs = all_required_jobs() if jobs is None else jobs
        self.run = self.runs[0] if run is None else run
        self.failure = failure
        self.malformed = malformed
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, params: Mapping[str, str] | None = None) -> ApiResponse:
        params = dict(params or {})
        self.calls.append((path, params))
        if self.failure is not None:
            return self.failure
        if path.endswith("/runs") and "/workflows/" in path:
            if self.malformed:
                return ApiResponse(200, {"workflow_runs": "not-a-list"})
            return ApiResponse(
                200,
                {"total_count": len(self.runs), "workflow_runs": self._page(self.runs, params)},
            )
        # Only the attempt-specific jobs endpoint exists: the un-pinned
        # ``/runs/<id>/jobs?filter=latest`` endpoint is never served, so a
        # regression to it fails loudly instead of silently switching attempts.
        attempt_jobs = re.fullmatch(
            r"/repos/[^/]+/[^/]+/actions/runs/(\d+)/attempts/(\d+)/jobs", path
        )
        if attempt_jobs:
            if self.malformed:
                return ApiResponse(200, {"jobs": [{"name": 5}]})
            if int(attempt_jobs.group(1)) != int(self.run.get("id", 0)) or int(
                attempt_jobs.group(2)
            ) != int(self.run.get("run_attempt", 0)):
                return ApiResponse(404, error="GitHub API returned HTTP 404")
            return ApiResponse(
                200, {"total_count": len(self.jobs), "jobs": self._page(self.jobs, params)}
            )
        if re.fullmatch(r"/repos/[^/]+/[^/]+/actions/runs/\d+", path):
            if self.malformed:
                return ApiResponse(200, "not-an-object")
            requested = int(path.rsplit("/", 1)[-1])
            if requested != int(self.run.get("id", 0)):
                return ApiResponse(404, error="GitHub API returned HTTP 404")
            return ApiResponse(200, self.run)
        return ApiResponse(404, error=f"unexpected path {path}")

    @staticmethod
    def _page(items: list[dict], params: Mapping[str, str]) -> list[dict]:
        page = int(params.get("page", "1"))
        size = int(params.get("per_page", "100"))
        return items[(page - 1) * size : page * size]


class RerunDuringJobsApi(FakeGitHubApi):
    """Simulates a re-run starting while the attempt jobs are being read.

    The mutation is applied when the jobs endpoint has answered, i.e. between
    the verification's run read and its post-jobs recheck.
    """

    def __init__(self, mutation: dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mutation = mutation
        self.mutated = False

    def get(self, path: str, params: Mapping[str, str] | None = None) -> ApiResponse:
        response = super().get(path, params)
        if path.endswith("/jobs") and not self.mutated:
            self.mutated = True
            self.run = {**self.run, **self.mutation}
        return response


def declared_ci_run(
    *,
    run: dict | None = None,
    jobs: list[dict] | None = None,
) -> dict:
    run = ci_run() if run is None else run
    jobs = all_required_jobs() if jobs is None else jobs
    return {
        "ci_run": {
            "run_id": str(run["id"]),
            "run_attempt": run["run_attempt"],
            "run_url": run["html_url"],
            "workflow_path": run["path"],
            "head_sha": run["head_sha"],
            "event": run["event"],
            "jobs": jobs,
        }
    }


def ci_evidence_envelope(
    *,
    report: dict | None = None,
    producer: dict | None = None,
    status: str = "PASS",
    detail: str = "fixture",
) -> dict:
    envelope = build_envelope(
        gate_id="G1",
        status=status,
        commit_sha=RELEASE_SHA,
        detail=detail,
        subject={"kind": "source"},
        producer=CI_PRODUCER if producer is None else producer,
    )
    if report is not None:
        envelope["report"] = report
    return envelope


def write_evidence(tmp_path: Path, envelope: dict | None) -> Path:
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    if envelope is not None:
        (evidence / "ci-run.json").write_text(json.dumps(envelope), encoding="utf-8")
    return evidence


def gate_row(
    evidence: Path,
    *,
    api: FakeGitHubApi | None = None,
    factory=None,
    local: bool = False,
    context: dict | None = None,
) -> tuple[dict, bool]:
    """Evaluate only G1 so the row assertions are unambiguous."""

    policy = copy.deepcopy(shipped_policy())
    policy["gates"] = [gate_in(policy, "G1")]
    rows, failed = evaluate_gates(
        policy,
        evidence,
        "rc",
        context=release_context() if context is None else context,
        local_dry_run=local,
        ci_api_factory=(
            factory
            if factory is not None
            else (lambda: (api, "the test provided no API transport"))
        ),
    )
    return rows[0], failed


# ---------------------------------------------------------------------------
# Policy and CI-workflow contract
# ---------------------------------------------------------------------------


def test_policy_pins_the_trusted_repository_and_required_jobs() -> None:
    policy = shipped_policy()
    spec = load_ci_acceptance_spec(policy)
    assert spec.repository == REPOSITORY
    assert spec.workflow_path == WORKFLOW_PATH
    assert spec.event == "push"
    assert spec.required_jobs == tuple(required_jobs())
    assert gate_in(policy, "G1")["verification"] == ci_verification.CI_VERIFICATION_KIND
    assert "ci-verification" in gate_in(policy, "G1")["producers"]
    assert policy["producers"]["ci-verification"]["workflow"] == "release.yml"
    assert policy["producers"]["ci-verification"]["job"] == "validate"


def test_required_jobs_are_exactly_the_workflows_always_run_jobs() -> None:
    """Policy drift in either direction would silently weaken the gate."""

    workflow = yaml.safe_load(CI_WORKFLOW_PATH.read_text(encoding="utf-8"))
    always_run = set()
    for key, job in workflow["jobs"].items():
        condition = str(job.get("if", "")).strip()
        if condition.startswith("github.event_name =="):
            continue  # e.g. desktop packaging is pull-request-only
        always_run.add(str(job.get("name") or key))
    assert set(required_jobs()) == always_run


def test_policy_refuses_a_foreign_api_host_or_malformed_job_list() -> None:
    policy = shipped_policy()
    for mutation in (
        {"api_host": "evil.example"},
        {"repository": "someone"},
        {"repository": "someone/else/extra"},
        {"repository": ""},
        {"workflow_path": "ci.yml"},
        {"workflow_path": ".github/other.yml"},
        {"required_jobs": []},
        {"required_jobs": ["validate", "validate"]},
        {"max_pages": 0},
        {"request_timeout_seconds": 0},
        {"max_attempts": 0},
    ):
        mutated = copy.deepcopy(policy)
        mutated["ci_acceptance"].update(mutation)
        with pytest.raises(ValueError):
            load_ci_acceptance_spec(mutated)


def test_a_policy_repository_that_is_not_the_context_repository_blocks(tmp_path: Path) -> None:
    policy = copy.deepcopy(shipped_policy())
    policy["ci_acceptance"]["repository"] = "someone/else"
    policy["gates"] = [gate_in(policy, "G1")]
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    rows, failed = evaluate_gates(
        policy,
        evidence,
        "rc",
        context=release_context(),
        ci_api_factory=lambda: (FakeGitHubApi(), ""),
    )
    assert failed is True
    assert rows[0]["state"] == "FAIL"
    assert "trusted repository" in rows[0]["detail"]


# ---------------------------------------------------------------------------
# Verification outcomes
# ---------------------------------------------------------------------------


def test_valid_run_for_the_release_commit_passes(tmp_path: Path) -> None:
    api = FakeGitHubApi()
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "PASS", row["detail"]
    assert failed is False
    job_calls = [(path, params) for path, params in api.calls if path.endswith("/jobs")]
    assert job_calls
    for path, params in job_calls:
        # The attempt is pinned in the path; filter=latest (which can switch
        # attempts mid-verification) is never used.
        assert re.fullmatch(
            rf"/repos/{REPOSITORY}/actions/runs/{CI_RUN_ID}/attempts/1/jobs", path
        ), path
        assert "filter" not in params, params
    list_calls = [params for path, params in api.calls if path.endswith(("/runs", "/jobs"))]
    assert list_calls and all(params.get("per_page") == "100" for params in list_calls)
    run_reads = [
        path
        for path, _ in api.calls
        if re.fullmatch(rf"/repos/{REPOSITORY}/actions/runs/{CI_RUN_ID}", path)
    ]
    assert len(run_reads) == 2  # the initial read and the post-jobs recheck


@pytest.mark.parametrize(
    "mutation",
    [
        {"run_attempt": 2, "status": "in_progress", "conclusion": None},
        {"status": "queued", "conclusion": None},
        {"conclusion": "failure"},
        {"head_sha": FOREIGN_SHA},
    ],
)
def test_a_rerun_race_between_the_run_and_jobs_reads_blocks(
    tmp_path: Path, mutation: dict
) -> None:
    """A re-run that lands during the jobs read must invalidate the result."""

    api = RerunDuringJobsApi(mutation)
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True
    assert "changed while its jobs were being verified" in row["detail"]
    assert api.mutated is True


def test_a_rerun_race_in_the_writer_records_failure_not_pass(tmp_path: Path) -> None:
    output = tmp_path / "ci-run.json"
    api = RerunDuringJobsApi({"run_attempt": 2, "status": "in_progress", "conclusion": None})
    exit_code = writer_main(writer_arguments(output), api_factory=lambda: (api, ""))
    assert exit_code == 0
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["status"] == "FAIL"
    assert "report" not in envelope
    assert "changed while its jobs were being verified" in envelope["detail"]


@pytest.mark.parametrize(
    "report",
    [
        None,
        {},
        {"ci_run": "1234567890"},
        {"ci_run": {"run_id": "not-a-number"}},
        {
            "ci_run": {
                "run_id": str(CI_RUN_ID),
                "run_attempt": 1,
                "run_url": f"https://github.com/{REPOSITORY}/actions/runs/{CI_RUN_ID}",
                "workflow_path": WORKFLOW_PATH,
                "head_sha": RELEASE_SHA,
                "event": "push",
            }
        },
    ],
)
def test_undeclared_or_malformed_run_metadata_blocks(tmp_path: Path, report) -> None:
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=report))
    row, failed = gate_row(evidence, api=FakeGitHubApi())
    assert row["state"] == "FAIL"
    assert failed is True
    assert "report.ci_run" in row["detail"] or "declared CI run metadata" in row["detail"]


def test_declared_run_url_from_another_repository_is_refused(tmp_path: Path) -> None:
    forged = declared_ci_run()
    forged["ci_run"]["run_url"] = f"https://github.com/attacker/fork/actions/runs/{CI_RUN_ID}"
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=forged))
    row, failed = gate_row(evidence, api=FakeGitHubApi())
    assert row["state"] == "FAIL" and failed is True
    assert "run URL" in row["detail"]


@pytest.mark.parametrize(
    "run",
    [
        ci_run(path=".github/workflows/other.yml"),
        ci_run(head_sha=FOREIGN_SHA),
        ci_run(event="pull_request"),
    ],
)
def test_runs_for_another_workflow_commit_or_event_do_not_count(tmp_path: Path, run: dict) -> None:
    api = FakeGitHubApi(runs=[run], run=run)
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run(run=run)))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True
    assert "no .github/workflows/ci.yml push run exists" in row["detail"]


@pytest.mark.parametrize(
    ("status", "conclusion"),
    [
        ("completed", "failure"),
        ("in_progress", None),
        ("queued", None),
        ("completed", "cancelled"),
        ("completed", "timed_out"),
    ],
)
def test_unsuccessful_or_incomplete_runs_block(
    tmp_path: Path, status: str, conclusion: Any
) -> None:
    run = ci_run(status=status, conclusion=conclusion)
    api = FakeGitHubApi(runs=[run], run=run)
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run(run=run)))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True


def test_skipped_browser_acceptance_blocks(tmp_path: Path) -> None:
    jobs = all_required_jobs()
    for job in jobs:
        if job["name"] == "Browser acceptance (EN/ZH, 3 viewports)":
            job["conclusion"] = "skipped"
    api = FakeGitHubApi(jobs=jobs)
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True
    assert "Browser acceptance (EN/ZH, 3 viewports)" in row["detail"]
    assert "completed/skipped" in row["detail"]


def test_missing_and_duplicated_required_jobs_block(tmp_path: Path) -> None:
    for jobs in (
        [job for job in all_required_jobs() if job["name"] != "web-client-build"],
        [*all_required_jobs(), ci_job("validate")],
    ):
        api = FakeGitHubApi(jobs=jobs)
        evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
        row, failed = gate_row(evidence, api=api)
        assert row["state"] == "FAIL" and failed is True


def test_multiple_pages_of_runs_and_jobs_are_followed(tmp_path: Path) -> None:
    # The qualifying run and the required jobs both live on page two.
    runs = [ci_run(run_id=CI_RUN_ID + 200 - index) for index in range(120)]
    runs[-1] = ci_run()
    jobs = [ci_job(f"unrelated-{index}") for index in range(120)] + all_required_jobs()
    api = FakeGitHubApi(runs=runs, jobs=jobs, run=ci_run())
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "PASS", row["detail"]
    assert failed is False
    assert any(params.get("page") == "2" and path.endswith("/runs") for path, params in api.calls)
    assert any(params.get("page") == "2" and path.endswith("/jobs") for path, params in api.calls)


def test_a_stale_declared_run_attempt_blocks(tmp_path: Path) -> None:
    run = ci_run(attempt=2)
    api = FakeGitHubApi(runs=[run], run=run)
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run(run=ci_run())))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True
    assert "stale" in row["detail"]


def test_a_forged_copy_of_a_valid_envelope_cannot_pass(tmp_path: Path) -> None:
    """A copied file may claim an authorised producer; the API still decides."""

    # The claimed run simply does not exist for this commit.
    unknown = ci_run(run_id=424242)
    api = FakeGitHubApi(runs=[ci_run()], run=ci_run())
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run(run=unknown)))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True
    assert "424242" in row["detail"]

    # The claimed jobs disagree with the API's own job results.
    jobs = all_required_jobs()
    for job in jobs:
        if job["name"] == "validate":
            job["conclusion"] = "skipped"
    api = FakeGitHubApi(jobs=jobs)
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    row, failed = gate_row(evidence, api=api)
    assert row["state"] == "FAIL" and failed is True


def test_an_api_failure_or_absence_of_credentials_stays_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = write_evidence(tmp_path, ci_evidence_envelope(report=declared_ci_run()))
    for failure in (
        ApiResponse(404, error="GitHub API returned HTTP 404"),
        ApiResponse(403, error="GitHub API returned HTTP 403"),
        ApiResponse(0, error="GitHub API request failed (URLError)"),
    ):
        row, failed = gate_row(evidence, api=FakeGitHubApi(failure=failure))
        assert row["state"] == "FAIL" and failed is True
    row, failed = gate_row(evidence, api=FakeGitHubApi(malformed=True))
    assert row["state"] == "FAIL" and failed is True

    # No configured credential must not silently skip the API check.
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    api, unavailable = api_from_environment(load_ci_acceptance_spec(shipped_policy()))
    assert api is None and "GH_TOKEN" in unavailable
    row, failed = gate_row(evidence, factory=lambda: (None, unavailable))
    assert row["state"] == "FAIL" and failed is True
    assert "GH_TOKEN" in row["detail"]


def test_pagination_limit_blocks_instead_of_truncating(tmp_path: Path) -> None:
    policy = shipped_policy()
    policy["ci_acceptance"]["max_pages"] = 1
    spec = load_ci_acceptance_spec(policy)
    api = FakeGitHubApi(runs=[ci_run(run_id=CI_RUN_ID - index) for index in range(101)])
    verdict = verify_same_sha_ci_run(api, spec, head_sha=RELEASE_SHA)
    assert verdict.ok is False
    assert "pagination" in verdict.detail


def test_local_dry_run_flag_cannot_bypass_the_api_check(tmp_path: Path) -> None:
    failing_run = ci_run(conclusion="failure")
    api = FakeGitHubApi(runs=[failing_run], run=failing_run)
    evidence = write_evidence(
        tmp_path,
        ci_evidence_envelope(producer=DRY_RUN_PRODUCER, report=declared_ci_run()),
    )
    row, failed = gate_row(evidence, api=api, local=True)
    assert row["state"] == "FAIL" and failed is True
    assert "not successful" in row["detail"]

    # A pass claim without declared run metadata never falls back to a local
    # success either.
    row, failed = gate_row(
        write_evidence(tmp_path / "strict", ci_evidence_envelope(producer=DRY_RUN_PRODUCER)),
        api=FakeGitHubApi(),
    )
    assert row["state"] == "FAIL" and failed is True


def test_local_dry_run_pending_evidence_never_consults_the_api(tmp_path: Path) -> None:
    """Non-PASS evidence stays pending locally and makes no API call."""

    def never_called():
        raise AssertionError("the GitHub API must not be consulted for non-PASS evidence")

    envelope = ci_evidence_envelope(
        producer=DRY_RUN_PRODUCER,
        status="PENDING_EXTERNAL",
        detail="local dry-run is not a GitHub Actions run",
    )
    row, failed = gate_row(write_evidence(tmp_path, envelope), factory=never_called, local=True)
    assert row["state"] == "PENDING_EXTERNAL"
    assert failed is True


# ---------------------------------------------------------------------------
# Evidence writer
# ---------------------------------------------------------------------------


def writer_arguments(output: Path) -> list[str]:
    return [
        "--commit-sha",
        RELEASE_SHA,
        "--repo",
        REPOSITORY,
        "--workflow",
        "release.yml",
        "--job",
        "validate",
        "--environment",
        "github-actions/linux/x64",
        "--run-id",
        RELEASE_RUN_ID,
        "--run-url",
        RELEASE_RUN_URL,
        "--output",
        str(output),
    ]


def test_writer_records_a_pass_only_from_api_metadata(tmp_path: Path) -> None:
    output = tmp_path / "ci-run.json"
    exit_code = writer_main(writer_arguments(output), api_factory=lambda: (FakeGitHubApi(), ""))
    assert exit_code == 0
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["status"] == "PASS"
    assert envelope["gate_id"] == "G1"
    assert "Browser acceptance (EN/ZH, 3 viewports)" in envelope["detail"]
    assert envelope["commit_sha"] == RELEASE_SHA
    assert envelope["subject"] == {"kind": "source", "digests": {}}
    assert envelope["producer"] == {
        "workflow": "release.yml",
        "job": "validate",
        "environment": "github-actions/linux/x64",
        "run_id": RELEASE_RUN_ID,
        "run_url": RELEASE_RUN_URL,
    }
    assert envelope["report"]["ci_run"]["run_id"] == str(CI_RUN_ID)
    assert envelope["report"]["ci_run"]["run_attempt"] == 1
    assert envelope["report"]["ci_run"]["head_sha"] == RELEASE_SHA
    assert envelope["report"]["ci_run"]["jobs"] == [
        {"name": name, "conclusion": "success"} for name in required_jobs()
    ]

    # The written evidence is accepted by the validator using the same API.
    evidence = write_evidence(tmp_path, envelope)
    row, failed = gate_row(evidence, api=FakeGitHubApi())
    assert row["state"] == "PASS" and failed is False


def test_writer_records_failure_instead_of_a_fallback_pass(tmp_path: Path) -> None:
    output = tmp_path / "ci-run.json"
    run = ci_run(status="in_progress", conclusion=None)
    exit_code = writer_main(
        writer_arguments(output),
        api_factory=lambda: (FakeGitHubApi(runs=[run], run=run), ""),
    )
    assert exit_code == 0
    envelope = json.loads(output.read_text(encoding="utf-8"))
    assert envelope["status"] == "FAIL"
    assert "report" not in envelope
    row, failed = gate_row(write_evidence(tmp_path, envelope), api=FakeGitHubApi())
    assert row["state"] == "FAIL" and failed is True

    # Without a usable credential the file records PENDING_EXTERNAL, never PASS.
    exit_code = writer_main(
        writer_arguments(tmp_path / "pending.json"),
        api_factory=lambda: (None, "no read-only GitHub credential in GH_TOKEN/GITHUB_TOKEN"),
    )
    assert exit_code == 0
    pending = json.loads((tmp_path / "pending.json").read_text(encoding="utf-8"))
    assert pending["status"] == "PENDING_EXTERNAL"
    assert "GH_TOKEN" in pending["detail"]


def test_writer_refuses_a_repository_outside_the_policy(tmp_path: Path) -> None:
    output = tmp_path / "ci-run.json"
    arguments = writer_arguments(output)
    arguments[arguments.index(REPOSITORY)] = "attacker/fork"
    assert writer_main(arguments, api_factory=lambda: (FakeGitHubApi(), "")) == 2
    assert not output.exists()


def test_the_generic_writer_refuses_a_hand_written_ci_claim(tmp_path: Path) -> None:
    """Only the API-backed writer may produce G1 evidence."""

    from scripts.release.write_gate_evidence import main as generic_writer_main

    output = tmp_path / "ci-run.json"
    exit_code = generic_writer_main(
        [
            "--gate-id",
            "G1",
            "--status",
            "PASS",
            "--commit-sha",
            RELEASE_SHA,
            "--workflow",
            "release.yml",
            "--job",
            "validate",
            "--environment",
            "github-actions/linux/x64",
            "--output",
            str(output),
        ]
    )
    assert exit_code == 2
    assert not output.exists()


def test_release_workflow_grants_actions_read_only_to_the_gate_jobs() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    )
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    # The validate job writes G1's evidence from the read-only Actions API; the
    # publish jobs and the gate-first image-promotion jobs re-derive that claim
    # in their promotion gates. No other job may read the Actions API, and each
    # keeps exactly the permission it needs.
    assert jobs["validate"]["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["publish-preview-rc"]["permissions"] == {
        "contents": "write",
        "actions": "read",
    }
    assert jobs["publish-stable"]["permissions"] == {"contents": "write", "actions": "read"}
    for name, job in jobs.items():
        if name in {
            "validate",
            "publish-preview-rc",
            "publish-stable",
            "promote-image",
            "promote-image-stable",
        }:
            continue
        assert "actions" not in (job.get("permissions") or {}), name
    step = next(
        candidate
        for candidate in jobs["validate"]["steps"]
        if str(candidate.get("name", "")).startswith("Record same-SHA CI acceptance")
    )
    assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "write_ci_run_evidence.py" in step["run"]
    assert '--commit-sha "$GITHUB_SHA"' in step["run"]
    assert "release-assets/release-evidence/ci-run.json" in step["run"]
    assert "|| true" not in step["run"]
    assert "workflow_dispatch" not in step["run"]
    gate_step = next(
        candidate
        for candidate in jobs["publish-stable"]["steps"]
        if str(candidate.get("name", "")).startswith("Stable promotion gate")
    )
    assert gate_step["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "validate_stable_release.py" in gate_step["run"]
    assert "--reject-existing-tag" in gate_step["run"]
    preview_gate = next(
        candidate
        for candidate in jobs["publish-preview-rc"]["steps"]
        if str(candidate.get("name", "")).startswith("Preview/RC promotion gate")
    )
    assert preview_gate["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert "validate_stable_release.py" in preview_gate["run"]
    assert "--reject-existing-tag" not in preview_gate["run"]


# ---------------------------------------------------------------------------
# Transport bounds
# ---------------------------------------------------------------------------


class FakeHttpResponse:
    def __init__(self, payload: dict, *, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class FakeOpener:
    """Scripted opener stand-in (the injected transport seam); no network."""

    def __init__(self, responder) -> None:
        self.responder = responder
        self.requests: list[urllib.request.Request] = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return self.responder(request, timeout)


def test_transport_pins_the_host_and_never_echoes_the_credential() -> None:
    captured: dict[str, Any] = {}

    def responder(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["timeout"] = timeout
        return FakeHttpResponse({"ok": True})

    opener = FakeOpener(responder)
    api = StdlibGitHubApi("token-that-must-never-be-printed", timeout_seconds=7, opener=opener)
    response = api.get(f"/repos/{REPOSITORY}/actions/runs/{CI_RUN_ID}", {"per_page": "100"})
    assert response.status == 200
    assert captured["url"].startswith(f"https://api.github.com/repos/{REPOSITORY}/")
    assert "token-that-must-never-be-printed" not in captured["url"]
    assert captured["headers"]["authorization"] == "Bearer token-that-must-never-be-printed"
    assert captured["timeout"] == 7

    refused = api.get("https://evil.example/repos/x/y/actions/runs/1")
    assert refused.status == 0
    assert "outside the repository scope" in refused.error
    assert len(opener.requests) == 1  # the refused path never reached the transport

    def unauthorized(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    api = StdlibGitHubApi(
        "token-that-must-never-be-printed", opener=FakeOpener(unauthorized)
    )
    failed = api.get(f"/repos/{REPOSITORY}/actions/runs/{CI_RUN_ID}")
    assert failed.status == 401
    assert "token-that-must-never-be-printed" not in failed.error


def test_transport_retries_transient_failures_within_the_limit() -> None:
    attempts: list[int] = []

    def flaky(request, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)
        return FakeHttpResponse({"ok": True})

    sleeps: list[float] = []
    api = StdlibGitHubApi("token", max_attempts=3, sleep=sleeps.append, opener=FakeOpener(flaky))
    assert api.get(f"/repos/{REPOSITORY}/actions/runs/1").status == 200
    assert len(attempts) == 3 and len(sleeps) == 2

    def unreachable(request, timeout=None):
        attempts.append(1)
        raise urllib.error.URLError("connection refused")

    attempts.clear()
    api = StdlibGitHubApi(
        "token", max_attempts=3, sleep=sleeps.append, opener=FakeOpener(unreachable)
    )
    exhausted = api.get(f"/repos/{REPOSITORY}/actions/runs/1")
    assert exhausted.status == 0
    assert len(attempts) == 3
    assert "URLError" in exhausted.error


def test_transport_does_not_retry_client_errors() -> None:
    attempts: list[int] = []

    def unauthorized(request, timeout=None):
        attempts.append(1)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    api = StdlibGitHubApi(
        "token", max_attempts=3, sleep=lambda _: None, opener=FakeOpener(unauthorized)
    )
    response = api.get(f"/repos/{REPOSITORY}/actions/runs/1")
    assert response.status == 403
    assert len(attempts) == 1


class RedirectingHttpsHandler(urllib.request.HTTPSHandler):
    """Network stand-in that answers every request with a redirect."""

    def __init__(self, location: str, *, code: int = 302) -> None:
        super().__init__()
        self.location = location
        self.code = code
        self.requests: list[urllib.request.Request] = []

    def https_open(self, request):
        self.requests.append(request)
        headers = email.message.Message()
        headers["Location"] = self.location
        headers["Content-Length"] = "0"
        return RedirectHttpResponse(request.full_url, headers, code=self.code)


class RedirectHttpResponse:
    """Minimal 302 response object for the redirect path (no real socket)."""

    def __init__(self, url: str, headers, *, code: int = 302) -> None:
        self.url = url
        self.headers = headers
        self.code = code
        self.msg = "Found"

    def info(self):
        return self.headers

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return b""

    def close(self) -> None:
        pass


@pytest.mark.parametrize(
    ("code", "location"),
    [
        (302, "https://evil.example/collect"),  # cross-host redirect
        (302, f"https://api.github.com/repos/{REPOSITORY}/releases"),  # same host, out of scope
        (301, "https://evil.example/collect"),
        (307, f"https://api.github.com/repos/{REPOSITORY}/releases"),
    ],
)
def test_transport_refuses_a_redirect_without_a_second_request(code: int, location: str) -> None:
    """Any redirect must fail closed: no second request, no token forwarding."""

    handler = RedirectingHttpsHandler(location, code=code)
    api = StdlibGitHubApi("token-that-must-never-leave-the-pinned-host")
    # Exercise the real production opener (RefuseRedirects included) with only
    # its network leg replaced by the redirect fixture - no socket is opened.
    api._opener.handle_open["https"] = [handler]
    response = api.get(f"/repos/{REPOSITORY}/actions/runs/{CI_RUN_ID}")
    assert response.status == code
    assert "redirect" in response.error
    assert "token-that-must-never-leave-the-pinned-host" not in response.error
    # Exactly one request reached the wire: the Location target was never
    # contacted, so the Authorization header could not be forwarded to it.
    assert len(handler.requests) == 1
    sent = {key.lower(): value for key, value in handler.requests[0].header_items()}
    assert sent["authorization"] == "Bearer token-that-must-never-leave-the-pinned-host"


def test_default_transport_opener_refuses_redirects() -> None:
    api = StdlibGitHubApi("token")
    handlers = list(api._opener.handlers)
    assert any(isinstance(handler, ci_verification.RefuseRedirects) for handler in handlers)
    assert not any(type(handler) is urllib.request.HTTPRedirectHandler for handler in handlers)


def test_api_from_environment_prefers_a_read_only_token() -> None:
    spec = load_ci_acceptance_spec(shipped_policy())
    api, detail = api_from_environment(spec, environ={"GITHUB_TOKEN": "  "})
    assert api is None and "GH_TOKEN" in detail
    api, detail = api_from_environment(spec, environ={"GH_TOKEN": " ", "GITHUB_TOKEN": "t"})
    assert api is not None and detail == ""
