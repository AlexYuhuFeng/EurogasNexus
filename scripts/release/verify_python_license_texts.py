#!/usr/bin/env python
"""Verify the Python license/notice evidence delivered inside the API image.

Read-only companion to ``scripts/release/collect_python_license_texts.py``: it
re-reads the collector's ``manifest.json`` together with the bytes it covers
and refuses to accept the delivery unless every recorded claim still holds. It
re-derives the locked package inventory with the same shared structured lock
reader (``scripts/release/generate_sboms.py``) instead of re-parsing the lock,
and it reuses the collector's path-refusal helpers so collection and
verification refuse the same unsafe path shapes.

Check together:

* the manifest is a well-formed object of the expected schema and kind with
  ``status: complete``;
* the shipped ``requirements-runtime.lock`` still hashes to the recorded
  SHA-256 and still resolves to exactly the recorded package name/version set
  (no missing, extra or duplicated package evidence);
* every package is ``collected`` with no recorded problems and at least one
  delivered file, the recorded counts agree with the evidence, and there are
  no recorded global problems;
* every recorded destination is a safe relative ``texts/<name>/<version>/...``
  path with no traversal, absolute path, backslash or symlink/junction
  component, and no unrecorded file exists anywhere in the evidence tree;
* every delivered file's bytes re-hash to its recorded SHA-256 and match its
  recorded size.

The default paths match the delivered image (``deploy/runtime/Dockerfile.api``):
the evidence directory is
``/usr/share/licenses/eurogas-nexus/python-license-texts`` and the lock is the
image's own ``requirements-runtime.lock`` copy relative to its ``/app`` workdir.

Exit codes:
    0 - evidence verified against the shipped lock and the delivered bytes;
    1 - the manifest is missing, malformed or incomplete, or does not match
        the shipped lock or the delivered bytes;
    2 - the evidence directory or the lock input is missing or refused.

This is a technical delivery check inside the artifact: it makes no
legal-clearance or redistribution claim, never interprets a license and never
waives a license finding. Failures print paths, counts and hashes only, never
file contents or secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release import generate_sboms  # noqa: E402
from scripts.release.collect_python_license_texts import (  # noqa: E402
    _has_reparse_point,
    _relative_parts,
)
from scripts.release.release_artifacts import sha256_file  # noqa: E402

DEFAULT_EVIDENCE_DIR = "/usr/share/licenses/eurogas-nexus/python-license-texts"
#: Relative to the image workdir (``/app`` in deploy/runtime/Dockerfile.api).
DEFAULT_RUNTIME_LOCK = "requirements-runtime.lock"

MANIFEST_NAME = "manifest.json"
EXPECTED_KIND = "python-license-text-evidence"
EXPECTED_SCHEMA_VERSION = 1
STATUS_COMPLETE = "complete"
STATUS_COLLECTED = "collected"
FILE_ORIGINS = frozenset({"license-file", "record"})
STATUS_COUNT_KEYS = ("locked", STATUS_COLLECTED, "incomplete", "unresolved", "files")
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
SPDX_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _plain_int(value: object) -> bool:
    """True for a genuine integer; ``bool`` is not accepted as a count."""

    return isinstance(value, int) and not isinstance(value, bool)


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Read ``manifest.json`` as a JSON object, or explain why it cannot be used."""

    if _has_reparse_point(path):
        return None, [f"{MANIFEST_NAME} is a symlink or junction (refused)"]
    if not path.is_file():
        return None, [f"{MANIFEST_NAME} is missing or not a regular file"]
    try:
        raw = path.read_bytes()
    except OSError as error:
        return None, [f"{MANIFEST_NAME} is unreadable ({type(error).__name__})"]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, [f"{MANIFEST_NAME} is not valid UTF-8"]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, [f"{MANIFEST_NAME} is not valid JSON"]
    if not isinstance(data, dict):
        return None, [f"{MANIFEST_NAME} must be a JSON object"]
    return data, []


def _walk_evidence(root: Path) -> tuple[list[str], list[str]]:
    """List the regular files below ``root``; refuse symlinks/junctions anywhere."""

    files: list[str] = []
    problems: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        directory = Path(dirpath)
        for name in sorted(dirnames):
            path = directory / name
            if _has_reparse_point(path):
                problems.append(
                    "refusing a symlink or junction inside the evidence tree: "
                    f"{path.relative_to(root).as_posix()!r}"
                )
        dirnames[:] = [name for name in dirnames if not _has_reparse_point(directory / name)]
        for name in sorted(filenames):
            path = directory / name
            relative = path.relative_to(root).as_posix()
            if _has_reparse_point(path):
                problems.append(
                    f"refusing a symlink or junction inside the evidence tree: {relative!r}"
                )
            elif not path.is_file():
                problems.append(f"not a regular file inside the evidence tree: {relative!r}")
            else:
                files.append(relative)
    return files, problems


def _file_problems(
    *,
    evidence: Path,
    package_label: str,
    index: int,
    entry: object,
    seen_destinations: dict[str, str],
) -> tuple[list[str], str | None]:
    """Check one recorded file entry; return its problems and its destination."""

    problems: list[str] = []
    label = f"{package_label} files[{index}]"
    if not isinstance(entry, dict):
        return [f"{label} is not an object"], None
    origin = entry.get("origin")
    if origin not in FILE_ORIGINS:
        problems.append(f"{label}: origin must be one of {sorted(FILE_ORIGINS)}, got {origin!r}")
    source = entry.get("source")
    if not isinstance(source, str) or _relative_parts(source) is None:
        problems.append(f"{label}: source is not a safe relative path")
    destination = entry.get("destination")
    parts = _relative_parts(destination) if isinstance(destination, str) else None
    if parts is None or len(parts) < 4 or parts[0] != "texts":
        problems.append(f"{label}: destination is not a safe texts/<package>/<version>/<file> path")
        return problems, None
    if destination in seen_destinations:
        problems.append(
            f"{label}: destination {destination!r} duplicates {seen_destinations[destination]}"
        )
        return problems, None
    current = evidence
    for part in parts:
        current = current / part
        if _has_reparse_point(current):
            problems.append(f"{label}: refusing to follow a symlink or junction at {part!r}")
            return problems, destination
    path = evidence.joinpath(*parts)
    if not path.is_file():
        problems.append(f"{label}: delivered file is missing or not a regular file")
        return problems, destination
    recorded_digest = entry.get("sha256")
    if not isinstance(recorded_digest, str) or SHA256_HEX.fullmatch(recorded_digest) is None:
        problems.append(f"{label}: sha256 is not a lowercase 64-hex digest")
    elif sha256_file(path) != recorded_digest:
        problems.append(f"{label}: delivered bytes do not match the recorded SHA-256")
    size = entry.get("size_bytes")
    actual_size = path.stat().st_size
    if not _plain_int(size) or size < 0 or size != actual_size:
        problems.append(
            f"{label}: size_bytes does not match the delivered file ({actual_size} bytes)"
        )
    return problems, destination


def _evidence_problems(
    evidence: Path,
    manifest: dict[str, Any],
    lock: Path,
    lock_digest: str,
    inventory: Any,
) -> list[str]:
    """Check the manifest, the lock binding and the delivered files."""

    problems: list[str] = []

    if manifest.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        problems.append(
            f"schema_version must be {EXPECTED_SCHEMA_VERSION}, "
            f"got {manifest.get('schema_version')!r}"
        )
    if manifest.get("kind") != EXPECTED_KIND:
        problems.append(f"kind must be {EXPECTED_KIND!r}, got {manifest.get('kind')!r}")
    if manifest.get("status") != STATUS_COMPLETE:
        problems.append(
            f"manifest status must be {STATUS_COMPLETE!r} for a delivered image, "
            f"got {manifest.get('status')!r}"
        )
    generated_at = manifest.get("generated_at_utc")
    if not isinstance(generated_at, str) or SPDX_TIMESTAMP.fullmatch(generated_at) is None:
        problems.append("generated_at_utc must be a UTC 'YYYY-MM-DDThh:mm:ssZ' timestamp")
    limits = manifest.get("limits")
    if (
        not isinstance(limits, list)
        or not limits
        or any(not isinstance(item, str) for item in limits)
    ):
        problems.append("limits must be a non-empty list of strings")
    global_problems = manifest.get("global_problems")
    if not isinstance(global_problems, list) or any(
        not isinstance(item, str) for item in global_problems
    ):
        problems.append("global_problems must be a list of strings")
    elif global_problems:
        problems.append("recorded global problems: " + "; ".join(sorted(global_problems)))

    lock_block = manifest.get("runtime_lock")
    if not isinstance(lock_block, dict):
        problems.append("runtime_lock block is missing or not an object")
    else:
        recorded_digest = lock_block.get("sha256")
        if not isinstance(recorded_digest, str) or SHA256_HEX.fullmatch(recorded_digest) is None:
            problems.append("runtime_lock.sha256 is not a lowercase 64-hex digest")
        elif recorded_digest != lock_digest:
            problems.append(
                "runtime_lock.sha256 does not match the shipped lock file: recorded "
                f"{recorded_digest}, actual {lock_digest}"
            )
        recorded_path = lock_block.get("path")
        if not isinstance(recorded_path, str) or _relative_parts(recorded_path) is None:
            problems.append("runtime_lock.path is not a safe relative path")
        elif PurePosixPath(recorded_path).name != lock.name:
            problems.append(
                f"runtime_lock.path {recorded_path!r} does not name the verified lock {lock.name!r}"
            )
        locked_packages = lock_block.get("locked_packages")
        if not _plain_int(locked_packages) or locked_packages != len(inventory.packages):
            problems.append(
                "runtime_lock.locked_packages does not equal the shipped lock's package count"
            )
        if lock_block.get("excluded_entries") != inventory.excluded:
            problems.append(
                "runtime_lock.excluded_entries does not match the shipped lock inventory"
            )

    packages = manifest.get("packages")
    if not isinstance(packages, list) or not packages:
        problems.append("packages must be a non-empty list")
        packages = []

    locked_identities = {(item["name"], item["version"]) for item in inventory.packages}
    seen_identities: set[tuple[str, str]] = set()
    seen_destinations: dict[str, str] = {}
    status_counts = {STATUS_COLLECTED: 0, "incomplete": 0, "unresolved": 0}
    delivered_files = 0
    for index, package in enumerate(packages):
        label = f"packages[{index}]"
        if not isinstance(package, dict):
            problems.append(f"{label} is not an object")
            continue
        name, version = package.get("name"), package.get("version")
        if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
            problems.append(f"{label} has no usable name/version")
            continue
        label = f"{name} {version}"
        identity = (name, version)
        if identity in seen_identities:
            problems.append(f"{label}: duplicate package evidence")
        seen_identities.add(identity)

        status = package.get("status")
        if status not in status_counts:
            problems.append(f"{label}: unrecognized status {status!r}")
            continue
        status_counts[status] += 1
        if status != STATUS_COLLECTED:
            reason = package.get("reason")
            detail = reason if isinstance(reason, str) and reason else "no reason recorded"
            problems.append(f"{label}: status is {status!r} ({detail})")
        recorded_problems = package.get("problems")
        if not isinstance(recorded_problems, list) or any(
            not isinstance(item, str) for item in recorded_problems
        ):
            problems.append(f"{label}: problems must be a list of strings")
        elif recorded_problems:
            problems.append(f"{label}: recorded problems: {'; '.join(sorted(recorded_problems))}")

        distribution = package.get("distribution")
        if (
            not isinstance(distribution, str)
            or _relative_parts(distribution) is None
            or not distribution.endswith(".dist-info")
        ):
            problems.append(f"{label}: distribution is not a plain .dist-info directory name")

        files = package.get("files")
        if not isinstance(files, list) or not files:
            problems.append(f"{label}: no delivered text files")
            continue
        for file_index, entry in enumerate(files):
            entry_problems, destination = _file_problems(
                evidence=evidence,
                package_label=label,
                index=file_index,
                entry=entry,
                seen_destinations=seen_destinations,
            )
            problems.extend(entry_problems)
            if destination is not None:
                seen_destinations[destination] = f"{label} files[{file_index}]"
                delivered_files += 1

    missing = sorted(locked_identities - seen_identities)
    unexpected = sorted(seen_identities - locked_identities)
    if missing:
        problems.append(
            "no evidence for locked packages: "
            + ", ".join(f"{name} {version}" for name, version in missing)
        )
    if unexpected:
        problems.append(
            "evidence for packages outside the shipped lock: "
            + ", ".join(f"{name} {version}" for name, version in unexpected)
        )

    counts = manifest.get("counts")
    expected_counts = {
        "locked": len(inventory.packages),
        STATUS_COLLECTED: status_counts[STATUS_COLLECTED],
        "incomplete": status_counts["incomplete"],
        "unresolved": status_counts["unresolved"],
        "files": delivered_files,
    }
    if not isinstance(counts, dict):
        problems.append("counts block is missing or not an object")
    else:
        for key in STATUS_COUNT_KEYS:
            value = counts.get(key)
            if not _plain_int(value) or value != expected_counts[key]:
                problems.append(f"counts.{key} is {value!r}, expected {expected_counts[key]}")

    site = manifest.get("site_packages")
    if not isinstance(site, dict):
        problems.append("site_packages block is missing or not an object")
    else:
        directory_name = site.get("directory_name")
        if not isinstance(directory_name, str) or not directory_name:
            problems.append("site_packages.directory_name must be a non-empty string")
        scanned = site.get("distributions_scanned")
        if not _plain_int(scanned) or scanned < len(packages):
            problems.append(
                "site_packages.distributions_scanned does not cover every delivered package"
            )

    actual_files, walk_problems = _walk_evidence(evidence)
    problems.extend(walk_problems)
    recorded_files = {MANIFEST_NAME, *seen_destinations}
    extra = sorted(set(actual_files) - recorded_files)
    absent = sorted(recorded_files - set(actual_files))
    if extra:
        problems.append("unrecorded files in the evidence directory: " + ", ".join(extra))
    if absent:
        problems.append("recorded files missing from the evidence directory: " + ", ".join(absent))

    return problems


def verify(*, evidence_dir: Path, runtime_lock: Path) -> int:
    """Verify the delivered evidence and return the process exit code."""

    evidence = Path(evidence_dir)
    lock = Path(runtime_lock)

    if not evidence.is_dir() or _has_reparse_point(evidence):
        print(f"evidence directory is missing, not a directory or refused: {evidence}")
        return 2
    if not lock.is_file() or _has_reparse_point(lock):
        print(f"runtime lock input is missing, not a file or refused: {lock}")
        return 2

    manifest, load_problems = _load_manifest(evidence / MANIFEST_NAME)
    if manifest is None:
        print(f"delivered license/notice evidence is not acceptable: {evidence}")
        for problem in load_problems:
            print(f"  {problem}")
        print("STATUS: not verified")
        return 1

    lock_digest = sha256_file(lock)
    try:
        inventory = generate_sboms.python_packages(lock)
    except generate_sboms.SbomInputError as error:
        print("shipped runtime lock could not be inventoried (fail-closed); nothing accepted:")
        for item in sorted(error.errors):
            print(f"  {item}")
        print("STATUS: not verified")
        return 1

    problems = _evidence_problems(evidence, manifest, lock, lock_digest, inventory)
    packages = manifest.get("packages")
    delivered = (
        sum(
            len(package["files"])
            for package in packages
            if isinstance(package, dict) and isinstance(package.get("files"), list)
        )
        if isinstance(packages, list)
        else 0
    )
    if problems:
        print(f"delivered license/notice evidence failed verification: {evidence}")
        for problem in sorted(problems):
            print(f"  {problem}")
        print("STATUS: not verified (technical check only; no legal-clearance claim)")
        return 1
    print(
        f"Verified {len(packages)} locked packages and {delivered} delivered text files "
        f"against runtime-lock SHA-256 {lock_digest}."
    )
    print(
        "STATUS: verified (technical evidence only; not legal clearance and not a "
        "redistribution review)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; defaults match the delivered image paths."""

    parser = argparse.ArgumentParser(
        description=(
            "Verify the Python license/notice text evidence delivered inside the API "
            "image against the shipped runtime lock and the delivered bytes."
        )
    )
    parser.add_argument(
        "--evidence-dir",
        default=DEFAULT_EVIDENCE_DIR,
        help=(
            "delivered evidence directory containing manifest.json and texts/ "
            f"(default: {DEFAULT_EVIDENCE_DIR})"
        ),
    )
    parser.add_argument(
        "--runtime-lock",
        default=DEFAULT_RUNTIME_LOCK,
        help=(
            "runtime lock the evidence must still match, relative to the image "
            f"workdir (default: {DEFAULT_RUNTIME_LOCK})"
        ),
    )
    args = parser.parse_args(argv)
    return verify(evidence_dir=Path(args.evidence_dir), runtime_lock=Path(args.runtime_lock))


if __name__ == "__main__":
    raise SystemExit(main())
