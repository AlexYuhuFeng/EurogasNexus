"""Cut a new application version in one step.

    python scripts/release/bump_version.py 0.6.0            # writes every surface
    python scripts/release/bump_version.py 0.6.0 --dry-run  # shows what would change

It sets ``pyproject.toml``, syncs every machine-readable copy (Python, web, desktop,
lockfiles) through ``check_version_consistency.py --write``, updates the README and the
deployment guides, and moves the CHANGELOG's ``[Unreleased]`` entries under the new
version with today's date. Then commit, push, and tag ``vX.Y.Z-rc.1`` for a release
candidate; tag ``vX.Y.Z`` on the accepted commit for the stable release
(docs/release/RELEASE_CHANNELS.md).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_UNRELEASED = "## [Unreleased]"

# Prose files that state the current version, and the phrase that carries it.
_TEXT_SURFACES = (
    ("README.md", "Package version: `{}`"),
    ("README-CN.md", "软件包版本：`{}`"),
    ("CHANGELOG.md", "package version `{}`"),
    ("docs/deployment/DEPLOYMENT_ROLES-EN.md", None),
    ("docs/deployment/DEPLOYMENT_ROLES-CN.md", None),
    ("docs/operations/RELEASE_SIGNING.md", None),
    ("scripts/ci/fixtures/release.env", "EUROGAS_NEXUS_VERSION={}"),
)


def _current() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    if match is None:
        raise SystemExit("pyproject.toml has no [project] version")
    return match.group(1)


def _key(version: str) -> tuple[int, int, int]:
    match = _SEMVER.match(version)
    if match is None:
        raise SystemExit(f"{version!r} is not X.Y.Z")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _rewrite(relative: str, old: str, new: str, template: str | None) -> bool:
    path = ROOT / relative
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    updated = (
        text.replace(template.format(old), template.format(new), 1)
        if template
        else re.sub(rf"(?<![\d.]){re.escape(old)}(?![\d.])", new, text)
    )
    if updated != text:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def _cut_changelog(version: str, today: str) -> bool:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    if _UNRELEASED not in text or f"## [{version}]" in text:
        return False
    head, body = text.split(_UNRELEASED, 1)
    path.write_text(
        f"{head}{_UNRELEASED}\n\n## [{version}] - {today}{body}",
        encoding="utf-8",
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="new version, X.Y.Z")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    old, new = _current(), args.version
    if _key(new) <= _key(old):
        print(f"{new} is not later than the current version {old}", file=sys.stderr)
        return 2
    print(f"{old} -> {new}")
    if args.dry_run:
        for relative, _template in _TEXT_SURFACES:
            print(f"  would update {relative}")
        return 0

    pyproject = ROOT / "pyproject.toml"
    pyproject.write_text(
        re.sub(
            r'^version = "[^"]+"$',
            f'version = "{new}"',
            pyproject.read_text(encoding="utf-8"),
            count=1,
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )
    # --write syncs the machine-readable copies, then reports the prose surfaces still on
    # the old version; those are updated below and checked once at the end.
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/check_version_consistency.py"), "--write"],
        stdout=subprocess.DEVNULL,
    )
    # The env templates take the version from the configuration contract.
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/generate_env_template.py")],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    for relative, template in _TEXT_SURFACES:
        if _rewrite(relative, old, new, template):
            print(f"  updated {relative}")
    if _cut_changelog(new, date.today().isoformat()):
        print(f"  CHANGELOG: [Unreleased] entries now under [{new}]")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/check_version_consistency.py")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout + result.stderr, file=sys.stderr)
        return 1
    print(f"Version {new} is consistent. Commit, then tag v{new}-rc.1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
