"""Dependency license audit and lock tests (Gate 4)."""

from pathlib import Path

import pytest

from scripts.ci.audit_dependencies import audit
from scripts.ci.freeze_lock import _LOCKS

ROOT = Path(__file__).resolve().parents[2]


def _write_metadata(dist_dir: Path, name: str, version: str, license_text: str) -> None:
    _write_raw_metadata(dist_dir, name, version, f"License: {license_text}\n")


def _write_raw_metadata(dist_dir: Path, name: str, version: str, headers: str) -> None:
    target = dist_dir / f"{name}-{version}.dist-info"
    target.mkdir(parents=True)
    (target / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{headers}",
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


def test_audit_allows_expression_only_permissive_license(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(site, "demo-mit", "1.0.0", "License-Expression: MIT\n")

    assert audit(site) == 0
    output = capsys.readouterr().out
    assert "License policy: OK" in output
    assert "UNKNOWN LICENSE" not in output


@pytest.mark.parametrize(
    "expression",
    [
        "PolyForm-Noncommercial-1.0.0",
        "SSPL-1.0",
        "BUSL-1.1",
        "Elastic-2.0",
        "MIT OR GPL-3.0-only",
        "GPL-2.0-only WITH Classpath-exception-2.0",
    ],
)
def test_audit_fails_closed_on_expression_only_restricted_license(
    tmp_path, capsys, expression: str
) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(site, "demo-restricted", "1.0.0", f"License-Expression: {expression}\n")

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "FORBIDDEN LICENSE" in output
    assert "demo-restricted" in output


def test_license_expression_takes_precedence_over_legacy_license(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(
        site,
        "demo-conflict",
        "1.0.0",
        "License: GPL-3.0-only\nLicense-Expression: MIT\n",
    )

    assert audit(site) == 0
    assert "License policy: OK" in capsys.readouterr().out


def test_audit_reads_folded_legacy_license_header(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(
        site,
        "demo-folded-license",
        "1.0.0",
        "License: Permission is granted under the terms of the\n"
        " GNU Affero General Public License (AGPL).\n",
    )

    assert audit(site) == 1
    assert "demo-folded-license" in capsys.readouterr().out


def test_audit_reads_folded_license_expression(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(
        site,
        "demo-folded-expression",
        "1.0.0",
        "License-Expression: MIT OR\n PolyForm-Noncommercial-1.0.0\n",
    )

    assert audit(site) == 1
    assert "demo-folded-expression" in capsys.readouterr().out


def test_audit_reads_folded_license_classifier(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(
        site,
        "demo-folded-classifier",
        "1.0.0",
        "Classifier: License :: OSI Approved ::\n GNU Affero General Public License v3 (AGPLv3)\n",
    )

    assert audit(site) == 1
    assert "demo-folded-classifier" in capsys.readouterr().out


def test_audit_reads_all_license_classifiers_not_only_osi_approved(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(
        site,
        "demo-non-osi",
        "1.0.0",
        "Classifier: License :: GNU General Public License v3 (GPLv3)\n",
    )

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "FORBIDDEN LICENSE" in output
    assert "demo-non-osi" in output


def test_audit_reads_repeated_license_classifiers(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(
        site,
        "demo-repeated",
        "1.0.0",
        "Classifier: License :: OSI Approved :: MIT License\n"
        "Classifier: License :: GNU General Public License v3 (GPLv3)\n",
    )

    assert audit(site) == 1
    assert "demo-repeated" in capsys.readouterr().out


def test_audit_fails_when_no_distribution_metadata_is_present(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    site.mkdir()

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "nothing was audited" in output
    assert "License policy: OK" not in output


def test_audit_fails_when_dist_info_directory_has_no_metadata_file(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    (site / "demo-broken-1.0.0.dist-info").mkdir(parents=True)

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "METADATA PROBLEMS" in output
    assert "demo-broken" in output


def test_audit_fails_on_empty_metadata_file(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    dist_info = site / "demo-empty-1.0.0.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text("", encoding="utf-8")

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "empty METADATA" in output
    assert "demo-empty" in output


def test_audit_fails_on_malformed_metadata(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(site, "demo-malformed", "1.0.0", "this is not a header\n")

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "malformed METADATA" in output
    assert "demo-malformed" in output


def test_audit_fails_on_unreadable_metadata(tmp_path, capsys, monkeypatch) -> None:
    site = tmp_path / "site"
    _write_raw_metadata(site, "demo-unreadable", "1.0.0", "License: MIT\n")

    def _raise_oserror(self: Path) -> bytes:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", _raise_oserror)

    assert audit(site) == 1
    output = capsys.readouterr().out
    assert "unreadable METADATA" in output
    assert "License policy: OK" not in output


def test_audit_success_is_detection_not_commercial_clearance(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    _write_metadata(site, "demo-mit", "1.0.0", "MIT")

    assert audit(site) == 0
    output = capsys.readouterr().out
    assert "no restricted license terms detected" in output
    assert "not a commercial clearance" in output


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
