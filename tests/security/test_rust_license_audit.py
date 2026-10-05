"""Rust declared-license gate contracts (desktop crate graph).

These tests prove the bounded ``--cargo-lock`` mode added to
``scripts/ci/audit_dependencies.py``. The gate reuses the shared structured
``Cargo.lock`` reader from ``scripts/release/generate_sboms.py`` for the
third-party inventory and the shared restricted/license-value checks, and it
matches ``cargo metadata`` output to that inventory by exact
name/version/source identity. The only package the gate may exclude is the
audited root, verified from the sibling ``Cargo.toml`` ``[package]`` identity
read structurally with ``tomllib``, exactly one metadata entry whose
``manifest_path`` resolves to that exact manifest with a null source, and
exactly one matching ``Cargo.lock`` disclosure -- ``workspace_members`` is
never trusted and every other project name or same-name path is a reported
gap. ``cargo`` is not installed in this environment and no live ``cargo
metadata`` result is claimed here: every test drives the subprocess/JSON
boundary with fixtures and a fake ``subprocess.run``, and the workflow wiring
tests pin that the real gate runs in the release runner. The live ``cargo
metadata`` acceptance therefore remains explicitly pending.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import audit_dependencies
from scripts.ci.audit_dependencies import CARGO_LOCK_FLAG, audit_cargo_lock, main

ROOT = Path(__file__).resolve().parents[2]

INDEX = "registry+https://github.com/rust-lang/crates.io-index"
GIT_SOURCE = "git+https://example.invalid/org/dep?rev=deadbeef#deadbeefcafefeed"

CARGO_LOCK_COMMAND = (
    "python scripts/ci/audit_dependencies.py --cargo-lock clients/desktop/src-tauri/Cargo.lock"
)
JOB_HEADER_RE = re.compile(r"^  ([a-z0-9][a-z0-9-]*):$", re.MULTILINE)

ROOT_NAME = "eurogas-nexus-desktop"
ROOT_VERSION = "0.5.0"

#: Sentinels for the sanitized-failure regression: raw cargo stderr and
#: exception payloads can carry private registry URLs and credentials and must
#: never appear in the audit output.
SENTINEL = "SENTINEL-DO-NOT-LEAK"
SECRET_URL = "https://ci-user:s3cr3t-token@packages.private.invalid/index"


def write_cargo_lock(path: Path, entries: list[dict[str, Any]]) -> Path:
    blocks = []
    for entry in entries:
        lines = ["[[package]]"]
        for key, value in entry.items():
            lines.append(f"{key} = {json.dumps(value)}")
        blocks.append("\n".join(lines))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("version = 4\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


def fixture_tree(root: Path, entries: list[dict[str, Any]]) -> Path:
    """Write a fixture ``Cargo.lock`` plus the sibling manifest cargo would read."""

    lock = write_cargo_lock(root / "src-tauri" / "Cargo.lock", entries)
    (lock.parent / "Cargo.toml").write_text(
        f'[package]\nname = "{ROOT_NAME}"\nversion = "{ROOT_VERSION}"\n', encoding="utf-8"
    )
    return lock


def project_entry(version: str = ROOT_VERSION) -> dict[str, Any]:
    return {"name": ROOT_NAME, "version": version}


def registry_entry(name: str, version: str = "1.0.0") -> dict[str, Any]:
    return {"name": name, "version": version, "source": INDEX, "checksum": "a" * 64}


def package(
    name: str,
    version: str = "1.0.0",
    *,
    source: Any = INDEX,
    license: Any = "MIT",
    license_file: Any = None,
    manifest_path: Any = None,
    **fields: Any,
) -> dict[str, Any]:
    if manifest_path is None:
        if source is None:
            # Fixture honesty: a source-less package is a path crate (or the
            # root) whose real manifest location must be stated explicitly.
            raise ValueError("source-less metadata packages require an explicit manifest_path")
        manifest_path = f"/cargo/registry/src/index.invalid/{name}-{version}/Cargo.toml"
    entry: dict[str, Any] = {
        "name": name,
        "version": version,
        "source": source,
        "license": license,
        "license_file": license_file,
        "manifest_path": manifest_path,
    }
    entry.update(fields)
    return entry


def root_package(
    lock: Path,
    *,
    name: str = ROOT_NAME,
    version: str = ROOT_VERSION,
    license: Any = "Proprietary",
    manifest_path: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Metadata entry for the audited root, tied to the fixture's real manifest."""

    return package(
        name,
        version,
        source=None,
        license=license,
        manifest_path=manifest_path
        if manifest_path is not None
        else str(lock.parent / "Cargo.toml"),
        **fields,
    )


def cargo_metadata(packages: list[Any], *, extra: dict[str, Any] | None = None) -> str:
    root_reference = f"path+file:///fixture#{ROOT_NAME}@{ROOT_VERSION}"
    payload: dict[str, Any] = {
        "packages": packages,
        "workspace_members": [root_reference],
        "workspace_default_members": [root_reference],
        "resolve": None,
        "target_directory": "/fixture/target",
        "version": 1,
    }
    if extra is not None:
        payload.update(extra)
    return json.dumps(payload)


class FakeCargo:
    """Record the argv/kwargs of the fake ``subprocess.run`` and reply."""

    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        error: BaseException | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.error = error
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append((argv, kwargs))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(
            argv, self.returncode, stdout=self.stdout, stderr=self.stderr
        )

    @property
    def argv(self) -> list[str]:
        assert self.calls, "cargo was never invoked"
        return self.calls[-1][0]


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeCargo) -> FakeCargo:
    monkeypatch.setattr(audit_dependencies.subprocess, "run", fake)
    return fake


def _unexpected_run(*args: Any, **kwargs: Any) -> None:
    raise AssertionError("cargo must not be invoked for this input")


def test_cargo_metadata_argv_is_locked_all_features_and_full_graph() -> None:
    manifest = Path("clients/desktop/src-tauri/Cargo.toml")

    argv = audit_dependencies._cargo_metadata_argv(manifest)

    assert argv[0:2] == ["cargo", "metadata"]
    # --locked refuses an implicit Cargo.lock rewrite, --all-features widens
    # feature coverage and --no-deps is deliberately absent.
    assert "--locked" in argv
    assert "--all-features" in argv
    assert argv[argv.index("--format-version") + 1] == "1"
    assert argv[argv.index("--manifest-path") + 1] == str(manifest)
    assert "--no-deps" not in argv
    assert all(isinstance(part, str) for part in argv)


def test_cargo_audit_passes_matching_registry_declarations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(
        tmp_path,
        [
            project_entry(),
            registry_entry("serde"),
            registry_entry("serde_json"),
            registry_entry("tauri", "2.8.0"),
        ],
    )
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    package("serde", license="MIT OR Apache-2.0"),
                    package("serde_json", license="MIT"),
                    package("tauri", "2.8.0", license="Apache-2.0 OR MIT"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 0
    output = capsys.readouterr().out
    assert "Audited 3 third-party crate entries" in output
    assert "3 registry entries passed the declared-license check" in output
    assert f"structural [package] identity {ROOT_NAME} {ROOT_VERSION}" in output
    assert "Excluded 1 non-third-party Cargo.lock entries" in output
    assert (
        "the only exemption this audit grants is the verified root package "
        f"({ROOT_NAME} {ROOT_VERSION})" in output
    )
    assert "cargo declared-license policy: OK" in output
    # Conservative full-graph coverage is labelled as such, not shipped-artifact proof.
    assert "conservative full-graph coverage" in output
    assert "over-includes build, dev and inactive-feature packages" in output
    assert "not shipped-artifact proof" in output
    assert "no SPDX legal interpretation of OR/WITH" in output
    assert "not a commercial or redistribution clearance" in output


def test_cargo_audit_passes_explicit_timeout_and_argv_without_a_shell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    fake = install(
        monkeypatch, FakeCargo(stdout=cargo_metadata([root_package(lock), package("serde")]))
    )

    assert audit_cargo_lock(lock) == 0
    argv, kwargs = fake.calls[-1]
    assert isinstance(argv, list)
    assert kwargs.get("shell") in (None, False)
    assert kwargs.get("capture_output") is True
    assert kwargs.get("timeout") == audit_dependencies.CARGO_METADATA_TIMEOUT_SECONDS
    # The manifest defaults to the sibling Cargo.toml of the audited lock.
    assert argv[argv.index("--manifest-path") + 1] == str(lock.parent / "Cargo.toml")
    capsys.readouterr()

    fake = install(
        monkeypatch, FakeCargo(stdout=cargo_metadata([root_package(lock), package("serde")]))
    )
    assert audit_cargo_lock(lock, timeout=5.0) == 0
    assert fake.calls[-1][1].get("timeout") == 5.0


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (FileNotFoundError(f"cargo {SENTINEL} {SECRET_URL}"), "cargo executable not found"),
        (
            subprocess.TimeoutExpired(
                ["cargo", "metadata"], 300.0, stderr=f"{SENTINEL} {SECRET_URL}"
            ),
            "timed out after",
        ),
        (PermissionError(f"{SENTINEL} {SECRET_URL}"), "could not be executed (PermissionError)"),
    ],
)
def test_cargo_audit_fails_closed_when_cargo_cannot_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    expected: str,
) -> None:
    lock = fixture_tree(tmp_path, [registry_entry("serde")])
    install(monkeypatch, FakeCargo(error=error))

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "CARGO GATE PROBLEMS" in output
    assert expected in output
    # An unavailable toolchain must not be reported as a lock/metadata mismatch.
    assert "omitted from cargo metadata output" not in output
    assert "cargo declared-license policy: OK" not in output
    # Raw exception payloads can embed private registry URLs or credentials.
    assert SENTINEL not in output
    assert SECRET_URL not in output


def test_cargo_audit_fails_closed_on_nonzero_exit_without_echoing_cargo_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    install(
        monkeypatch,
        FakeCargo(
            returncode=101,
            stderr=(
                f"error: failed to fetch {SECRET_URL}\n"
                f"{SENTINEL}\n"
                "error: the lock file needs to be updated but --locked was passed\n"
            ),
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "exit code 101" in output
    assert "not echoed" in output
    # Raw cargo stderr can carry private registry URLs or credentials.
    assert SENTINEL not in output
    assert SECRET_URL not in output
    assert "the lock file needs to be updated" not in output
    assert "omitted from cargo metadata output" not in output
    assert "cargo declared-license policy: OK" not in output


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "{not json",
        "[]",
        '"text"',
        "{}",
        '{"packages": {}}',
        '{"packages": []}',
        '{"packages": [1, 2]}',
    ],
)
def test_cargo_audit_rejects_malformed_or_empty_metadata(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
) -> None:
    lock = fixture_tree(tmp_path, [registry_entry("serde")])
    install(monkeypatch, FakeCargo(stdout=stdout))

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "CARGO GATE PROBLEMS" in output
    assert "omitted from cargo metadata output" not in output
    assert "cargo declared-license policy: OK" not in output


@pytest.mark.parametrize(
    "broken",
    [
        "not-an-object",
        {"version": "1.0.0", "source": INDEX, "license": "MIT"},
        {"name": "   ", "version": "1.0.0", "source": INDEX, "license": "MIT"},
        {"name": "crate", "source": INDEX, "license": "MIT"},
        {"name": "crate", "version": 1, "source": INDEX, "license": "MIT"},
        {"name": "crate", "version": "", "source": INDEX, "license": "MIT"},
        {"name": "crate", "version": "1.0.0", "source": 42, "license": "MIT"},
        {"name": "crate", "version": "1.0.0", "source": "", "license": "MIT"},
        {"name": "crate", "version": "1.0.0", "source": INDEX, "license": "MIT", "license_file": 7},
        {"name": "crate", "version": "1.0.0", "source": INDEX, "license": "MIT"},
        {
            "name": "crate",
            "version": "1.0.0",
            "source": INDEX,
            "license": "MIT",
            "manifest_path": 7,
        },
        {
            "name": "crate",
            "version": "1.0.0",
            "source": INDEX,
            "license": "MIT",
            "manifest_path": "   ",
        },
    ],
)
def test_cargo_audit_rejects_malformed_metadata_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    broken: Any,
) -> None:
    lock = fixture_tree(tmp_path, [registry_entry("crate")])
    install(monkeypatch, FakeCargo(stdout=cargo_metadata([broken])))

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "CARGO GATE PROBLEMS" in output
    assert "omitted from cargo metadata output" not in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_requires_exact_name_version_source_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(
        tmp_path, [project_entry(), registry_entry("alpha"), registry_entry("beta")]
    )
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    # Same name and version, different source: contradictory.
                    package("alpha", source=GIT_SOURCE),
                    # Same name, different version: omitted coverage.
                    package("beta", version="2.0.0"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "alpha@1.0.0" in output
    assert "identities must match exactly" in output
    assert "beta@1.0.0" in output
    assert "omitted from cargo metadata output" in output
    assert "metadata carries version(s): 2.0.0" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_rejects_duplicate_metadata_identities(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("dup")])
    install(
        monkeypatch,
        FakeCargo(stdout=cargo_metadata([root_package(lock), package("dup"), package("dup")])),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "duplicate cargo metadata entries for dup@1.0.0" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_rejects_metadata_packages_outside_the_lock_inventory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("knowngood")])
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [root_package(lock), package("knowngood"), package("sneaky", "0.1.0")]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "sneaky@0.1.0" in output
    assert "not covered by the Cargo.lock inventory" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_never_excludes_by_project_name_without_matching_identity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    # A registry crate reusing the project name is not the
                    # project package and must not be excluded by name alone.
                    package(ROOT_NAME, ROOT_VERSION, license="GPL-3.0-only"),
                    package("serde"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "not covered by the Cargo.lock inventory" in output
    assert f"{ROOT_NAME}@{ROOT_VERSION}" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_requires_a_metadata_manifest_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("crate")])
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    {"name": "crate", "version": "1.0.0", "source": INDEX, "license": "MIT"},
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "no non-blank string 'manifest_path'" in output
    assert "cargo declared-license policy: OK" not in output


@pytest.mark.parametrize(
    ("manifest", "expected"),
    [
        (None, "audited root manifest is missing"),
        ("[[package]\nname = ", "not valid TOML"),
        ('version = "0.5.0"\n', "no [package] table"),
        ('package = "not a table"\n', "no [package] table"),
        ('[package]\nversion = "0.5.0"\n', "no non-blank string 'name'"),
        (f'[package]\nname = "{ROOT_NAME}"\n', "no non-blank string 'version'"),
        ('[package]\nname = "   "\nversion = "0.5.0"\n', "no non-blank string 'name'"),
        (f'[package]\nname = "{ROOT_NAME}"\nversion = 5\n', "no non-blank string 'version'"),
    ],
)
def test_cargo_audit_fails_closed_without_a_verifiable_root_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    manifest: str | None,
    expected: str,
) -> None:
    # The root Cargo.toml is read structurally with tomllib and must identify
    # the root [package]: a missing, malformed or identity-less manifest fails
    # closed instead of silently excluding anything.
    lock = write_cargo_lock(
        tmp_path / "src-tauri" / "Cargo.lock", [project_entry(), registry_entry("serde")]
    )
    if manifest is not None:
        (lock.parent / "Cargo.toml").write_text(manifest, encoding="utf-8")
    monkeypatch.setattr(audit_dependencies.subprocess, "run", _unexpected_run)

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "CARGO GATE PROBLEMS" in output
    assert expected in output
    assert "nothing is excluded" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_rejects_a_metadata_root_that_does_not_match_the_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    install(
        monkeypatch,
        FakeCargo(stdout=cargo_metadata([root_package(lock, version="0.4.9"), package("serde")])),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert f"does not match the audited Cargo.toml [package] {ROOT_NAME} {ROOT_VERSION}" in output
    assert "refusing to exclude it" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_rejects_a_metadata_root_with_a_non_null_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    package(
                        ROOT_NAME,
                        ROOT_VERSION,
                        source=INDEX,
                        license="Proprietary",
                        manifest_path=str(lock.parent / "Cargo.toml"),
                    ),
                    package("serde"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "must have a null source to be this repository's own root" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_refuses_a_root_name_spoofed_at_another_manifest_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same name/version/source as the root, but its manifest_path resolves to a
    # different manifest: it must not inherit the root exemption.
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    spoof = tmp_path / "elsewhere" / "Cargo.toml"
    spoof.parent.mkdir(parents=True)
    spoof.write_text(
        f'[package]\nname = "{ROOT_NAME}"\nversion = "{ROOT_VERSION}"\n', encoding="utf-8"
    )
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    package(
                        ROOT_NAME,
                        ROOT_VERSION,
                        source=None,
                        license="Proprietary",
                        manifest_path=str(spoof),
                    ),
                    package("serde"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert (
        "carries 0 package(s) whose 'manifest_path' resolves to the audited root manifest" in output
    )
    assert "workspace_members are not trusted" in output
    assert "not covered by the Cargo.lock inventory" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_rejects_duplicate_root_identity_at_two_manifest_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    other = tmp_path / "shadow" / "Cargo.toml"
    other.parent.mkdir(parents=True)
    other.write_text(
        f'[package]\nname = "{ROOT_NAME}"\nversion = "{ROOT_VERSION}"\n', encoding="utf-8"
    )
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    package(
                        ROOT_NAME,
                        ROOT_VERSION,
                        source=None,
                        license="Proprietary",
                        manifest_path=str(other),
                    ),
                    package("serde"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert f"duplicate cargo metadata entries for {ROOT_NAME}@{ROOT_VERSION}" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_requires_exactly_one_metadata_package_for_the_root_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    package(
                        ROOT_NAME,
                        "0.5.1",
                        source=None,
                        license="Proprietary",
                        manifest_path=str(lock.parent / "Cargo.toml"),
                    ),
                    package("serde"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert (
        "carries 2 package(s) whose 'manifest_path' resolves to the audited root manifest" in output
    )
    assert "exactly one verified root package is required" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_refuses_other_project_package_exclusions_from_the_lock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Other known project names dropped by the shared reader must not inherit
    # the root exemption: each is reported as an unaudited gap.
    lock = fixture_tree(
        tmp_path,
        [
            project_entry(),
            {"name": "eurogas-nexus-web", "version": "0.5.0"},
            {"name": "eurogas-nexus", "version": "0.5.0"},
            registry_entry("serde"),
        ],
    )
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    package(
                        "eurogas-nexus-web",
                        "0.5.0",
                        source=None,
                        license="MIT",
                        manifest_path=str(tmp_path / "web" / "Cargo.toml"),
                    ),
                    package(
                        "eurogas-nexus",
                        "0.5.0",
                        source=None,
                        license="MIT",
                        manifest_path=str(tmp_path / "python" / "Cargo.toml"),
                    ),
                    package("serde"),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "'eurogas-nexus-web 0.5.0' which is not the verified audited root package" in output
    assert "'eurogas-nexus 0.5.0' which is not the verified audited root package" in output
    assert "not covered by the Cargo.lock inventory" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_refuses_a_root_metadata_entry_the_lock_does_not_disclose(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [registry_entry("serde")])
    install(
        monkeypatch,
        FakeCargo(stdout=cargo_metadata([root_package(lock), package("serde")])),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert f"does not disclose the audited root package '{ROOT_NAME} {ROOT_VERSION}'" in output
    assert "not covered by the Cargo.lock inventory" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_never_trusts_workspace_members_for_the_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    # workspace_members naming the root never exempts a metadata graph that
    # does not carry the verified root package itself.
    stdout = cargo_metadata(
        [package("serde")],
        extra={"workspace_members": [f"path+file:///fixture#{ROOT_NAME}@{ROOT_VERSION}"]},
    )
    install(monkeypatch, FakeCargo(stdout=stdout))
    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "carries 0 package(s)" in output
    assert "workspace_members are not trusted" in output

    # ...and an empty workspace_members list never blocks a verified root.
    stdout = cargo_metadata([root_package(lock), package("serde")], extra={"workspace_members": []})
    install(monkeypatch, FakeCargo(stdout=stdout))
    assert audit_cargo_lock(lock) == 0
    capsys.readouterr()


def test_cargo_audit_workspace_members_never_exclude_third_party_path_crates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A vendored path crate that cargo reports as a workspace member is still
    # third-party: it stays in the inventory and fails its restricted term.
    lock = fixture_tree(
        tmp_path, [project_entry(), {"name": "vendored-widget", "version": "0.1.0"}]
    )
    stdout = cargo_metadata(
        [
            root_package(lock),
            package(
                "vendored-widget",
                "0.1.0",
                source=None,
                license="GPL-3.0-only",
                manifest_path=str(
                    tmp_path / "src-tauri" / "vendor" / "vendored-widget" / "Cargo.toml"
                ),
            ),
        ],
        extra={
            "workspace_members": [
                "path+file:///fixture#vendored-widget@0.1.0",
                "path+file:///fixture#eurogas-nexus-desktop@0.5.0",
            ]
        },
    )
    install(monkeypatch, FakeCargo(stdout=stdout))

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "vendored-widget@0.1.0 [path]" in output
    assert "restricted term 'gpl'" in output
    assert "cargo declared-license policy: OK" not in output


def test_cargo_audit_lists_git_and_path_packages_for_provenance_review(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(
        tmp_path,
        [
            project_entry(),
            registry_entry("serde"),
            {"name": "git-dep", "version": "0.2.0", "source": GIT_SOURCE},
            {"name": "path-dep", "version": "0.1.0"},
        ],
    )
    install(
        monkeypatch,
        FakeCargo(
            stdout=cargo_metadata(
                [
                    root_package(lock),
                    package("serde"),
                    package("git-dep", "0.2.0", source=GIT_SOURCE, license="MIT"),
                    package(
                        "path-dep",
                        "0.1.0",
                        source=None,
                        license="Apache-2.0",
                        manifest_path=str(tmp_path / "src-tauri" / "path-dep" / "Cargo.toml"),
                    ),
                ]
            )
        ),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    # Unreviewed provenance blocks the gate rather than becoming a warning-only pass.
    assert "1 registry entries passed the declared-license check" in output
    assert "2 git/path/alternate-registry entries are listed for provenance review" in output
    assert "PROVENANCE REVIEW (not auto-approved" in output
    assert "git-dep@0.2.0 [git]" in output
    assert "path-dep@0.1.0 [path]" in output
    assert "cargo declared-license policy: OK" not in output


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"license": "GPL-3.0-only"}, "restricted term 'gpl'"),
        ({"license": "MIT OR GPL-3.0-only"}, "restricted term 'gpl'"),
        ({"license": "AGPL-3.0-or-later"}, "restricted term 'gpl' in 'AGPL-3.0-or-later'"),
        ({"license": "Elastic-2.0"}, "restricted term 'elastic'"),
        ({"license": "UNKNOWN"}, "unreviewed license placeholder"),
        ({"license": "NOASSERTION"}, "unreviewed license placeholder"),
        ({"license": "LicenseRef-Custom"}, "custom license reference"),
        ({"license": "UNLICENSED"}, "explicit UNLICENSED"),
        ({"license": "SEE LICENSE IN LICENSE.txt"}, "file-only license reference"),
        ({"license": "LICENSE.md"}, "file-only license reference"),
        ({"license": 42}, "non-string 'license' value (int)"),
        ({"license": None}, "missing 'license' value"),
        ({}, "missing 'license' value"),
        (
            {"license": None, "license_file": "/registry/guarded-1.0.0/LICENSE"},
            "file-only references are not auto-approved",
        ),
    ],
)
def test_cargo_audit_applies_the_shared_declared_license_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    fields: dict[str, Any],
    expected: str,
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("guarded")])
    metadata_package = {
        "name": "guarded",
        "version": "1.0.0",
        "source": INDEX,
        "manifest_path": "/cargo/registry/src/index.invalid/guarded-1.0.0/Cargo.toml",
        **fields,
    }
    install(
        monkeypatch,
        FakeCargo(stdout=cargo_metadata([root_package(lock), metadata_package])),
    )

    assert audit_cargo_lock(lock) == 1
    output = capsys.readouterr().out
    assert "RUST LICENSE PROBLEMS" in output
    assert "guarded@1.0.0 [registry]" in output
    assert expected in output
    assert "cargo declared-license policy: OK" not in output


def test_declared_license_check_is_shared_between_npm_and_cargo_modes() -> None:
    # The npm gate no longer owns a private copy of the restricted/placeholder/
    # file-only rules: both modes call the same shared checker.
    assert not hasattr(audit_dependencies, "_npm_license_problem")
    assert audit_dependencies._declared_license_problem("GPL-3.0-only") == (
        "restricted term 'gpl' in 'GPL-3.0-only'"
    )
    assert audit_dependencies._declared_license_problem("MIT OR Apache-2.0") is None


def test_cargo_audit_fails_closed_when_the_lock_cannot_be_inventoried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A lock the shared reader rejects fails before cargo is even invoked.
    monkeypatch.setattr(audit_dependencies.subprocess, "run", _unexpected_run)

    missing = tmp_path / "src-tauri" / "Cargo.lock"
    assert audit_cargo_lock(missing) == 1
    output = capsys.readouterr().out
    assert "CARGO GATE PROBLEMS" in output
    assert "required lock input missing" in output

    malformed = tmp_path / "malformed" / "Cargo.lock"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("[[package]\nname = ", encoding="utf-8")
    assert audit_cargo_lock(malformed) == 1
    assert "invalid TOML" in capsys.readouterr().out

    root_only = fixture_tree(tmp_path / "root-only", [project_entry()])
    assert audit_cargo_lock(root_only) == 1
    assert "no third-party packages" in capsys.readouterr().out


def test_main_cargo_mode_and_mode_exclusivity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = fixture_tree(tmp_path, [project_entry(), registry_entry("serde")])
    install(monkeypatch, FakeCargo(stdout=cargo_metadata([root_package(lock), package("serde")])))

    assert main([CARGO_LOCK_FLAG, str(lock)]) == 0
    assert "cargo declared-license policy: OK" in capsys.readouterr().out
    assert main([f"{CARGO_LOCK_FLAG}={lock}"]) == 0
    capsys.readouterr()

    assert main([CARGO_LOCK_FLAG]) == 2
    assert "requires a lock path argument" in capsys.readouterr().out

    second = fixture_tree(tmp_path / "second", [project_entry(), registry_entry("serde")])
    assert main([CARGO_LOCK_FLAG, str(lock), CARGO_LOCK_FLAG, str(second)]) == 2
    assert "accepts exactly one" in capsys.readouterr().out

    npm_lock = tmp_path / "package-lock.json"
    npm_lock.write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "eurogas-nexus-web", "version": "0.5.0"},
                    "node_modules/left-pad": {"version": "1.3.0", "license": "MIT"},
                },
            }
        ),
        encoding="utf-8",
    )
    assert main([CARGO_LOCK_FLAG, str(lock), "--npm-lock", str(npm_lock)]) == 2
    assert "not both" in capsys.readouterr().out


def _job_section(workflow: str, job: str) -> str:
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    headers = list(JOB_HEADER_RE.finditer(text))
    for index, header in enumerate(headers):
        if header.group(1) == job:
            end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
            return text[header.start() : end]
    raise AssertionError(f"job {job!r} not found in {workflow}")


def test_release_cargo_license_gate_is_wired_after_rust_setup_and_before_evidence() -> None:
    section = _job_section("release.yml", "dependency-scan")

    assert section.count("Rust license policy audit") == 1
    assert section.count(CARGO_LOCK_COMMAND) == 1
    assert (ROOT / "clients/desktop/src-tauri/Cargo.lock").is_file()
    rust_setup = section.index("Set up Rust")
    audit_at = section.index(CARGO_LOCK_COMMAND)
    wrap_at = section.index("Wrap scan evidence in a bound envelope")
    upload_at = section.index("Upload scan evidence")
    assert rust_setup < audit_at < wrap_at < upload_at


def test_ci_dependency_audit_stays_free_of_a_rust_toolchain_install() -> None:
    # Bounded slice: the CI dependency-audit job installs no Rust toolchain, so
    # this gate ships to the release runner only; the fixture tests above pin
    # the behaviour and no live local cargo result is claimed anywhere.
    section = _job_section("ci.yml", "dependency-audit")

    assert "--cargo-lock" not in section
    assert "Set up Rust" not in section
    assert "dtolnay/rust-toolchain" not in section


def test_workflows_remain_valid_yaml() -> None:
    for workflow in ("ci.yml", "release.yml"):
        text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
        payload = yaml.safe_load(text)
        assert isinstance(payload, dict), workflow
        assert "jobs" in payload, workflow
