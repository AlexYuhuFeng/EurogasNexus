"""The lock-completeness gate (scripts/ci/check_lock_completeness.py), run before every push.

Hosted CI installs only from the hash-pinned locks into a clean canonical Python, so a
dependency that is declared but not locked for that interpreter fails there and nowhere else.
"""

from __future__ import annotations

from pathlib import Path

from scripts.ci import check_lock_completeness as gate

ROOT = Path(__file__).resolve().parents[2]
HASH = " \\\n    --hash=sha256:" + "0" * 64 + "\n"


def _tree(tmp_path: Path, *, runtime: str, full: str, deps: str = '"valkey>=6.1,<7"') -> Path:
    (tmp_path / ".python-version").write_text("3.11.12\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "demo"\ndependencies = [{deps}]\n'
        '[project.optional-dependencies]\ndev = ["pytest>=8"]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements-build.in").write_text("setuptools>=68\n", encoding="utf-8")
    (tmp_path / "requirements-build.lock").write_text("setuptools==80.0" + HASH, encoding="utf-8")
    (tmp_path / "requirements-runtime.lock").write_text(runtime, encoding="utf-8")
    (tmp_path / "requirements.lock").write_text(full, encoding="utf-8")
    return tmp_path


def test_the_repository_locks_are_complete_for_the_canonical_python() -> None:
    assert gate.check(ROOT) == []


def test_a_declared_dependency_missing_from_a_lock_is_named(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        runtime="valkey==6.2.0" + HASH,
        full="pytest==9.0" + HASH,
    )
    problems = gate.check(root)
    assert any("valkey" in item and "requirements.lock" in item for item in problems), problems


def test_a_dependency_locked_only_for_another_python_is_not_pinned(tmp_path: Path) -> None:
    only_old = "valkey==6.2.0 ; python_full_version < '3.11.3'" + HASH
    root = _tree(tmp_path, runtime=only_old, full=only_old + "pytest==9.0" + HASH)
    problems = gate.check(root)
    assert any("valkey" in item and "3.11.12" in item for item in problems), problems


def test_runtime_and_test_locks_must_pin_the_same_version(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        runtime="valkey==6.2.0" + HASH,
        full="valkey==6.1.0" + HASH + "pytest==9.0" + HASH,
    )
    problems = gate.check(root)
    assert any("pins 6.2.0" in item for item in problems), problems


def test_a_marker_that_excludes_the_interpreter_is_not_a_missing_package(tmp_path: Path) -> None:
    lock = (
        "valkey==6.2.0" + HASH + "async-timeout==5.0.1 ; python_full_version < '3.11.3'" + HASH
    )
    root = _tree(tmp_path, runtime=lock, full=lock + "pytest==9.0" + HASH)
    assert gate.check(root) == []
