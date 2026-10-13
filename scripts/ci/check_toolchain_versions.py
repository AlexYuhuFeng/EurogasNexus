#!/usr/bin/env python
"""Verify every toolchain version declaration agrees with its canonical file.

The same toolchain version is declared in several places, and nothing connected
them:

* ``.python-version`` -- what pyenv and several IDEs read;
* ``.nvmrc`` -- what nvm reads;
* ``rust-toolchain.toml`` -- what rustup reads;
* ``pyproject.toml`` ``requires-python`` -- what a package installer enforces;
* ``clients/*/package.json`` ``engines.node`` -- what npm warns about;
* the ``PYTHON_VERSION`` / ``NODE_VERSION`` / ``RUST_TOOLCHAIN`` environment blocks
  in each workflow -- what the runners actually use;
* the ``--python-version`` argument recorded in the ``requirements*.lock`` headers
  -- what the locked dependency set was resolved for.

A version bump that misses one of these produces the failure this gate exists to
prevent: a developer or a runner working on a version the lock file was not
compiled for, which is exactly the situation that let a length-sensitive defect
pass on SQLite while failing on the deployed stack.

The canonical values are the three files a toolchain manager reads. Everything
else is asserted to match them.

Exit codes: 0 consistent, 1 a disagreement, 2 cannot check.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
NODE_VERSION_FILE = REPO_ROOT / ".nvmrc"
RUST_TOOLCHAIN_FILE = REPO_ROOT / "rust-toolchain.toml"
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
CLIENT_PACKAGES = (
    REPO_ROOT / "clients" / "web" / "package.json",
    REPO_ROOT / "clients" / "desktop" / "package.json",
)
LOCK_FILES = (
    REPO_ROOT / "requirements.lock",
    REPO_ROOT / "requirements-runtime.lock",
    REPO_ROOT / "requirements-build.lock",
)


def canonical_python() -> str:
    return PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()


def canonical_node() -> str:
    return NODE_VERSION_FILE.read_text(encoding="utf-8").strip()


def canonical_rust() -> str:
    match = re.search(
        r'^channel\s*=\s*"([^"]+)"', RUST_TOOLCHAIN_FILE.read_text(encoding="utf-8"), re.M
    )
    if not match:
        raise SystemExit(f"cannot check: no channel in {RUST_TOOLCHAIN_FILE.name}")
    return match.group(1)


def python_minor(version: str) -> str:
    """Return ``MAJOR.MINOR`` for a full version."""

    parts = version.split(".")
    return ".".join(parts[:2])


def check_pyproject(python: str) -> list[str]:
    """``requires-python`` must accept the pinned interpreter."""

    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        return ["pyproject.toml: no requires-python declared"]
    specifier = match.group(1)
    floor = re.search(r">=\s*(\d+\.\d+)", specifier)
    if not floor:
        return [f"pyproject.toml: requires-python={specifier!r} has no lower bound to check"]
    pinned = python_minor(python)
    if floor.group(1) != pinned:
        return [
            f"pyproject.toml: requires-python={specifier!r} does not match the pinned "
            f"interpreter {python} (.python-version)"
        ]
    return []


def check_client_engines(node: str) -> list[str]:
    """``engines.node`` must admit the pinned Node version."""

    findings: list[str] = []
    for path in CLIENT_PACKAGES:
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        specifier = (data.get("engines") or {}).get("node")
        relative = path.relative_to(REPO_ROOT)
        if not specifier:
            findings.append(f"{relative}: no engines.node declared")
            continue
        floor = re.search(r">=\s*(\d+\.\d+\.\d+)", specifier)
        if not floor:
            findings.append(f"{relative}: engines.node={specifier!r} has no lower bound")
            continue
        if floor.group(1) != node:
            findings.append(
                f"{relative}: engines.node={specifier!r} does not admit the pinned "
                f"Node {node} (.nvmrc)"
            )
    return findings


def check_workflows(python: str, node: str, rust: str) -> list[str]:
    """Every workflow version source must equal the canonical value."""

    findings: list[str] = []
    expected = {
        "PYTHON_VERSION": python,
        "NODE_VERSION": node,
        "RUST_TOOLCHAIN": rust,
    }
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(REPO_ROOT)

        for name, want in expected.items():
            for match in re.finditer(rf'^\s*{name}:\s*"([^"]+)"', text, re.M):
                if match.group(1) != want:
                    findings.append(
                        f"{relative}: {name}={match.group(1)!r} but the canonical value is {want!r}"
                    )

        # A literal version inside a setup action's `with:` bypasses the env block
        # and is the shape most likely to be missed by a bump.
        for match in re.finditer(r"^\s*python-version:\s*\"([^\"]+)\"", text, re.M):
            if match.group(1) != python:
                findings.append(
                    f"{relative}: literal python-version={match.group(1)!r} "
                    f"(expected {python!r} or the env reference)"
                )
        for match in re.finditer(r"^\s*node-version:\s*\"([^\"]+)\"", text, re.M):
            if match.group(1) != node:
                findings.append(
                    f"{relative}: literal node-version={match.group(1)!r} "
                    f"(expected {node!r} or the env reference)"
                )
        for match in re.finditer(r"^\s*toolchain:\s*\"([^\"]+)\"", text, re.M):
            if match.group(1) != rust:
                findings.append(
                    f"{relative}: literal rust toolchain={match.group(1)!r} "
                    f"(expected {rust!r} or the env reference)"
                )
    return findings


def check_lock_files(python: str) -> list[str]:
    """The locks must record the same Python minor version they were compiled for."""

    findings: list[str] = []
    pinned = python_minor(python)
    for path in LOCK_FILES:
        if not path.is_file():
            findings.append(f"{path.name}: missing")
            continue
        header = "\n".join(
            path.read_text(encoding="utf-8").splitlines()[:4]
        )
        match = re.search(r"--python-version\s+(\d+\.\d+)", header)
        relative = path.relative_to(REPO_ROOT)
        if not match:
            findings.append(
                f"{relative}: the generator command does not record --python-version, "
                "so the interpreter the lock was resolved for cannot be checked"
            )
            continue
        if match.group(1) != pinned:
            findings.append(
                f"{relative}: compiled for Python {match.group(1)} but the pinned "
                f"interpreter is {pinned} (.python-version)"
            )
    return findings


def main() -> int:
    for required in (PYTHON_VERSION_FILE, NODE_VERSION_FILE, RUST_TOOLCHAIN_FILE):
        if not required.is_file():
            print(f"cannot check: {required.name} is missing")
            return 2

    python = canonical_python()
    node = canonical_node()
    rust = canonical_rust()

    print("Toolchain version consistency")
    print(f"  python : {python}   (.python-version)")
    print(f"  node   : {node}   (.nvmrc)")
    print(f"  rust   : {rust}   (rust-toolchain.toml)")
    print()

    findings = (
        check_pyproject(python)
        + check_client_engines(node)
        + check_workflows(python, node, rust)
        + check_lock_files(python)
    )

    if findings:
        print(f"FAIL {len(findings)} disagreement(s):")
        for finding in findings:
            print(f"  {finding}")
        print()
        print("Update the canonical file, then every declaration that must follow it.")
        return 1

    print("OK every declaration agrees with the canonical toolchain files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
