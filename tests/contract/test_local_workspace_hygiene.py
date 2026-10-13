"""Guard the convention that local working directories are both ignored and unlinted.

Why this test exists
--------------------
Every local working directory created while verifying this project starts with
``.dnx-``. They hold hash-locked dependency trees, captured evidence, a local npm and
an embedded PostgreSQL. Two things must stay true for each of them:

1. **Git ignores them.** The audit's CA-08 finding is about delivery boundary: local
   harness files must not reach a public repository. A single ``git add -A`` on an
   unignored ``.dnx-cov`` would commit a dependency tree.
2. **Ruff excludes them.** Ruff reads the filesystem rather than Git, so an unexcluded
   local target makes ``ruff check .`` report thousands of findings inside third-party
   packages, which reads as "the project does not lint" and hides the real findings.

Both were maintained as explicit lists, and both were wrong three times: ``.dnx-verify``,
then ``.dnx-audit``, then ``.dnx-cov``. Each time the fix was to append one more name.
The lists are now globs, and this test holds them there so the next local directory
cannot repeat the history.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
GITIGNORE = REPO_ROOT / ".gitignore"

#: A name that does not exist yet, standing in for whichever directory the next round
#: creates. The globs must cover it without anyone editing a list.
FUTURE_DIRECTORY = ".dnx-not-created-yet"


def _ruff_excludes() -> list[str]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return list(config["tool"]["ruff"]["exclude"])


def _gitignore_lines() -> list[str]:
    return [
        line.strip()
        for line in GITIGNORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_ruff_excludes_local_targets_by_glob_not_by_name() -> None:
    """A glob, not an enumeration, so a new directory is covered on creation."""

    excludes = _ruff_excludes()
    assert ".dnx-*" in excludes, (
        "pyproject [tool.ruff] exclude no longer carries the `.dnx-*` glob. An explicit "
        f"list has been wrong three times. Current entries: {excludes}"
    )
    named = [entry for entry in excludes if entry.startswith(".dnx-") and entry != ".dnx-*"]
    assert not named, (
        f"named `.dnx-*` entries reappeared alongside the glob: {named}. The glob makes "
        "them redundant; keeping both invites the belief that the list is the mechanism."
    )


def test_gitignore_ignores_the_whole_dnx_namespace() -> None:
    """One glob rather than one line per directory, and broad enough to be future-proof.

    The trailing-slash form `/.dnx-*/` is a trap: it matches only what is *inside* such
    a directory, so a freshly created `mkdir .dnx-cov` still shows as untracked. Verified
    against a scratch repository — `/.dnx-*/` gives bare-directory exit 1, `/.dnx-*` gives
    exit 0 for both the directory and its contents.
    """

    lines = _gitignore_lines()
    assert "/.dnx-*" in lines, (
        ".gitignore no longer carries `/.dnx-*`. Without it a new local working "
        f"directory is untracked but NOT ignored, and `git add -A` commits it (CA-08). "
        f"Current dnx lines: {[line for line in lines if 'dnx' in line]}"
    )
    named = [line for line in lines if line.startswith("/.dnx-") and line != "/.dnx-*"]
    assert not named, (
        f"per-directory `.dnx-*` entries reappeared alongside the glob: {named}. Remove "
        "them so the glob is the single mechanism, as ruff's exclusion now is."
    )
    assert "/.dnx-*/" not in lines, (
        "the trailing-slash form reappeared. It does not match the bare directory, so "
        "`mkdir .dnx-new` would leave the directory untracked-but-unignored."
    )


@pytest.mark.parametrize("directory", [FUTURE_DIRECTORY, ".dnx-cov", ".dnx-deps"])
def test_a_new_dnx_directory_is_covered_without_editing_a_list(directory: str) -> None:
    """The check that would have caught each of the three historical misses.

    The path does not have to exist: `git check-ignore` resolves patterns, so this
    proves the pattern covers a directory created later.
    """

    result = subprocess.run(
        ["git", "check-ignore", directory],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, (
        f"git does not ignore {directory!r} (git check-ignore exit "
        f"{result.returncode}). A local working directory must be ignored by pattern, "
        "not by having been added to a list."
    )


def test_the_glob_matches_every_ruff_exclusion_the_pattern_claims() -> None:
    """`.dnx-*` must actually mean the `.dnx-` prefix, not a literal directory name."""

    excludes = _ruff_excludes()
    assert ".dnx-*" in excludes
    for directory in (".dnx-cov", ".dnx-deps", ".dnx-out", FUTURE_DIRECTORY):
        # fnmatch semantics are what ruff uses for these entries.
        from fnmatch import fnmatch

        assert fnmatch(directory, ".dnx-*"), (
            f"{directory!r} is not matched by the ruff glob `.dnx-*`, so it would be "
            "linted and `ruff check .` would report third-party findings"
        )
