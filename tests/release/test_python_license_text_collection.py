"""Installed-evidence license/notice text collection contracts.

Fixture-only tests for ``scripts/release/collect_python_license_texts.py``:
declared License-File collection (PEP 639 and legacy locations), RECORD
fallback for legacy metadata, refusal of traversal/symlink/unrecorded paths,
duplicate and version-mismatched distributions, missing/malformed
METADATA/RECORD, non-overwrite of the output directory, exact copied
bytes/hashes and deterministic manifests. They are not installed/locked
coverage on the release runner and not legal clearance.

The final section pins the ordinary-CI wiring structurally: an independent
``python-license-texts`` job installs only the hash-pinned runtime lock into a
throwaway venv, collects against that venv's purelib and always uploads the
report and texts, failing on missing evidence rather than masking it. The
artifact remains review evidence, never legal approval or release publishing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from scripts.release.collect_python_license_texts import _license_basename_matches, collect, main

DIGEST = "0" * 64
FIXED_NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

COLLECTOR_SCRIPT = "scripts/release/collect_python_license_texts.py"
RUNTIME_LOCK_INSTALL = "--require-hashes -r requirements-runtime.lock"
EVIDENCE_JOB = "python-license-texts"
EVIDENCE_VENV = "$RUNNER_TEMP/python-license-venv"
EVIDENCE_OUTPUT_DIR = "artifacts/python-license-texts"
EVIDENCE_ARTIFACT_NAME = "eurogas-nexus-python-license-texts"

JOB_HEADER_RE = re.compile(r"^  ([a-z0-9][a-z0-9-]*):$", re.MULTILINE)
ACTION_PIN_RE = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}$")


@pytest.mark.parametrize(
    "name", ["LICENSE.py", "NOTICE.exe", "COPYING.dll", "copyright.js", "license.ts"]
)
def test_legacy_name_filter_does_not_collect_code(name: str) -> None:
    assert not _license_basename_matches("package/" + name)


def write_lock(path: Path, entries: list[tuple[str, str]]) -> None:
    lines = []
    for name, version in entries:
        lines.append(f"{name}=={version} \\\n    --hash=sha256:{DIGEST}\n")
    path.write_text("".join(lines), encoding="utf-8")


def add_dist_info(
    site: Path,
    name: str,
    version: str,
    *,
    dir_name: str | None = None,
    license_expression: str | None = "MIT",
    license_files: tuple[str, ...] = (),
    record_paths: tuple[str, ...] = (),
    record: bool = True,
    metadata: str | None = None,
) -> Path:
    directory = site / (dir_name or f"{name}-{version}.dist-info")
    directory.mkdir(parents=True)
    if metadata is None:
        headers = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n"
        if license_expression is not None:
            headers += f"License-Expression: {license_expression}\n"
        headers += "".join(f"License-File: {value}\n" for value in license_files)
        metadata = headers
    (directory / "METADATA").write_text(metadata, encoding="utf-8")
    if record:
        rows = [f"{directory.name}/METADATA,,", f"{directory.name}/RECORD,,"]
        rows.extend(f"{path},," for path in record_paths)
        (directory / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return directory


def write_site_file(site: Path, relative: str, content: bytes) -> Path:
    target = site / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def read_manifest(output: Path) -> dict:
    return json.loads((output / "manifest.json").read_text(encoding="utf-8"))


def run_collect(tmp_path: Path, *, site: Path, lock: Path, name: str = "out") -> tuple[int, Path]:
    output = tmp_path / name
    code = collect(site_packages=site, output_dir=output, runtime_lock=lock, now=FIXED_NOW)
    return code, output


def test_declared_license_file_is_copied_with_exact_bytes_and_hashes(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    site.mkdir()
    text = b"MIT License\n\nCopyright (c) 2026 Eurogas\n"
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    write_site_file(site, "demo-1.0.0.dist-info/LICENSE", text)
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 0
    manifest = read_manifest(output)
    assert manifest["status"] == "complete"
    assert manifest["runtime_lock"]["sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    package = manifest["packages"][0]
    assert (package["name"], package["version"]) == ("demo", "1.0.0")
    assert package["distribution"] == "demo-1.0.0.dist-info"
    assert package["declared_license"] == "License-Expression: MIT"
    assert package["status"] == "collected"
    entry = package["files"][0]
    assert entry["origin"] == "license-file"
    assert entry["source"] == "demo-1.0.0.dist-info/LICENSE"
    assert entry["sha256"] == hashlib.sha256(text).hexdigest()
    assert entry["size_bytes"] == len(text)
    assert (output / entry["destination"]).read_bytes() == text
    for value in (entry["destination"], entry["source"], manifest["runtime_lock"]["path"]):
        assert not Path(value).is_absolute()
    assert "STATUS: complete" in capsys.readouterr().out


def test_declared_license_file_in_pep639_licenses_directory(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    text = b"Apache License 2.0\n"
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE.txt",),
        record_paths=("demo-1.0.0.dist-info/licenses/LICENSE.txt",),
    )
    write_site_file(site, "demo-1.0.0.dist-info/licenses/LICENSE.txt", text)
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 0
    package = read_manifest(output)["packages"][0]
    entry = package["files"][0]
    assert entry["source"] == "demo-1.0.0.dist-info/licenses/LICENSE.txt"
    assert (output / entry["destination"]).read_bytes() == text


def test_record_fallback_copies_only_recorded_license_texts(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_expression=None,
        record_paths=("demo/__init__.py", "demo/LICENSE.txt", "demo/COPYING"),
    )
    write_site_file(site, "demo/__init__.py", b"print('package code')\n")
    write_site_file(site, "demo/LICENSE.txt", b"legacy license text\n")
    write_site_file(site, "demo/COPYING", b"copying text\n")
    # On-disk files that RECORD does not list must never be copied.
    write_site_file(site, "demo/NOTICE", b"unrecorded notice\n")
    write_site_file(site, "demo/extra/LICENCE.md", b"unrecorded licence\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 0
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "collected"
    assert package["declared_license"] is None
    copied = {entry["destination"]: entry for entry in package["files"]}
    assert set(copied) == {"texts/demo/1.0.0/LICENSE.txt", "texts/demo/1.0.0/COPYING"}
    assert all(entry["origin"] == "record" for entry in copied.values())
    assert (output / "texts/demo/1.0.0/LICENSE.txt").read_bytes() == b"legacy license text\n"
    assert (output / "texts/demo/1.0.0/COPYING").read_bytes() == b"copying text\n"
    written = sorted(
        path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()
    )
    assert written == ["manifest.json", "texts/demo/1.0.0/COPYING", "texts/demo/1.0.0/LICENSE.txt"]


def test_duplicate_basenames_get_unique_deterministic_destinations(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_expression=None,
        record_paths=("demo/LICENSE", "demo/vendor/LICENSE"),
    )
    write_site_file(site, "demo/LICENSE", b"top-level license\n")
    write_site_file(site, "demo/vendor/LICENSE", b"vendored license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 0
    package = read_manifest(output)["packages"][0]
    destinations = [entry["destination"] for entry in package["files"]]
    assert len(set(destinations)) == 2
    bytes_by_destination = {
        entry["destination"]: (output / entry["destination"]).read_bytes()
        for entry in package["files"]
    }
    assert sorted(bytes_by_destination.values()) == [b"top-level license\n", b"vendored license\n"]


def test_version_mismatch_is_unresolved_and_nonzero(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "2.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-2.0.0.dist-info/LICENSE",),
    )
    write_site_file(site, "demo-2.0.0.dist-info/LICENSE", b"wrong version license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    manifest = read_manifest(output)
    assert manifest["status"] == "incomplete"
    package = manifest["packages"][0]
    assert package["status"] == "unresolved"
    assert "version mismatch" in package["reason"]
    assert package["files"] == []
    assert not (output / "texts").exists()


def test_missing_distribution_is_unresolved(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(site, "other", "1.0.0")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "no installed distribution found" in package["reason"]


def test_distribution_without_license_text_is_unresolved(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_expression=None,
        record_paths=("demo/__init__.py",),
    )
    write_site_file(site, "demo/__init__.py", b"print('code only')\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    manifest = read_manifest(output)
    assert manifest["status"] == "incomplete"
    package = manifest["packages"][0]
    assert package["status"] == "unresolved"
    assert "no License-File metadata" in package["reason"]


def test_missing_metadata_fails_closed(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    directory = site / "demo-1.0.0.dist-info"
    directory.mkdir()
    (directory / "RECORD").write_text("demo-1.0.0.dist-info/RECORD,,\n", encoding="utf-8")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    manifest = read_manifest(output)
    package = manifest["packages"][0]
    assert package["status"] == "unresolved"
    assert "no METADATA" in package["reason"]


def test_malformed_metadata_fails_closed(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(site, "demo", "1.0.0", metadata="this is not a header\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "malformed METADATA" in package["reason"]


def test_malformed_record_fails_closed(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    directory = add_dist_info(site, "demo", "1.0.0")
    (directory / "RECORD").write_text("only-one-field\n", encoding="utf-8")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "malformed RECORD" in package["reason"]


def test_duplicate_distributions_are_refused(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(site, "demo", "1.0.0", dir_name="demo-1.0.0.dist-info")
    add_dist_info(site, "demo", "1.0.0", dir_name="demo-copy-1.0.0.dist-info")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "duplicate installed distributions" in package["reason"]
    assert "demo-copy-1.0.0.dist-info" in package["reason"]


@pytest.mark.parametrize(
    "declared",
    ["../../outside.txt", "/absolute/LICENSE", "C:/outside/LICENSE", "..\\..\\outside.txt"],
)
def test_unsafe_declared_paths_are_refused(tmp_path, declared: str) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(site, "demo", "1.0.0", license_files=(declared,))
    write_site_file(site, "outside.txt", b"outside the site tree\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "not a safe relative path" in package["reason"]
    assert package["files"] == []


def test_record_paths_outside_the_package_area_are_skipped_not_followed(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    outside = site.parent / "outside"
    outside.mkdir()
    (outside / "LICENSE").write_bytes(b"outside the site tree\n")
    directory = add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_expression=None,
        record_paths=("demo/LICENSE",),
    )
    (directory / "RECORD").write_text(
        "demo-1.0.0.dist-info/METADATA,,\n"
        "demo-1.0.0.dist-info/RECORD,,\n"
        "demo/LICENSE,,\n"
        "../../Scripts/demo.exe,,\n"
        "../outside/LICENSE,,\n",
        encoding="utf-8",
    )
    write_site_file(site, "demo/LICENSE", b"recorded license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 0
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "collected"
    assert package["skipped_record_paths"] == ["../../Scripts/demo.exe", "../outside/LICENSE"]
    assert [entry["source"] for entry in package["files"]] == ["demo/LICENSE"]
    assert (output / package["files"][0]["destination"]).read_bytes() == b"recorded license\n"
    written = sorted(
        path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()
    )
    assert written == ["manifest.json", package["files"][0]["destination"]]


def test_record_with_only_out_of_area_paths_leaves_package_unresolved(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    outside = site.parent / "outside"
    outside.mkdir()
    (outside / "LICENSE").write_bytes(b"outside the site tree\n")
    directory = add_dist_info(site, "demo", "1.0.0", license_expression=None)
    (directory / "RECORD").write_text(
        "demo-1.0.0.dist-info/METADATA,,\ndemo-1.0.0.dist-info/RECORD,,\n../outside/LICENSE,,\n",
        encoding="utf-8",
    )
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert package["skipped_record_paths"] == ["../outside/LICENSE"]
    assert package["files"] == []


def test_symlinked_declared_file_is_refused(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    outside = tmp_path / "outside-license.txt"
    outside.write_bytes(b"outside secret\n")
    directory = add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    try:
        (directory / "LICENSE").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "symlink" in package["reason"]
    assert package["files"] == []
    assert outside.read_bytes() == b"outside secret\n"


def test_symlinked_package_directory_is_refused(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    outside_dir = tmp_path / "outside-package"
    outside_dir.mkdir()
    (outside_dir / "LICENSE").write_bytes(b"outside license\n")
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_expression=None,
        record_paths=("demo/LICENSE",),
    )
    try:
        (site / "demo").symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable in this environment")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "symlink" in package["reason"]


@pytest.mark.skipif(sys.platform != "win32", reason="junction refusal is Windows-specific")
def test_junctioned_package_directory_is_refused(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    outside_dir = tmp_path / "outside-package"
    outside_dir.mkdir()
    (outside_dir / "LICENSE").write_bytes(b"outside license\n")
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_expression=None,
        record_paths=("demo/LICENSE",),
    )
    junction = site / "demo"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("junction creation is unavailable in this environment")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    try:
        code, output = run_collect(tmp_path, site=site, lock=lock)
    finally:
        os.rmdir(junction)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "symlink" in package["reason"]
    assert package["files"] == []


def test_declared_file_missing_from_record_is_refused(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(site, "demo", "1.0.0", license_files=("LICENSE",))
    write_site_file(site, "demo-1.0.0.dist-info/LICENSE", b"unrecorded license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "not recorded in the distribution's RECORD" in package["reason"]
    assert package["files"] == []


def test_declared_file_missing_on_disk_is_refused(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    package = read_manifest(output)["packages"][0]
    assert package["status"] == "unresolved"
    assert "missing or not a regular file" in package["reason"]


def test_existing_output_directory_is_never_overwritten(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    write_site_file(site, "demo-1.0.0.dist-info/LICENSE", b"license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])
    output = tmp_path / "out"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    code = collect(site_packages=site, output_dir=output, runtime_lock=lock, now=FIXED_NOW)

    assert code == 2
    assert (output / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert sorted(path.name for path in output.iterdir()) == ["keep.txt"]


def test_empty_lock_is_not_a_pass(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    site.mkdir()
    lock = tmp_path / "requirements-runtime.lock"
    lock.write_text("# no requirements\n", encoding="utf-8")
    output = tmp_path / "out"

    code = collect(site_packages=site, output_dir=output, runtime_lock=lock, now=FIXED_NOW)

    assert code == 1
    assert not output.exists()
    assert "nothing was collected" in capsys.readouterr().out


def test_empty_site_packages_reports_incomplete_manifest(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    manifest = read_manifest(output)
    assert manifest["status"] == "incomplete"
    assert manifest["global_problems"]
    assert manifest["packages"][0]["status"] == "unresolved"


def test_partial_collection_preserves_texts_and_marks_incomplete(tmp_path, capsys) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo-ok",
        "1.0.0",
        dir_name="demo_ok-1.0.0.dist-info",
        license_files=("LICENSE",),
        record_paths=("demo_ok-1.0.0.dist-info/LICENSE",),
    )
    write_site_file(site, "demo_ok-1.0.0.dist-info/LICENSE", b"good license\n")
    add_dist_info(
        site,
        "demo-missing",
        "1.0.0",
        license_expression=None,
        record_paths=("demo_missing/__init__.py",),
    )
    write_site_file(site, "demo_missing/__init__.py", b"code only\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo-ok", "1.0.0"), ("demo-missing", "1.0.0")])

    code, output = run_collect(tmp_path, site=site, lock=lock)

    assert code == 1
    manifest = read_manifest(output)
    assert manifest["status"] == "incomplete"
    assert manifest["counts"]["collected"] == 1
    assert manifest["counts"]["unresolved"] == 1
    collected = [item for item in manifest["packages"] if item["status"] == "collected"][0]
    entry = collected["files"][0]
    assert (output / entry["destination"]).read_bytes() == b"good license\n"
    assert "STATUS: incomplete" in capsys.readouterr().out


def test_manifest_is_deterministic_with_fixed_timestamp(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    write_site_file(site, "demo-1.0.0.dist-info/LICENSE", b"license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])

    first_code, first = run_collect(tmp_path, site=site, lock=lock, name="out-one")
    second_code, second = run_collect(tmp_path, site=site, lock=lock, name="out-two")

    assert (first_code, second_code) == (0, 0)
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()


def test_cli_requires_explicit_site_packages_and_output_dir(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()

    with pytest.raises(SystemExit) as missing_output:
        main(["--site-packages", str(site)])
    assert missing_output.value.code == 2

    with pytest.raises(SystemExit) as missing_site:
        main(["--output-dir", str(tmp_path / "out")])
    assert missing_site.value.code == 2


def test_cli_runs_complete_fixture(tmp_path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    add_dist_info(
        site,
        "demo",
        "1.0.0",
        license_files=("LICENSE",),
        record_paths=("demo-1.0.0.dist-info/LICENSE",),
    )
    write_site_file(site, "demo-1.0.0.dist-info/LICENSE", b"license\n")
    lock = tmp_path / "requirements-runtime.lock"
    write_lock(lock, [("demo", "1.0.0")])
    output = tmp_path / "out"

    code = main(
        [
            "--site-packages",
            str(site),
            "--output-dir",
            str(output),
            "--runtime-lock",
            str(lock),
        ]
    )

    assert code == 0
    assert read_manifest(output)["status"] == "complete"


def _workflow(name: str) -> dict:
    payload = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(payload, dict), name
    return payload


def _job_section(workflow: str, job: str) -> str:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    headers = list(JOB_HEADER_RE.finditer(text))
    for index, header in enumerate(headers):
        if header.group(1) == job:
            end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
            return text[header.start() : end]
    raise AssertionError(f"job {job!r} not found in {workflow}")


def _step(workflow: str, job: str, name: str) -> dict:
    for step in _workflow(workflow)["jobs"][job]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"step {name!r} not found in {workflow}:{job}")


def test_ci_python_license_text_job_is_independent_and_reuses_pinned_actions() -> None:
    payload = _workflow("ci.yml")
    assert EVIDENCE_JOB in payload["jobs"]
    job = payload["jobs"][EVIDENCE_JOB]

    assert job["runs-on"] == "ubuntu-latest"
    # Independent evidence job: it runs on its own and cannot mask another job's
    # failure (or be masked by one) through needs/continue-on-error.
    assert "needs" not in job
    assert "continue-on-error" not in job
    # Event-conditional on purpose: the review-evidence artifact must not alter
    # the release acceptance required-job set (ci_acceptance in
    # scripts/release/policy/stable_gate_policy.json), so the job stays out of
    # the always-run set that the release gate requires.
    assert job["if"] == "github.event_name == 'push'"

    pinned: dict[str, str] = {}
    for other in payload["jobs"].values():
        for step in other.get("steps", []):
            uses = step.get("uses")
            if uses:
                action = uses.split("@", 1)[0]
                assert pinned.setdefault(action, uses) == uses, action

    job_actions = {
        step["uses"].split("@", 1)[0]: step["uses"]
        for step in job["steps"]
        if "uses" in step
    }
    # No new third-party action is introduced: the job reuses the repository's
    # existing pinned checkout/setup/upload actions at the same SHAs.
    assert set(job_actions) == {
        "actions/checkout",
        "actions/setup-python",
        "actions/upload-artifact",
    }
    for action, uses in job_actions.items():
        assert uses == pinned[action], action
        assert ACTION_PIN_RE.match(uses), uses

    assert _step("ci.yml", EVIDENCE_JOB, "Set up Python")["with"]["python-version"] == "3.11.12"


def test_ci_python_license_text_job_installs_only_the_hash_checked_runtime_lock() -> None:
    section = _job_section("ci.yml", EVIDENCE_JOB)
    install = _step("ci.yml", EVIDENCE_JOB, "Install the runtime lock into an isolated venv")
    command = install["run"]

    assert f'python -m venv "{EVIDENCE_VENV}"' in command
    assert f'"{EVIDENCE_VENV}/bin/python" -m pip install {RUNTIME_LOCK_INSTALL}' in command

    # Exactly one install, into the throwaway venv, from the runtime lock alone:
    # no dev extras, no build/dev locks and no global tooling as evidence.
    assert section.count("-m pip install") == 1
    for forbidden in (
        '".[dev]"',
        "-e .",
        "requirements.lock",
        "requirements-build.lock",
        "pip_audit",
        "pip-audit",
        "pytest",
        "ruff",
        "npm",
        "playwright",
    ):
        assert forbidden not in section, forbidden


def test_ci_python_license_text_evidence_uses_the_locked_venv_purelib_and_fresh_output() -> None:
    collect = _step(
        "ci.yml", EVIDENCE_JOB, "Collect license/notice texts from the locked venv"
    )
    command = collect["run"]

    assert 'print(sysconfig.get_paths()["purelib"])' in command
    assert f'"{EVIDENCE_VENV}/bin/python" -c' in command
    assert '--site-packages "$venv_purelib"' in command
    assert f"--output-dir {EVIDENCE_OUTPUT_DIR}" in command
    assert "--runtime-lock requirements-runtime.lock" in command
    assert command.count(COLLECTOR_SCRIPT) == 1
    # The collector runs under the pinned setup-python interpreter and scans the
    # venv; the runner's own site-packages is never the evidence source.
    lines = [line.strip() for line in command.splitlines()]
    assert f"python {COLLECTOR_SCRIPT} \\" in lines

    # The collector refuses an existing output directory, so the evidence
    # directory may only be mentioned by the collection step and the upload.
    section = _job_section("ci.yml", EVIDENCE_JOB)
    assert section.count(EVIDENCE_OUTPUT_DIR) == 2
    assert section.index(EVIDENCE_OUTPUT_DIR) > section.index(
        "Collect license/notice texts from the locked venv"
    )


def test_ci_python_license_text_upload_always_runs_and_missing_files_fail() -> None:
    upload = _step("ci.yml", EVIDENCE_JOB, "Upload Python license text evidence")

    # An incomplete collection also uploads its manifest/partial texts, and a
    # missing report is an upload error: evidence cannot silently disappear.
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == EVIDENCE_ARTIFACT_NAME
    assert upload["with"]["path"] == EVIDENCE_OUTPUT_DIR
    assert upload["with"]["if-no-files-found"] == "error"

    section = _job_section("ci.yml", EVIDENCE_JOB)
    assert section.index("Upload Python license text evidence") > section.index(
        "Collect license/notice texts from the locked venv"
    )
    assert "continue-on-error" not in section


def test_ci_python_license_text_artifact_is_not_wired_into_release_publishing() -> None:
    release = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")

    assert COLLECTOR_SCRIPT not in release
    assert EVIDENCE_ARTIFACT_NAME not in release
    assert EVIDENCE_OUTPUT_DIR not in release


def test_ci_python_license_text_evidence_inputs_exist() -> None:
    assert (ROOT / "requirements-runtime.lock").is_file()
    assert (ROOT / COLLECTOR_SCRIPT).is_file()
    assert EVIDENCE_JOB in _workflow("ci.yml")["jobs"]
