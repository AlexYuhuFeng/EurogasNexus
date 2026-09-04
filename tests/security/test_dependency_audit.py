"""Dependency license audit and lock tests (Gate 4)."""

from pathlib import Path

from scripts.ci.audit_dependencies import audit
from scripts.ci.freeze_lock import _LOCKS

ROOT = Path(__file__).resolve().parents[2]


def _write_metadata(dist_dir: Path, name: str, version: str, license_text: str) -> None:
    (dist_dir / f"{name}-{version}.dist-info").mkdir(parents=True)
    (dist_dir / f"{name}-{version}.dist-info" / "METADATA").write_text(
        f"Name: {name}\nVersion: {version}\nLicense: {license_text}\n",
        encoding="utf-8",
    )


def test_audit_allows_permissive_licenses(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_metadata(site, "demo-mit", "1.0.0", "MIT")
    _write_metadata(site, "demo-apache", "1.0.0", "Apache-2.0")

    assert audit(site) == 0
    assert "License policy: OK" in capsys.readouterr().out


def test_audit_fails_closed_on_forbidden_license(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_metadata(site, "demo-mit", "1.0.0", "MIT")
    _write_metadata(site, "demo-gpl", "1.0.0", "GPL-3.0-only")

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "FORBIDDEN LICENSE" in output
    assert "demo-gpl" in output


def test_audit_reports_unknown_licenses(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_metadata(site, "demo-unknown", "1.0.0", "")

    assert audit(site) == 0
    assert "UNKNOWN LICENSE" in capsys.readouterr().out


def test_freeze_lock_spec_covers_runtime_dev_and_build() -> None:
    outputs = [output for output, _command in _LOCKS]

    assert outputs == [
        "requirements.lock",
        "requirements-runtime.lock",
        "requirements-build.lock",
    ]
    for _output, command in _LOCKS:
        assert command[0] == "uv"
        assert "--python-version" in command
        assert "--generate-hashes" in command
        assert "--universal" in command
        assert command[-1] in {"pyproject.toml", "requirements-build.in"}


def test_requirements_lock_exists_is_hash_pinned_and_includes_dev_tools() -> None:
    lock = ROOT / "requirements.lock"
    assert lock.is_file(), "requirements.lock must exist (regenerate via scripts/ci/freeze_lock.py)"
    text = lock.read_text(encoding="utf-8").lower()
    assert "--hash=sha256:" in text
    for package in ("fastapi", "pydantic", "sqlalchemy", "alembic", "pg8000", "rdflib"):
        assert f"{package}==" in text, f"requirements.lock missing exact pin for {package}"
    for dev_tool in ("pytest==", "ruff=="):
        assert dev_tool in text, f"requirements.lock missing validation tool {dev_tool}"


def test_runtime_and_build_locks_separate_concerns() -> None:
    runtime = (ROOT / "requirements-runtime.lock").read_text(encoding="utf-8").lower()
    build = (ROOT / "requirements-build.lock").read_text(encoding="utf-8").lower()

    assert "pytest==" not in runtime
    assert "ruff==" not in runtime
    assert "rdflib==" not in runtime
    assert "setuptools==" in build
    assert "wheel==" in build
    assert "--hash=sha256:" in runtime
    assert "--hash=sha256:" in build


def test_audit_and_freeze_scripts_are_registered_in_ci() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "dependency-audit" in ci
    assert "audit_dependencies.py" in ci
    assert "pip-audit" in ci or "pip_audit" in ci
