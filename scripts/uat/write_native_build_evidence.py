#!/usr/bin/env python
"""Write hash-bound evidence for a native build-only acceptance artifact.

This script is the input/output boundary for
``.github/workflows/native-acceptance.yml``. It exists so the workflow does not
have to build JSON with platform-specific shell snippets, and so every path,
identity and artifact that reaches the uploaded evidence is validated rather
than trusted.

It deliberately:

* reads no environment variable, credential or remote service;
* runs only local ``git`` commands, without a shell, to bind the evidence to the
  checked-out commit and to refuse a dirty tracked worktree;
* refuses missing, symlinked, escaping or ambiguous build outputs;
* stages the exact bytes that are uploaded, hashes the staged bytes and writes a
  checksum file beside them;
* measures the installed Python, Node and Rust versions without a shell, refuses
  drift from the canonical declarations, and records canonical, expected and
  actual values beside the lock/build-input hashes;
* accepts only the reviewed trigger events (direct/manual dispatch, plus the
  ordinary-CI push and pull request callers) and records the actual event; and
* states plainly that the result is unsigned, unreviewed and build-only. It is
  not a customer release and no installed native UI was launched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVIDENCE_SCHEMA_VERSION = 1
EVIDENCE_DOCUMENT = "eurogas-nexus-native-build-evidence"
ARTIFACT_ROOT = Path("artifacts") / "native-acceptance"
EVIDENCE_DIRECTORY = "evidence"
EVIDENCE_FILENAME = "native-build-evidence.json"
CHECKSUMS_FILENAME = "checksums.sha256"
NATIVE_WORKFLOW = ".github/workflows/native-acceptance.yml"
# The shared workflow can observe these events: direct dispatch and manual CI
# report workflow_dispatch; ordinary CI reports push or pull_request. Anything
# else is refused rather than admitted as an unreviewed trigger path.
SUPPORTED_EVENT_NAMES = frozenset({"workflow_dispatch", "push", "pull_request"})

LOCK_FILES = (
    "requirements.lock",
    "requirements-runtime.lock",
    "requirements-build.lock",
    "clients/web/package-lock.json",
    "clients/desktop/package-lock.json",
    "clients/desktop/src-tauri/Cargo.lock",
)

BUILD_INPUT_FILES = (
    NATIVE_WORKFLOW,
    ".python-version",
    ".nvmrc",
    "rust-toolchain.toml",
    "pyproject.toml",
    "scripts/ci/install_linux_tauri_dependencies.sh",
    "scripts/ci/install_windows_canonical_python.ps1",
    "scripts/uat/write_native_build_evidence.py",
    "clients/web/package.json",
    "clients/desktop/package.json",
    "clients/desktop/src-tauri/Cargo.toml",
    "clients/desktop/src-tauri/tauri.conf.json",
)

TOOLCHAIN_FILES = (".python-version", ".nvmrc", "rust-toolchain.toml")

GitRunner = Callable[[Path, tuple[str, ...]], str]


@dataclass(frozen=True)
class PlatformSpec:
    """The authoritative three-platform native matrix."""

    runner_os: str
    runner_arch: str
    bundle: str
    package_suffix: str
    portable_mode: str


PLATFORMS: dict[str, PlatformSpec] = {
    "windows-x64": PlatformSpec("Windows", "X64", "nsis", ".exe", "raw"),
    "linux-x64": PlatformSpec("Linux", "X64", "deb", ".deb", "tar.gz"),
    "linux-arm64": PlatformSpec("Linux", "ARM64", "deb", ".deb", "tar.gz"),
}


class EvidenceError(RuntimeError):
    """A refused evidence input or an unsafe output path."""


def _sha256_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _sha256_stream(handle: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total


def _write_text_atomic(path: Path, text: str) -> None:
    if path.exists():
        raise EvidenceError(f"refusing to overwrite existing evidence output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".native-evidence-", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _validate_relative_text(value: str, field: str, *, max_length: int = 240) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} is required")
    if len(value) > max_length:
        raise EvidenceError(f"{field} is longer than {max_length} characters")
    if value.startswith(("/", "\\")) or "\\" in value or ":" in value:
        raise EvidenceError(f"{field} must be a relative POSIX path: {value!r}")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise EvidenceError(f"{field} contains a control character")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise EvidenceError(f"{field} contains an empty, '.' or '..' path segment")
    return value


def _resolve_relative(repo_root: Path, value: str, field: str) -> Path:
    text = _validate_relative_text(value, field)
    candidate = repo_root / text
    if candidate.is_symlink():
        raise EvidenceError(f"{field} may not be a symlink: {value!r}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(repo_root):
        raise EvidenceError(f"{field} escapes the repository: {value!r}")
    return resolved


def _validate_glob(pattern: str) -> str:
    text = _validate_relative_text(pattern, "package output glob")
    parts = text.split("/")
    if any(any(marker in part for marker in "*?[") for part in parts[:-1]):
        raise EvidenceError("package output glob may use wildcards only in its final component")
    if "**" in text:
        raise EvidenceError("package output glob may not be recursive")
    if not any(marker in parts[-1] for marker in "*?["):
        raise EvidenceError("package output glob must select the build output by pattern")
    return text


def _resolve_glob(repo_root: Path, pattern: str) -> Path:
    text = _validate_glob(pattern)
    try:
        matches = sorted(repo_root.glob(text))
    except (OSError, ValueError, NotImplementedError) as exc:
        raise EvidenceError(f"invalid package output glob {text!r}: {exc}") from exc
    if len(matches) != 1:
        raise EvidenceError(
            f"expected exactly one package output matching {text!r}, found {len(matches)}"
        )
    match = matches[0]
    if match.is_symlink() or not match.is_file():
        raise EvidenceError(f"package output is not a regular file: {text!r}")
    resolved = match.resolve()
    if not resolved.is_relative_to(repo_root):
        raise EvidenceError(f"package output escapes the repository: {text!r}")
    return resolved


def _validate_source_sha(value: str) -> str:
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise EvidenceError("source SHA must be 40 or 64 lowercase hexadecimal characters")
    return value


def _validate_run_field(value: str, field: str, pattern: str, max_length: int) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise EvidenceError(f"{field} is required and bounded to {max_length} characters")
    if not re.fullmatch(pattern, value):
        raise EvidenceError(f"{field} has an unexpected shape: {value!r}")
    return value


def _run_git(repo_root: Path, arguments: tuple[str, ...]) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise EvidenceError(f"cannot run git: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:300]
        raise EvidenceError(f"git {arguments[0]} failed: {detail}")
    return completed.stdout


def _read_git_state(
    repo_root: Path, source_sha: str, git_runner: GitRunner
) -> dict[str, Any]:
    head = git_runner(repo_root, ("rev-parse", "HEAD")).strip()
    if head != source_sha:
        raise EvidenceError(
            f"checked-out git HEAD {head!r} does not match the dispatched source SHA "
            f"{source_sha!r}"
        )
    status = git_runner(
        repo_root, ("status", "--porcelain=v1", "--untracked-files=no")
    )
    changes = [line for line in status.splitlines() if line.strip()]
    if changes:
        shown = "; ".join(changes[:5])
        raise EvidenceError(
            "tracked worktree changes are present after the build, so the source is not "
            f"the immutable commit the evidence would name: {shown}"
        )
    return {
        "git_sha": source_sha,
        "git_head": head,
        "tracked_worktree_clean": True,
    }


def _canonical_toolchain(repo_root: Path) -> dict[str, str]:
    python_path = repo_root / ".python-version"
    node_path = repo_root / ".nvmrc"
    rust_path = repo_root / "rust-toolchain.toml"
    for path in (python_path, node_path, rust_path):
        if not path.is_file():
            raise EvidenceError(f"canonical toolchain file is missing: {path.name}")
    python = python_path.read_text(encoding="utf-8").strip()
    node = node_path.read_text(encoding="utf-8").strip()
    rust_match = re.search(
        r'^channel\s*=\s*"([^"]+)"',
        rust_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not rust_match:
        raise EvidenceError("rust-toolchain.toml has no channel declaration")
    canonical = {"python": python, "node": node, "rust": rust_match.group(1)}
    for name, value in canonical.items():
        if not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise EvidenceError(f"canonical {name} version is not a full version: {value!r}")
    return canonical


def _compare_toolchain(
    canonical: Mapping[str, str], expected: Mapping[str, str]
) -> dict[str, str]:
    compared: dict[str, str] = {}
    for name in ("python", "node", "rust"):
        try:
            value = expected[name]
        except KeyError as exc:
            raise EvidenceError(f"expected toolchain is missing {name}") from exc
        if value != canonical[name]:
            raise EvidenceError(
                f"expected {name} toolchain {value!r} does not match the canonical "
                f"value {canonical[name]!r}"
            )
        compared[name] = value
    return compared


VersionRunner = Callable[[str], str]


def _python_version_text() -> str:
    info = sys.version_info
    return f"{info.major}.{info.minor}.{info.micro}"


def _run_version_command(tool: str) -> str:
    """Measure an installed toolchain version with a fixed argv and no shell."""
    if tool == "python":
        return _python_version_text()
    if tool == "node":
        arguments = ("node", "--version")
    elif tool == "rust":
        arguments = ("rustc", "--version")
    else:
        raise EvidenceError(f"unsupported toolchain probe: {tool}")
    try:
        completed = subprocess.run(
            arguments,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise EvidenceError(f"{tool} version probe could not start") from exc
    if completed.returncode != 0:
        raise EvidenceError(
            f"{tool} version probe failed with exit code {completed.returncode}"
        )
    return completed.stdout


def _parse_version_output(tool: str, output: str) -> str:
    text = output.strip()
    if tool == "python":
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
    elif tool == "node":
        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text)
    elif tool == "rust":
        match = re.fullmatch(r"rustc (\d+)\.(\d+)\.(\d+)(?: \([^()]*\))?", text)
    else:
        raise EvidenceError(f"unsupported toolchain probe: {tool}")
    if match is None:
        raise EvidenceError(f"actual {tool} version output is not a full X.Y.Z version")
    return ".".join(match.groups())


def _measure_actual_toolchain(
    canonical: Mapping[str, str], version_runner: VersionRunner
) -> dict[str, str]:
    actual: dict[str, str] = {}
    for tool in ("python", "node", "rust"):
        try:
            output = version_runner(tool)
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError(
                f"{tool} version probe failed: {type(exc).__name__}"
            ) from None
        observed = _parse_version_output(tool, output)
        if observed != canonical[tool]:
            raise EvidenceError(
                f"actual {tool} version {observed} does not match the canonical "
                f"value {canonical[tool]}"
            )
        actual[tool] = observed
    return actual


def _required_file_records(
    repo_root: Path, relatives: tuple[str, ...], category: str
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative in relatives:
        path = repo_root / relative
        if path.is_symlink() or not path.is_file():
            raise EvidenceError(f"required {category} file is missing: {relative}")
        resolved = path.resolve()
        if not resolved.is_relative_to(repo_root):
            raise EvidenceError(f"required {category} file escapes the repository: {relative}")
        digest, size = _sha256_path(resolved)
        records[relative] = {"sha256": digest, "bytes": size}
    return records


def _validate_platform(
    platform_label: str, runner_os: str, runner_arch: str, bundle: str
) -> PlatformSpec:
    try:
        spec = PLATFORMS[platform_label]
    except KeyError as exc:
        raise EvidenceError(
            f"platform label must be one of {', '.join(sorted(PLATFORMS))}: "
            f"{platform_label!r}"
        ) from exc
    if runner_os != spec.runner_os:
        raise EvidenceError(
            f"runner OS {runner_os!r} does not match platform {platform_label!r} "
            f"({spec.runner_os})"
        )
    if runner_arch != spec.runner_arch:
        raise EvidenceError(
            f"runner architecture {runner_arch!r} does not match platform "
            f"{platform_label!r} ({spec.runner_arch})"
        )
    if bundle != spec.bundle:
        raise EvidenceError(
            f"bundle {bundle!r} does not match platform {platform_label!r} ({spec.bundle})"
        )
    return spec


def _stage_copy(source: Path, destination: Path, field: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise EvidenceError(f"refusing to overwrite stale staged {field}: {destination}")
    shutil.copy2(source, destination)
    if source.is_symlink() or not source.is_file() or destination.is_symlink():
        raise EvidenceError(f"staged {field} is not a regular file")
    source_hash, source_size = _sha256_path(source)
    staged_hash, staged_size = _sha256_path(destination)
    if (source_hash, source_size) != (staged_hash, staged_size):
        raise EvidenceError(f"staged {field} bytes do not match the build output")


def _write_single_member_tar(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise EvidenceError(f"refusing to overwrite stale portable archive: {destination}")
    with tarfile.open(destination, mode="w:gz") as archive:
        info = archive.gettarinfo(str(source), arcname=source.name)
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        info.mode = 0o755
        with source.open("rb") as handle:
            archive.addfile(info, handle)

    with tarfile.open(destination, mode="r:gz") as archive:
        members = archive.getmembers()
        if len(members) != 1:
            raise EvidenceError("portable archive must contain exactly one member")
        member = members[0]
        if member.name != source.name or not member.isfile():
            raise EvidenceError("portable archive member does not match the native binary")
        if member.mode & 0o777 != 0o755:
            raise EvidenceError("portable archive member is not executable")
        extracted = archive.extractfile(member)
        if extracted is None:
            raise EvidenceError("portable archive member cannot be read")
        extracted_hash, extracted_size = _sha256_stream(extracted)

    source_hash, source_size = _sha256_path(source)
    if (extracted_hash, extracted_size) != (source_hash, source_size):
        raise EvidenceError("portable archive member bytes do not match the native binary")


def _artifact_record(
    *,
    label: str,
    source: Path,
    staged: Path,
    repo_root: Path,
    stage: Path,
    packaging: str,
    archive_member: str | None = None,
) -> dict[str, Any]:
    source_relative = source.resolve().relative_to(repo_root).as_posix()
    staged_relative = staged.resolve().relative_to(repo_root).as_posix()
    artifact_relative = staged.resolve().relative_to(stage).as_posix()
    source_hash, source_size = _sha256_path(source)
    staged_hash, staged_size = _sha256_path(staged)
    record: dict[str, Any] = {
        "label": label,
        "source_path": source_relative,
        "staged_path": staged_relative,
        "artifact_path": artifact_relative,
        "source_sha256": source_hash,
        "source_bytes": source_size,
        "sha256": staged_hash,
        "bytes": staged_size,
        "packaging": packaging,
    }
    if archive_member is not None:
        record["archive_member"] = archive_member
    return record


def _checksum_line(record: Mapping[str, Any]) -> str:
    return f"{record['sha256']}  {record['artifact_path']}"


def build_evidence(
    *,
    repo_root: Path,
    source_sha: str,
    platform_label: str,
    runner_os: str,
    runner_arch: str,
    bundle: str,
    package_glob: str,
    portable_source: str,
    stage_dir: str,
    output: str,
    expected_toolchain: Mapping[str, str],
    run_id: str,
    run_attempt: str,
    ref: str,
    event_name: str,
    repository: str,
    workflow_file: str = NATIVE_WORKFLOW,
    git_runner: GitRunner | None = None,
    version_runner: VersionRunner | None = None,
) -> dict[str, Any]:
    """Validate the inputs, stage the artifacts and write the evidence files."""

    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise EvidenceError(f"repository root is not a directory: {repo_root}")

    source_sha = _validate_source_sha(source_sha)
    spec = _validate_platform(platform_label, runner_os, runner_arch, bundle)
    if workflow_file != NATIVE_WORKFLOW:
        raise EvidenceError(f"workflow file must be {NATIVE_WORKFLOW}")
    _validate_run_field(run_id, "run id", r"[0-9]{1,20}", 20)
    _validate_run_field(run_attempt, "run attempt", r"[0-9]{1,20}", 20)
    _validate_run_field(ref, "workflow ref", r"refs/[A-Za-z0-9._/@+-]{1,190}", 200)
    if event_name not in SUPPORTED_EVENT_NAMES:
        raise EvidenceError(
            "native acceptance evidence is only valid for workflow_dispatch, push "
            "or pull_request"
        )
    _validate_run_field(
        repository,
        "repository",
        r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}",
        201,
    )

    stage = _resolve_relative(root, stage_dir, "stage directory")
    allowed_root = (root / ARTIFACT_ROOT).resolve()
    if stage.parent != allowed_root:
        raise EvidenceError(
            "stage directory must be a direct child of "
            f"{ARTIFACT_ROOT.as_posix()}: {stage_dir!r}"
        )
    if stage.name != platform_label:
        raise EvidenceError("stage directory name must equal the platform label")
    if stage.is_symlink():
        raise EvidenceError("stage directory may not be a symlink")
    if stage.exists() and not stage.is_dir():
        raise EvidenceError("stage directory exists but is not a directory")
    if stage.exists() and any(stage.iterdir()):
        raise EvidenceError("stage directory is not empty; refusing stale or mixed artifacts")

    expected_output = stage / EVIDENCE_DIRECTORY / EVIDENCE_FILENAME
    output_path = _resolve_relative(root, output, "evidence output")
    if output_path != expected_output.resolve():
        raise EvidenceError(
            "evidence output must be "
            f"{(stage / EVIDENCE_DIRECTORY / EVIDENCE_FILENAME).relative_to(root).as_posix()}"
        )
    checksums_path = stage / CHECKSUMS_FILENAME
    if output_path.exists() or checksums_path.exists():
        raise EvidenceError("evidence output already exists; refusing to overwrite")

    runner = git_runner or _run_git
    source = _read_git_state(root, source_sha, runner)
    canonical = _canonical_toolchain(root)
    expected = _compare_toolchain(canonical, expected_toolchain)
    actual = _measure_actual_toolchain(
        canonical, version_runner or _run_version_command
    )
    toolchain_files = _required_file_records(root, TOOLCHAIN_FILES, "toolchain")
    locks = _required_file_records(root, LOCK_FILES, "lock")
    build_inputs = _required_file_records(root, BUILD_INPUT_FILES, "build input")

    package_source = _resolve_glob(root, package_glob)
    if package_source.suffix.lower() != spec.package_suffix:
        raise EvidenceError(
            f"package output must end with {spec.package_suffix}: {package_source.name}"
        )
    portable_path = _resolve_relative(root, portable_source, "portable native binary")
    if portable_path.is_symlink() or not portable_path.is_file():
        raise EvidenceError(f"portable native binary is missing: {portable_source}")
    if not portable_path.is_relative_to(root):
        raise EvidenceError("portable native binary escapes the repository")
    if spec.portable_mode == "raw" and portable_path.suffix.lower() != ".exe":
        raise EvidenceError("Windows portable native binary must be the built .exe")
    if spec.portable_mode == "tar.gz" and portable_path.suffix.lower() == ".exe":
        raise EvidenceError("Linux portable native binary must be the Linux build output")

    stage.mkdir(parents=True, exist_ok=True)
    package_staged = (
        stage
        / "package"
        / (
            f"Eurogas-Nexus-{platform_label}-setup{spec.package_suffix}"
            if spec.bundle == "nsis"
            else f"Eurogas-Nexus-{platform_label}{spec.package_suffix}"
        )
    )
    _stage_copy(package_source, package_staged, "package")

    if spec.portable_mode == "raw":
        portable_staged = stage / "portable" / f"eurogas-nexus-desktop-{platform_label}.exe"
        _stage_copy(portable_path, portable_staged, "portable native binary")
        portable_packaging = "executable"
        archive_member = None
    else:
        portable_staged = (
            stage / "portable" / f"eurogas-nexus-desktop-{platform_label}.tar.gz"
        )
        _write_single_member_tar(portable_path, portable_staged)
        portable_packaging = "tar.gz"
        archive_member = portable_path.name

    package_record = _artifact_record(
        label="package",
        source=package_source,
        staged=package_staged,
        repo_root=root,
        stage=stage,
        packaging="bundle",
    )
    portable_record = _artifact_record(
        label="portable",
        source=portable_path,
        staged=portable_staged,
        repo_root=root,
        stage=stage,
        packaging=portable_packaging,
        archive_member=archive_member,
    )

    checksums_text = "\n".join(
        _checksum_line(record) for record in (package_record, portable_record)
    )
    _write_text_atomic(checksums_path, checksums_text + "\n")
    checksums_hash, checksums_size = _sha256_path(checksums_path)

    evidence = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "document": EVIDENCE_DOCUMENT,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "declarations": {
            "scope": "native-build-only",
            "status": "BUILT_NOT_ACCEPTED",
            "unsigned": True,
            "unreviewed": True,
            "customer_release": False,
            "release_published": False,
            "native_ui_executed": False,
            "installed_launch_verified": False,
            "signing_performed": False,
        },
        "statement": (
            "Unsigned, unreviewed internal build-only artifact. This evidence binds "
            "build outputs, source and toolchain hashes only. No installed native UI "
            "launch, code signing, release publication, deployment or customer "
            "acceptance was performed."
        ),
        "source": source,
        "workflow": {
            "file": workflow_file,
            "run_id": run_id,
            "run_attempt": run_attempt,
            "ref": ref,
            "event_name": event_name,
            "repository": repository,
        },
        "build": {
            "platform_label": platform_label,
            "runner_os": runner_os,
            "runner_arch": runner_arch,
            "bundle": bundle,
        },
        "toolchain": {
            "canonical": canonical,
            "expected": expected,
            "actual": actual,
            "files": toolchain_files,
        },
        "locks": locks,
        "build_inputs": build_inputs,
        "artifacts": {
            "package": package_record,
            "portable": portable_record,
        },
        "checksums": {
            "algorithm": "sha256",
            "path": checksums_path.relative_to(root).as_posix(),
            "artifact_path": CHECKSUMS_FILENAME,
            "sha256": checksums_hash,
            "bytes": checksums_size,
        },
        "evidence_path": output_path.relative_to(root).as_posix(),
        "evidence_artifact_path": (
            Path(EVIDENCE_DIRECTORY) / EVIDENCE_FILENAME
        ).as_posix(),
    }

    _write_text_atomic(
        output_path,
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
    )
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--platform-label", required=True)
    parser.add_argument("--runner-os", required=True)
    parser.add_argument("--runner-arch", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--package-glob", required=True)
    parser.add_argument("--portable-source", required=True)
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--node-version", required=True)
    parser.add_argument("--rust-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-file", default=NATIVE_WORKFLOW)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        evidence = build_evidence(
            repo_root=Path(args.repo_root),
            source_sha=args.source_sha,
            platform_label=args.platform_label,
            runner_os=args.runner_os,
            runner_arch=args.runner_arch,
            bundle=args.bundle,
            package_glob=args.package_glob,
            portable_source=args.portable_source,
            stage_dir=args.stage_dir,
            output=args.output,
            expected_toolchain={
                "python": args.python_version,
                "node": args.node_version,
                "rust": args.rust_version,
            },
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            ref=args.ref,
            event_name=args.event_name,
            repository=args.repository,
            workflow_file=args.workflow_file,
        )
    except EvidenceError as exc:
        print(f"native build evidence refused: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": "EVIDENCE_WRITTEN",
                "build_status": "BUILT",
                "acceptance_status": "NOT_ACCEPTED",
                "scope": evidence["declarations"]["scope"],
                "unsigned": evidence["declarations"]["unsigned"],
                "unreviewed": evidence["declarations"]["unreviewed"],
                "customer_release": evidence["declarations"]["customer_release"],
                "native_ui_executed": evidence["declarations"]["native_ui_executed"],
                "evidence": evidence["evidence_path"],
                "package_sha256": evidence["artifacts"]["package"]["sha256"],
                "portable_sha256": evidence["artifacts"]["portable"]["sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
