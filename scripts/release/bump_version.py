"""Cut a new application version in one step.

    python scripts/release/bump_version.py 0.6.0            # writes every surface
    python scripts/release/bump_version.py 0.6.0 --dry-run  # shows what would change
    python scripts/release/bump_version.py 1.0.0b1          # a beta (1.0.0-beta.1)

It sets ``pyproject.toml``, syncs every machine-readable copy (Python, web, desktop,
lockfiles) through ``check_version_consistency.py --write``, updates the README and the
deployment guides, and moves the CHANGELOG's ``[Unreleased]`` entries under the new
version with today's date. Then commit, push, and tag ``vX.Y.Z-rc.1`` for a release
candidate, ``vX.Y.Z-beta.N`` for a beta (version ``X.Y.ZbN``); tag ``vX.Y.Z`` on the
accepted commit for the stable release (docs/release/RELEASE_CHANNELS.md). Prose
surfaces carry the display spelling (``1.0.0-beta``).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from eurogas_nexus.release.versioning import SemVer, parse_app_version  # noqa: E402

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


def _parse(version: str) -> SemVer:
    try:
        return parse_app_version(version)
    except ValueError:
        raise SystemExit(f"{version!r} is not X.Y.Z or X.Y.ZbN") from None


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

    old_identity, new_identity = _parse(_current()), _parse(args.version)
    if new_identity <= old_identity:
        print(
            f"{args.version} is not later than the current version {_current()}",
            file=sys.stderr,
        )
        return 2
    # pyproject takes PEP 440 (1.0.0b1); prose takes the display spelling (1.0.0-beta).
    old, new = old_identity.display, new_identity.display
    print(f"{old_identity.pep440} -> {new_identity.pep440}")
    if args.dry_run:
        for relative, _template in _TEXT_SURFACES:
            print(f"  would update {relative}")
        return 0

    pyproject = ROOT / "pyproject.toml"
    pyproject.write_text(
        re.sub(
            r'^version = "[^"]+"$',
            f'version = "{new_identity.pep440}"',
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
        # An environment file carries the runtime (SemVer) spelling, prose the display one.
        machine = relative.endswith(".env")
        before = old_identity.semver if machine else old
        after = new_identity.semver if machine else new
        if _rewrite(relative, before, after, template):
            print(f"  updated {relative}")
    if _cut_changelog(new_identity.display, date.today().isoformat()):
        print(f"  CHANGELOG: [Unreleased] entries now under [{new}]")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/check_version_consistency.py")],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout + result.stderr, file=sys.stderr)
        return 1
    tag = (
        f"v{new_identity.semver}"
        if new_identity.is_prerelease
        else f"v{new}-rc.1 (or v{new} on the accepted commit)"
    )
    print(f"Version {new_identity.pep440} is consistent. Commit, then tag {tag}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
