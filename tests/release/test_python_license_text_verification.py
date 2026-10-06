"""Delivered Python license/notice text verification contracts.

Fixture-only behavioural tests for
``scripts/release/verify_python_license_texts.py``: the image-delivered
evidence produced by the existing collector is accepted only while the
manifest is complete and still bound to the shipped lock and the delivered
bytes. Tampered bytes, extra or missing files, altered counts, inconsistent
counts, traversal destinations, swapped lock digests, mismatched inventory and
symlink escapes are refused with a non-zero exit and a clear non-secret
message, and the CLI defaults match the paths in
``deploy/runtime/Dockerfile.api``.

The workflow section pins that the release ``container-acceptance`` job
executes this verifier inside the immutable amd64 image digest with no network
and the image's default non-root user before the G19 PASS is written, while
the arm64 index entry is only checked for manifest presence and is not
executed. No container is run, no image is pulled and no release is touched;
this is technical verification, not legal clearance.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from scripts.release.collect_python_license_texts import collect
from scripts.release.verify_python_license_texts import (
    DEFAULT_EVIDENCE_DIR,
    DEFAULT_RUNTIME_LOCK,
    verify,
)
from scripts.release.verify_python_license_texts import (
    main as verify_main,
)

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "deploy" / "runtime" / "Dockerfile.api"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
VERIFIER = "scripts/release/verify_python_license_texts.py"
DIGEST = "0" * 64


def write_lock(path: Path, entries: list[tuple[str, str]]) -> None:
    lines = []
    for name, version in entries:
        lines.append(f"{name}=={version} \\\n    --hash=sha256:{DIGEST}\n")
    path.write_text("".join(lines), encoding="utf-8")


def add_dist_info(site: Path, name: str, version: str) -> Path:
    directory = site / f"{name}-{version}.dist-info"
    directory.mkdir(parents=True)
    metadata = (
        "Metadata-Version: 2.4\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        "License-Expression: MIT\n"
        "License-File: LICENSE\n"
    )
    (directory / "METADATA").write_text(metadata, encoding="utf-8")
    rows = [
        f"{directory.name}/METADATA,,",
        f"{directory.name}/RECORD,,",
        f"{directory.name}/LICENSE,,",
    ]
    (directory / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (directory / "LICENSE").write_text(f"{name} license text\n", encoding="utf-8")
    return directory


def build_evidence(
    tmp_path: Path, packages: tuple[tuple[str, str], ...] = (("alpha", "1.0.0"), ("beta", "2.1.0"))
) -> tuple[Path, Path]:
    """Run the real collector so the verifier is tested against its manifest."""

    site = tmp_path / "site"
    site.mkdir(parents=True)
    for name, version in packages:
        add_dist_info(site, name, version)
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, list(packages))
    output = tmp_path / "evidence"
    code = collect(site_packages=site, output_dir=output, runtime_lock=lock)
    assert code == 0, "fixture collection must be complete for verification tests"
    return output, lock


def read_manifest(evidence: Path) -> dict:
    return json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))


def write_manifest(evidence: Path, manifest: dict) -> None:
    (evidence / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_complete_delivery_verifies_against_the_shipped_lock_and_bytes(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 0

    output = capsys.readouterr().out
    assert "Verified 2 locked packages and 2 delivered text files" in output
    assert "STATUS: verified" in output
    assert "not legal clearance" in output
    manifest = read_manifest(evidence)
    assert manifest["runtime_lock"]["sha256"] in output


def test_cli_arguments_run_the_same_verification(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)

    code = verify_main(["--evidence-dir", str(evidence), "--runtime-lock", str(lock)])

    assert code == 0
    assert "STATUS: verified" in capsys.readouterr().out


def test_default_paths_match_the_dockerfile_delivery_paths() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")

    output_match = re.search(r"--output-dir (\S+)", text)
    lock_match = re.search(r"--runtime-lock (\S+)", text)
    assert output_match and output_match.group(1) == DEFAULT_EVIDENCE_DIR
    assert lock_match and lock_match.group(1) == DEFAULT_RUNTIME_LOCK
    assert not Path(DEFAULT_RUNTIME_LOCK).is_absolute()
    # The verifier ships in the image through the existing scripts copy.
    assert "COPY scripts ./scripts" in text
    assert (ROOT / VERIFIER).is_file()


def test_lock_digest_and_package_identity_mismatch_is_refused(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)
    manifest = read_manifest(evidence)
    manifest["runtime_lock"]["sha256"] = "f" * 64
    write_manifest(evidence, manifest)

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "does not match the shipped lock file" in capsys.readouterr().out

    evidence, lock = build_evidence(tmp_path / "second")
    manifest = read_manifest(evidence)
    manifest["packages"][0]["version"] = "9.9.9"
    write_manifest(evidence, manifest)

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    output = capsys.readouterr().out
    assert "no evidence for locked packages" in output
    assert "evidence for packages outside the shipped lock" in output


def test_grown_lock_inventory_is_refused(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)
    with lock.open("a", encoding="utf-8") as handle:
        handle.write(f"gamma==3.0.0 \\\n    --hash=sha256:{DIGEST}\n")

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1

    output = capsys.readouterr().out
    assert "does not match the shipped lock file" in output
    assert "no evidence for locked packages: gamma 3.0.0" in output


def test_tampered_bytes_and_extra_or_missing_files_are_refused(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)
    manifest = read_manifest(evidence)
    destination = evidence / manifest["packages"][0]["files"][0]["destination"]
    destination.write_bytes(b"tampered bytes\n")

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "do not match the recorded SHA-256" in capsys.readouterr().out

    evidence, lock = build_evidence(tmp_path / "second")
    manifest = read_manifest(evidence)
    (evidence / manifest["packages"][1]["files"][0]["destination"]).unlink()

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "missing from the evidence directory" in capsys.readouterr().out

    evidence, lock = build_evidence(tmp_path / "third")
    (evidence / "texts" / "unrecorded.txt").write_bytes(b"unrecorded\n")

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "unrecorded files in the evidence directory" in capsys.readouterr().out


def test_incomplete_status_problems_and_counts_are_refused(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)
    manifest = read_manifest(evidence)
    manifest["status"] = "incomplete"
    manifest["counts"]["locked"] = 3
    manifest["packages"][0]["status"] = "incomplete"
    manifest["packages"][0]["problems"] = ["collector acknowledged a problem"]
    write_manifest(evidence, manifest)

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1

    output = capsys.readouterr().out
    assert "manifest status must be 'complete'" in output
    assert "recorded problems: collector acknowledged a problem" in output
    assert "counts.locked is 3, expected 2" in output


def test_unsafe_destinations_and_symlinked_files_are_refused(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)
    manifest = read_manifest(evidence)
    manifest["packages"][0]["files"][0]["destination"] = "texts/../../escape"
    write_manifest(evidence, manifest)

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "destination is not a safe texts/" in capsys.readouterr().out

    evidence, lock = build_evidence(tmp_path / "second")
    manifest = read_manifest(evidence)
    target = evidence / manifest["packages"][0]["files"][0]["destination"]
    outside = tmp_path / "outside.txt"
    outside.write_bytes(target.read_bytes())
    try:
        target.unlink()
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")

    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "symlink" in capsys.readouterr().out


def test_missing_inputs_are_refused_without_accepting_anything(tmp_path, capsys) -> None:
    evidence, lock = build_evidence(tmp_path)

    assert verify(evidence_dir=tmp_path / "absent", runtime_lock=lock) == 2
    assert "evidence directory is missing" in capsys.readouterr().out
    assert verify(evidence_dir=evidence, runtime_lock=tmp_path / "absent.lock") == 2
    assert "runtime lock input is missing" in capsys.readouterr().out

    (evidence / "manifest.json").unlink()
    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "manifest.json is missing" in capsys.readouterr().out

    (evidence / "manifest.json").write_text("{ not json", encoding="utf-8")
    assert verify(evidence_dir=evidence, runtime_lock=lock) == 1
    assert "manifest.json is not valid JSON" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Release workflow: executed amd64 notice verification before the G19 PASS
# ---------------------------------------------------------------------------


def container_acceptance_steps() -> list[dict]:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["container-acceptance"]["steps"]


def step_run(step: dict) -> str:
    return str(step.get("run") or "")


def test_release_executes_the_verifier_in_the_amd64_digest_before_g19_pass() -> None:
    steps = container_acceptance_steps()
    verify_index = next(index for index, step in enumerate(steps) if VERIFIER in step_run(step))
    g19_index = next(index for index, step in enumerate(steps) if "--gate-id G19" in step_run(step))
    assert verify_index < g19_index, [step.get("name") for step in steps]

    step = steps[verify_index]
    run = step_run(step)
    assert not step.get("continue-on-error", False)
    assert not step.get("if")
    assert "set -euo pipefail" in run
    assert "docker run" in run
    assert "--rm" in run
    assert "--network none" in run
    assert "--platform linux/amd64" in run
    assert '"$IMAGE@$DIGEST"' in run
    assert "image-metadata/image-metadata.json" in run
    # The digest is format-checked, never trusted: an unvalidated value must
    # not reach the docker command.
    assert "re.fullmatch" in run
    # The image's own default (non-root) user runs the verifier: no explicit
    # user override, privilege escalation or alternative network mode.
    for forbidden in ("--user", "-u root", "sudo", "--privileged", "--network host", "docker exec"):
        assert forbidden not in run, forbidden

    # Both-platform manifest presence is inspected first; only amd64 is run.
    inspect = "\n".join(step_run(earlier) for earlier in steps[:verify_index])
    assert "linux/amd64" in inspect
    assert "linux/arm64" in inspect

    g19 = step_run(steps[g19_index])
    assert "amd64 and arm64 entries present" in g19
    assert "notice evidence executed and verified inside the amd64 image" in g19
    assert "arm64 image contents were not executed" in g19
    assert "not legal clearance" in g19
    assert '--image-digest "$DIGEST"' in g19
