"""Tracked paths must be plain ASCII, and must not smuggle the local harness out.

Why this test exists
--------------------
The repository tracked a root-level file whose name ended in U+F022 (a private-use
code point, originally Powerline's branch glyph) followed by a space and a backtick:

    eek-homemodels.json<U+F022> `

Its content was the `.automation` tree's `git diff --stat` — 38 paths from the local
autonomous-development harness. The commercial audit's CA-08 finding requires that
harness to stay out of the delivery boundary, and `.gitignore` cannot provide that once
a file is *tracked*: tracked content travels into `git archive` output and GitHub's
source tarballs.

Two properties are worth holding mechanically:

1. **Names are ASCII.** A path containing a private-use character or a stray backtick is
   the fingerprint of a pasted terminal prompt being captured as a filename. It is
   unquotable on a normal shell and cannot be reviewed confidently.
2. **No tracked file leaks the harness paths.** `.automation` is excluded from delivery,
   so nothing in the index should describe its contents.

The name check is the cheap general guard; the content check is the specific one for the
class of mistake that produced the file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Private-use area, where terminal glyphs live, plus the replacement character.
_PRIVATE_USE = re.compile(r"[\uE000-\uF8FF\uFFFD]")

#: A path under the harness followed by a diff-stat pipe, i.e. an actual listing rather
#: than prose that happens to name the directory. Engineering documents and policy tests
#: legitimately *mention* `.automation/` when explaining the exclusion; what must not be
#: tracked is a file that *enumerates* its contents, which is what the removed artefact
#: did with 38 paths of `git diff --stat`.
_HARNESS_LISTING = re.compile(r"\.automation/[^\s|]*\s*\|\s*\d+")


def _tracked_paths() -> list[str]:
    raw = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True
    ).stdout
    return [entry.decode("utf-8", errors="replace") for entry in raw.split(b"\x00") if entry]


#: Extensions where a BOM is never wanted.
_TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".js", ".mjs", ".ts", ".tsx",
    ".sh", ".ps1", ".txt", ".in", ".lock", ".css", ".html", ".cfg", ".ini",
}


def test_no_text_file_carries_a_utf8_bom() -> None:
    """A BOM is invisible in most tools and changes how the first line is read.

    This repository has a concrete reason to care: `scripts/ops/check_config.py` reads
    environment files, and a BOM on the first key silently detached it from its prefix,
    so `EUROGAS_NEXUS_ENV=release` was dropped and a release environment resolved as
    development. That fix is covered by `tests/contract/test_env_file_bom.py`.

    The check is repository-wide because the mark is introduced by tooling, not by
    intent: a PowerShell `Set-Content -Encoding UTF8` round trip adds one, and this
    session's own defect-injection steps added one to the very file being fixed for BOM
    handling. Thirteen tracked documents and two source files carried one before this
    test existed.
    """

    offending = []
    for path in _tracked_paths():
        if Path(path).suffix not in _TEXT_SUFFIXES:
            continue
        candidate = REPO_ROOT / path
        if not candidate.is_file() or candidate.stat().st_size > 4_000_000:
            continue
        try:
            if candidate.read_bytes()[:3] == b"\xef\xbb\xbf":
                offending.append(path)
        except OSError:
            continue

    assert not offending, (
        "these tracked text files begin with a UTF-8 BOM. The mark is invisible in most "
        "tools and silently changes how the first line is parsed; re-save as UTF-8 "
        f"without a BOM: {offending}"
    )


def test_no_tracked_path_contains_a_private_use_character() -> None:
    """The exact defect: a captured terminal glyph in a filename."""

    offending = [path for path in _tracked_paths() if _PRIVATE_USE.search(path)]
    assert not offending, (
        "tracked paths contain private-use characters, which are the fingerprint of a "
        f"pasted prompt captured as a filename: {offending!r}"
    )


def test_no_tracked_path_contains_a_control_or_stray_backtick() -> None:
    """Backticks and control characters in a path are equally unreviewable."""

    offending = []
    for path in _tracked_paths():
        if "`" in path:
            offending.append(path)
            continue
        if any(ord(ch) < 32 for ch in path):
            offending.append(path)
    assert not offending, f"tracked paths contain control characters or backticks: {offending!r}"


@pytest.mark.parametrize("needle", [".automation/"])
def test_the_local_harness_is_not_tracked(needle: str) -> None:
    """CA-08: the harness stays out of the delivery boundary."""

    tracked = [path for path in _tracked_paths() if path.startswith(needle)]
    assert not tracked, (
        f"{len(tracked)} files under {needle!r} are tracked. The audit requires that "
        "harness to be excluded from delivery; a tracked file reaches source archives "
        "regardless of .gitignore."
    )


def test_no_tracked_file_enumerates_the_harness_tree() -> None:
    """The content half of the same finding: nothing should list the harness contents.

    Narrowed to the actual leak signature after a first version flagged six files that
    only mention the directory while explaining the exclusion. A test that fails on
    correct documents teaches people to widen the allowlist until it means nothing, so
    this asserts the shape the removed artefact had: a harness path followed by a
    diff-stat count.
    """

    leaks = []
    for path in _tracked_paths():
        candidate = REPO_ROOT / path
        if not candidate.is_file():
            continue
        if candidate.stat().st_size > 2_000_000:
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _HARNESS_LISTING.search(text):
            leaks.append(path)

    assert not leaks, (
        "these tracked files enumerate the local `.automation` harness with diff-stat "
        f"counts, which CA-08 requires be kept out of delivery: {leaks}"
    )
