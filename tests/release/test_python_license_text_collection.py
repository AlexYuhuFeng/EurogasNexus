"""Installed-evidence license/notice text collection contracts.

Fixture-only tests for ``scripts/release/collect_python_license_texts.py``:
declared License-File collection (PEP 639 and legacy locations), RECORD
fallback for legacy metadata, refusal of traversal/symlink/unrecorded paths,
duplicate and version-mismatched distributions, missing/malformed
METADATA/RECORD, non-overwrite of the output directory, exact copied
bytes/hashes and deterministic manifests. They are not installed/locked
coverage on the release runner and not legal clearance.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.release.collect_python_license_texts import _license_basename_matches, collect, main

DIGEST = "0" * 64
FIXED_NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


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
