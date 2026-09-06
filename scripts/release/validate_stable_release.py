#!/usr/bin/env python
"""Machine-readable release gate for preview/RC/stable promotion.

Internal gates must PASS (or NOT_APPLICABLE) for the requested channel.
External gates remain PENDING_EXTERNAL and stable promotion fails closed until
their referenced evidence file exists and records PASS. A boolean CLI flag can
never mark an external gate complete.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from eurogas_nexus.release.versioning import parse_release_tag  # noqa: E402
from scripts.release.release_metadata import ROOT, canonical_app_version  # noqa: E402
from scripts.release.validate_release_artifacts import validate as validate_artifacts  # noqa: E402

VALID_STATUSES = {"PASS", "FAIL", "PENDING_EXTERNAL", "NOT_APPLICABLE"}


def load_evidence(path: Path) -> dict:
    if not path.is_file():
        return {"status": "PENDING_EXTERNAL", "detail": f"evidence file missing: {path.name}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "FAIL", "detail": f"invalid evidence JSON: {exc}"}
    status = str(data.get("status", "")).upper()
    if status not in VALID_STATUSES:
        return {"status": "FAIL", "detail": f"invalid evidence status {status!r}"}
    return {"status": status, "detail": data.get("detail", "")}


def evaluate_gates(policy: dict, evidence_dir: Path, channel: str) -> tuple[list[dict], bool]:
    rows = []
    failed = False
    for gate in policy["gates"]:
        required = gate["required_for"] in {channel, "all"}
        evidence = load_evidence(evidence_dir / gate["evidence"])
        if not required:
            state = evidence["status"]
            rows.append({**gate, "required": False, "state": state, "detail": evidence["detail"]})
            continue
        if gate["type"] == "internal" and evidence["status"] in {"PASS", "NOT_APPLICABLE"}:
            state = evidence["status"]
        elif gate["type"] == "internal" and evidence["status"] in {"FAIL", "PENDING_EXTERNAL"}:
            state = evidence["status"]
            failed = True
        elif gate["type"] == "external":
            # External gates require a committed/deployed evidence file with PASS.
            state = evidence["status"] if evidence["status"] == "PASS" else "PENDING_EXTERNAL"
            if state != "PASS":
                failed = True
        else:
            state = "FAIL"
            failed = True
        rows.append({**gate, "required": True, "state": state, "detail": evidence["detail"]})
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

    gate_rows, gate_failed = evaluate_gates(policy, Path(args.evidence_dir), channel)
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
