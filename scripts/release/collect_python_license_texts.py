#!/usr/bin/env python
"""Collect installed Python license/notice text evidence for the runtime lock.

Bounded release utility with no third-party imports: for every third-party
package in the enforced Python runtime lock (``requirements-runtime.lock`` by
default, parsed by the shared structured lock reader in
``scripts/release/generate_sboms.py``) it locates the matching installed
distribution under an explicitly given site-packages directory and copies the
license/notice text files that the distribution itself declares or records:

* ``METADATA`` ``License-File`` headers are the primary source. Header values
  are read with the standard library email parser and resolved at the
  ``<dist-info>/licenses/<path>`` location (PEP 639 wheel layout) or the
  legacy ``<dist-info>/<path>`` location; the resolved file must still be
  listed in the matching distribution's own ``RECORD``.
* Only when a distribution declares no ``License-File`` headers, its ``RECORD``
  (parsed as CSV) is scanned for legacy license/notice/copying/copyright
  basenames. RECORD rows outside the site-packages tree (pip records installed
  console scripts at paths such as ``../../Scripts/*.exe``) are disclosed and
  skipped, never resolved or copied.

Nothing is downloaded, installed, invented, substituted or reformatted: every
copied byte comes from a regular file inside the given site-packages tree, and
the SHA-256 of each copy is re-checked against the source. Absolute paths,
traversal, non-portable separators and symlink/junction path components are
refused, and the output directory must not already exist, so a run never
overwrites earlier evidence.

A run is complete only when every locked package was matched to exactly one
installed distribution by exact name/version and yielded at least one text
with no problem; a missing, duplicate, version-mismatched, metadata-broken or
text-less distribution makes the run non-zero, and a declared ``License-File``
that cannot be used is reported instead of being replaced by a RECORD-derived
text. Incomplete runs still write ``manifest.json`` and keep partial texts,
clearly marked ``status: incomplete`` with per-package reasons. The manifest
records only relative paths, the runtime-lock SHA-256, each package's exact
lock name/version, installed dist-info directory, declared-license evidence
and every copied file's source path, size and SHA-256.

This is technical evidence collection, not legal clearance: it does not
determine license obligations, does not prove the copied texts are complete or
authoritative, and does not cover packages outside the runtime lock,
vendored/native/OS/container components or build/test-only Python tooling.
Ordinary CI runs this collector on main-branch pushes as an independent
review-evidence job against a hash-installed runtime-lock venv (see
``.github/workflows/ci.yml``); an incomplete collection fails that job and
still uploads the manifest and any partial texts. Release publishing consumes
no report from this utility: that CI artifact stays review evidence. The API
runtime image (``deploy/runtime/Dockerfile.api``) also runs this collector in
its final runtime stage for delivery, against that stage's own installed
purelib and the lock shipped in the image, and a missing or incomplete
collection fails the image build.

Usage:
    python scripts/release/collect_python_license_texts.py \
        --site-packages .deps \
        --output-dir release-evidence/python-license-texts
    python scripts/release/collect_python_license_texts.py \
        --site-packages .deps --output-dir .tmp_work/python-license-texts \
        --runtime-lock requirements-runtime.lock
"""

from __future__ import annotations

import argparse
import csv
import email
import email.errors
import email.policy
import io
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ci.audit_dependencies import _read_metadata  # noqa: E402
from scripts.release import generate_sboms  # noqa: E402
from scripts.release.release_artifacts import sha256_file  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_LOCK = ROOT / "requirements-runtime.lock"

SCHEMA_VERSION = 1

STATUS_COMPLETE = "complete"
STATUS_COLLECTED = "collected"
STATUS_INCOMPLETE = "incomplete"
STATUS_UNRESOLVED = "unresolved"

ORIGIN_LICENSE_FILE = "license-file"
ORIGIN_RECORD = "record"

#: A RECORD entry is legacy license-text evidence only when one of these tokens
#: is a whole token of its basename (delimited by start/end or ``.``/``_``/``-``
#: or whitespace): ``LICENSE``, ``LICENSE.txt``, ``MIT-LICENSE``,
#: ``COPYING.LESSER``, ``NOTICE.md`` and ``copyright`` qualify, while code files
#: such as ``licenses.py`` or ``__init__.py`` never do.
_LICENSE_BASENAME_TOKENS = frozenset({"license", "licence", "copying", "copyright", "notice"})
_BASENAME_SPLIT_RE = re.compile(r"[._\-\s]+")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_PEP503_RUN_RE = re.compile(r"[-_.]+")

MANIFEST_LIMITS = [
    (
        "technical evidence only: this collection is not legal clearance, not a license "
        "interpretation and not a redistribution approval"
    ),
    (
        "only the exact third-party inventory of the given runtime lock is collected; "
        "packages outside that lock, the build/test toolchain and OS/container/native "
        "components are not covered"
    ),
    (
        "only files that the matching installed distribution declares via METADATA "
        "License-File headers or lists in its own RECORD with a recognized "
        "license/notice/copying/copyright basename are copied; no text is downloaded, "
        "invented or substituted, and RECORD rows outside the site-packages tree are "
        "disclosed and never followed"
    ),
    (
        "copied texts are recorded as-is: completeness, authority and applicability of "
        "each text are not verified, and declared license expressions are not "
        "cross-checked against them"
    ),
    (
        "a declared License-File that cannot be used is reported instead of being "
        "replaced by a RECORD-derived text"
    ),
]


@dataclass(frozen=True)
class InstalledDistribution:
    """One ``*.dist-info`` directory found under the given site-packages tree."""

    dist_info_name: str
    path: Path
    name: str
    version: str | None
    license_files: tuple[str, ...]
    problem: str | None


@dataclass(frozen=True)
class SourceCandidate:
    """One resolved, inside-site-packages license/notice text file to copy."""

    origin: str
    declared: str
    relative: str
    path: Path


def _normalized(value: object) -> str:
    """Collapse header folding and whitespace runs into single spaces."""

    return " ".join(str(value).split())


def _canonical_name(name: str) -> str:
    """PEP 503 canonical name (same rule as the shared SBOM reader's PyPI names)."""

    return _PEP503_RUN_RE.sub("-", name).lower()


def _has_reparse_point(path: Path) -> bool:
    """True for a symlink or a Windows junction; both are refused, not followed."""

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _relative_parts(relative: str) -> tuple[str, ...] | None:
    """Split a portable relative path, refusing absolute/traversal/non-portable forms."""

    if not relative or "\x00" in relative or "\\" in relative:
        return None
    if relative.startswith("/") or _WINDOWS_DRIVE_RE.match(relative):
        return None
    parts = PurePosixPath(relative).parts
    if not parts or any(part in {"..", ""} for part in parts):
        return None
    return parts


def _resolve_source_file(site_packages: Path, relative: str) -> tuple[Path | None, str | None]:
    """Resolve one declared/recorded path inside site-packages, or refuse it.

    ``site_packages`` is the resolved tree root. A path that is absolute, uses
    a Windows drive or backslashes, contains ``..``, crosses a symlink or
    junction, is not a regular file, or resolves outside the tree is rejected
    with a reason instead of being copied.
    """

    parts = _relative_parts(relative)
    if parts is None:
        return None, (
            f"refusing unsafe path {relative!r} (absolute, traversal, empty or "
            "non-portable separator)"
        )
    current = site_packages
    for part in parts:
        current = current / part
        if _has_reparse_point(current):
            return None, f"refusing to follow a symlink or junction: {relative!r}"
    if not current.is_file():
        return None, f"recorded or declared file is missing or not a regular file: {relative!r}"
    resolved = current.resolve()
    if site_packages not in resolved.parents:
        return None, f"refusing a path outside the site-packages tree: {relative!r}"
    return current, None


def _read_record_paths(
    dist_info_dir: Path,
) -> tuple[list[str] | None, list[str], str | None]:
    """Parse ``<dist-info>/RECORD`` (CSV ``path,hash,size``).

    Returns (paths inside the site-packages tree, skipped rows outside that
    recorded package area, problem). Every data row must carry exactly three
    fields; a missing, symlinked, unreadable, non-UTF-8, malformed, empty or
    duplicate-path RECORD is refused instead of being partially used. Rows
    whose path is absolute, traverses outside the tree or uses a non-portable
    separator are *skipped and disclosed* rather than resolved: pip itself
    records installed console scripts at paths like ``../../Scripts/*.exe``
    or ``../../../bin/*``, and such rows must never be followed or copied.
    """

    record_path = dist_info_dir / "RECORD"
    if _has_reparse_point(record_path):
        return None, [], "symlinked or junctioned RECORD (refused)"
    if not record_path.is_file():
        return None, [], "no RECORD file"
    try:
        raw = record_path.read_bytes()
    except OSError as error:
        return None, [], f"unreadable RECORD ({type(error).__name__})"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, [], "RECORD is not valid UTF-8"
    paths: list[str] = []
    skipped: list[str] = []
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        if len(row) != 3:
            return None, [], f"malformed RECORD row with {len(row)} fields (expected 3)"
        raw_path = row[0].strip()
        if not raw_path:
            return None, [], "malformed RECORD row with an empty path field"
        parts = _relative_parts(raw_path)
        if parts is None:
            skipped.append(raw_path)
            continue
        paths.append("/".join(parts))
    if not paths:
        return None, [], "empty RECORD"
    if len(set(paths)) != len(paths):
        return None, [], "duplicate RECORD paths"
    return paths, skipped, None


def _metadata_headers(
    metadata_path: Path,
) -> tuple[str | None, str | None, list[str], str | None]:
    """Return (Name, Version, License-File values, problem) via the email parser."""

    if _has_reparse_point(metadata_path):
        return None, None, [], "symlinked or junctioned METADATA (refused)"
    if not metadata_path.is_file():
        return None, None, [], "no METADATA file"
    try:
        raw = metadata_path.read_bytes()
    except OSError as error:
        return None, None, [], f"unreadable METADATA ({type(error).__name__})"
    try:
        message = email.message_from_bytes(raw, policy=email.policy.default)
    except email.errors.MessageError as error:
        return None, None, [], f"unparseable METADATA ({type(error).__name__})"
    defects = sorted({type(defect).__name__ for defect in message.defects})
    if defects:
        return None, None, [], f"malformed METADATA ({', '.join(defects)})"
    name = _normalized(message.get("Name", ""))
    version = _normalized(message.get("Version", ""))
    license_files = [
        value
        for value in (_normalized(item) for item in message.get_all("License-File", []))
        if value
    ]
    if not name:
        return None, None, license_files, "METADATA has no non-blank string 'Name' header"
    if not version:
        return None, None, license_files, "METADATA has no non-blank string 'Version' header"
    return name, version, license_files, None


def _declared_license_evidence(metadata_path: Path) -> tuple[str | None, list[str]]:
    """Return (structural problem, declared-license evidence) for one METADATA.

    ``scripts.ci.audit_dependencies._read_metadata`` is reused deliberately so
    ``License-Expression`` precedence, every ``License ::`` classifier and
    email/RFC 5322 header-folding rules keep their single implementation. The
    evidence is recorded for review only: this utility neither interprets nor
    approves any license term.
    """

    _name, evidence, problem = _read_metadata(metadata_path)
    return problem, evidence


def _distribution_key_from_dir_name(dist_info_name: str) -> str:
    """Best-effort name key when a distribution's METADATA cannot be used.

    The directory name is ``{name}-{version}.dist-info`` with wheel filename
    escaping, so the version is the last ``-``-separated field when it starts
    with a digit. The key only lets a locked package fail loudly with the
    metadata problem instead of silently reporting "no installed distribution".
    """

    stem = dist_info_name.removesuffix(".dist-info")
    head, separator, tail = stem.rpartition("-")
    if separator and tail and tail[0].isdigit():
        return head
    return stem


def _scan_distributions(site_packages: Path) -> dict[str, list[InstalledDistribution]]:
    """Index every ``*.dist-info`` directory by canonical METADATA package name."""

    index: dict[str, list[InstalledDistribution]] = {}
    for entry in sorted(site_packages.glob("*.dist-info")):
        dist_info_name = entry.name
        if _has_reparse_point(entry):
            record = InstalledDistribution(
                dist_info_name=dist_info_name,
                path=entry,
                name=_distribution_key_from_dir_name(dist_info_name),
                version=None,
                license_files=(),
                problem="symlinked or junctioned .dist-info directory (refused)",
            )
        elif not entry.is_dir():
            continue
        else:
            name, version, license_files, problem = _metadata_headers(entry / "METADATA")
            record = InstalledDistribution(
                dist_info_name=dist_info_name,
                path=entry,
                name=name or _distribution_key_from_dir_name(dist_info_name),
                version=version,
                license_files=tuple(license_files),
                problem=problem,
            )
        index.setdefault(_canonical_name(record.name), []).append(record)
    return index


def _match_distribution(
    locked_name: str, locked_version: str, index: dict[str, list[InstalledDistribution]]
) -> tuple[InstalledDistribution | None, str | None]:
    """Match one lock entry to exactly one installed distribution, or explain why not."""

    candidates = index.get(_canonical_name(locked_name), [])
    if not candidates:
        return None, f"no installed distribution found for {locked_name!r}"
    if len(candidates) > 1:
        names = ", ".join(sorted(dist.dist_info_name for dist in candidates))
        return None, (
            f"duplicate installed distributions for {locked_name!r} ({names}); exactly one "
            "matching distribution is required"
        )
    dist = candidates[0]
    if dist.problem is not None:
        return None, f"{dist.dist_info_name}: unusable installed metadata ({dist.problem})"
    if dist.version != locked_version:
        return None, (
            f"version mismatch for {locked_name!r}: lock pins {locked_version!r}, installed "
            f"distribution {dist.dist_info_name} reports {dist.version!r}"
        )
    return dist, None


def _license_basename_matches(relative: str) -> bool:
    """True when a recorded basename is a recognized license/notice text name."""

    basename = PurePosixPath(relative).name.lower()
    if PurePosixPath(basename).suffix in {
        ".py",
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".exe",
        ".js",
        ".ts",
    }:
        return False
    return any(token in _LICENSE_BASENAME_TOKENS for token in _BASENAME_SPLIT_RE.split(basename))


def _resolve_declared_file(
    dist: InstalledDistribution, site_packages: Path, record_paths: list[str], declared: str
) -> tuple[SourceCandidate | None, list[str]]:
    """Resolve one ``License-File`` value inside the distribution's RECORD area.

    PEP 639 wheels install license files under ``<dist-info>/licenses/`` while
    legacy metadata pointed straight at ``<dist-info>/<path>``; both locations
    are tried and the resolved file must still appear in the distribution's own
    RECORD, so an unrecorded or outside-tree file is never copied.
    """

    parts = _relative_parts(declared)
    if parts is None:
        return None, [
            f"License-File {declared!r} is not a safe relative path (absolute, traversal, "
            "empty or non-portable separator)"
        ]
    joined = "/".join(parts)
    record_set = set(record_paths)
    reasons: list[str] = []
    attempted: set[str] = set()
    for relative in (f"{dist.dist_info_name}/licenses/{joined}", f"{dist.dist_info_name}/{joined}"):
        if relative in attempted:
            continue
        attempted.add(relative)
        if relative not in record_set:
            reasons.append(f"{relative!r} is not recorded in the distribution's RECORD")
            continue
        path, error = _resolve_source_file(site_packages, relative)
        if error is not None:
            reasons.append(error)
            continue
        return (
            SourceCandidate(
                origin=ORIGIN_LICENSE_FILE, declared=declared, relative=relative, path=path
            ),
            [],
        )
    return None, [
        f"{dist.dist_info_name}: License-File {declared!r} could not be used: " + "; ".join(reasons)
    ]


def _record_fallback_candidates(
    dist: InstalledDistribution, site_packages: Path, record_paths: list[str]
) -> tuple[list[SourceCandidate], list[str]]:
    """Collect recognized license text files recorded by the distribution itself."""

    candidates: list[SourceCandidate] = []
    problems: list[str] = []
    for relative in record_paths:
        if not _license_basename_matches(relative):
            continue
        path, error = _resolve_source_file(site_packages, relative)
        if error is not None:
            problems.append(f"{dist.dist_info_name}: {error}")
            continue
        candidates.append(
            SourceCandidate(origin=ORIGIN_RECORD, declared=relative, relative=relative, path=path)
        )
    if not candidates and not problems:
        problems.append(
            f"{dist.dist_info_name}: no License-File metadata and no license, notice, "
            "copying or copyright text recorded in RECORD"
        )
    return candidates, problems


def _sanitize_file_name(value: str) -> str:
    """Reduce one path component to a deterministic, portable destination name."""

    cleaned = _UNSAFE_FILENAME_RE.sub("_", value).strip("._")
    return cleaned or "text"


def _unique_file_name(relative: str, taken: set[str]) -> str:
    """Return a deterministic destination file name that never collides."""

    base = _sanitize_file_name(PurePosixPath(relative).name)
    if base not in taken:
        taken.add(base)
        return base
    counter = 2
    while f"{base}__{counter}" in taken:
        counter += 1
    name = f"{base}__{counter}"
    taken.add(name)
    return name


def _collect_package(
    *,
    locked: dict,
    dist: InstalledDistribution,
    site_packages: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Copy one package's declared or recorded license texts and build its report."""

    name, version = locked["name"], locked["version"]
    metadata_problem, evidence = _declared_license_evidence(dist.path / "METADATA")
    record_paths, skipped_record_paths, record_problem = _read_record_paths(dist.path)
    problems: list[str] = []
    if metadata_problem is not None:
        problems.append(metadata_problem)
    if record_problem is not None:
        problems.append(f"{dist.dist_info_name}: {record_problem}")

    candidates: list[SourceCandidate] = []
    if not problems and record_paths is not None:
        if dist.license_files:
            seen_declared: set[str] = set()
            seen_relative: set[str] = set()
            for declared in dist.license_files:
                if declared in seen_declared:
                    continue
                seen_declared.add(declared)
                candidate, declared_problems = _resolve_declared_file(
                    dist, site_packages, record_paths, declared
                )
                if candidate is None:
                    problems.extend(declared_problems)
                elif candidate.relative in seen_relative:
                    continue
                else:
                    seen_relative.add(candidate.relative)
                    candidates.append(candidate)
        else:
            candidates, problems = _record_fallback_candidates(dist, site_packages, record_paths)

    files: list[dict[str, Any]] = []
    taken: set[str] = set()
    for candidate in candidates:
        destination = (
            f"texts/{_canonical_name(name)}/{_sanitize_file_name(version)}/"
            f"{_unique_file_name(candidate.relative, taken)}"
        )
        target = output_dir / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(candidate.path, target)
        except OSError as error:
            problems.append(
                f"{dist.dist_info_name}: could not copy {candidate.relative!r} "
                f"({type(error).__name__})"
            )
            continue
        source_digest = sha256_file(candidate.path)
        copied_digest = sha256_file(target)
        if source_digest != copied_digest:
            problems.append(
                f"{dist.dist_info_name}: copied bytes for {candidate.relative!r} do not "
                "match the source; the copy was removed"
            )
            target.unlink(missing_ok=True)
            continue
        files.append(
            {
                "origin": candidate.origin,
                "source": candidate.relative,
                "destination": destination,
                "sha256": copied_digest,
                "size_bytes": target.stat().st_size,
            }
        )

    if not files:
        status = STATUS_UNRESOLVED
    elif problems:
        status = STATUS_INCOMPLETE
    else:
        status = STATUS_COLLECTED

    report: dict[str, Any] = {
        "name": name,
        "version": version,
        "declared_license": " | ".join(evidence) if evidence else None,
        "distribution": dist.dist_info_name,
        "status": status,
        "files": files,
        "skipped_record_paths": sorted(skipped_record_paths),
        "problems": sorted(problems),
    }
    if status == STATUS_UNRESOLVED:
        report["reason"] = "; ".join(sorted(problems)) or ("no license or notice text collected")
    return report


def _recorded_input_path(path: Path) -> str:
    """Record an input path repository-relative when possible, else by name only."""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def collect(
    *,
    site_packages: Path,
    output_dir: Path,
    runtime_lock: Path = DEFAULT_RUNTIME_LOCK,
    now: datetime | None = None,
) -> int:
    """Collect license/notice text evidence and return the process exit code.

    Returns:
        0 when every locked package was collected, 1 when the run is incomplete
        (including an unusable lock or nothing to audit), 2 for a refused or
        missing input/output path.
    """

    site = Path(site_packages)
    output = Path(output_dir)
    lock = Path(runtime_lock)

    if not site.is_dir():
        print(f"site-packages directory not found: {site}")
        return 2
    if output.exists():
        print(f"refusing to overwrite existing output path: {output}")
        return 2

    try:
        inventory = generate_sboms.python_packages(lock)
    except generate_sboms.SbomInputError as error:
        print("Python runtime lock could not be inventoried (fail-closed; nothing was collected):")
        print("  " + "\n  ".join(sorted(error.errors)))
        return 1

    try:
        output.mkdir(parents=True)
    except FileExistsError:
        print(f"refusing to overwrite existing output directory: {output}")
        return 2
    except OSError as error:
        print(f"could not create output directory ({type(error).__name__}): {output}")
        return 2

    resolved_site = site.resolve()
    index = _scan_distributions(resolved_site)

    counts = {
        "locked": len(inventory.packages),
        STATUS_COLLECTED: 0,
        STATUS_INCOMPLETE: 0,
        STATUS_UNRESOLVED: 0,
        "files": 0,
    }
    reports: list[dict[str, Any]] = []

    def _sort_key(package: dict) -> tuple[str, str]:
        return (_canonical_name(package["name"]), package["version"])

    for item in sorted(inventory.packages, key=_sort_key):
        dist, match_problem = _match_distribution(item["name"], item["version"], index)
        if dist is None:
            report: dict[str, Any] = {
                "name": item["name"],
                "version": item["version"],
                "declared_license": None,
                "distribution": None,
                "status": STATUS_UNRESOLVED,
                "reason": match_problem,
                "files": [],
                "skipped_record_paths": [],
                "problems": [match_problem],
            }
        else:
            report = _collect_package(
                locked=item, dist=dist, site_packages=resolved_site, output_dir=output
            )
        reports.append(report)
        counts[report["status"]] += 1
        counts["files"] += len(report["files"])

    global_problems: list[str] = []
    if not index:
        global_problems.append(
            "no installed distributions (*.dist-info) found under the given site-packages "
            "directory; nothing could be collected"
        )
    status = (
        STATUS_COMPLETE
        if reports
        and not global_problems
        and all(report["status"] == STATUS_COLLECTED for report in reports)
        else STATUS_INCOMPLETE
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "python-license-text-evidence",
        "status": status,
        "generated_at_utc": generate_sboms.utc_timestamp(now),
        "runtime_lock": {
            "path": _recorded_input_path(lock),
            "sha256": sha256_file(lock),
            "locked_packages": len(inventory.packages),
            "excluded_entries": inventory.excluded,
        },
        "site_packages": {
            "directory_name": resolved_site.name,
            "distributions_scanned": sum(len(items) for items in index.values()),
        },
        "counts": counts,
        "global_problems": sorted(global_problems),
        "packages": reports,
        "limits": MANIFEST_LIMITS,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        f"Collected license/notice text evidence for {counts[STATUS_COLLECTED]} of "
        f"{counts['locked']} locked Python packages ({counts['files']} files)."
    )
    print(
        f"Runtime lock: {manifest['runtime_lock']['path']} "
        f"(sha256 {manifest['runtime_lock']['sha256']})"
    )
    print(f"Output: {output}")
    skipped_total = sum(len(report["skipped_record_paths"]) for report in reports)
    if skipped_total:
        print(
            f"Skipped {skipped_total} RECORD path entries outside the recorded package "
            "area (never followed or copied); they are disclosed per package in the manifest."
        )
    for problem in global_problems:
        print(f"  problem: {problem}")
    for report in reports:
        if report["status"] == STATUS_COLLECTED:
            continue
        detail = report.get("reason") or "; ".join(report["problems"])
        print(f"  {report['name']} {report['version']}: {report['status']}: {detail}")
    if status == STATUS_COMPLETE:
        print(
            "STATUS: complete (technical evidence only; not legal clearance and not a "
            "redistribution review)"
        )
        return 0
    print(
        "STATUS: incomplete (manifest.json and any partial texts were preserved; the exit "
        "code is non-zero because collection did not cover every locked package)"
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: explicit site-packages and output directory are required."""

    parser = argparse.ArgumentParser(
        description=(
            "Collect installed Python license/notice text evidence for the exact "
            "requirements-runtime.lock name/version inventory."
        )
    )
    parser.add_argument(
        "--site-packages",
        required=True,
        help="installed site-packages directory that contains the *.dist-info trees",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="new directory for manifest.json and the texts/ tree; must not exist",
    )
    parser.add_argument(
        "--runtime-lock",
        default=str(DEFAULT_RUNTIME_LOCK),
        help="enforced Python runtime lock (default: requirements-runtime.lock)",
    )
    args = parser.parse_args(argv)
    return collect(
        site_packages=Path(args.site_packages),
        output_dir=Path(args.output_dir),
        runtime_lock=Path(args.runtime_lock),
    )


if __name__ == "__main__":
    raise SystemExit(main())
