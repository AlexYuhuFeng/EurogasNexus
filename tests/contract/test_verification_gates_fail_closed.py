"""Guard the repository's verification gates: they must fail when violated.

A gate that cannot fail is not a control. The five gates below were added to close
delivery gaps found in review, and each one exists because a specific defect
reached the tree:

* ``check_config_contract.py`` -- ``.env.example`` documented a handful of
  variables while the code read 69, and ``EUROGAS_NEXUS_ALLOW_FILE_FALLBACK`` was
  documented and set by compose while nothing read it;
* ``generate_env_template.py`` -- the templates drifted because they were
  hand-maintained;
* ``check_config.py`` -- a missing credential key surfaced only on first use and a
  mistyped variable name was ignored entirely;
* ``check_toolchain_versions.py`` -- the pinned interpreter is declared in eight
  places and a partial bump leaves a caller on a version the lock file was not
  compiled for.

These tests assert the *detection*, not the current state, so they stay meaningful
after the counts change. Each case mutates one file in a throwaway copy of the
tree and requires the gate to report that specific defect.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Everything the gates read. Copying the dependency trees would be pointless.
COPY_DIRECTORIES = ("src", "packages", "scripts", "apps", ".github")
COPY_FILES = (
    "pyproject.toml",
    ".python-version",
    ".nvmrc",
    "rust-toolchain.toml",
    "requirements.lock",
    "requirements-runtime.lock",
    "requirements-build.lock",
    ".env.example",
)

#: (label, file to mutate, mutation, marker the gate must print, gate script)
CASES = (
    (
        "an undeclared environment variable read",
        "src/eurogas_nexus/core/config.py",
        lambda text: text.replace(
            'os.getenv("EUROGAS_NEXUS_ENV", "development")',
            'os.getenv("EUROGAS_NEXUS_ENV", "development")\n'
            '        _probe = os.getenv("EUROGAS_NEXUS_UNDECLARED_PROBE", "")',
            1,
        ),
        "EUROGAS_NEXUS_UNDECLARED_PROBE",
        "check_config_contract.py",
    ),
    (
        "a template variable nothing reads",
        ".env.example",
        lambda text: text + "\nEUROGAS_NEXUS_ALLOW_FILE_FALLBACK=true\n",
        "EUROGAS_NEXUS_ALLOW_FILE_FALLBACK",
        "check_config_contract.py",
    ),
    (
        "a stale generated template",
        ".env.example",
        lambda text: text.replace(
            "EUROGAS_NEXUS_DB_POOL_SIZE=10", "EUROGAS_NEXUS_DB_POOL_SIZE=999"
        ),
        "STALE   .env.example",
        "generate_env_template.py",
    ),
    (
        "a partial toolchain bump",
        ".python-version",
        lambda text: "3.12.0\n",
        "does not match the pinned interpreter",
        "check_toolchain_versions.py",
    ),
    (
        "a workflow version edited away from the canonical file",
        ".github/workflows/ci.yml",
        lambda text: text.replace(
            'PYTHON_VERSION: "3.11.12"', 'PYTHON_VERSION: "3.12.0"'
        ),
        "canonical value is",
        "check_toolchain_versions.py",
    ),
)


def _build_tree(destination: Path) -> None:
    for directory in COPY_DIRECTORIES:
        source = REPO_ROOT / directory
        if source.is_dir():
            shutil.copytree(
                source,
                destination / directory,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("node_modules"),
            )
    for name in COPY_FILES:
        source = REPO_ROOT / name
        if source.is_file():
            shutil.copy2(source, destination / name)


def _run_gate(tree: Path, gate: str) -> tuple[int, str]:
    argv = [sys.executable, str(tree / "scripts" / "ci" / gate)]
    if gate == "generate_env_template.py":
        argv.append("--check")
    result = subprocess.run(
        argv,
        cwd=tree,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


@pytest.mark.parametrize(
    "label,relative,mutation,marker,gate",
    CASES,
    ids=[case[0] for case in CASES],
)
def test_gate_reports_its_defect(tmp_path, label, relative, mutation, marker, gate) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    _build_tree(tree)

    target = tree / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(mutation(target.read_text(encoding="utf-8")), encoding="utf-8")

    code, output = _run_gate(tree, gate)

    assert code != 0, (
        f"{gate} accepted {label!r}: it exited 0, so this defect would reach the "
        f"tree undetected. Output:\n{output[-800:]}"
    )
    assert marker in output, (
        f"{gate} failed for {label!r} but did not name the defect "
        f"(expected {marker!r}). Output:\n{output[-800:]}"
    )


def test_the_gates_pass_on_the_unmodified_tree(tmp_path) -> None:
    """The other half of the assertion: no false positive on a clean tree."""

    tree = tmp_path / "tree"
    tree.mkdir()
    _build_tree(tree)

    for gate in ("check_config_contract.py", "check_toolchain_versions.py"):
        code, output = _run_gate(tree, gate)
        assert code == 0, f"{gate} failed on an unmodified tree:\n{output[-800:]}"
