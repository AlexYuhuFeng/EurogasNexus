"""The release builds and attaches the small-desk bundle (deploy/small-desk)."""

from __future__ import annotations

import json
import re
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
DIGEST = "sha256:" + "ab" * 32


def test_release_workflow_packages_and_attaches_the_bundle() -> None:
    jobs = WORKFLOW["jobs"]
    job = jobs["small-desk"]
    # The published digest and this release's own web client, never a rebuild.
    assert set(job["needs"]) == {"resolve", "web", "runtime-image"}
    for step in job["steps"]:
        uses = step.get("uses")
        if uses:
            assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", uses.split(" ")[0]), uses
    text = json.dumps(job)
    assert "package_small_desk_bundle.py" in text and "--image-digest" in text
    assert "--release-context" in text and "--archive" in text
    assert "/usr/bin/python3 -I" in text  # the tool starts on Ubuntu's own Python
    upload = next(step for step in job["steps"] if "upload-artifact" in step.get("uses", ""))
    assert upload["with"]["name"].startswith("release-")  # merged by assemble (release-*)
    assemble = jobs["assemble"]
    assert "small-desk" in assemble["needs"]
    assert "needs.small-desk.result == 'success'" in assemble["if"]


def test_the_artifact_contract_names_the_bundle() -> None:
    from scripts.release.release_artifacts import artifact_platform_arch, artifact_type

    name = "eurogas-nexus-small-desk-1.0.0-beta.2.tar.gz"
    assert artifact_type(name) == "small-desk-bundle"
    assert artifact_platform_arch(name) == ("linux", "all")
    assert artifact_type("eurogas-nexus-web-1.0.0-beta.2.tar.gz") == "web-bundle"


def _web_archive(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>")
    (dist / "assets" / "app.js").write_text("1")
    archive = tmp_path / "eurogas-nexus-web-1.0.0-beta.2.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(dist, arcname=".")
    return archive


def _package(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    context = tmp_path / "release-context.json"
    context.write_text(json.dumps({
        "release_version": "v1.0.0-beta.2",
        "api_image": "ghcr.io/example/eurogasnexus-api",
    }))
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/release/package_small_desk_bundle.py"),
         "--release-context", str(context), "--web-archive", str(_web_archive(tmp_path)),
         "--out", str(tmp_path / "release-assets"), "--archive", *extra],
        capture_output=True, text=True,
    )


def test_bundle_from_the_release_context_is_one_pinned_archive(tmp_path) -> None:
    done = _package(tmp_path, "--image-digest", DIGEST)
    assert done.returncode == 0, done.stderr
    archive = tmp_path / "release-assets" / "eurogas-nexus-small-desk-1.0.0-beta.2.tar.gz"
    assert Path(done.stdout.strip()) == archive
    assert [p.name for p in (tmp_path / "release-assets").iterdir()] == [archive.name]
    top = "eurogas-nexus-small-desk-1.0.0-beta.2"
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        assert all(name == top or name.startswith(top + "/") for name in names)
        nexus = tar.getmember(f"{top}/nexus")
        assert nexus.mode & stat.S_IXUSR
        release = json.load(tar.extractfile(f"{top}/release.json"))
        for name in ("deploy/compose.yaml", "deploy/Caddyfile", "deploy/database_roles.sql",
                     "nexusctl/cli.py", "web.tar.gz"):
            assert f"{top}/{name}" in names, name
        assert not any("__pycache__" in name for name in names)
    assert release["version"] == "1.0.0-beta.2"
    assert release["api_image"] == f"ghcr.io/example/eurogasnexus-api@{DIGEST}"
    assert set(release["sha256"]) >= {"web.tar.gz", "deploy/compose.yaml"}


@pytest.mark.parametrize("digest", ["", "latest", "sha256:1234", "SHA256:" + "AB" * 32])
def test_bundle_refuses_an_image_that_is_not_pinned(tmp_path, digest) -> None:
    done = _package(tmp_path, "--image-digest", digest)
    assert done.returncode != 0
    assert not (tmp_path / "release-assets").exists() or not any(
        (tmp_path / "release-assets").iterdir()
    )
