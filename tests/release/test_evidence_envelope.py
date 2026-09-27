"""PILOT-B evidence-envelope contract tests.

Release gate evidence must be a schema-version 2 envelope bound to the release
identity: full tested commit SHA, precise tested subject digest(s), producer
workflow/job identity, environment and a UTC production timestamp. Status-only,
old-format, foreign, stale, future-dated, malformed or unapproved evidence must
never read as PASS, and external gates must stay PENDING_EXTERNAL until a
configured approval identity exists.

Every commit SHA, digest, run id and approval identity in this module is a
test-only fixture. None of them is a real release identity, approval or
credential, and none of these tests publishes, tags or deploys anything.

Trust boundary: the validator re-derives identity from the release context and
the actual artifact files, but envelope fields remain self-declared JSON text.
This is not cryptographic provenance; see the pilot plan for the residual
signed-attestation work.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from scripts.release.evidence_envelope import (
    API_IMAGE_DIGEST_KEY,
    build_envelope,
)
from scripts.release.release_artifacts import sha256_file
from scripts.release.validate_stable_release import evaluate_gates

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json"
WRITER = ROOT / "scripts" / "release" / "write_gate_evidence.py"

# Test-only identity fixtures: never a real commit, digest, run or approver.
RELEASE_SHA = "1" * 40
FOREIGN_SHA = "2" * 40
RUN_ID = "1234567890"
RUN_URL = f"https://github.com/AlexYuhuFeng/EurogasNexus/actions/runs/{RUN_ID}"
API_IMAGE_DIGEST = "sha256:" + "9f" * 32

RELIABILITY_PRODUCER = {
    "workflow": "release.yml",
    "job": "reliability",
    "environment": "github-actions/linux/x64",
    "run_id": RUN_ID,
    "run_url": RUN_URL,
}
ASSEMBLE_PRODUCER = {**RELIABILITY_PRODUCER, "job": "assemble"}
CONTAINER_PRODUCER = {**RELIABILITY_PRODUCER, "job": "container-acceptance"}


def shipped_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def gate_in(policy: dict, gate_id: str) -> dict:
    return next(gate for gate in policy["gates"] if gate["id"] == gate_id)


def release_context() -> dict:
    """Minimal trusted release context; only the fields the gate uses."""

    return {
        "schema_version": 1,
        "app_version": "0.5.0",
        "release_version": "v0.5.0-rc.4",
        "channel": "rc",
        "git_sha": RELEASE_SHA,
        "git_short_sha": RELEASE_SHA[:12],
        "git_ref": "refs/tags/v0.5.0-rc.4",
        "source_repository": "https://github.com/AlexYuhuFeng/EurogasNexus",
    }


def write_json(path: Path, payload) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def envelope(
    gate_id: str,
    *,
    status: str = "PASS",
    commit_sha: str = RELEASE_SHA,
    subject: dict | None = None,
    producer: dict | None = None,
    approval: dict | None = None,
    produced_at: str | None = None,
    detail: str = "fixture",
) -> dict:
    return build_envelope(
        gate_id=gate_id,
        status=status,
        commit_sha=commit_sha,
        detail=detail,
        subject={"kind": "source"} if subject is None else subject,
        producer=RELIABILITY_PRODUCER if producer is None else producer,
        approval=approval,
        produced_at_utc=produced_at,
    )


def row_for(
    evidence_dir: Path,
    gate_id: str,
    *,
    channel: str = "rc",
    artifacts_dir: Path | None = None,
    local: bool = False,
    policy: dict | None = None,
) -> tuple[dict, bool]:
    """Evaluate exactly one policy gate so row assertions are unambiguous."""

    base = copy.deepcopy(policy if policy is not None else shipped_policy())
    base["gates"] = [gate_in(base, gate_id)]
    rows, failed = evaluate_gates(
        base,
        evidence_dir,
        channel,
        context=release_context(),
        artifacts_dir=artifacts_dir,
        local_dry_run=local,
    )
    return rows[0], failed


# ---------------------------------------------------------------------------
# Missing, old-format, malformed and foreign evidence
# ---------------------------------------------------------------------------


def test_missing_evidence_stays_pending_and_channel_inheritance_holds(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    policy = shipped_policy()
    rows, failed = evaluate_gates(policy, evidence, "rc", context=release_context())
    assert failed
    states = {row["id"]: row["state"] for row in rows}
    assert states["G3"] == "PENDING_EXTERNAL"
    # External gates stay PENDING_EXTERNAL, never PASS, without approved evidence.
    assert states["G15"] == "PENDING_EXTERNAL"

    # Channel inheritance: stable must not skip RC gates; preview must not be
    # asked for RC/stable-only gates (and stable must not skip RC-only gates).
    preview = {row["id"]: row for row in evaluate_gates(
        policy, evidence, "preview", context=release_context()
    )[0]}
    assert preview["G2"]["required"] is True
    # CA-03: same-SHA CI acceptance is required for every published channel;
    # stable-only external gates are still not demanded of preview.
    assert preview["G1"]["required"] is True
    assert preview["G15"]["required"] is False
    stable = {row["id"]: row for row in evaluate_gates(
        policy, evidence, "stable", context=release_context()
    )[0]}
    assert stable["G1"]["required"] is True
    assert stable["G15"]["required"] is True


@pytest.mark.parametrize(
    "payload",
    [
        '{"status": "PASS"}',  # old status-only format
        '{"schema_version": 1, "status": "PASS", "detail": "looks fine"}',
        '"PASS"',  # non-object JSON
        '[{"status": "PASS"}]',
        '{"schema_version": 2, "gate_id": "G3", "status": "PASS"}',  # missing metadata
        "{not json",
    ],
)
def test_old_format_malformed_and_status_only_evidence_fails_closed(
    tmp_path: Path, payload: str
) -> None:
    evidence = tmp_path / "release-evidence"
    write_json(evidence / "postgres-migration.json", payload)
    row, failed = row_for(evidence, "G3")
    assert failed
    assert row["state"] == "FAIL"


def test_wrong_gate_id_fails(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    write_json(evidence / "postgres-migration.json", envelope("G14"))
    row, failed = row_for(evidence, "G3")
    assert failed
    assert row["state"] == "FAIL"
    assert "gate_id" in row["detail"]


def test_foreign_short_and_missing_commit_sha_fail(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    path = evidence / "postgres-migration.json"
    write_json(path, envelope("G3", commit_sha=FOREIGN_SHA))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "not the release commit" in row["detail"]

    payload = envelope("G3")
    payload["commit_sha"] = RELEASE_SHA[:12]
    write_json(path, payload)
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"

    payload = envelope("G3")
    del payload["commit_sha"]
    write_json(path, payload)
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"


# ---------------------------------------------------------------------------
# Subject binding: source vs artifact vs image
# ---------------------------------------------------------------------------


def test_source_gate_rejects_artifact_digest_relabelling(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    # A relabelled file is written as raw JSON: the writer-side builder refuses
    # to construct it, but a hostile or careless producer can still drop it in.
    payload = envelope("G3")
    payload["subject"] = {"kind": "source", "digests": {"server.zip": API_IMAGE_DIGEST}}
    write_json(evidence / "postgres-migration.json", payload)
    row, failed = row_for(evidence, "G3")
    assert failed
    assert row["state"] == "FAIL"
    assert "must not carry artifact digests" in row["detail"]


def test_artifact_gate_verifies_the_actual_artifact(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    artifacts = tmp_path / "release-assets"
    artifacts.mkdir()
    artifact = artifacts / "SHA256SUMS"
    artifact.write_bytes(b"pilot-b fixture artifact\n")
    digest = f"sha256:{sha256_file(artifact)}"
    path = evidence / "checksums.json"

    write_json(
        path,
        envelope(
            "G12",
            subject={"kind": "artifact", "digests": {"SHA256SUMS": digest}},
            producer=ASSEMBLE_PRODUCER,
        ),
    )
    row, failed = row_for(evidence, "G12", artifacts_dir=artifacts)
    assert row["state"] == "PASS"
    assert failed is False

    wrong = "sha256:" + "ab" * 32
    write_json(
        path,
        envelope(
            "G12",
            subject={"kind": "artifact", "digests": {"SHA256SUMS": wrong}},
            producer=ASSEMBLE_PRODUCER,
        ),
    )
    row, failed = row_for(evidence, "G12", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"
    assert "does not match the shipped file" in row["detail"]

    write_json(
        path,
        envelope(
            "G12",
            subject={"kind": "artifact", "digests": {"missing.zip": digest}},
            producer=ASSEMBLE_PRODUCER,
        ),
    )
    row, failed = row_for(evidence, "G12", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"

    write_json(
        path,
        envelope(
            "G12",
            subject={"kind": "artifact", "digests": {"../escape.zip": digest}},
            producer=ASSEMBLE_PRODUCER,
        ),
    )
    row, failed = row_for(evidence, "G12", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"

    # A PASS for an artifact-bound gate must bind at least one tested artifact.
    write_json(path, envelope("G12", producer=ASSEMBLE_PRODUCER))
    row, failed = row_for(evidence, "G12", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"


def test_image_gate_verifies_against_trusted_image_metadata(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    artifacts = tmp_path / "release-assets"
    write_json(
        artifacts / "image-metadata" / "image-metadata.json",
        {"image": "ghcr.io/example/eurogasnexus-api", "digest": API_IMAGE_DIGEST},
    )
    write_json(
        artifacts / "release-manifest.json",
        {"runtime_images": [{"digest": API_IMAGE_DIGEST}]},
    )
    path = evidence / "container-acceptance.json"
    subject = {"kind": "image", "digests": {API_IMAGE_DIGEST_KEY: API_IMAGE_DIGEST}}

    write_json(path, envelope("G19", subject=subject, producer=CONTAINER_PRODUCER))
    row, failed = row_for(evidence, "G19", artifacts_dir=artifacts)
    assert row["state"] == "PASS"
    assert failed is False

    other = "sha256:" + "cd" * 32
    write_json(
        path,
        envelope(
            "G19",
            subject={"kind": "image", "digests": {API_IMAGE_DIGEST_KEY: other}},
            producer=CONTAINER_PRODUCER,
        ),
    )
    row, failed = row_for(evidence, "G19", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"

    # Missing trusted metadata cannot verify the tested digest.
    empty = tmp_path / "empty-assets"
    empty.mkdir()
    write_json(path, envelope("G19", subject=subject, producer=CONTAINER_PRODUCER))
    row, failed = row_for(evidence, "G19", artifacts_dir=empty)
    assert failed and row["state"] == "FAIL"

    # Disagreeing trusted digests fail closed instead of picking one.
    write_json(
        artifacts / "release-manifest.json",
        {"runtime_images": [{"digest": other}]},
    )
    row, failed = row_for(evidence, "G19", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"

    # Malformed trusted metadata (a mapping where a list is expected, and a
    # non-string digest) leaves no usable trusted source: fail closed instead
    # of crashing or inventing a digest.
    write_json(
        artifacts / "image-metadata" / "image-metadata.json",
        {"digest": 12345},
    )
    write_json(
        artifacts / "release-manifest.json",
        {"runtime_images": {"digest": API_IMAGE_DIGEST}},
    )
    row, failed = row_for(evidence, "G19", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"
    assert "no trusted image metadata" in row["detail"]


# ---------------------------------------------------------------------------
# Freshness, producer identity and approvals
# ---------------------------------------------------------------------------


def test_stale_future_and_non_utc_timestamps_fail(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    path = evidence / "postgres-migration.json"
    now = datetime.now(UTC).replace(microsecond=0)

    write_json(path, envelope("G3", produced_at=(now - timedelta(days=31)).isoformat()))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "older than" in row["detail"]

    write_json(path, envelope("G3", produced_at=(now + timedelta(hours=1)).isoformat()))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "future" in row["detail"]

    payload = envelope("G3")
    payload["produced_at_utc"] = now.astimezone().strftime("%Y-%m-%dT%H:%M:%S+05:00")
    write_json(path, payload)
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"

    payload = envelope("G3")
    del payload["produced_at_utc"]
    write_json(path, payload)
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"


def test_unapproved_producer_and_missing_run_identity_fail(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    path = evidence / "postgres-migration.json"

    rogue = {**RELIABILITY_PRODUCER, "workflow": "rogue.yml"}
    write_json(path, envelope("G3", producer=rogue))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "authorised producer" in row["detail"]

    # A producer authorised for another gate is foreign evidence for this one.
    write_json(path, envelope("G3", producer=CONTAINER_PRODUCER))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"

    no_run = {**RELIABILITY_PRODUCER, "run_id": "", "run_url": ""}
    write_json(path, envelope("G3", producer=no_run))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "run" in row["detail"]

    wrong_url = {**RELIABILITY_PRODUCER, "run_url": f"https://example.invalid/runs/{RUN_ID}"}
    write_json(path, envelope("G3", producer=wrong_url))
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"

    write_json(path, envelope("G3"))
    row, failed = row_for(evidence, "G3")
    assert row["state"] == "PASS"
    assert failed is False


def test_local_dry_run_evidence_requires_the_local_flag(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    producer = {
        "workflow": "run_release_dry_run.py",
        "job": "postgres-migration",
        "environment": "local-dry-run",
    }
    write_json(evidence / "postgres-migration.json", envelope("G3", producer=producer))

    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "local" in row["detail"]

    row, failed = row_for(evidence, "G3", local=True)
    assert row["state"] == "PASS"
    assert failed is False


def test_not_applicable_requires_an_explicit_policy_allowance(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    write_json(
        evidence / "postgres-migration.json",
        envelope("G3", status="NOT_APPLICABLE"),
    )
    row, failed = row_for(evidence, "G3")
    assert failed and row["state"] == "FAIL"
    assert "NOT_APPLICABLE" in row["detail"]

    policy = shipped_policy()
    gate_in(policy, "G3")["not_applicable_allowed"] = True
    row, failed = row_for(evidence, "G3", policy=policy)
    assert row["state"] == "NOT_APPLICABLE"
    assert failed is False


def test_external_pass_requires_a_configured_approval_identity(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    artifacts = tmp_path / "release-assets"
    artifacts.mkdir()
    tested = artifacts / "acceptance-bundle.zip"
    tested.write_bytes(b"pilot-b fixture acceptance subject\n")
    subject = {
        "kind": "artifact",
        "digests": {"acceptance-bundle.zip": f"sha256:{sha256_file(tested)}"},
    }
    path = evidence / "external-security-acceptance.json"
    approval = {"identity": "release-owner@example.invalid", "role": "release-owner"}

    write_json(
        path,
        envelope(
            "G15",
            subject=subject,
            producer=RELIABILITY_PRODUCER,
            approval=approval,
        ),
    )
    row, failed = row_for(evidence, "G15", channel="stable", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"
    assert "approval" in row["detail"]

    write_json(path, envelope("G15", status="PENDING_EXTERNAL", subject={"kind": "artifact"}))
    row, failed = row_for(evidence, "G15", channel="stable")
    assert row["state"] == "PENDING_EXTERNAL"
    assert failed

    policy = shipped_policy()
    policy["authorized_external_approvals"] = [approval]
    write_json(
        path,
        envelope(
            "G15",
            subject=subject,
            producer=RELIABILITY_PRODUCER,
            approval=approval,
        ),
    )
    row, failed = row_for(
        evidence, "G15", channel="stable", artifacts_dir=artifacts, policy=policy
    )
    assert row["state"] == "PASS"
    assert failed is False


def test_shipped_policy_declares_bindings_for_every_gate() -> None:
    policy = shipped_policy()
    assert policy["evidence_policy"]["envelope_schema_version"] == 2
    assert policy["evidence_policy"]["max_age_days"] > 0
    assert policy["evidence_policy"]["future_skew_minutes"] > 0
    assert policy["authorized_external_approvals"] == []
    evidence_names = set()
    for gate in policy["gates"]:
        assert gate["subject_kind"] in {"source", "artifact", "image"}
        assert gate["not_applicable_allowed"] is False
        # An empty producer list means no producer is authorised yet for this
        # gate: any evidence for it must fail closed until a reviewed policy
        # change adds the producing profile (or approval identity).
        for producer in gate["producers"]:
            assert producer in policy["producers"], (gate["id"], producer)
        assert gate["evidence"] not in evidence_names, gate["evidence"]
        evidence_names.add(gate["evidence"])
    for gate_id in ("G2", "G3", "G4", "G9", "G12", "G14", "G19"):
        assert gate_in(policy, gate_id)["producers"], gate_id
    assert gate_in(policy, "G19")["subject_kind"] == "image"
    assert gate_in(policy, "G19")["required_for"] == "rc"


# ---------------------------------------------------------------------------
# Writers must emit the same envelope the validator accepts
# ---------------------------------------------------------------------------


def test_write_gate_evidence_cli_emits_a_bound_envelope(tmp_path: Path) -> None:
    output = tmp_path / "release-evidence" / "python-tests.json"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITER),
            "--gate-id", "G2",
            "--status", "PASS",
            "--detail", "fixture run",
            "--commit-sha", RELEASE_SHA,
            "--workflow", "release.yml",
            "--job", "validate",
            "--environment", "github-actions/linux/x64",
            "--run-id", RUN_ID,
            "--run-url", RUN_URL,
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["gate_id"] == "G2"
    assert payload["commit_sha"] == RELEASE_SHA

    # The CLI writes a validate-job envelope for G2; that producer profile is
    # authorised for G2 in the shipped policy.
    row, failed = row_for(output.parent, "G2")
    assert row["state"] == "PASS"
    assert failed is False

    # A source gate refuses artifact digests (no relabelling), and an
    # artifact gate refuses a PASS without a tested artifact digest.
    refused = subprocess.run(
        [
            sys.executable,
            str(WRITER),
            "--gate-id", "G3",
            "--status", "PASS",
            "--commit-sha", RELEASE_SHA,
            "--workflow", "release.yml",
            "--job", "reliability",
            "--environment", "github-actions/linux/x64",
            "--subject-artifact", "SHA256SUMS",
            "--artifacts-dir", str(tmp_path),
            "--output", str(tmp_path / "refused.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0


def test_write_gate_evidence_cli_verifies_artifact_digests(tmp_path: Path) -> None:
    artifacts = tmp_path / "release-assets"
    artifacts.mkdir()
    (artifacts / "SHA256SUMS").write_bytes(b"pilot-b fixture artifact\n")
    output = tmp_path / "release-evidence" / "checksums.json"
    result = subprocess.run(
        [
            sys.executable,
            str(WRITER),
            "--gate-id", "G12",
            "--status", "PASS",
            "--detail", "fixture bundle checksums verified",
            "--commit-sha", RELEASE_SHA,
            "--workflow", "release.yml",
            "--job", "assemble",
            "--environment", "github-actions/linux/x64",
            "--run-id", RUN_ID,
            "--run-url", RUN_URL,
            "--artifacts-dir", str(artifacts),
            "--subject-artifact", "SHA256SUMS",
            "--output", str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["subject"]["digests"] == {
        "SHA256SUMS": f"sha256:{sha256_file(artifacts / 'SHA256SUMS')}"
    }
    row, failed = row_for(output.parent, "G12", artifacts_dir=artifacts)
    assert row["state"] == "PASS"
    assert failed is False


def test_valid_source_evidence_from_the_validate_producer_passes(tmp_path: Path) -> None:
    evidence = tmp_path / "release-evidence"
    producer = {
        "workflow": "release.yml",
        "job": "validate",
        "environment": "github-actions/linux/x64",
        "run_id": RUN_ID,
        "run_url": RUN_URL,
    }
    write_json(evidence / "python-tests.json", envelope("G2", producer=producer))
    row, failed = row_for(evidence, "G2")
    assert row["state"] == "PASS"
    assert failed is False


def test_dry_run_writer_emits_local_bound_envelopes(tmp_path: Path) -> None:
    from scripts.release import run_release_dry_run as dry_run

    artifacts = tmp_path / "release-assets"
    artifacts.mkdir()
    (artifacts / "SHA256SUMS").write_bytes(b"pilot-b fixture artifact\n")
    path = artifacts / "release-evidence" / "checksums.json"
    dry_run.write_evidence(
        path,
        "checksums",
        "PASS",
        "fixture bundle checksums verified",
        commit_sha=RELEASE_SHA,
        artifacts_dir=artifacts,
        subject_artifacts=("SHA256SUMS",),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    assert payload["gate_id"] == "G12"
    assert payload["commit_sha"] == RELEASE_SHA
    assert payload["producer"]["workflow"] == "run_release_dry_run.py"
    assert payload["producer"]["environment"] == "local-dry-run"
    assert payload["subject"]["digests"] == {
        "SHA256SUMS": f"sha256:{sha256_file(artifacts / 'SHA256SUMS')}"
    }

    row, failed = row_for(path.parent, "G12", artifacts_dir=artifacts, local=True)
    assert row["state"] == "PASS"
    assert failed is False
    row, failed = row_for(path.parent, "G12", artifacts_dir=artifacts)
    assert failed and row["state"] == "FAIL"

    # Writers must not invent a PASS without the tested artifact.
    with pytest.raises(ValueError):
        dry_run.write_evidence(
            path,
            "checksums",
            "PASS",
            "missing artifacts",
            commit_sha=RELEASE_SHA,
            artifacts_dir=artifacts,
        )
    with pytest.raises(KeyError):
        dry_run.write_evidence(
            path,
            "not-a-gate",
            "PASS",
            "unknown",
            commit_sha=RELEASE_SHA,
        )


# ---------------------------------------------------------------------------
# Workflow writer/consumer contract
# ---------------------------------------------------------------------------


def test_release_workflow_writers_and_gate_consumer_use_the_envelope() -> None:
    text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)

    # Every gate evidence writer goes through the envelope CLI; the old inline
    # status-only writers are gone so no silent compatibility path remains.
    assert text.count("scripts/release/write_gate_evidence.py") >= 6
    assert '{"name":"postgres-migration"' not in text
    assert '{"name":"container-acceptance"' not in text
    for gate_id in ("G2", "G3", "G4", "G9", "G12", "G14", "G19"):
        assert f"--gate-id {gate_id}" in text, gate_id
    assert '"$GITHUB_SHA"' in text

    # The stable gate must never accept local dry-run evidence in CI.
    assert "--allow-local-dry-run-evidence" not in text
    gate_step = next(
        step
        for step in workflow["jobs"]["publish-stable"]["steps"]
        if step["name"] == "Stable promotion gate"
    )
    assert "validate_stable_release.py" in gate_step["run"]

    # Container acceptance evidence must be part of the assembled bundle
    # before the stable gate re-verifies the image digest.
    assert "container-acceptance" in workflow["jobs"]["assemble"]["needs"]
