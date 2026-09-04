"""Regenerate the hash-pinned dependency lock files with ``uv``.

Writes three locks from the sources of truth:

- ``requirements.lock``        runtime + dev extras from ``pyproject.toml``
- ``requirements-runtime.lock`` runtime dependencies only
- ``requirements-build.lock``   build-system dependencies only

All locks target the minimum supported Python (3.11), use universal
cross-platform hashes, and must be installed with ``--require-hashes``.

Usage:
    python scripts/ci/freeze_lock.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_PYTHON = "3.11"

_LOCKS: tuple[tuple[str, list[str]], ...] = (
    (
        "requirements.lock",
        [
            "uv",
            "pip",
            "compile",
            "--python-version",
            LOCK_PYTHON,
            "--all-extras",
            "--universal",
            "--generate-hashes",
            "--upgrade",
            "pyproject.toml",
        ],
    ),
    (
        "requirements-runtime.lock",
        [
            "uv",
            "pip",
            "compile",
            "--python-version",
            LOCK_PYTHON,
            "--universal",
            "--generate-hashes",
            "--upgrade",
            "pyproject.toml",
        ],
    ),
    (
        "requirements-build.lock",
        [
            "uv",
            "pip",
            "compile",
            "--python-version",
            LOCK_PYTHON,
            "--universal",
            "--generate-hashes",
            "--upgrade",
            "requirements-build.in",
        ],
    ),
)


def freeze(root: Path = ROOT) -> int:
    """Generate every hash-pinned lock file.

    Returns:
        Exit code: 0 on success, 1 when a lock step fails."""
    if shutil.which("uv") is None:
        print("uv is required to regenerate hash-pinned locks")
        return 2

    for output_name, command in _LOCKS:
        print(f"writing {output_name}")
        subprocess.run([*command, "-o", output_name], cwd=root, check=True)
    return 0


def main() -> int:
    """CLI entry point for lock regeneration."""
    try:
        return freeze()
    except subprocess.CalledProcessError as exc:
        print(f"uv failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
