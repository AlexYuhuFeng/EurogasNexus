"""PILOT-C/D container promotion contracts.

The release workflow must build the API image once under a run-attempt-unique
candidate tag, publish the GitHub Release, verify it, and only then copy the
tested multi-platform digest to the customer-facing channel tag in gate-first,
repository-wide-serialized promotion jobs. These tests parse the workflow,
replay the promotion job with the real gate command and a recorded promotion
command, and exercise the promotion tool itself against an in-memory registry
fake - no registry, workflow dispatch, release, credential or database is
used.

The fake serves manifest *bytes*, not a stubbed digest: the bytes for the
tested digest hash to the digest under test, exactly as content-addressed
storage behaves, so the tool's digest-basis verification is exercised for
real. The fixtures use the documented ``imagetools inspect`` manifest JSON
schema (the same shape ``--format '{{json .Manifest}}'`` renders), served
through the documented ``--raw`` original-bytes flag.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import scripts.release.promote_image as promotion

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
PLAN_PATH = ROOT / "docs" / "release" / "CONTAINER_PROMOTION_PLAN.md"
GATE_SCRIPT = "scripts/release/validate_stable_release.py"
PROMOTE_SCRIPT = "scripts/release/promote_image.py"
PROMOTE_JOBS = ("promote-image", "promote-image-stable")
TRUSTED_REPOSITORY = "AlexYuhuFeng/EurogasNexus"

# Test-only fixtures: never a real commit, release, tag, digest or credential.
RELEASE_SHA = "1" * 40
DIGEST = "sha256:" + "ab" * 32
IMAGE = "ghcr.io/example/eurogasnexus-api"
TAG = "0.5.0-preview"
INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"
DOCKER_INDEX_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.list.v2+json"
PLATFORM_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
INSPECT_ARGV = ("docker", "buildx", "imagetools", "inspect", "--raw")


# ---------------------------------------------------------------------------
# Workflow structure: candidate-only builds, gate-first serialized promotion
# ---------------------------------------------------------------------------


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def steps_of(job: str) -> list[dict]:
    return workflow()["jobs"][job]["steps"]


def run_text(step: dict) -> str:
    return str(step.get("run") or "")


def test_runtime_image_publishes_only_a_run_attempt_unique_candidate_tag() -> None:
    job = workflow()["jobs"]["runtime-image"]
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    text = "\n".join(run_text(step) for step in job["steps"])
    assert "candidate-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" in text

    build = next(
        step
        for step in job["steps"]
        if str(step.get("uses", "")).startswith("docker/build-push-action@")
    )
    tags = build["with"]["tags"]
    # Exactly one pushed tag: the run-attempt-unique candidate. No semantic
    # channel tag and no sha-<commit> alias may exist before the gates.
    assert tags.strip() == (
        "${{ steps.image.outputs.name }}:${{ steps.image.outputs.candidate_tag }}"
    )
    assert "channel_tag" not in text
    assert "app_version" not in text
    assert "sha-${{ github.sha }}" not in WORKFLOW_PATH.read_text(encoding="utf-8")


def test_no_semantic_or_sha_alias_tag_is_written_anywhere_by_the_build() -> None:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "channel_tag" not in text
    assert ":sha-" not in text


def test_promotion_jobs_are_downstream_of_publish_and_post_publish_verification() -> None:
    jobs = workflow()["jobs"]
    assert "promote-image" in jobs and "promote-image-stable" in jobs
    for name in PROMOTE_JOBS:
        job = jobs[name]
        assert "post-publish-verify" in job["needs"], name
        condition = job["if"]
        assert "always()" in condition, name
        assert "needs.post-publish-verify.result == 'success'" in condition, name
    assert "needs.resolve.outputs.channel != 'stable'" in jobs["promote-image"]["if"]
    assert "needs.resolve.outputs.channel == 'stable'" in jobs["promote-image-stable"]["if"]
    # The stable promotion keeps the production environment boundary; the
    # preview/RC promotion adds no second boundary to an already-published
    # preview or RC.
    assert jobs["promote-image-stable"]["environment"] == "production"
    assert "environment" not in jobs["promote-image"]


def test_promotion_serialization_is_repository_wide_with_cancellation_off() -> None:
    jobs = workflow()["jobs"]
    expected = {"group": "eurogas-nexus-image-promotion", "cancel-in-progress": False}
    for name in PROMOTE_JOBS:
        assert jobs[name]["concurrency"] == expected, name
    # The group must not be ref-scoped: promotion of any channel serializes
    # against every other promotion of the package.
    assert "${{" not in expected["group"]


def test_only_the_candidate_build_and_promotion_jobs_hold_packages_write() -> None:
    holders = {
        name
        for name, job in workflow()["jobs"].items()
        if "packages" in (job.get("permissions") or {})
    }
    assert holders == {"runtime-image", "promote-image", "promote-image-stable"}
    for name in holders:
        assert workflow()["jobs"][name]["permissions"]["packages"] == "write", name


def test_promotion_is_gate_first_with_minimal_permissions_and_no_bypass() -> None:
    jobs = workflow()["jobs"]
    for name in PROMOTE_JOBS:
        job = jobs[name]
        assert job["permissions"] == {
            "contents": "read",
            "actions": "read",
            "packages": "write",
        }, name
        steps = job["steps"]
        gate_index = next(i for i, step in enumerate(steps) if GATE_SCRIPT in run_text(step))
        release_index = next(
            i for i, step in enumerate(steps) if "gh release view" in run_text(step)
        )
        login_index = next(
            i
            for i, step in enumerate(steps)
            if str(step.get("uses", "")).startswith("docker/login-action@")
        )
        promote_index = next(i for i, step in enumerate(steps) if PROMOTE_SCRIPT in run_text(step))
        # Gate first, then the read-only release confirmation, then the
        # registry login, then the only tag write.
        assert gate_index < release_index < login_index < promote_index, name
        for index in (gate_index, release_index, promote_index):
            assert "if" not in steps[index], (name, steps[index].get("name"))
            assert not steps[index].get("continue-on-error", False), name

        tokens = shlex.split(re.sub(r"\\\s*\n", " ", run_text(steps[gate_index])))
        flags = {token for token in tokens if token.startswith("--")}
        assert flags == {"--context", "--artifacts-dir", "--sbom-dir", "--evidence-dir", "--repo"}
        # The release must already exist when promotion runs, so the
        # stable-only reject-existing-tag guard is deliberately not re-applied;
        # a failed-job rerun after release creation must still promote.
        assert "--reject-existing-tag" not in flags
        assert "--allow-missing-platform-artifacts" not in tokens
        assert "--allow-local-dry-run-evidence" not in tokens

        promote_run = run_text(steps[promote_index])
        assert "--metadata release-assets/image-metadata/image-metadata.json" in promote_run
        assert "--result-output" in promote_run
        assert "|| true" not in promote_run


def test_promotion_steps_cannot_rebuild_push_or_publish() -> None:
    jobs = workflow()["jobs"]
    for name in PROMOTE_JOBS:
        job = jobs[name]
        assert not any(
            str(step.get("uses", "")).startswith("docker/build-push-action@")
            for step in job["steps"]
        ), name
        text = "\n".join(run_text(step) for step in job["steps"])
        assert "docker build " not in text, name
        assert "docker push" not in text, name
        assert "buildx build" not in text, name
        assert "gh release create" not in text, name


def test_promotion_gate_is_the_same_validator_every_publish_path_ran() -> None:
    def gate_flags(job: str) -> set[str]:
        step = next(step for step in steps_of(job) if GATE_SCRIPT in run_text(step))
        tokens = shlex.split(re.sub(r"\\\s*\n", " ", run_text(step)))
        return {token for token in tokens if token.startswith("--")}

    publish_flags = gate_flags("publish-preview-rc")
    for name in PROMOTE_JOBS:
        # One validator, no parallel approval system; stable publication alone
        # adds the existing-tag rejection, which promotion must not inherit.
        assert gate_flags(name) == publish_flags, name
    assert gate_flags("publish-stable") == publish_flags | {"--reject-existing-tag"}


def test_promotion_result_is_uploaded_as_a_workflow_artifact() -> None:
    for name in PROMOTE_JOBS:
        steps = steps_of(name)
        upload = next(
            step
            for step in steps
            if str(step.get("uses", "")).startswith("actions/upload-artifact@")
        )
        assert upload["with"]["name"] == "release-promotion-result", name
        assert upload["with"]["path"] == "promotion-evidence", name


# ---------------------------------------------------------------------------
# Executable replay: a failing gate cannot reach the tag write
# ---------------------------------------------------------------------------


def executable_gate_argv(step: dict) -> list[str]:
    tokens = shlex.split(re.sub(r"\\\s*\n", " ", run_text(step)))
    assert tokens[0] == "python" and tokens[1] == GATE_SCRIPT, tokens
    tokens = [TRUSTED_REPOSITORY if token == "${GITHUB_REPOSITORY}" else token for token in tokens]
    return [sys.executable, str(ROOT / GATE_SCRIPT), *tokens[2:]]


def replay_job(steps: list[dict], execute) -> str:
    """Replay the Actions job rule: the first failing step stops the job."""

    for step in steps:
        if not execute(step):
            return "stopped"
    return "completed"


def test_failing_gate_stops_the_job_before_the_mocked_promotion(tmp_path: Path) -> None:
    steps = steps_of("promote-image")
    gate_index = next(i for i, step in enumerate(steps) if GATE_SCRIPT in run_text(step))
    promote_index = next(i for i, step in enumerate(steps) if PROMOTE_SCRIPT in run_text(step))
    assert gate_index < promote_index

    # Fixture bundle: the trusted release context exists, the evidence does not.
    assets = tmp_path / "release-assets"
    (assets / "release-evidence").mkdir(parents=True)
    context = {
        "schema_version": 1,
        "app_version": "0.5.0",
        "release_version": "v0.5.0-preview.1.033df92a856e",
        "channel": "preview",
        "git_sha": RELEASE_SHA,
        "git_short_sha": RELEASE_SHA[:12],
        "git_ref": "refs/heads/main",
        "source_repository": f"https://github.com/{TRUSTED_REPOSITORY}",
    }
    (assets / "release-context.json").write_text(json.dumps(context), encoding="utf-8")

    argv = executable_gate_argv(steps[gate_index])
    result = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is False
    assert any(
        error.startswith("mandatory gates not satisfied for preview") for error in report["errors"]
    )

    promoted: list[str] = []

    def execute(step: dict) -> bool:
        if step is steps[gate_index]:
            return (
                subprocess.run(
                    argv, cwd=tmp_path, capture_output=True, text=True, check=False
                ).returncode
                == 0
            )
        if PROMOTE_SCRIPT in run_text(step):
            promoted.append(run_text(step))
        return True

    # The real gate command fails above; GitHub therefore stops the job, so the
    # mocked promotion step is never reached and no tag can be written.
    assert replay_job(steps, execute) == "stopped"
    assert promoted == []


# ---------------------------------------------------------------------------
# Manifest fixtures: the documented index schema, served as real bytes
# ---------------------------------------------------------------------------


def platform_digest(os_name: str, architecture: str, variant: str = "") -> str:
    return "sha256:" + hashlib.sha256(f"{os_name}/{architecture}/{variant}".encode()).hexdigest()


def descriptor(
    os_name: str, architecture: str, variant: str = "", digest: str | None = None
) -> dict:
    entry = {
        "mediaType": PLATFORM_MEDIA_TYPE,
        "digest": digest or platform_digest(os_name, architecture, variant),
        "size": 1234,
        "platform": {"os": os_name, "architecture": architecture},
    }
    if variant:
        entry["platform"]["variant"] = variant
    return entry


def default_descriptors() -> list[dict]:
    return [
        descriptor("linux", "amd64"),
        descriptor("linux", "arm64", "v8"),
        # Provenance/SBOM attestation descriptors use unknown/unknown; they
        # must be tolerated and must not count as a reviewed platform.
        descriptor("unknown", "unknown"),
    ]


def index_manifest_bytes(descriptors: list[dict] | None = None) -> bytes:
    """The documented ``imagetools inspect`` JSON for an OCI image index."""

    document = {
        "schemaVersion": 2,
        "mediaType": INDEX_MEDIA_TYPE,
        "manifests": default_descriptors() if descriptors is None else descriptors,
    }
    return json.dumps(document, indent=2).encode("utf-8")


def document_bytes(document: object) -> bytes:
    return json.dumps(document).encode("utf-8")


class FakeRegistry:
    """A stateful in-memory stand-in for the registry and the buildx CLI.

    Manifest bytes are the source of truth: the bytes served for the tested
    digest hash to the digest the fake reports, exactly as content-addressed
    storage behaves. ``newline`` emulates a CLI that appends one trailing
    newline to ``--raw`` output.
    """

    def __init__(
        self,
        *,
        descriptors: list[dict] | None = None,
        newline: bool = False,
        tag_newline: bool | None = None,
    ) -> None:
        self.subject_bytes = index_manifest_bytes(descriptors)
        self.digest = "sha256:" + hashlib.sha256(self.subject_bytes).hexdigest()
        self.newline = newline
        self.tag_newline = tag_newline
        self.tags: dict[str, bytes] = {}
        self.created: set[str] = set()
        self.commands: list[tuple[str, ...]] = []
        self.subject_override: bytes | None = None
        self.subject_failure: promotion.CommandResult | None = None
        self.tag_failure: promotion.CommandResult | None = None
        self.after_create_bytes: bytes | None = None
        self.after_create_failure: promotion.CommandResult | None = None
        self.create_failure: promotion.CommandResult | None = None

    @staticmethod
    def not_found(command: tuple[str, ...], reference: str) -> promotion.CommandResult:
        # The registry's explicit manifest-missing wording (MANIFEST_UNKNOWN).
        return promotion.CommandResult(
            command, returncode=1, stderr=f"ERROR: {reference}: manifest unknown"
        )

    def _present(
        self, command: tuple[str, ...], content: bytes, newline: bool
    ) -> promotion.CommandResult:
        payload = content + (b"\n" if newline else b"")
        return promotion.CommandResult(
            command, 0, stdout=payload.decode("utf-8"), stdout_raw=payload
        )

    def _tag_newline(self) -> bool:
        return self.newline if self.tag_newline is None else self.tag_newline

    def runner(self, argv, timeout) -> promotion.CommandResult:
        command = tuple(argv)
        self.commands.append(command)
        if command[1:5] == ("buildx", "imagetools", "inspect", "--raw"):
            reference = command[5]
            if reference == f"{IMAGE}@{self.digest}":
                if self.subject_failure is not None:
                    return self.subject_failure
                return self._present(
                    command, self.subject_override or self.subject_bytes, self.newline
                )
            tag = reference.rsplit(":", 1)[-1]
            if tag in self.created:
                if self.after_create_failure is not None:
                    return self.after_create_failure
                content = (
                    self.after_create_bytes
                    if self.after_create_bytes is not None
                    else self.tags[tag]
                )
                return self._present(command, content, self._tag_newline())
            if self.tag_failure is not None:
                return self.tag_failure
            if tag not in self.tags:
                return self.not_found(command, reference)
            return self._present(command, self.tags[tag], self._tag_newline())
        if command[1:4] == ("buildx", "imagetools", "create"):
            if self.create_failure is not None:
                return self.create_failure
            tag = command[command.index("--tag") + 1].rsplit(":", 1)[-1]
            self.tags[tag] = self.subject_bytes
            self.created.add(tag)
            return promotion.CommandResult(command, 0, "created")
        raise AssertionError(f"unexpected command: {command}")

    def writes(self) -> list[tuple[str, ...]]:
        return [command for command in self.commands if "create" in command]

    def tag_inspects(self) -> list[tuple[str, ...]]:
        return [
            command
            for command in self.commands
            if command[1:5] == ("buildx", "imagetools", "inspect", "--raw")
            and command[5] == f"{IMAGE}:{TAG}"
        ]


def run_promotion(registry: FakeRegistry, *, tag: str = TAG):
    return promotion.promote_image(
        image=IMAGE, tag=tag, digest=registry.digest, runner=registry.runner, timeout=5.0
    )


# ---------------------------------------------------------------------------
# Absence and refusal classification over the FULL command output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stderr",
    [
        "ERROR: denied: requested access to the resource is denied",
        "ERROR: unauthorized: authentication required",
        "ERROR: Get https://ghcr.io/v2/: dial tcp 1.2.3.4:443: i/o timeout",
        "ERROR: something unexpected happened",
        "",
    ],
)
def test_inspect_failure_other_than_a_manifest_not_found_never_writes(stderr: str) -> None:
    registry = FakeRegistry()
    registry.tag_failure = promotion.CommandResult(("docker",), returncode=1, stderr=stderr)
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused", result.detail
    assert registry.writes() == []
    assert registry.tags == {}


@pytest.mark.parametrize(
    "stderr",
    [
        # The registry client's generic wording: no manifest-missing marker.
        f"ERROR: {IMAGE}:{TAG}: not found",
        'ERROR: exec: "docker": executable file not found in $PATH',
        "error: config file not found: /home/runner/.docker/config.json",
        f"ERROR: {IMAGE}:{TAG}: no such manifest",
    ],
)
def test_generic_not_found_is_refused_and_never_writes(stderr: str) -> None:
    registry = FakeRegistry()
    registry.tag_failure = promotion.CommandResult(("docker",), returncode=1, stderr=stderr)
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused", result.detail
    assert "manifest-missing marker" in result.detail
    assert registry.writes() == []
    assert registry.tags == {}


def test_manifest_missing_with_auth_error_beyond_the_display_window_is_refused() -> None:
    registry = FakeRegistry()
    reference = f"{IMAGE}:{TAG}"
    registry.tag_failure = promotion.CommandResult(
        ("docker",),
        returncode=1,
        stderr=(
            f"ERROR: {reference}: manifest unknown "
            + "x" * 400
            + " denied: requested access to the resource is denied"
        ),
    )
    result = run_promotion(registry)
    # The refusal signal appears beyond the 300-character display window; it
    # must still be classified, so absence never wins by truncation.
    assert result.ok is False and result.outcome == "refused", result.detail
    assert "never treated as absence" in result.detail
    assert "denied" not in result.detail  # display is bounded, classification was not
    assert registry.writes() == []


def test_explicit_manifest_missing_marker_with_hash_digits_containing_500_is_absence() -> None:
    registry = FakeRegistry()
    # 64 hex chars containing "500": a bare 5dd pattern would misfire here.
    hex_ish = "500" + "ab" * 30 + "c"
    assert len(hex_ish) == 64
    registry.tag_failure = promotion.CommandResult(
        ("docker",),
        returncode=1,
        stderr=f"ERROR: {IMAGE}:{TAG}: manifest unknown (request digest sha256:{hex_ish})",
    )
    result = run_promotion(registry)
    assert result.ok is True and result.outcome == "promoted", result.detail
    assert registry.tags == {TAG: registry.subject_bytes}
    assert len(registry.writes()) == 1


@pytest.mark.parametrize(
    "stderr",
    [
        "ERROR: received response with status: 503 from the registry",
        "ERROR: HTTP/1.1 500 Internal Server Error",
        "ERROR: the registry returned code=502",
    ],
)
def test_contextual_http_5xx_is_refused(stderr: str) -> None:
    registry = FakeRegistry()
    registry.tag_failure = promotion.CommandResult(("docker",), returncode=1, stderr=stderr)
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused", result.detail
    assert registry.writes() == []


def test_inspect_timeout_is_refused_and_never_read_as_absence() -> None:
    registry = FakeRegistry()
    registry.tag_failure = promotion.CommandResult(("docker",), timed_out=True)
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused"
    assert "timed out" in result.detail and "never treated as absence" in result.detail
    assert registry.writes() == []


# ---------------------------------------------------------------------------
# Promotion flow against real bytes: digest basis, copy, post-copy verify
# ---------------------------------------------------------------------------


def test_absent_tag_copies_the_exact_tested_digest_then_verifies_it() -> None:
    registry = FakeRegistry()
    result = run_promotion(registry)
    assert result.ok is True and result.outcome == "promoted", result.detail
    assert registry.tags[TAG] == registry.subject_bytes
    assert registry.writes() == [
        (
            "docker",
            "buildx",
            "imagetools",
            "create",
            "--tag",
            f"{IMAGE}:{TAG}",
            f"{IMAGE}@{registry.digest}",
        )
    ]
    # One pre-write classification inspect and one post-write verification.
    assert len(registry.tag_inspects()) == 2
    for command in registry.commands:
        assert command[:3] == ("docker", "buildx", "imagetools"), command
    assert result.observed_digest == registry.digest


def test_matching_tag_is_a_no_op_and_retries_are_idempotent() -> None:
    registry = FakeRegistry()
    registry.tags[TAG] = registry.subject_bytes
    first = run_promotion(registry)
    second = run_promotion(registry)
    for result in (first, second):
        assert result.ok is True and result.outcome == "noop", result.detail
    assert registry.writes() == []
    assert registry.tags == {TAG: registry.subject_bytes}


def test_existing_tag_with_a_different_digest_is_refused_untouched() -> None:
    registry = FakeRegistry()
    conflicting = index_manifest_bytes([descriptor("linux", "386")])
    registry.tags[TAG] = conflicting
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused"
    # Refusal of an observed conflict is policy: the credential itself could
    # overwrite, and an external writer racing the check is not excluded.
    assert "policy" in result.detail
    assert "credential" in result.detail
    assert "external writer" in result.detail
    assert "owner/incident decision is required" in result.detail
    assert registry.writes() == []
    assert registry.tags == {TAG: conflicting}


def test_post_copy_digest_mismatch_fails_closed_and_leaves_tag_state_unknown() -> None:
    registry = FakeRegistry()
    registry.after_create_bytes = index_manifest_bytes([descriptor("linux", "386")])
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "verification_failed"
    assert result.detail.startswith("FAIL:")
    assert "tag state is UNKNOWN" in result.detail
    assert "escalate" in result.detail
    assert len(registry.writes()) == 1  # the single write attempt; nothing further


def test_post_copy_inspection_failure_is_unknown_state_not_a_missing_tag() -> None:
    registry = FakeRegistry()
    registry.after_create_failure = promotion.CommandResult(
        ("docker",), returncode=1, stderr="ERROR: something unexpected happened"
    )
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "verification_failed"
    assert "tag state is UNKNOWN" in result.detail
    # A failed post-copy inspection is never read as "the tag does not exist".
    assert "not proof that the tag exists" in result.detail
    assert len(registry.writes()) == 1


def test_tested_digest_must_verify_before_any_tag_read() -> None:
    registry = FakeRegistry()
    registry.subject_failure = promotion.CommandResult(
        ("docker",), returncode=1, stderr="ERROR: manifest unknown"
    )
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused"
    assert "is not verifiably present" in result.detail
    assert len(registry.commands) == 1  # no tag read, no write

    tampered = FakeRegistry()
    tampered.subject_override = index_manifest_bytes([descriptor("linux", "386")])
    result = run_promotion(tampered)
    assert result.ok is False and result.outcome == "refused"
    assert "do not hash to the tested digest" in result.detail
    assert len(tampered.commands) == 1
    assert tampered.writes() == []


def test_tested_digest_must_report_both_reviewed_platforms() -> None:
    single_platform = FakeRegistry(descriptors=[descriptor("linux", "amd64")])
    result = run_promotion(single_platform)
    assert result.ok is False and result.outcome == "refused"
    assert "linux/arm64" in result.detail
    assert single_platform.writes() == []

    # amd64/v2 is not the reviewed plain linux/amd64 build.
    odd_variant = FakeRegistry(
        descriptors=[descriptor("linux", "amd64", "v2"), descriptor("linux", "arm64", "v8")]
    )
    result = run_promotion(odd_variant)
    assert result.ok is False and result.outcome == "refused"
    assert "linux/amd64" in result.detail
    assert odd_variant.writes() == []


def test_cli_appended_trailing_newline_is_calibrated_on_the_tested_digest() -> None:
    registry = FakeRegistry(newline=True)
    result = run_promotion(registry)
    assert result.ok is True and result.outcome == "promoted", result.detail
    assert result.observed_digest == registry.digest
    assert registry.tags == {TAG: registry.subject_bytes}


def test_tag_output_without_the_calibrated_newline_is_refused() -> None:
    registry = FakeRegistry(newline=True, tag_newline=False)
    registry.tags[TAG] = registry.subject_bytes
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused"
    assert "trailing newline" in result.detail
    assert registry.writes() == []


def test_copy_timeout_writes_nothing_further_and_says_so() -> None:
    registry = FakeRegistry()
    registry.create_failure = promotion.CommandResult(("docker",), timed_out=True)
    result = run_promotion(registry)
    assert result.ok is False and result.outcome == "refused"
    assert "tag state is UNKNOWN" in result.detail
    assert len(registry.writes()) == 1


# ---------------------------------------------------------------------------
# Index parsing: documented schema, allowed variants, strict refusals
# ---------------------------------------------------------------------------


def test_reviewed_index_parses_with_platforms_and_attestations() -> None:
    parsed = promotion.parse_index_manifest(index_manifest_bytes())
    assert parsed.detail == ""
    assert parsed.satisfied_platforms == promotion.REQUIRED_PLATFORMS
    assert {"linux/amd64", "linux/arm64/v8"} <= parsed.platforms
    assert "unknown/unknown" not in parsed.platforms


def test_docker_manifest_list_and_bare_arm64_variant_are_accepted() -> None:
    document = {
        "schemaVersion": 2,
        "mediaType": DOCKER_INDEX_MEDIA_TYPE,
        "manifests": [descriptor("linux", "amd64"), descriptor("linux", "arm64")],
    }
    parsed = promotion.parse_index_manifest(document_bytes(document))
    assert parsed.detail == ""
    assert parsed.satisfied_platforms == promotion.REQUIRED_PLATFORMS


def test_descriptors_without_platform_are_tolerated_but_not_counted() -> None:
    document = {
        "schemaVersion": 2,
        "mediaType": INDEX_MEDIA_TYPE,
        "manifests": [
            descriptor("linux", "amd64"),
            {"mediaType": PLATFORM_MEDIA_TYPE, "digest": platform_digest("x", "y"), "size": 1},
        ],
    }
    parsed = promotion.parse_index_manifest(document_bytes(document))
    assert parsed.detail == ""
    assert parsed.satisfied_platforms == frozenset({"linux/amd64"})


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not json at all",
        b'"just a string"',
        document_bytes({"schemaVersion": 2, "manifests": []}),
        document_bytes(
            {"schemaVersion": 2, "mediaType": PLATFORM_MEDIA_TYPE, "manifests": []}
        ),
        document_bytes({"schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE, "manifests": "x"}),
        document_bytes(
            {
                "schemaVersion": 2,
                "mediaType": INDEX_MEDIA_TYPE,
                "manifests": [{"mediaType": PLATFORM_MEDIA_TYPE, "digest": "sha256:XYZ"}],
            }
        ),
        document_bytes(
            {
                "schemaVersion": 2,
                "mediaType": INDEX_MEDIA_TYPE,
                "manifests": [{"digest": platform_digest("linux", "amd64")}],
            }
        ),
        document_bytes(
            {
                "schemaVersion": 2,
                "mediaType": INDEX_MEDIA_TYPE,
                "manifests": [
                    {
                        "mediaType": PLATFORM_MEDIA_TYPE,
                        "digest": platform_digest("linux", "amd64"),
                        "platform": "linux/amd64",
                    }
                ],
            }
        ),
        document_bytes(
            {
                "schemaVersion": 2,
                "mediaType": INDEX_MEDIA_TYPE,
                "manifests": [
                    {
                        "mediaType": PLATFORM_MEDIA_TYPE,
                        "digest": platform_digest("linux", "amd64"),
                        "platform": {"os": "linux"},
                    }
                ],
            }
        ),
        document_bytes(
            {
                "schemaVersion": 2,
                "mediaType": INDEX_MEDIA_TYPE,
                "manifests": [
                    {
                        "mediaType": PLATFORM_MEDIA_TYPE,
                        "digest": platform_digest("linux", "amd64"),
                        "platform": {"os": "linux", "architecture": "amd64", "variant": 7},
                    }
                ],
            }
        ),
    ],
)
def test_absent_or_ambiguous_index_shapes_are_refused(content: bytes) -> None:
    assert promotion.parse_index_manifest(content).detail != ""


def test_inspect_reference_refuses_ambiguous_manifest_bytes() -> None:
    def run(argv):
        return promotion.CommandResult(tuple(argv), 0, stdout="raw", stdout_raw=b"raw")

    # The tag call always runs under the byte rule the tested digest
    # established; here that calibration is "exact".
    outcome = promotion.inspect_reference(f"{IMAGE}:{TAG}", run, byte_rule="exact")
    assert outcome.state == "refused"
    assert "ambiguous or unsupported" in outcome.detail


# ---------------------------------------------------------------------------
# The command runner and input validation
# ---------------------------------------------------------------------------


def test_subprocess_runner_enforces_timeouts_and_reports_launch_failures(
    tmp_path: Path,
) -> None:
    timed_out = promotion.subprocess_runner(
        [sys.executable, "-c", "import time; time.sleep(30)"], 0.2
    )
    assert timed_out.timed_out is True
    assert timed_out.returncode == -1

    missing = promotion.subprocess_runner([str(tmp_path / "no-such-binary")], 1.0)
    assert missing.timed_out is False
    assert missing.returncode == -1
    assert "could not be started" in missing.stderr

    ok = promotion.subprocess_runner([sys.executable, "-c", "print('registry')"], 10.0)
    assert ok.returncode == 0 and "registry" in ok.stdout
    # Exact bytes are preserved for hashing (no text-mode newline translation).
    assert ok.stdout_raw.strip() == b"registry"


@pytest.mark.parametrize(
    "timeout",
    [0, -1, float("inf"), float("-inf"), float("nan"), "5", True],
)
def test_promote_image_rejects_non_finite_or_non_positive_timeouts(timeout) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv, _timeout):
        calls.append(tuple(argv))
        raise AssertionError("no command may run for rejected inputs")

    result = promotion.promote_image(
        image=IMAGE, tag=TAG, digest=DIGEST, timeout=timeout, runner=runner
    )
    assert result.ok is False and result.outcome == "invalid_input", timeout
    assert result.commands == ()
    assert "finite positive" in result.detail
    assert calls == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"image": "docker.io/example/api", "tag": TAG, "digest": DIGEST}, "GHCR repository"),
        ({"image": IMAGE, "tag": "latest", "digest": DIGEST}, "latest"),
        ({"image": IMAGE, "tag": "candidate-1-1", "digest": DIGEST}, "staging or retired"),
        ({"image": IMAGE, "tag": TAG, "digest": DIGEST.upper()}, "lowercase hex"),
    ],
)
def test_promote_image_validates_image_tag_and_digest_before_any_command(
    kwargs: dict, message: str
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv, _timeout):
        calls.append(tuple(argv))
        raise AssertionError("no command may run for rejected inputs")

    result = promotion.promote_image(runner=runner, **kwargs)
    assert result.ok is False and result.outcome == "invalid_input", kwargs
    assert result.commands == ()
    assert message in result.detail, kwargs
    assert calls == []


def write_metadata(tmp_path: Path, payload) -> Path:
    path = tmp_path / "image-metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "payload",
    [
        {"image": IMAGE, "digest": DIGEST.upper()},
        {"image": IMAGE, "digest": "sha256:" + "ab" * 31},
        {"image": IMAGE, "digest": DIGEST + " "},
        {"image": IMAGE.upper(), "digest": DIGEST},
        {"image": "ghcr.io/example/eurogasnexus-api; rm -rf /", "digest": DIGEST},
        {"image": "ghcr.io/example/sub/dir", "digest": DIGEST},
        {"image": "docker.io/example/eurogasnexus-api", "digest": DIGEST},
        {"image": IMAGE},
        {"digest": DIGEST},
        ["not", "an", "object"],
    ],
)
def test_invalid_image_metadata_never_touches_the_registry(
    tmp_path: Path, monkeypatch, payload
) -> None:
    registry = FakeRegistry()
    monkeypatch.setattr(promotion, "subprocess_runner", registry.runner)
    output = tmp_path / "promotion-result.json"
    code = promotion.main(
        [
            "--metadata",
            str(write_metadata(tmp_path, payload)),
            "--tag",
            TAG,
            "--result-output",
            str(output),
        ]
    )
    assert code == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ok"] is False and report["outcome"] == "invalid_input"
    assert registry.commands == []


@pytest.mark.parametrize(
    "tag",
    [
        "latest",
        "sha-" + RELEASE_SHA,
        "candidate-123-1",
        "0.5.0 preview",
        "0.5.0;rm -rf /",
        "../0.5.0",
        "-leading",
        "",
        "a" * 129,
    ],
)
def test_invalid_or_retired_tags_never_touch_the_registry(
    tmp_path: Path, monkeypatch, tag: str
) -> None:
    registry = FakeRegistry()
    monkeypatch.setattr(promotion, "subprocess_runner", registry.runner)
    code = promotion.main(
        [
            "--metadata",
            str(write_metadata(tmp_path, {"image": IMAGE, "digest": DIGEST})),
            f"--tag={tag}",
        ]
    )
    assert code == 1
    assert registry.commands == []


@pytest.mark.parametrize("bad_timeout", ["0", "-1", "inf", "nan", "abc"])
def test_missing_metadata_and_bad_timeouts_never_touch_the_registry(
    tmp_path: Path, monkeypatch, capsys, bad_timeout: str
) -> None:
    registry = FakeRegistry()
    monkeypatch.setattr(promotion, "subprocess_runner", registry.runner)
    missing = promotion.main(["--metadata", str(tmp_path / "absent.json"), "--tag", TAG])
    assert missing == 1
    assert json.loads(capsys.readouterr().out)["outcome"] == "invalid_input"

    if bad_timeout == "abc":
        # argparse rejects a non-numeric timeout before any other work.
        with pytest.raises(SystemExit):
            promotion.main(
                [
                    "--metadata",
                    str(write_metadata(tmp_path, {"image": IMAGE, "digest": DIGEST})),
                    "--tag",
                    TAG,
                    "--timeout-seconds",
                    bad_timeout,
                ]
            )
        capsys.readouterr()
    else:
        code = promotion.main(
            [
                "--metadata",
                str(write_metadata(tmp_path, {"image": IMAGE, "digest": DIGEST})),
                "--tag",
                TAG,
                "--timeout-seconds",
                bad_timeout,
            ]
        )
        assert code == 1
        assert json.loads(capsys.readouterr().out)["outcome"] == "invalid_input"
    assert registry.commands == []


def test_valid_run_writes_the_result_and_returns_zero(tmp_path: Path, monkeypatch, capsys) -> None:
    registry = FakeRegistry()
    monkeypatch.setattr(promotion, "subprocess_runner", registry.runner)
    output = tmp_path / "evidence" / "promotion-result.json"
    code = promotion.main(
        [
            "--metadata",
            str(write_metadata(tmp_path, {"image": IMAGE, "digest": registry.digest})),
            "--tag",
            TAG,
            "--result-output",
            str(output),
        ]
    )
    assert code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ok"] is True and report["outcome"] == "promoted"
    assert report["tag"] == TAG and report["tested_digest"] == registry.digest
    assert report["platforms"] == sorted(promotion.REQUIRED_PLATFORMS)
    assert report["commands"]
    assert all(command.startswith("docker buildx imagetools") for command in report["commands"])
    assert any("inspect --raw" in command for command in report["commands"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True


def test_module_never_uses_a_shell() -> None:
    source = (ROOT / "scripts" / "release" / "promote_image.py").read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "os.system" not in source


# ---------------------------------------------------------------------------
# Documentation: implementation state without overclaiming registry acceptance
# ---------------------------------------------------------------------------


def test_plan_records_the_bounded_implementation_without_overclaiming() -> None:
    text = PLAN_PATH.read_text(encoding="utf-8")
    assert "## 9. Implementation state" in text
    for phrase in (
        "candidate-<run_id>-<attempt>",
        "promote-image-stable",
        "`scripts/release/promote_image.py`",
        "eurogas-nexus-image-promotion",
        "exclusive writer",
        "has not been exercised against any registry",
        "no false atomicity",
        "`--raw`",
        "MANIFEST_UNKNOWN",
        'generic "not found"',
        "the tag state is UNKNOWN",
    ):
        assert phrase in text, phrase
