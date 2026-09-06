"""Repository-level release metadata helpers for the release scripts.

Import-safe and side-effect free. The repository root is derived from this
file's location, never from the current working directory.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eurogas_nexus.release.versioning import (
    ReleaseChannel,
    build_release_tag,
    parse_app_version,
    parse_release_tag,
)

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_NAME = "Eurogas Nexus"
PACKAGE_NAME = "eurogas-nexus"


def load_pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def canonical_app_version() -> str:
    return str(load_pyproject()["project"]["version"]).strip()


def latest_alembic_revision() -> str:
    """Resolve the current Alembic head without importing alembic or env.py."""

    versions = sorted((ROOT / "alembic" / "versions").glob("*.py"))
    if not versions:
        raise RuntimeError("No Alembic migration files found.")
    # Migration filenames use a zero-padded monotonic prefix; the highest
    # prefix is the head of the expand-only chain.
    revisions: list[tuple[str, str]] = []
    for path in versions:
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("revision"):
                _, raw = stripped.split("=", 1)
                revisions.append((path.name, raw.strip().strip("\"' ,").replace('"', "")))
                break
    if not revisions:
        raise RuntimeError("No Alembic revision identifiers found.")
    return sorted(revisions)[-1][1]


def git_output(*args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def current_git_sha() -> str | None:
    return git_output("rev-parse", "HEAD")


def git_short_sha(sha: str, length: int = 12) -> str:
    return sha[:length].lower()


def is_ancestor_of_main(sha: str) -> bool:
    """Return whether ``sha`` is in the protected mainline lineage.

    GitHub workflows fetch the full history for release runs; local dry-runs
    use the tracked ``origin/main`` ref.
    """

    result = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", sha, "origin/main"],
        capture_output=False,
        check=False,
    )
    if result.returncode != 0:
        return False
    return True


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def resolve_release_context(
    *,
    channel: str,
    git_sha: str | None = None,
    git_ref: str | None = None,
    build_run_id: str | None = None,
    build_run_number: int | None = None,
    tag: str | None = None,
    require_mainline: bool = False,
) -> dict[str, Any]:
    """Resolve release identity into one JSON-safe context.

    The context is the only place where channel, application version, tag and
    commit are combined. Artifact names and image tags must be derived from it
    rather than from hard-coded strings.
    """

    resolved_channel = ReleaseChannel(channel)
    app_version = canonical_app_version()
    parsed_version = parse_app_version(app_version)
    resolved_sha = (git_sha or current_git_sha() or "").strip().lower()
    if not resolved_sha:
        raise RuntimeError("A git SHA is required to resolve release metadata.")

    if tag:
        parsed_tag = parse_release_tag(tag)
        if parsed_tag.app_version.core != parsed_version.core:
            raise ValueError(
                f"Tag {tag!r} does not match canonical application version {app_version}."
            )
        if parsed_tag.channel is not resolved_channel:
            raise ValueError(
                f"Tag {tag!r} is {parsed_tag.channel.value} but channel "
                f"{resolved_channel.value} was resolved."
            )
        release_version = parsed_tag.tag
        prerelease_number = parsed_tag.prerelease_number
    else:
        if resolved_channel is ReleaseChannel.STABLE:
            raise ValueError(
                "Stable releases require a pushed semantic tag vX.Y.Z; "
                "workflow_dispatch stable is not permitted."
            )
        number = build_run_number or 1
        release_version = build_release_tag(
            parsed_version,
            resolved_channel,
            prerelease_number=number,
            git_sha=resolved_sha[:12],
        )
        prerelease_number = number

    if require_mainline and not is_ancestor_of_main(resolved_sha):
        raise ValueError(
            f"Commit {resolved_sha} is not in the protected mainline lineage; "
            "preview/RC dispatch is restricted to mainline commits."
        )

    return {
        "schema_version": 1,
        "product_name": PRODUCT_NAME,
        "package_name": PACKAGE_NAME,
        "app_version": app_version,
        "release_version": release_version,
        "channel": resolved_channel.value,
        "prerelease_number": prerelease_number,
        "git_sha": resolved_sha,
        "git_short_sha": git_short_sha(resolved_sha),
        "git_ref": (git_ref or "").strip(),
        "build_run_id": (build_run_id or "").strip(),
        "build_timestamp": utc_now(),
        "source_repository": "https://github.com/AlexYuhuFeng/EurogasNexus",
        "api_image": "ghcr.io/alexyuhufeng/eurogasnexus-api",
        "database_schema_revision": latest_alembic_revision(),
    }


def write_context(path: str | Path, context: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(context, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def read_context(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit("This module is a helper for the release scripts, not an entrypoint.")
