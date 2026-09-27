#!/usr/bin/env python
"""Read-only GitHub API verification of same-SHA CI acceptance (PILOT-B2).

PILOT-B gate evidence is schema-version 2 JSON written by the release run, so a
copy of an authorised envelope could claim any run identity. This module makes
the CI acceptance claim re-verifiable instead of self-declared: it reads the
GitHub Actions API and re-derives, for the exact release commit, that

* a ``ci.yml`` push run exists for the trusted repository and workflow path;
* the run's head SHA equals the release commit;
* the run is ``completed``/``success`` with no other same-SHA CI run pending or
  failed, and its latest attempt matches the declared attempt (a re-run that is
  pending, failed or newer than the evidence blocks that evidence);
* every required job - including the bilingual three-viewport browser
  acceptance - is present exactly once with ``completed``/``success``; a
  skipped or missing job never counts.

Re-run races fail closed: the jobs of the verified attempt are read from the
attempt-specific jobs endpoint (never ``filter=latest``, which can switch
attempt between the run read and the jobs read), and the run is re-read after
the jobs query; a changed attempt, status, conclusion or head SHA rejects the
result instead of accepting a half-verified attempt.

Trust rules:

* only ``api.github.com`` is contacted, only under ``/repos/<owner>/<repo>/``,
  and only for the repository declared in the gate policy - never a URL, run id
  or repository supplied by the evidence file;
* requests are read-only GETs: no dispatch, release, tag or deployment API is
  used;
* redirects are refused outright (custom no-redirect opener): ``urllib`` would
  otherwise re-send the ``Authorization`` header to an unvetted ``Location``,
  including on another host or outside the repository scope;
* missing, pending, failed, stale or unreachable state is a failed
  verification; there is no offline-success fallback, and tests inject
  fixture transports instead of a network or a "success" shortcut;
* the credential is read from the environment and is never written to output,
  evidence files or error messages.

What this does not claim: it binds the source commit's CI run, not acceptance
of a packaged artifact or image (that remains G19/install/upgrade evidence),
and the other release-run envelopes still carry self-declared producer
identity.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from scripts.release.evidence_envelope import FULL_SHA

API_HOST = "api.github.com"
CI_VERIFICATION_KIND = "same_sha_ci_run"
TOKEN_ENVIRONMENT_VARIABLES = ("GH_TOKEN", "GITHUB_TOKEN")
PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_PAGES = 10
RETRYABLE_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})

REPOSITORY_PATH = re.compile(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
WORKFLOW_PATH = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")


@dataclass(frozen=True)
class ApiResponse:
    """One read-only GitHub API response.

    ``error`` is a bounded human-readable detail; it never contains the
    credential, because headers and request bodies are deliberately not
    echoed.
    """

    status: int
    payload: Any = None
    error: str = ""


class GitHubApi(Protocol):
    """Minimal read-only transport the verification code depends on."""

    def get(self, path: str, params: Mapping[str, str] | None = None) -> ApiResponse: ...


class Opener(Protocol):
    """Minimal opener interface (the ``urllib.request.OpenerDirector`` shape)."""

    def open(self, request: urllib.request.Request, timeout: float) -> Any: ...


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Fail closed on every redirect; the ``Location`` header is untrusted.

    ``urllib``'s default redirect handling builds a new request that keeps the
    original headers - including ``Authorization`` - and sends it to the
    ``Location`` target, which is not limited to ``api.github.com`` or to the
    ``/repos/<owner>/<repo>/`` scope. Returning ``None`` here makes the opener
    raise ``HTTPError`` for the original URL instead, so a hostile or
    mis-configured redirect can never forward the credential or issue a second
    request.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_only_opener() -> urllib.request.OpenerDirector:
    """Build the production opener: standard handlers, redirects refused."""

    return urllib.request.build_opener(RefuseRedirects)


def _redirect_detail(status: int) -> str:
    return (
        f"GitHub API answered with a redirect (HTTP {status}); redirects are "
        "refused so the credential is never forwarded off the pinned host"
    )


class StdlibGitHubApi:
    """Read-only GitHub REST client with bounded timeout, retries and scope.

    The host is pinned to ``api.github.com`` and only ``/repos/<owner>/<repo>/``
    paths are requested, so a misconfigured policy or a hostile evidence value
    cannot redirect the release run at another endpoint. HTTP redirects of any
    kind are refused (``RefuseRedirects``) rather than followed, so the token
    is never re-sent to a ``Location`` host. Retries cover transient transport
    failures and GitHub 5xx/429 responses only; 3xx/401/403/404 fail
    immediately.
    """

    def __init__(
        self,
        token: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        opener: Opener | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._token = token or ""
        self._timeout_seconds = float(timeout_seconds)
        self._max_attempts = int(max_attempts)
        self._sleep = sleep
        self._opener = opener if opener is not None else read_only_opener()

    def get(self, path: str, params: Mapping[str, str] | None = None) -> ApiResponse:
        if REPOSITORY_PATH.match(path) is None:
            return ApiResponse(0, error="refused a GitHub API path outside the repository scope")
        url = f"https://{API_HOST}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(sorted(params.items()))}"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "eurogas-nexus-release-ci-verification",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        for attempt in range(1, self._max_attempts + 1):
            try:
                with self._opener.open(request, timeout=self._timeout_seconds) as response:
                    status = int(getattr(response, "status", 200))
                    body = response.read()
            except urllib.error.HTTPError as error:
                status = int(getattr(error, "code", 0))
                if 300 <= status < 400:
                    # A redirect (e.g. the 302 raised by RefuseRedirects) must
                    # never be retried or followed.
                    return ApiResponse(status, error=_redirect_detail(status))
                if status in RETRYABLE_HTTP_STATUSES and attempt < self._max_attempts:
                    self._sleep(min(2.0 * attempt, 5.0))
                    continue
                return ApiResponse(status, error=f"GitHub API returned HTTP {status}")
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt < self._max_attempts:
                    self._sleep(min(2.0 * attempt, 5.0))
                    continue
                return ApiResponse(0, error=f"GitHub API request failed ({type(error).__name__})")
            if 300 <= status < 400:
                # Defence in depth: even a custom opener that surfaced a 3xx
                # response must not be treated as a usable API answer.
                return ApiResponse(status, error=_redirect_detail(status))
            if status != 200:
                return ApiResponse(status, error=f"GitHub API returned HTTP {status}")
            try:
                payload = json.loads(body.decode("utf-8")) if body else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                return ApiResponse(status, error="GitHub API returned a non-JSON response")
            return ApiResponse(status, payload)
        return ApiResponse(0, error="GitHub API request failed")


@dataclass(frozen=True)
class CiAcceptanceSpec:
    """The policy-declared contract a same-SHA CI acceptance claim must meet."""

    repository: str
    workflow_path: str
    event: str
    required_jobs: tuple[str, ...]
    max_pages: int
    request_timeout_seconds: float
    max_attempts: int


@dataclass(frozen=True)
class CiRunVerdict:
    """Outcome of one same-SHA CI verification.

    ``run`` and ``jobs`` are populated only from API responses, and only after
    every check passed, so they are the only values allowed into evidence.
    """

    ok: bool
    detail: str
    run: dict[str, Any] | None = None
    jobs: tuple[dict[str, Any], ...] = ()


def parse_repository(value: object) -> str:
    """Return a validated ``owner/name`` repository, refusing anything else."""

    text = str(value or "").strip()
    if REPOSITORY.fullmatch(text) is None:
        raise ValueError(f"repository must be owner/name: {value!r}")
    return text


def repository_from_source_url(url: object) -> str | None:
    """Return ``owner/name`` for a github.com repository URL, else ``None``."""

    text = str(url or "").strip().rstrip("/")
    prefix = "https://github.com/"
    if not text.startswith(prefix):
        return None
    candidate = text[len(prefix) :].removesuffix(".git")
    return candidate if REPOSITORY.fullmatch(candidate) else None


def load_ci_acceptance_spec(policy: Mapping[str, Any]) -> CiAcceptanceSpec:
    """Read and validate the ``ci_acceptance`` policy section.

    Raises ``ValueError`` with a precise reason for anything that would let the
    verification reach a host or repository other than the trusted one.
    """

    spec = policy.get("ci_acceptance")
    if not isinstance(spec, Mapping):
        raise ValueError("gate policy does not declare a ci_acceptance section")
    api_host = str(spec.get("api_host", "")).strip()
    if api_host != API_HOST:
        raise ValueError(f"ci_acceptance api_host must be {API_HOST!r}: {spec.get('api_host')!r}")
    repository = parse_repository(spec.get("repository"))
    workflow_path = str(spec.get("workflow_path", "")).strip()
    if WORKFLOW_PATH.fullmatch(workflow_path) is None:
        raise ValueError(
            "ci_acceptance workflow_path must be a .github/workflows/*.yml path: "
            f"{spec.get('workflow_path')!r}"
        )
    event = str(spec.get("event", "push")).strip()
    if not event:
        raise ValueError("ci_acceptance event must be a non-empty string")
    raw_jobs = spec.get("required_jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise ValueError("ci_acceptance required_jobs must be a non-empty list")
    required_jobs: list[str] = []
    for entry in raw_jobs:
        name = str(entry or "").strip()
        if not name:
            raise ValueError("ci_acceptance required_jobs entries must be non-empty strings")
        if name in required_jobs:
            raise ValueError(f"ci_acceptance required_jobs repeats {name!r}")
        required_jobs.append(name)
    max_pages = spec.get("max_pages", DEFAULT_MAX_PAGES)
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or not 1 <= max_pages <= 50:
        raise ValueError(f"ci_acceptance max_pages must be 1..50: {max_pages!r}")
    timeout = spec.get("request_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout_seconds = float(timeout)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"ci_acceptance request_timeout_seconds is not a number: {error}"
        ) from error
    if not 0 < timeout_seconds <= 120:
        raise ValueError(f"ci_acceptance request_timeout_seconds must be 0..120: {timeout!r}")
    attempts = spec.get("max_attempts", DEFAULT_MAX_ATTEMPTS)
    if not isinstance(attempts, int) or isinstance(attempts, bool) or not 1 <= attempts <= 10:
        raise ValueError(f"ci_acceptance max_attempts must be 1..10: {attempts!r}")
    return CiAcceptanceSpec(
        repository=repository,
        workflow_path=workflow_path,
        event=event,
        required_jobs=tuple(required_jobs),
        max_pages=max_pages,
        request_timeout_seconds=timeout_seconds,
        max_attempts=attempts,
    )


def api_from_environment(
    spec: CiAcceptanceSpec, *, environ: Mapping[str, str] | None = None
) -> tuple[StdlibGitHubApi | None, str]:
    """Build the production (network) transport from the environment.

    Returns ``(None, detail)`` when no read token is configured; the caller must
    treat that as unavailable verification, never as success.
    """

    environment = os.environ if environ is None else environ
    for name in TOKEN_ENVIRONMENT_VARIABLES:
        token = str(environment.get(name) or "").strip()
        if token:
            return (
                StdlibGitHubApi(
                    token,
                    timeout_seconds=spec.request_timeout_seconds,
                    max_attempts=spec.max_attempts,
                ),
                "",
            )
    return None, (
        "no read-only GitHub credential in GH_TOKEN/GITHUB_TOKEN; the same-SHA CI "
        "run cannot be verified, so this evidence can never read as PASS"
    )


def _get_paged(
    api: GitHubApi,
    path: str,
    params: Mapping[str, str],
    *,
    key: str,
    max_pages: int,
) -> tuple[list[dict[str, Any]] | None, str]:
    """Collect every page of one GitHub list endpoint (bounded page count)."""

    items: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        response = api.get(path, {**params, "page": str(page), "per_page": str(PAGE_SIZE)})
        if response.status != 200:
            return None, response.error or f"GitHub API returned HTTP {response.status}"
        payload = response.payload
        if not isinstance(payload, Mapping) or not isinstance(payload.get(key), list):
            return None, f"malformed GitHub API payload: expected a {key!r} list"
        chunk = payload[key]
        for entry in chunk:
            if not isinstance(entry, dict):
                return None, f"malformed GitHub API payload: {key!r} entries must be objects"
        items.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            return items, ""
    return None, f"GitHub API pagination exceeded the {max_pages}-page limit"


def _run_summary(run: Mapping[str, Any]) -> str:
    return f"run {run.get('id')} {run.get('status')}/{run.get('conclusion')}"


def discover_same_sha_runs(
    api: GitHubApi, spec: CiAcceptanceSpec, head_sha: str
) -> tuple[list[dict[str, Any]] | None, str]:
    """Return the trusted repository's CI runs for exactly this commit/event."""

    workflow_file = spec.workflow_path.rsplit("/", 1)[-1]
    path = f"/repos/{spec.repository}/actions/workflows/{workflow_file}/runs"
    runs, detail = _get_paged(
        api,
        path,
        {"head_sha": head_sha, "event": spec.event},
        key="workflow_runs",
        max_pages=spec.max_pages,
    )
    if runs is None:
        return None, detail
    matching: list[dict[str, Any]] = []
    for run in runs:
        if run.get("path") != spec.workflow_path:
            continue
        if str(run.get("head_sha", "")).lower() != head_sha:
            continue
        if run.get("event") != spec.event:
            continue
        if not isinstance(run.get("id"), int) or isinstance(run.get("id"), bool):
            return None, "malformed GitHub API payload: run entries must carry a numeric id"
        repository = run.get("repository")
        if isinstance(repository, Mapping) and repository.get("full_name") not in (
            None,
            spec.repository,
        ):
            continue
        matching.append(run)
    return matching, ""


def _fetch_run(
    api: GitHubApi, spec: CiAcceptanceSpec, run_id: int
) -> tuple[dict[str, Any] | None, str]:
    response = api.get(f"/repos/{spec.repository}/actions/runs/{run_id}")
    if response.status != 200:
        return None, response.error or f"GitHub API returned HTTP {response.status}"
    run = response.payload
    if not isinstance(run, Mapping):
        return None, "malformed GitHub API payload: a run must be an object"
    repository = run.get("repository")
    if isinstance(repository, Mapping) and repository.get("full_name") not in (
        None,
        spec.repository,
    ):
        return None, "the GitHub run belongs to a different repository"
    for field_name in ("path", "head_sha", "event", "status"):
        if not isinstance(run.get(field_name), str):
            return None, f"malformed GitHub API payload: run {field_name!r} must be a string"
    # GitHub reports ``conclusion: null`` until the run completes; a completed
    # run without a conclusion is malformed, and a null conclusion never counts
    # as success below.
    conclusion = run.get("conclusion")
    if conclusion is None:
        if run.get("status") == "completed":
            return None, "malformed GitHub API payload: a completed run carries no conclusion"
    elif not isinstance(conclusion, str):
        return None, "malformed GitHub API payload: run 'conclusion' must be a string or null"
    if not isinstance(run.get("id"), int) or isinstance(run.get("id"), bool):
        return None, "malformed GitHub API payload: run id must be a number"
    if not isinstance(run.get("run_attempt"), int) or isinstance(run.get("run_attempt"), bool):
        return None, "malformed GitHub API payload: run_attempt must be a number"
    return dict(run), ""


def _verify_required_jobs(
    jobs: Sequence[Mapping[str, Any]], required_jobs: Sequence[str]
) -> tuple[list[dict[str, Any]] | None, str]:
    verified: list[dict[str, Any]] = []
    problems: list[str] = []
    for name in required_jobs:
        named = [job for job in jobs if str(job.get("name", "")).strip() == name]
        if not named:
            problems.append(f"required job {name!r} is not present in the run")
            continue
        if len(named) > 1:
            problems.append(f"required job {name!r} is reported more than once")
            continue
        job = named[0]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            problems.append(f"required job {name!r} is {job.get('status')}/{job.get('conclusion')}")
            continue
        verified.append({"name": name, "conclusion": "success"})
    if problems:
        return None, "; ".join(problems)
    return verified, ""


def _declared_problems(declared: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    run_id = str(declared.get("run_id", ""))
    if not run_id.isdigit():
        problems.append("run_id must be the numeric GitHub run id")
    attempt = declared.get("run_attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        problems.append("run_attempt must be a positive integer")
    for field_name in ("run_url", "workflow_path", "head_sha", "event"):
        value = declared.get(field_name)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field_name} must be a non-empty string")
    jobs = declared.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        problems.append("jobs must be a non-empty list of {name, conclusion} objects")
    else:
        for job in jobs:
            if (
                not isinstance(job, Mapping)
                or not isinstance(job.get("name"), str)
                or not isinstance(job.get("conclusion"), str)
            ):
                problems.append("jobs must be a list of {name, conclusion} objects")
                break
    return problems


def verify_same_sha_ci_run(
    api: GitHubApi,
    spec: CiAcceptanceSpec,
    *,
    head_sha: str,
    declared: Mapping[str, Any] | None = None,
) -> CiRunVerdict:
    """Verify the same-SHA CI acceptance claim against the GitHub API.

    ``declared`` is the claim read from an evidence envelope. When it is
    supplied (release validation) it must match the API exactly; when it is
    ``None`` (evidence writer) the newest qualifying run is selected so its
    identity can be recorded. Either way only API responses are authoritative.
    """

    sha = str(head_sha or "").strip().lower()
    if FULL_SHA.fullmatch(sha) is None:
        return CiRunVerdict(
            False, "the release commit must be the full 40-character lowercase commit SHA"
        )
    if declared is not None:
        if not isinstance(declared, Mapping):
            return CiRunVerdict(False, "declared CI run metadata must be an object")
        problems = _declared_problems(declared)
        if problems:
            return CiRunVerdict(False, "malformed declared CI run metadata: " + "; ".join(problems))

    runs, detail = discover_same_sha_runs(api, spec, sha)
    if runs is None:
        return CiRunVerdict(False, detail)
    if not runs:
        return CiRunVerdict(
            False,
            f"no {spec.workflow_path} {spec.event} run exists for commit {sha}; "
            "CI acceptance for this exact commit is missing",
        )
    not_green = [
        run
        for run in runs
        if run.get("status") != "completed" or run.get("conclusion") != "success"
    ]
    if not_green:
        return CiRunVerdict(
            False,
            f"CI is not successful for commit {sha}: "
            + ", ".join(_run_summary(run) for run in not_green),
        )

    if declared is not None:
        run_id = int(str(declared["run_id"]))
        if run_id not in {int(entry["id"]) for entry in runs}:
            return CiRunVerdict(
                False,
                f"declared CI run {run_id} is not one of the {spec.event} "
                f"{spec.workflow_path} runs the GitHub API reports for commit {sha}",
            )
    else:
        run_id = max(int(run["id"]) for run in runs)
    run, detail = _fetch_run(api, spec, run_id)
    if run is None:
        return CiRunVerdict(False, detail)
    if run["id"] != run_id:
        return CiRunVerdict(False, "the GitHub API returned a different run than requested")
    if run["path"] != spec.workflow_path:
        return CiRunVerdict(
            False,
            f"run {run_id} is {run['path']}, not the required {spec.workflow_path}",
        )
    if run["event"] != spec.event:
        return CiRunVerdict(False, f"run {run_id} is a {run['event']} run, not {spec.event}")
    if run["head_sha"].lower() != sha:
        return CiRunVerdict(
            False, f"run {run_id} tested commit {run['head_sha']}, not the release commit {sha}"
        )
    if run["status"] != "completed" or run["conclusion"] != "success":
        return CiRunVerdict(False, _run_summary(run))
    if declared is not None:
        if int(declared["run_attempt"]) != run["run_attempt"]:
            return CiRunVerdict(
                False,
                f"declared attempt {declared['run_attempt']} is stale; run {run_id} is at "
                f"attempt {run['run_attempt']}",
            )
        expected_url = str(run.get("html_url") or "").rstrip("/")
        declared_url = str(declared["run_url"]).rstrip("/")
        if not expected_url or declared_url != expected_url:
            return CiRunVerdict(
                False, f"declared run URL does not match the GitHub URL of run {run_id}"
            )

    # Read the verified attempt's jobs from the attempt-specific endpoint. The
    # run's plain jobs endpoint with ``filter=latest`` can switch to a newer
    # attempt between the run read above and the jobs read, which would validate
    # one attempt's run metadata against another attempt's jobs.
    attempt = int(run["run_attempt"])
    jobs, detail = _get_paged(
        api,
        f"/repos/{spec.repository}/actions/runs/{run_id}/attempts/{attempt}/jobs",
        {},
        key="jobs",
        max_pages=spec.max_pages,
    )
    if jobs is None:
        return CiRunVerdict(False, detail, run=run)
    # Re-read the run after the jobs query: a re-run that starts while the jobs
    # are being read must invalidate the attempt whose jobs were just fetched
    # instead of being accepted as if the two reads had been consistent.
    rechecked, detail = _fetch_run(api, spec, run_id)
    if rechecked is None:
        return CiRunVerdict(
            False, f"the CI run could not be re-read after its jobs: {detail}", run=run
        )
    changed: list[str] = []
    if rechecked["id"] != run_id:
        changed.append(f"run id {run_id} -> {rechecked['id']}")
    if rechecked["run_attempt"] != attempt:
        changed.append(f"attempt {attempt} -> {rechecked['run_attempt']}")
    if rechecked["status"] != "completed" or rechecked["conclusion"] != "success":
        changed.append(f"status {rechecked['status']}/{rechecked['conclusion']}")
    if rechecked["head_sha"].lower() != sha:
        changed.append(f"commit {rechecked['head_sha']}")
    if changed:
        return CiRunVerdict(
            False,
            f"run {run_id} changed while its jobs were being verified ("
            + ", ".join(changed)
            + "); refusing a CI result that is not stable",
            run=run,
        )
    verified_jobs, detail = _verify_required_jobs(jobs, spec.required_jobs)
    if verified_jobs is None:
        return CiRunVerdict(False, detail, run=run)
    if declared is not None:
        declared_jobs = {str(job["name"]): str(job["conclusion"]) for job in declared["jobs"]}
        actual_jobs = {job["name"]: job["conclusion"] for job in verified_jobs}
        if declared_jobs != actual_jobs:
            return CiRunVerdict(
                False,
                "declared job results do not match the GitHub API results for the required jobs",
                run=run,
            )
    return CiRunVerdict(
        True,
        f"CI run {run_id} attempt {run['run_attempt']} completed successfully for commit "
        f"{sha}; required jobs succeeded: " + ", ".join(job["name"] for job in verified_jobs),
        run=run,
        jobs=tuple(verified_jobs),
    )


def verified_run_report(verdict: CiRunVerdict) -> dict[str, Any]:
    """Build the evidence ``report`` payload for a verified run.

    Raises ``ValueError`` for a failed verdict: evidence may only record run
    identity that the API actually reported.
    """

    if not verdict.ok or verdict.run is None:
        raise ValueError("verified run metadata is only available for a passing verdict")
    run = verdict.run
    return {
        "ci_run": {
            "run_id": str(run["id"]),
            "run_attempt": int(run["run_attempt"]),
            "run_url": str(run.get("html_url", "")),
            "workflow_path": str(run["path"]),
            "head_sha": str(run["head_sha"]).lower(),
            "event": str(run["event"]),
            "jobs": [dict(job) for job in verdict.jobs],
        }
    }
