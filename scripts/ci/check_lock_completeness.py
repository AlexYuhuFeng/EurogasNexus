#!/usr/bin/env python
"""Every declared Python dependency is pinned, for the canonical interpreter, in each lock a
CI job installs from.

Hosted CI installs only from the hash-pinned locks into a clean canonical Python
(``.python-version``, 3.11.12 on the runners). A developer's virtualenv has whatever was
installed into it over time, so a dependency added to ``pyproject.toml`` and never locked, or
locked behind an environment marker that excludes the canonical interpreter, passes every
local test and fails on the runner (``ModuleNotFoundError``) or in the license evidence job
(a locked package with no installed distribution). This check reads the files only; it
installs nothing and needs no network.

Checked, for the canonical interpreter on Linux x86-64 (the runners and the API image):

* each runtime dependency of ``pyproject.toml`` is pinned in ``requirements-runtime.lock``
  (the image and the license evidence) and ``requirements.lock`` (the test jobs);
* each ``dev`` extra is pinned in ``requirements.lock``; each ``requirements-build.in`` entry
  in ``requirements-build.lock``;
* every runtime-lock entry that applies is pinned at the same version in
  ``requirements.lock``, so the tests run what the image ships;
* every environment marker in those locks can be decided (an undecidable one would make the
  license evidence and its image verifier refuse the lock).

What it cannot see is whether an installed distribution carries a license text: that remains
the hosted ``Python license text evidence (runtime lock)`` job.

Exit codes: 0 complete, 1 something missing, 2 cannot check.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.release import generate_sboms  # noqa: E402

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_name(spec: str) -> str | None:
    match = _NAME_RE.match(spec)
    return canonical_name(match.group(1)) if match else None


def canonical_environment(python_full_version: str) -> dict[str, str]:
    """The PEP 508 marker values of the CI runners and the API image (CPython, Linux)."""

    major_minor = ".".join(python_full_version.split(".")[:2])
    return {
        "extra": "",
        "implementation_name": "cpython",
        "implementation_version": python_full_version,
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_release": "",
        "platform_system": "Linux",
        "platform_version": "",
        "python_full_version": python_full_version,
        "python_version": major_minor,
        "sys_platform": "linux",
    }


def locked(lock: Path, environment: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """``{canonical name: version}`` of the entries that apply, and the problems found."""

    problems: list[str] = []
    try:
        inventory = generate_sboms.python_packages(lock)
    except generate_sboms.SbomInputError as error:
        return {}, [f"{lock.name}: {item}" for item in error.errors]
    pins: dict[str, str] = {}
    for item in inventory.packages:
        marker = item.get("environment_marker")
        try:
            if marker is not None and not generate_sboms.evaluate_python_marker(
                marker, environment
            ):
                continue
        except generate_sboms.SbomInputError as error:
            problems.append(f"{lock.name}: {item['name']}: {error}")
            continue
        pins[canonical_name(item["name"])] = item["version"]
    for item in inventory.excluded:
        pins.setdefault(canonical_name(item["name"]), "(project)")
    return pins, problems


def check(root: Path = ROOT) -> list[str]:
    version = (root / ".python-version").read_text(encoding="utf-8").strip()
    environment = canonical_environment(version)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    runtime_deps = [requirement_name(spec) for spec in project.get("dependencies", [])]
    dev_deps = [
        requirement_name(spec) for spec in project.get("optional-dependencies", {}).get("dev", [])
    ]
    build_deps = [
        requirement_name(line)
        for line in (root / "requirements-build.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]

    problems: list[str] = []
    runtime, found = locked(root / "requirements-runtime.lock", environment)
    problems += found
    full, found = locked(root / "requirements.lock", environment)
    problems += found
    build, found = locked(root / "requirements-build.lock", environment)
    problems += found

    for name in filter(None, runtime_deps):
        for lock_name, pins in (
            ("requirements-runtime.lock", runtime),
            ("requirements.lock", full),
        ):
            if name not in pins:
                problems.append(
                    f"{name}: a runtime dependency in pyproject.toml is not pinned for Python "
                    f"{version} in {lock_name} (run python scripts/ci/freeze_lock.py)"
                )
    for name in filter(None, dev_deps):
        if name not in full:
            problems.append(f"{name}: a dev dependency is not pinned in requirements.lock")
    for name in filter(None, build_deps):
        if name not in build:
            problems.append(f"{name}: a build dependency is not pinned in requirements-build.lock")
    for name, pinned in sorted(runtime.items()):
        if pinned == "(project)":
            continue
        if full.get(name) != pinned:
            problems.append(
                f"{name}: requirements-runtime.lock pins {pinned} but requirements.lock pins "
                f"{full.get(name, 'nothing')}: the tests would not run what the image ships"
            )
    return problems


def main() -> int:
    try:
        problems = check()
    except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
        print(f"lock completeness cannot be checked: {error}")
        return 2
    if problems:
        print("Python locks are incomplete for the canonical interpreter:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("Python locks complete: every declared dependency is pinned for the canonical Python")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
