#!/usr/bin/env python
"""Package the Server operator deployment bundle from one explicit file allowlist.

The bundle is a customer-facing artifact: it must contain exactly the payload
reviewed for operator delivery and nothing else, so recursive directory copying
is deliberately not used here. `package_deployment_bundle.policy.json` is the
single source of truth for the selection, and packaging fails closed when a
required file is missing, a path is unsafe, a source is a symlink (including a
symlinked repository root), or two entries collide.

`package_deployment_bundle.sh` and `package_deployment_bundle.ps1` are thin
wrappers around this module, so the three entry points cannot drift.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = Path(__file__).with_name("package_deployment_bundle.policy.json")
SUPPORTED_POLICY_SCHEMA = 1

_POLICY_KEYS = frozenset(
    {
        "schema_version",
        "description",
        "archive_name",
        "bundle_root",
        "forbidden_member_globs",
        "entries",
    }
)
_ENTRY_KEYS = frozenset({"source", "destination", "required", "purpose"})


class PackagingError(RuntimeError):
    """Raised when the bundle cannot be built exactly as the policy specifies."""


@dataclass(frozen=True)
class Entry:
    """One allowlisted file: a repository source and its bundle destination."""

    source: str
    destination: str
    required: bool
    purpose: str


@dataclass(frozen=True)
class Policy:
    """Validated packaging policy."""

    schema_version: int
    archive_name: str
    bundle_root: str
    entries: tuple[Entry, ...]
    forbidden_member_globs: tuple[str, ...]


def _validate_relative_path(value: object, *, field: str) -> str:
    """Return a bundle-relative POSIX path, or raise on anything unsafe."""

    if not isinstance(value, str) or not value.strip():
        raise PackagingError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise PackagingError(f"{field} must not carry surrounding whitespace: {value!r}")
    if "\\" in value:
        raise PackagingError(f"{field} must use forward slashes: {value!r}")
    for segment in value.split("/"):
        if segment in {"", ".", ".."}:
            raise PackagingError(f"{field} contains an unsafe path segment: {value!r}")
        if ":" in segment or any(ord(character) < 32 for character in segment):
            raise PackagingError(f"{field} contains a reserved character: {value!r}")
    return value


def _validate_archive_name(value: object) -> str:
    if not isinstance(value, str) or not value.endswith(".zip"):
        raise PackagingError("policy archive_name must be a .zip file name")
    if "/" in value or "\\" in value or ":" in value or value in {".", ".."}:
        raise PackagingError(f"policy archive_name must be a plain file name: {value!r}")
    return value


def load_policy(policy_path: str | Path = POLICY_PATH) -> Policy:
    """Load and validate the deployment bundle policy manifest."""

    path = Path(policy_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PackagingError(f"deployment bundle policy is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise PackagingError(f"deployment bundle policy is not valid JSON: {path}") from error
    if not isinstance(raw, dict):
        raise PackagingError("deployment bundle policy must be a JSON object")
    unknown_policy_keys = sorted(set(raw) - _POLICY_KEYS)
    if unknown_policy_keys:
        raise PackagingError(
            f"deployment bundle policy has unknown keys: {', '.join(unknown_policy_keys)}"
        )
    if raw.get("schema_version") != SUPPORTED_POLICY_SCHEMA:
        raise PackagingError(
            "unsupported deployment bundle policy schema_version "
            f"{raw.get('schema_version')!r}; this packager supports {SUPPORTED_POLICY_SCHEMA}"
        )
    for key in ("archive_name", "bundle_root", "forbidden_member_globs", "entries"):
        if key not in raw:
            raise PackagingError(f"deployment bundle policy is missing the {key!r} key")
    archive_name = _validate_archive_name(raw["archive_name"])
    bundle_root = _validate_relative_path(raw["bundle_root"], field="policy bundle_root")
    if "/" in bundle_root:
        raise PackagingError("policy bundle_root must be a single directory name")
    globs = raw["forbidden_member_globs"]
    if not isinstance(globs, list) or not all(
        isinstance(pattern, str) and pattern for pattern in globs
    ):
        raise PackagingError("policy forbidden_member_globs must be a list of non-empty strings")
    raw_entries = raw["entries"]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise PackagingError("policy entries must be a non-empty list")

    entries: list[Entry] = []
    destinations: dict[str, str] = {}
    sources: dict[str, str] = {}
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            raise PackagingError(f"policy entries[{index}] must be an object")
        unknown_entry_keys = sorted(set(item) - _ENTRY_KEYS)
        if unknown_entry_keys:
            raise PackagingError(
                f"policy entries[{index}] has unknown keys: {', '.join(unknown_entry_keys)}"
            )
        missing_entry_keys = sorted(_ENTRY_KEYS - set(item))
        if missing_entry_keys:
            raise PackagingError(
                f"policy entries[{index}] is missing keys: {', '.join(missing_entry_keys)}"
            )
        source = _validate_relative_path(item["source"], field=f"entries[{index}].source")
        destination = _validate_relative_path(
            item["destination"], field=f"entries[{index}].destination"
        )
        if not isinstance(item["required"], bool):
            raise PackagingError(f"policy entries[{index}].required must be a boolean")
        purpose = item["purpose"]
        if not isinstance(purpose, str) or not purpose.strip():
            raise PackagingError(f"policy entries[{index}].purpose must be a non-empty string")
        if destination in destinations:
            raise PackagingError(f"duplicate bundle destination in policy: {destination}")
        if source in sources:
            raise PackagingError(f"duplicate bundle source in policy: {source}")
        destinations[destination] = source
        sources[source] = destination
        entries.append(
            Entry(
                source=source,
                destination=destination,
                required=item["required"],
                purpose=purpose,
            )
        )

    return Policy(
        schema_version=SUPPORTED_POLICY_SCHEMA,
        archive_name=archive_name,
        bundle_root=bundle_root,
        entries=tuple(entries),
        forbidden_member_globs=tuple(globs),
    )


def forbidden_match(member: str, policy: Policy) -> str | None:
    """Return the forbidden glob matching a bundle-relative member, if any.

    A glob containing `/` is matched against the whole relative path (a leading
    `**/` also matches the path without that prefix); a glob without `/` is
    matched against the member's file name only.
    """

    name = member.rsplit("/", 1)[-1]
    for pattern in policy.forbidden_member_globs:
        if "/" in pattern:
            if fnmatch.fnmatchcase(member, pattern):
                return pattern
            if pattern.startswith("**/") and fnmatch.fnmatchcase(member, pattern[3:]):
                return pattern
        elif fnmatch.fnmatchcase(name, pattern):
            return pattern
    return None


def _assert_within(path: Path, root: Path, *, description: str) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise PackagingError(f"{description} escapes {resolved_root}: {path}")


def _is_reparse_point(path: Path) -> bool:
    """True for a symlink or a Windows junction; both are refused, not followed."""

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _resolve_source(repo_root: Path, entry: Entry) -> Path:
    """Resolve an allowlisted source, refusing to follow any reparse point."""

    if _is_reparse_point(repo_root):
        raise PackagingError(
            "refusing to package from a symlinked repository root "
            f"(symlink or junction): {repo_root}"
        )
    candidate = repo_root
    for segment in PurePosixPath(entry.source).parts:
        candidate = candidate / segment
        if _is_reparse_point(candidate):
            raise PackagingError(
                f"refusing to follow a symlink or junction while packaging "
                f"{entry.source!r}: {candidate}"
            )
    source = candidate.resolve()
    _assert_within(source, repo_root, description=f"bundle source {entry.source!r}")
    if not source.is_file():
        raise PackagingError(f"bundle source is not a regular file: {entry.source!r}")
    return source


def _stage_payload(repo_root: Path, policy: Policy, staging_root: Path) -> list[str]:
    """Copy the allowlisted files into the staging tree, returning destinations."""

    staged: list[str] = []
    for entry in policy.entries:
        candidate = repo_root / entry.source
        if not candidate.exists() and not candidate.is_symlink():
            if entry.required:
                raise PackagingError(
                    f"required bundle file is missing from the repository: {entry.source} "
                    f"({entry.purpose})"
                )
            continue
        source = _resolve_source(repo_root, entry)
        target = staging_root / policy.bundle_root / entry.destination
        _assert_within(
            target, staging_root, description=f"bundle destination {entry.destination!r}"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        staged.append(entry.destination)
    if not staged:
        raise PackagingError("deployment bundle policy selected no files")
    return staged


def _verify_members(members: list[str], policy: Policy, *, staged: list[str]) -> None:
    """Fail unless the archive contains exactly the staged, allowed members."""

    if len(members) != len(set(members)):
        raise PackagingError("archive contains duplicate members")
    expected = sorted(f"{policy.bundle_root}/{destination}" for destination in staged)
    if sorted(members) != expected:
        missing = sorted(set(expected) - set(members))
        unexpected = sorted(set(members) - set(expected))
        raise PackagingError(
            f"archive members differ from the policy: missing={missing} unexpected={unexpected}"
        )
    for member in members:
        if member.startswith("/") or ".." in PurePosixPath(member).parts:
            raise PackagingError(f"archive member has an unsafe path: {member!r}")
        prefix = f"{policy.bundle_root}/"
        if not member.startswith(prefix):
            raise PackagingError(f"archive member is outside {policy.bundle_root!r}: {member!r}")
        relative = member[len(prefix) :]
        matched = forbidden_match(relative, policy)
        if matched:
            raise PackagingError(
                f"archive member {relative!r} matches forbidden pattern {matched!r}"
            )


def _create_staging_root() -> Path:
    """Create an empty staging directory outside the repository.

    A plain uniquely named `mkdir` is used instead of `tempfile.mkdtemp` so the
    staging directory inherits the platform's default permissions on Windows.
    """

    base = Path(tempfile.gettempdir())
    candidate = base / f"eurogas-nexus-deployment-{uuid.uuid4().hex[:12]}"
    try:
        candidate.mkdir()
    except OSError as error:
        raise PackagingError(
            f"could not create a staging directory at {candidate}: {error}"
        ) from error
    return candidate


def package(
    output_dir: str | Path,
    *,
    repo_root: str | Path = ROOT,
    policy_path: str | Path = POLICY_PATH,
) -> Path:
    """Build the deployment bundle archive and return its path."""

    policy = load_policy(policy_path)
    repo = Path(repo_root)
    if not repo.is_dir():
        raise PackagingError(f"repository root is not a directory: {repo}")
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / policy.archive_name

    staging_root = _create_staging_root()
    try:
        staged = _stage_payload(repo, policy, staging_root)
        partial = target_dir / f"{policy.archive_name}.partial"
        partial.unlink(missing_ok=True)
        try:
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as bundle:
                for destination in sorted(staged):
                    bundle.write(
                        staging_root / policy.bundle_root / destination,
                        f"{policy.bundle_root}/{destination}",
                    )
            with zipfile.ZipFile(partial) as bundle:
                _verify_members(bundle.namelist(), policy, staged=staged)
            partial.replace(archive)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
        if staging_root.exists():
            print(
                f"warning: staging directory could not be removed: {staging_root}",
                file=sys.stderr,
            )
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="dist/releases",
        help="directory that receives the bundle archive",
    )
    args = parser.parse_args(argv)
    try:
        archive = package(args.output_dir)
    except PackagingError as error:
        print(f"deployment bundle packaging failed: {error}", file=sys.stderr)
        return 1
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
