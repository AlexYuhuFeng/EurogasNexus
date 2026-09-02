#!/usr/bin/env python3
"""Check internal Markdown links in the Eurogas Nexus repository.

External URLs, fragment-only links, autolinks, and generated or ignored
directories are excluded. The check uses the Git index plus untracked files
when available so ignored directories such as ``output/`` are never scanned.

Exit status is 0 when every local link resolves to an existing file, 1
otherwise.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Directories that are generated, local-only, or deliberately excluded from
# repository documentation checks.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp_work",
    ".playwright-cli",
    "node_modules",
    "__pycache__",
    "output",
    "dist",
    "tmp",
}

EXTERNAL_SCHEMES = ("http://", "https://", "mailto:", "data:", "ftp://", "file://")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


@dataclass(frozen=True)
class BrokenLink:
    source: str
    target: str
    reason: str


def repository_markdown_files() -> list[Path]:
    """Return tracked and untracked, non-ignored Markdown files."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=False,
        )
    except (OSError, subprocess.CalledProcessError):
        result = None

    if result is not None:
        raw_paths = result.stdout.split(b"\0")
        files: list[Path] = []
        for raw in raw_paths:
            if not raw:
                continue
            path = Path(os.fsdecode(raw))
            if path.suffix.lower() == ".md" and not is_excluded(path):
                files.append(path)
        return sorted(files)

    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [
            name for name in dirnames if name not in EXCLUDED_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            if filename.lower().endswith(".md"):
                path = Path(dirpath, filename)
                if not is_excluded(path):
                    files.append(path)
    return sorted(files)


_ALLOWED_HIDDEN_DIRS = {".github", ".agent", ".agents"}


def is_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT).parts if path.is_absolute() else path.parts
    return any(
        part in EXCLUDED_DIRS or (part.startswith(".") and part not in _ALLOWED_HIDDEN_DIRS)
        for part in relative
    )


def strip_code_spans(text: str) -> str:
    text = FENCE_RE.sub("", text)
    return INLINE_CODE_RE.sub("", text)


def link_targets(source: Path, text: str) -> list[str]:
    targets: list[str] = []
    for match in LINK_RE.finditer(text):
        raw = match.group(1).strip()
        if not raw or raw.startswith(EXTERNAL_SCHEMES):
            continue
        if raw.startswith(("#", "<")):
            continue
        # Strip an optional Markdown title such as (path "title").
        target = raw.split()[0] if " " in raw else raw
        # Absolute local filesystem paths are outside this repository and are
        # ignored by the internal-link gate.
        if target.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\/]", target):
            continue
        targets.append(target)
    return targets


def resolve_target(source: Path, raw_target: str) -> Path | None:
    path_only = urllib.parse.unquote(raw_target.split("#", 1)[0])
    if not path_only:
        return None
    candidate = (source.parent / path_only).resolve()
    if not candidate.is_file():
        return candidate
    return candidate


def find_broken_links() -> list[BrokenLink]:
    broken: list[BrokenLink] = []
    for source in repository_markdown_files():
        try:
            text = source.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        plain = strip_code_spans(text)
        for raw_target in link_targets(source, plain):
            target_path = resolve_target(source, raw_target)
            if target_path is None:
                continue  # fragment-only link; no file target to validate
            if not target_path.is_relative_to(ROOT):
                broken.append(
                    BrokenLink(str(source), raw_target, "outside repository")
                )
            elif not target_path.exists():
                broken.append(
                    BrokenLink(str(source), raw_target, "missing target")
                )
    return broken


def main() -> int:
    broken = find_broken_links()
    files = repository_markdown_files()
    print(f"checked {len(files)} Markdown files")
    if broken:
        print(f"broken local links: {len(broken)}")
        for item in broken:
            print(f"  {item.source}: {item.target} ({item.reason})")
        return 1
    print("all local Markdown links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
