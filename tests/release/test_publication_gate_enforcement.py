"""CA-03 publication-path enforcement.

Every release write (``gh release create/upload/edit/delete``) must be preceded
in the same job by the same fail-closed validator that guards stable promotion,
and the shipped policy must require same-SHA CI acceptance (G1) for every
published channel while still refusing to demand stable-only external gates of
preview or RC. These tests parse the workflow, execute the configured gate
command against a fixture bundle that has no evidence, and replay the publish
job's step order with the publication command mocked. Nothing here dispatches a
workflow, tags, publishes, touches a database or uses a credential.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.release.validate_stable_release import evaluate_gates

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
POLICY_PATH = ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json"

GATE_SCRIPT = "scripts/release/validate_stable_release.py"
RELEASE_WRITE = re.compile(r"\bgh\s+release\s+(create|upload|edit|delete)\b")
PUBLISH_JOBS = ("publish-preview-rc", "publish-stable")
TRUSTED_REPOSITORY = "AlexYuhuFeng/EurogasNexus"

# Test-only fixtures: never a real commit, release, run or credential.
RELEASE_SHA = "1" * 40
PREVIEW_TAG = "v0.5.0-preview.1.033df92a856e"


def workflow() -> dict:
    return yaml.safe_load((WORKFLOWS / "release.yml").read_text(encoding="utf-8"))


def steps_of(job: str) -> list[dict]:
    return workflow()["jobs"][job]["steps"]


def run_text(step: dict) -> str:
    return str(step.get("run") or "")


def gate_step(job: str) -> dict:
    gates = [step for step in steps_of(job) if GATE_SCRIPT in run_text(step)]
    assert len(gates) == 1, f"{job} must run exactly one gate step, found {len(gates)}"
    return gates[0]


def gate_tokens(step: dict) -> list[str]:
    """The workflow's gate command as executable tokens (env substituted)."""

    text = re.sub(r"\\\s*\n", " ", run_text(step))
    tokens = shlex.split(text)
    assert tokens[0] == "python", tokens
    assert tokens[1] == GATE_SCRIPT, tokens
    return [
        TRUSTED_REPOSITORY if token == "${GITHUB_REPOSITORY}" else token
        for token in tokens
    ]


def executable_gate_argv(step: dict) -> list[str]:
    tokens = gate_tokens(step)
    return [sys.executable, str(ROOT / GATE_SCRIPT), *tokens[2:]]


def flag_names(tokens: list[str]) -> set[str]:
    return {token for token in tokens if token.startswith("--")}


def replay_job(steps: list[dict], execute) -> str:
    """Replay the Actions job rule: the first failing step stops the job."""

    for step in steps:
        if not execute(step):
            return "stopped"
    return "completed"


def fixture_context(channel: str = "preview") -> dict:
    return {
        "schema_version": 1,
        "app_version": "0.5.0",
        "release_version": PREVIEW_TAG if channel == "preview" else "v0.5.0-rc.1",
        "channel": channel,
        "git_sha": RELEASE_SHA,
        "git_short_sha": RELEASE_SHA[:12],
        "git_ref": "refs/heads/main",
        "source_repository": f"https://github.com/{TRUSTED_REPOSITORY}",
    }


# ---------------------------------------------------------------------------
# Workflow structure: every release write is gated in the same job
# ---------------------------------------------------------------------------


def test_every_release_write_is_preceded_by_the_gate_in_the_same_job() -> None:
    writes: dict[str, list[tuple[str, int]]] = {}
    documents: dict[Path, dict] = {}
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        documents[path] = document
        for name, job in (document.get("jobs") or {}).items():
            for index, step in enumerate(job.get("steps") or []):
                if RELEASE_WRITE.search(run_text(step)):
                    writes.setdefault(path.name, []).append((name, index))

    # Release writes exist, and they live only in the two publish jobs.
    assert set(writes) == {"release.yml"}
    assert {job for job, _ in writes["release.yml"]} == set(PUBLISH_JOBS)

    for filename, entries in writes.items():
        document = documents[WORKFLOWS / filename]
        for job_name, index in entries:
            job_steps = document["jobs"][job_name]["steps"]
            gate_indexes = [
                i
                for i, earlier in enumerate(job_steps[:index])
                if GATE_SCRIPT in run_text(earlier)
            ]
            assert gate_indexes, (
                f"{filename}:{job_name}#{index} writes a release without the gate"
            )
            gate = job_steps[gate_indexes[-1]]
            write = job_steps[index]
            # The gate itself must always run and must be able to fail the job...
            assert not gate.get("if"), f"{filename}:{job_name} gate step is conditional"
            assert not gate.get("continue-on-error", False)
            # ...and the release write must never run around a failed gate.
            assert not write.get("if"), f"{filename}:{job_name} publish step is conditional"
            assert not write.get("continue-on-error", False)


def test_publish_gate_commands_have_no_bypass_flags_or_local_evidence_escape() -> None:
    text = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    assert "--allow-missing-platform-artifacts" not in text
    assert "--allow-local-dry-run-evidence" not in text
    assert "continue-on-error" not in text

    for job_name in PUBLISH_JOBS:
        step = gate_step(job_name)
        tokens = gate_tokens(step)
        assert "--allow-missing-platform-artifacts" not in tokens, job_name
        assert "--allow-local-dry-run-evidence" not in tokens, job_name
        assert {"--context", "--artifacts-dir", "--evidence-dir"} <= flag_names(tokens)
        assert "|| true" not in run_text(step)


def test_preview_and_stable_run_the_same_gate_implementation() -> None:
    preview = flag_names(gate_tokens(gate_step("publish-preview-rc")))
    stable = flag_names(gate_tokens(gate_step("publish-stable")))
    # One validator, no parallel approval system: stable only adds the
    # stable-only existing-tag guard, which preview/RC must not inherit.
    assert stable - preview == {"--reject-existing-tag"}
    assert preview - stable == set()


def test_publish_jobs_grant_only_the_release_write_and_the_ci_read() -> None:
    jobs = workflow()["jobs"]
    for name in PUBLISH_JOBS:
        assert jobs[name]["permissions"] == {"contents": "write", "actions": "read"}, name
        # The gate re-derives G1 with the step-scoped workflow token, not a PAT.
        assert gate_step(name)["env"] == {"GH_TOKEN": "${{ github.token }}"}
    assert jobs["publish-stable"]["environment"] == "production"
    holders = {
        name
        for name, job in jobs.items()
        if (job.get("permissions") or {}).get("actions") == "read"
    }
    # The image-promotion jobs re-run the same gate (and therefore the same
    # read-only G1 re-derivation) before their tag write; no other job reads
    # the Actions API.
    assert holders == {
        "validate",
        "publish-preview-rc",
        "publish-stable",
        "promote-image",
        "promote-image-stable",
    }


# ---------------------------------------------------------------------------
# Policy: same-SHA CI acceptance for every published channel
# ---------------------------------------------------------------------------


def test_policy_requires_same_sha_ci_for_every_published_channel(tmp_path: Path) -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    gates = {gate["id"]: gate for gate in policy["gates"]}
    assert gates["G1"]["required_for"] == "all"
    assert gates["G1"]["verification"] == "same_sha_ci_run"
    assert gates["G1"]["not_applicable_allowed"] is False

    ranks = {"preview": 0, "rc": 1, "stable": 2}
    required: dict[str, set[str]] = {}
    for channel in ranks:
        rows, failed = evaluate_gates(
            policy, tmp_path / "missing-evidence", channel, context=fixture_context()
        )
        required[channel] = {row["id"] for row in rows if row["required"]}
        states = {row["id"]: row["state"] for row in rows}
        # No same-SHA CI run, no publication: G1 is demanded of every channel
        # and its missing evidence can only read as pending.
        assert "G1" in required[channel]
        assert states["G1"] == "PENDING_EXTERNAL"
        assert failed is True

    # Channel inheritance: preview <= rc <= stable, and the stable-only
    # external gates are never accidentally imposed on preview or RC.
    assert required["preview"] <= required["rc"] <= required["stable"]
    for gate_id in ("G15", "G16", "G17", "G18"):
        assert gate_id not in required["preview"] | required["rc"]
        assert gate_id in required["stable"]
    # G19 stays RC-and-above: rc inherits it, preview does not.
    assert "G19" in required["rc"]
    assert "G19" not in required["preview"]


# ---------------------------------------------------------------------------
# Executable replay: a failing gate cannot reach the release write
# ---------------------------------------------------------------------------


def test_replay_helper_stops_at_the_first_failing_step() -> None:
    steps = [
        {"name": "gate", "run": "gate"},
        {"name": "publish", "run": "publish"},
    ]
    seen: list[str] = []

    def execute(step: dict) -> bool:
        seen.append(step["name"])
        return step["name"] != "gate"

    assert replay_job(steps, execute) == "stopped"
    assert seen == ["gate"]

    seen.clear()
    assert replay_job(steps, lambda step: seen.append(step["name"]) or True) == "completed"
    assert seen == ["gate", "publish"]


def test_a_failed_gate_stops_the_job_before_the_mocked_release_write(
    tmp_path: Path,
) -> None:
    steps = steps_of("publish-preview-rc")
    gate_index = next(i for i, step in enumerate(steps) if GATE_SCRIPT in run_text(step))
    publish_index = next(
        i for i, step in enumerate(steps) if RELEASE_WRITE.search(run_text(step))
    )
    assert gate_index < publish_index

    # Fixture bundle: the trusted release context exists, the evidence does not.
    assets = tmp_path / "release-assets"
    (assets / "release-evidence").mkdir(parents=True)
    (assets / "release-context.json").write_text(
        json.dumps(fixture_context()), encoding="utf-8"
    )

    argv = executable_gate_argv(steps[gate_index])
    result = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is False
    states = {row["id"]: row["state"] for row in report["gates"]}
    assert report["gates"][0]["id"] == "G1"
    assert report["gates"][0]["required"] is True
    assert states["G1"] == "PENDING_EXTERNAL"
    assert any(
        error.startswith("mandatory gates not satisfied for preview")
        for error in report["errors"]
    )

    published: list[str] = []

    def execute(step: dict) -> bool:
        if step is steps[gate_index]:
            return (
                subprocess.run(
                    argv, cwd=tmp_path, capture_output=True, text=True, check=False
                ).returncode
                == 0
            )
        if RELEASE_WRITE.search(run_text(step)):
            published.append(run_text(step))
        return True

    # The real gate command fails above; GitHub therefore stops the job, so
    # the mocked `gh release create` is never reached.
    assert replay_job(steps, execute) == "stopped"
    assert published == []
