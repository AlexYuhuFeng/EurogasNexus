"""npm lock license audit contracts (client lock coverage gate).

These tests prove the strict npm license mode added to
``scripts/ci/audit_dependencies.py``. The audit reuses the structured
``npm_packages`` reader from ``scripts/release/generate_sboms.py`` instead of
re-implementing package identity, nesting/scoping or workspace exclusions, so
these tests also pin that shared behaviour for the gate. All inputs are
fixtures; the wiring tests assert CI and the release workflow execute the gate
for exactly the two real client locks, before evidence/publication steps.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci.audit_dependencies import NPM_LOCK_FLAG, audit_npm_locks, main

ROOT = Path(__file__).resolve().parents[2]

NPM_LOCK_COMMAND = (
    "python scripts/ci/audit_dependencies.py "
    "--npm-lock clients/web/package-lock.json "
    "--npm-lock clients/desktop/package-lock.json"
)
JOB_HEADER_RE = re.compile(r"^  ([a-z0-9][a-z0-9-]*):$", re.MULTILINE)


def write_lock(path: Path, packages: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"name": "fixture", "version": "0.0.0", "lockfileVersion": 3, "packages": packages}
        ),
        encoding="utf-8",
    )
    return path


def client_locks(tmp_path: Path, web: dict[str, Any], desktop: dict[str, Any]) -> list[Path]:
    return [
        write_lock(tmp_path / "clients/web/package-lock.json", web),
        write_lock(tmp_path / "clients/desktop/package-lock.json", desktop),
    ]


def project(name: str, packages: dict[str, Any]) -> dict[str, Any]:
    """Return a lock ``packages`` map whose root entry is the project package."""
    return {"": {"name": name, "version": "0.5.0"}, **packages}


@pytest.mark.parametrize(
    "license_value",
    ["UNKNOWN", "NONE", "NOASSERTION", "N/A", "LicenseRef-Custom", "MIT OR LicenseRef-Custom"],
)
def test_unreviewed_license_markers_fail(tmp_path: Path, license_value: str) -> None:
    lock = write_lock(
        tmp_path / "package-lock.json",
        {
            "node_modules/example": {"version": "1.0.0", "license": license_value},
        },
    )
    assert audit_npm_locks([lock]) == 1


def test_npm_audit_allows_permissive_licenses_and_labels_lock_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {
                "node_modules/left-pad": {"version": "1.3.0", "license": "MIT"},
                "node_modules/mpl": {"version": "1.0.0", "license": "MPL-2.0"},
                "node_modules/dual": {"version": "1.0.0", "license": "(MIT OR Apache-2.0)"},
                "node_modules/zero-bsd": {"version": "1.0.0", "license": "0BSD"},
            },
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/@tauri-apps/cli": {"version": "2.8.4", "license": "Apache-2.0 OR MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 0
    output = capsys.readouterr().out
    assert "Audited 5 npm third-party package entries from 2 of 2 lock file(s)." in output
    assert "npm license policy: OK" in output
    # Conservative lock coverage is labelled as such, not shipped-artifact proof.
    assert "conservative lock coverage" in output
    assert "not a shipped-artifact proof" in output
    assert "no SPDX legal interpretation of OR/WITH" in output
    assert "no redistribution clearance" in output


@pytest.mark.parametrize(
    "expression",
    [
        "GPL-3.0-only",
        "LGPL-2.1-only",
        "AGPL-3.0-or-later",
        "SSPL-1.0",
        "BUSL-1.1",
        "Elastic-2.0",
        "RSALv2",
        "Commons-Clause",
        "PolyForm-Noncommercial-1.0.0",
        # OR/WITH/AND combinations are never approved because one branch is
        # permissive: any restricted term anywhere fails the entry.
        "MIT OR GPL-3.0-only",
        "MIT AND BUSL-1.1",
        "(MIT OR Apache-2.0) AND GPL-2.0-only",
        "Apache-2.0 WITH PolyForm-Strict-1.0.0",
    ],
)
def test_npm_audit_never_approves_restricted_terms_even_in_or_with_combinations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], expression: str
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {"node_modules/restricted": {"version": "1.0.0", "license": expression}},
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    assert "NPM LICENSE PROBLEMS" in output
    assert "restricted@1.0.0" in output
    assert "restricted term" in output
    assert "npm license policy: OK" not in output


def test_npm_audit_rejects_missing_blank_and_non_string_licenses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {
                "node_modules/no-license": {"version": "1.0.0"},
                "node_modules/blank-license": {"version": "1.0.0", "license": "   "},
                "node_modules/numeric-license": {"version": "1.0.0", "license": 42},
            },
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "ISC"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    assert "no-license@1.0.0: missing 'license' value" in output
    assert "blank-license@1.0.0: blank 'license' value" in output
    assert "numeric-license@1.0.0: non-string 'license' value (int)" in output
    assert "npm license policy: OK" not in output


@pytest.mark.parametrize("value", ["UNLICENSED", "Unlicensed", "unlicensed"])
def test_npm_audit_rejects_explicit_unlicensed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {"node_modules/private": {"version": "1.0.0", "license": value}},
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    assert "private@1.0.0: explicit UNLICENSED" in output
    assert "npm license policy: OK" not in output


@pytest.mark.parametrize(
    "reference",
    [
        "SEE LICENSE IN LICENSE.txt",
        "see license in ../LICENSE",
        "LICENSE",
        "LICENCE",
        "LICENSE.md",
        "./LICENSE",
        "docs/COPYING",
        "NOTICE.txt",
    ],
)
def test_npm_audit_rejects_file_only_references_pending_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reference: str
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {"node_modules/file-ref": {"version": "1.0.0", "license": reference}},
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    assert "file-ref@1.0.0: file-only license reference" in output
    assert "pending review" in output
    assert "npm license policy: OK" not in output


def test_npm_audit_fails_closed_on_missing_malformed_and_empty_locks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "clients/web/package-lock.json"
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    no_packages_map = tmp_path / "no-packages.json"
    no_packages_map.write_text(json.dumps({"name": "fixture"}), encoding="utf-8")

    assert audit_npm_locks([missing, malformed, empty, no_packages_map]) == 1
    output = capsys.readouterr().out
    assert "LOCK PROBLEMS" in output
    assert "Audited 0 npm third-party package entries from 0 of 4 lock file(s)." in output
    assert "required lock input missing" in output
    assert "invalid JSON" in output
    assert "unsupported npm lock" in output
    assert "npm license policy: OK" not in output


def test_npm_audit_rejects_a_lock_with_only_excluded_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        {
            "": {"name": "eurogas-nexus-web", "version": "0.5.0"},
            "node_modules/linked": {"resolved": "packages/linked", "link": True},
        },
        project(
            "eurogas-nexus-desktop",
            {"node_modules/@tauri-apps/cli": {"version": "2.8.4", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    assert "no third-party packages" in output
    assert "npm license policy: OK" not in output


def test_npm_audit_uses_shared_reader_identity_for_nested_and_scoped_packages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {
                "node_modules/@scope/tool": {"version": "2.0.0", "license": "MIT"},
                "node_modules/@scope/tool/node_modules/dup": {
                    "version": "1.0.0",
                    "license": "GPL-3.0-only",
                },
                "node_modules/dup": {"version": "0.9.0", "license": "ISC"},
                "node_modules/alias-dir": {
                    "name": "real-package",
                    "version": "3.0.0",
                    "license": "BSD-3-Clause",
                },
            },
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    # The failing entry is reported by resolved package identity, never by the
    # nested install path; the passing duplicates are not reported at all.
    assert "dup@1.0.0" in output
    assert "dup@0.9.0" not in output
    assert "@scope/tool" not in output
    assert "real-package@3.0.0" not in output
    assert "node_modules" not in output


def test_npm_audit_excludes_workspace_links_and_project_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        {
            "": {"name": "eurogas-nexus-web", "version": "0.5.0"},
            "node_modules/left-pad": {"version": "1.3.0", "license": "MIT"},
            # A local workspace link is not a registry package, so its
            # (synthetic) restricted value is excluded, never audited.
            "node_modules/@scope/local": {
                "resolved": "packages/local",
                "link": True,
                "license": "GPL-3.0-only",
            },
        },
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 0
    output = capsys.readouterr().out
    assert "Audited 2 npm third-party package entries from 2 of 2 lock file(s)." in output
    assert "Excluded 3 non-third-party lock entries" in output
    assert "workspace links" in output
    assert "npm license policy: OK" in output


def test_npm_audit_covers_dev_and_optional_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {
                "node_modules/dev-tool": {"version": "1.0.0", "license": "MIT", "dev": True},
                "node_modules/optional-dep": {
                    "version": "1.0.0",
                    "license": "GPL-3.0-only",
                    "optional": True,
                },
            },
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "MIT"}},
        ),
    )

    assert audit_npm_locks(locks) == 1
    output = capsys.readouterr().out
    assert "Audited 3 npm third-party package entries" in output
    assert "optional-dep@1.0.0" in output
    assert "dev-tool@1.0.0" not in output


def test_npm_audit_refuses_an_empty_lock_path_list(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert audit_npm_locks([]) == 1
    output = capsys.readouterr().out
    assert "nothing was audited" in output
    assert "npm license policy: OK" not in output


def test_main_npm_mode_and_preserved_python_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    locks = client_locks(
        tmp_path,
        project(
            "eurogas-nexus-web",
            {"node_modules/left-pad": {"version": "1.3.0", "license": "MIT"}},
        ),
        project(
            "eurogas-nexus-desktop",
            {"node_modules/ok": {"version": "1.0.0", "license": "ISC"}},
        ),
    )

    assert main([NPM_LOCK_FLAG, str(locks[0]), NPM_LOCK_FLAG, str(locks[1])]) == 0
    assert "npm license policy: OK" in capsys.readouterr().out
    assert main([f"{NPM_LOCK_FLAG}={locks[0]}", f"{NPM_LOCK_FLAG}={locks[1]}"]) == 0
    capsys.readouterr()

    assert main([NPM_LOCK_FLAG]) == 2
    assert "requires a lock path argument" in capsys.readouterr().out
    assert main([NPM_LOCK_FLAG, str(locks[0]), str(tmp_path / "site")]) == 2
    assert "not both" in capsys.readouterr().out

    # Python mode is preserved: a directory without distribution metadata still
    # fails closed exactly as before the npm mode existed.
    empty_site = tmp_path / "site"
    empty_site.mkdir()
    assert main([str(empty_site)]) == 1
    assert "nothing was audited" in capsys.readouterr().out


def _job_section(workflow: str, job: str) -> str:
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    headers = list(JOB_HEADER_RE.finditer(text))
    for index, header in enumerate(headers):
        if header.group(1) == job:
            end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
            return text[header.start() : end]
    raise AssertionError(f"job {job!r} not found in {workflow}")


@pytest.mark.parametrize(
    ("workflow", "job"),
    [("ci.yml", "dependency-audit"), ("release.yml", "dependency-scan")],
)
def test_npm_license_gate_is_wired_for_exactly_both_client_locks(workflow: str, job: str) -> None:
    section = _job_section(workflow, job)

    assert section.count("Node license policy audit") == 1
    assert section.count(NPM_LOCK_COMMAND) == 1
    assert section.count("--npm-lock clients/web/package-lock.json") == 1
    assert section.count("--npm-lock clients/desktop/package-lock.json") == 1


def test_release_npm_license_gate_runs_before_scan_evidence_publication() -> None:
    section = _job_section("release.yml", "dependency-scan")

    audit_at = section.index(NPM_LOCK_COMMAND)
    wrap_at = section.index("Wrap scan evidence in a bound envelope")
    upload_at = section.index("Upload scan evidence")
    assert audit_at < wrap_at < upload_at


def test_release_packaging_job_depends_on_dependency_scan() -> None:
    assemble = _job_section("release.yml", "assemble")

    assert "\n      - dependency-scan\n" in assemble
    assert "python scripts/release/generate_sboms.py" in assemble


def test_ci_and_release_workflows_remain_valid_yaml() -> None:
    for workflow in ("ci.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        payload = yaml.safe_load(text)
        assert isinstance(payload, dict), workflow
        assert "jobs" in payload, workflow
