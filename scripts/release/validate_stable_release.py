#!/usr/bin/env python
"""Machine-readable release gate for preview/RC/stable promotion.

Gate evidence must be a schema-version 2 envelope (``evidence_envelope``) bound
to the release identity: full tested commit SHA, precise tested subject
digest(s), producing workflow/job/run identity, environment and a fresh UTC
timestamp. Evidence is verified against the trusted release context and the
actual release bundle - never against expected values declared in the same
evidence file. Status-only, old-format, foreign, stale, future-dated, malformed
or unapproved evidence can never read as PASS; a missing file stays pending.
External gates remain PENDING_EXTERNAL until evidence carries an approval
identity configured in the gate policy, and a boolean CLI flag can never mark
an external gate complete.

Trust boundary: envelope fields are self-declared JSON text. This validator
binds them to identity the release run re-derives (commit, artifact digests,
image metadata) and to producer profiles declared in the policy, but it is not
cryptographic provenance; signed attestation and authoritative GitHub-run
metadata checks remain documented residual work.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eurogas_nexus.release.versioning import parse_release_tag  # noqa: E402
from scripts.release.evidence_envelope import (  # noqa: E402
    API_IMAGE_DIGEST_KEY,
    EVIDENCE_SCHEMA_VERSION,
    FULL_SHA,
    SHA256_DIGEST,
    SUBJECT_KINDS,
    VALID_STATUSES,
    parse_utc_timestamp,
)
from scripts.release.release_artifacts import sha256_file  # noqa: E402
from scripts.release.release_metadata import ROOT, canonical_app_version  # noqa: E402
from scripts.release.validate_release_artifacts import validate as validate_artifacts  # noqa: E402


def load_evidence(path: Path) -> tuple[dict | None, str, str]:
    """Return ``(envelope, state, detail)`` for one gate evidence file.

    A missing file is pending (never PASS). Unreadable, non-object or malformed
    JSON is a hard fail so no compatibility path can read an old-format file.
    """

    if not path.is_file():
        return None, "PENDING_EXTERNAL", f"evidence file missing: {path.name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, "FAIL", f"invalid evidence JSON: {exc}"
    except OSError as exc:
        return None, "FAIL", f"unreadable evidence file: {exc}"
    if not isinstance(data, dict):
        return None, "FAIL", f"evidence JSON must be an object, got {type(data).__name__}"
    return data, "", ""


def _trusted_image_digests(artifacts_dir: Path | None) -> dict[str, str]:
    """Image digests the release run itself produced, keyed by provenance file."""

    trusted: dict[str, str] = {}
    if artifacts_dir is None:
        return trusted
    for label, path in (
        ("image-metadata.json", artifacts_dir / "image-metadata" / "image-metadata.json"),
        ("release-manifest.json", artifacts_dir / "release-manifest.json"),
    ):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        digest = None
        if isinstance(data, dict):
            if label == "image-metadata.json":
                digest = data.get("digest")
            else:
                runtime_images = data.get("runtime_images")
                if isinstance(runtime_images, list) and runtime_images:
                    first = runtime_images[0]
                    if isinstance(first, dict):
                        digest = first.get("digest")
        if isinstance(digest, str) and SHA256_DIGEST.fullmatch(digest):
            trusted[label] = digest
    return trusted


def _verify_subject(
    *, gate: dict, subject: dict, status: str, artifacts_dir: Path | None
) -> str:
    """Verify the declared test subject; return a failure detail or ""."""

    declared_kind = gate.get("subject_kind")
    if declared_kind not in SUBJECT_KINDS:
        return f"gate {gate.get('id')!r} does not declare a valid subject_kind in the policy"
    kind = subject.get("kind")
    if kind != declared_kind:
        return (
            f"evidence subject kind {kind!r} does not match the gate subject kind "
            f"{declared_kind!r}; evidence must not be relabelled across gate kinds"
        )
    digests = subject.get("digests", {})
    if not isinstance(digests, dict):
        return "evidence subject digests must be an object of name to sha256 digest"
    for name, digest in digests.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or SHA256_DIGEST.fullmatch(digest) is None
        ):
            return f"evidence subject digest {name!r} must be sha256:<64 lowercase hex>"
    if kind in {"artifact", "image"} and status == "PASS" and not digests:
        return (
            f"{kind}-bound gate PASS must bind the tested digest(s); a status-only "
            "claim cannot authorise release"
        )
    if not digests:
        return ""
    if kind == "source":
        return (
            "a source-bound gate must not carry artifact digests; a source test binds "
            "the commit SHA and cannot be relabelled with artifact hashes"
        )
    if kind == "artifact":
        if artifacts_dir is None or not artifacts_dir.is_dir():
            return (
                "artifact digests are declared but no artifact directory is available "
                "to verify them"
            )
        for name, digest in digests.items():
            if name != Path(name).name or name in {"", ".", ".."}:
                return f"tested artifact name {name!r} is not a plain file name"
            path = artifacts_dir / name
            if not path.is_file():
                return f"tested artifact {name!r} is missing from the release bundle"
            if f"sha256:{sha256_file(path)}" != digest:
                return (
                    f"declared digest of tested artifact {name!r} does not match the "
                    "shipped file"
                )
        return ""
    # image-bound subject
    if set(digests) != {API_IMAGE_DIGEST_KEY}:
        return f"image-bound evidence must declare exactly {API_IMAGE_DIGEST_KEY!r}"
    trusted = _trusted_image_digests(artifacts_dir)
    if not trusted:
        return (
            "no trusted image metadata (image-metadata.json / release-manifest.json) "
            "is available to verify the tested image digest"
        )
    if len(set(trusted.values())) != 1:
        return (
            "trusted image metadata disagrees between image-metadata.json and "
            "release-manifest.json"
        )
    expected = next(iter(trusted.values()))
    if digests[API_IMAGE_DIGEST_KEY] != expected:
        return (
            f"declared image digest {digests[API_IMAGE_DIGEST_KEY]} does not match the "
            f"release image digest {expected}"
        )
    return ""


def _authorize_producer(
    gate: dict,
    producer: dict,
    policy: dict,
    context: dict | None,
    local_dry_run: bool,
) -> tuple[bool, str, bool]:
    """Check the producing workflow/job against the policy producer profiles.

    Returns ``(authorised, detail, local_blocked)``. Profiles marked local-only
    are rejected unless ``local_dry_run`` is set, which release CI never does.
    """

    profiles = policy.get("producers") or {}
    local_blocked = False
    identity_mismatch = ""
    for name in gate.get("producers") or []:
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            continue
        if producer.get("workflow") != str(profile.get("workflow", "")):
            continue
        profile_job = str(profile.get("job", "*"))
        if profile_job != "*" and producer.get("job") != profile_job:
            continue
        prefix = str(profile.get("environment_prefix", ""))
        if not prefix or not str(producer.get("environment", "")).startswith(prefix):
            continue
        if profile.get("local_only") and not local_dry_run:
            local_blocked = True
            continue
        if profile.get("require_run_identity"):
            run_id = str(producer.get("run_id", ""))
            run_url = str(producer.get("run_url", ""))
            repository = str((context or {}).get("source_repository", "")).rstrip("/")
            if (
                not run_id.isdigit()
                or not repository
                or not run_url.startswith(f"{repository}/actions/runs/")
                or not run_url.rstrip("/").endswith(f"/{run_id}")
            ):
                identity_mismatch = (
                    "authorised producers must carry the GitHub workflow run identity "
                    "(run_id/run_url) of this repository: "
                    f"{producer.get('workflow')}/{producer.get('job')}"
                )
                continue
        return True, "", False
    if local_blocked:
        return (
            False,
            "local dry-run evidence cannot authorise a release; strict validation "
            "rejects producers marked local-only (the local-only flag exists for the "
            "maintainer dry-run path and is never passed by release CI)",
            True,
        )
    if identity_mismatch:
        return False, identity_mismatch, False
    return (
        False,
        f"producer {producer.get('workflow')}/{producer.get('job')} "
        f"({producer.get('environment')}) is not an authorised producer for gate "
        f"{gate.get('id')!r}",
        False,
    )


def _authorize_external_approval(envelope: dict, policy: dict) -> tuple[bool, str]:
    approvals = policy.get("authorized_external_approvals") or []
    approval = envelope.get("approval")
    if not isinstance(approval, dict):
        return False, "external gate PASS requires an approval block in the evidence envelope"
    identity = approval.get("identity")
    role = approval.get("role")
    if not isinstance(identity, str) or not identity.strip():
        return False, "external gate approval requires a non-empty approval identity"
    configured = {
        (str(entry.get("identity", "")), str(entry.get("role", "")))
        for entry in approvals
        if isinstance(entry, dict)
    }
    if (str(identity), str(role if role is not None else "")) not in configured:
        return (
            False,
            f"approval identity {identity!r} is not configured in the gate policy; "
            "external gates cannot be marked PASS without an authorised approval",
        )
    return True, ""


def evaluate_envelope(
    gate: dict,
    envelope: dict,
    *,
    policy: dict,
    context: dict | None,
    artifacts_dir: Path | None,
    local_dry_run: bool,
    now: datetime,
) -> tuple[str, str]:
    """Validate one envelope against trusted context; return ``(state, detail)``."""

    problems: list[str] = []
    schema_version = envelope.get("schema_version")
    if schema_version != EVIDENCE_SCHEMA_VERSION:
        problems.append(
            f"unsupported evidence schema_version {schema_version!r}; evidence must be "
            f"a schema_version {EVIDENCE_SCHEMA_VERSION} envelope"
        )
    if envelope.get("gate_id") != gate.get("id"):
        problems.append(
            f"evidence gate_id {envelope.get('gate_id')!r} does not match gate "
            f"{gate.get('id')!r}"
        )
    status = str(envelope.get("status", "")).upper()
    if status not in VALID_STATUSES:
        problems.append(f"invalid evidence status {status!r}")
    if status == "NOT_APPLICABLE" and not gate.get("not_applicable_allowed", False):
        problems.append(
            f"NOT_APPLICABLE is not permitted for gate {gate.get('id')!r}; only an "
            "explicit reviewed policy change can exempt a gate"
        )
    commit_sha = envelope.get("commit_sha")
    if not isinstance(commit_sha, str) or FULL_SHA.fullmatch(commit_sha) is None:
        problems.append(
            "evidence commit_sha must be the full 40-character lowercase tested commit"
        )
    elif context is None:
        problems.append(
            "release context is unavailable; the evidence commit SHA cannot be verified"
        )
    elif commit_sha != context.get("git_sha"):
        problems.append(
            f"evidence commit {commit_sha} is not the release commit {context.get('git_sha')}"
        )
    evidence_policy = policy.get("evidence_policy") or {}
    produced_at = envelope.get("produced_at_utc")
    if not isinstance(produced_at, str) or not produced_at.strip():
        problems.append("evidence produced_at_utc is missing")
    else:
        parsed = parse_utc_timestamp(produced_at)
        if parsed is None:
            problems.append(f"evidence produced_at_utc {produced_at!r} is not a UTC timestamp")
        else:
            max_age = timedelta(days=float(evidence_policy.get("max_age_days", 30)))
            future_skew = timedelta(minutes=float(evidence_policy.get("future_skew_minutes", 15)))
            if parsed > now + future_skew:
                problems.append("evidence produced_at_utc is in the future")
            elif now - parsed > max_age:
                problems.append(
                    "evidence is older than the "
                    f"{evidence_policy.get('max_age_days', 30)}-day freshness window"
                )
    producer = envelope.get("producer")
    if not isinstance(producer, dict):
        problems.append("evidence producer metadata is missing")
    else:
        for field in ("workflow", "job", "environment"):
            value = producer.get(field)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"evidence producer {field} is missing")
    subject = envelope.get("subject")
    if not isinstance(subject, dict):
        problems.append("evidence subject metadata is missing")
    elif not problems:
        subject_error = _verify_subject(
            gate=gate, subject=subject, status=status, artifacts_dir=artifacts_dir
        )
        if subject_error:
            problems.append(subject_error)
    if problems:
        return "FAIL", "; ".join(problems)

    if gate.get("type") == "external" and not gate.get("producers"):
        # External acceptance is authorised by the approval identity below; the
        # producer block is structurally required above, but its workflow
        # identity cannot be re-derived from the release run.
        pass
    else:
        authorised, authorization_detail, _ = _authorize_producer(
            gate, producer, policy, context, local_dry_run
        )
        if not authorised:
            return "FAIL", authorization_detail
    if gate.get("type") == "external":
        if status == "PASS":
            approved, approval_detail = _authorize_external_approval(envelope, policy)
            if not approved:
                return "FAIL", approval_detail
            return "PASS", str(envelope.get("detail", ""))
        return (
            "PENDING_EXTERNAL",
            str(envelope.get("detail", "")) or f"external evidence records {status}",
        )
    if gate.get("type") != "internal":
        return "FAIL", f"gate type {gate.get('type')!r} is not supported by the policy"
    return status, str(envelope.get("detail", ""))


def evaluate_gates(
    policy: dict,
    evidence_dir: Path,
    channel: str,
    *,
    context: dict | None = None,
    artifacts_dir: Path | None = None,
    local_dry_run: bool = False,
    now: datetime | None = None,
) -> tuple[list[dict], bool]:
    rows = []
    failed = False
    if now is None:
        now = datetime.now(UTC)
    for gate in policy["gates"]:
        # Promotion inherits earlier-channel controls; stable must not skip RC gates.
        channel_rank = {"preview": 0, "rc": 1, "stable": 2}
        required_for = gate["required_for"]
        required = required_for == "all" or (
            required_for in channel_rank
            and channel_rank[channel] >= channel_rank[required_for]
        )
        envelope, evidence_state, evidence_detail = load_evidence(
            evidence_dir / gate["evidence"]
        )
        if envelope is None:
            state, detail = evidence_state, evidence_detail
        else:
            state, detail = evaluate_envelope(
                gate,
                envelope,
                policy=policy,
                context=context,
                artifacts_dir=artifacts_dir,
                local_dry_run=local_dry_run,
                now=now,
            )
        if not required:
            rows.append({**gate, "required": False, "state": state, "detail": detail})
            continue
        if gate.get("type") == "internal":
            if state not in {"PASS", "NOT_APPLICABLE"}:
                failed = True
        elif gate.get("type") == "external":
            # External gates require an approved evidence envelope with PASS.
            if state != "PASS":
                failed = True
        else:
            state = "FAIL"
            failed = True
        rows.append({**gate, "required": True, "state": state, "detail": detail})
    return rows, failed


def release_exists(tag: str, repo: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--sbom-dir", default="release-assets/sbom")
    parser.add_argument("--evidence-dir", default="release-assets/release-evidence")
    parser.add_argument(
        "--gate-policy",
        default=str(ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json"),
    )
    parser.add_argument("--repo", default="AlexYuhuFeng/EurogasNexus")
    parser.add_argument(
        "--allow-missing-platform-artifacts",
        action="store_true",
        help="local dry-run only; strict CI publishing never passes this flag",
    )
    parser.add_argument(
        "--allow-local-dry-run-evidence",
        action="store_true",
        help=(
            "local dry-run only; accept evidence produced by the local dry-run "
            "profile. Strict CI publishing never passes this flag."
        ),
    )
    parser.add_argument("--reject-existing-tag", action="store_true")
    args = parser.parse_args(argv)

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    channel = context["channel"]
    policy = json.loads(Path(args.gate_policy).read_text(encoding="utf-8"))
    errors = []

    try:
        tag = parse_release_tag(context["release_version"])
    except ValueError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        return 1
    if channel != tag.channel.value:
        errors.append("release context channel != tag channel")
    if tag.app_version.core != canonical_app_version():
        errors.append("release tag does not match canonical pyproject version")
    if channel == "stable":
        if not context.get("git_ref", "").startswith("refs/tags/"):
            errors.append("stable releases require a pushed semantic tag, not workflow_dispatch")
        if context["release_version"] != f"v{tag.app_version.core}":
            errors.append("stable tag is not vX.Y.Z")
        if args.reject_existing_tag and release_exists(context["release_version"], args.repo):
            errors.append(
                f"stable release {context['release_version']} already exists; never overwrite"
            )

    manifest_path = Path(args.artifacts_dir) / "release-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_report = validate_artifacts(
            context,
            manifest,
            Path(args.artifacts_dir),
            Path(args.sbom_dir),
            allow_missing_platform_artifacts=args.allow_missing_platform_artifacts,
        )
        errors.extend(artifact_report["errors"])
        signing_states = {item["name"]: item["signing_state"] for item in manifest["artifacts"]}
        windows_signed = [
            name
            for name, state in signing_states.items()
            if name.lower().endswith((".exe", ".msi")) and state == "authenticode_verified"
        ]
        windows_artifacts = [
            name for name in signing_states if name.lower().endswith((".exe", ".msi"))
        ]
        if channel == "stable" and windows_artifacts and not windows_signed:
            errors.append(
                "stable policy requires Authenticode-verified Windows installers; "
                "signing credentials are externally pending and were not fabricated"
            )
    else:
        errors.append("release-manifest.json missing")

    gate_rows, gate_failed = evaluate_gates(
        policy,
        Path(args.evidence_dir),
        channel,
        context=context,
        artifacts_dir=Path(args.artifacts_dir),
        local_dry_run=args.allow_local_dry_run_evidence,
    )
    if gate_failed:
        failed_names = [
            row["id"]
            for row in gate_rows
            if row["required"] and row["state"] not in {"PASS", "NOT_APPLICABLE"}
        ]
        errors.append(
            "mandatory gates not satisfied for " + channel + ": " + ", ".join(failed_names)
        )

    report = {
        "ok": not errors,
        "channel": channel,
        "release_version": context["release_version"],
        "errors": errors,
        "gates": gate_rows,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
