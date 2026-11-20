"""A beta .deb carries the Debian spelling of its version (1.0.0~beta1)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from eurogas_nexus.release.versioning import parse_app_version
from scripts.release import set_deb_version

pytestmark = pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="needs dpkg-deb")


def _build_deb(tmp_path: Path, version: str) -> Path:
    tree = tmp_path / "tree"
    (tree / "DEBIAN").mkdir(parents=True)
    (tree / "usr" / "share" / "doc" / "demo").mkdir(parents=True)
    (tree / "usr" / "share" / "doc" / "demo" / "README").write_text("demo\n")
    (tree / "DEBIAN" / "control").write_text(
        "Package: eurogas-nexus\n"
        f"Version: {version}\n"
        "Architecture: amd64\n"
        "Maintainer: Eurogas Nexus\n"
        "Description: test package\n",
        encoding="utf-8",
    )
    deb = tmp_path / "package.deb"
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "-b", str(tree), str(deb)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return deb


def _version(deb: Path) -> str:
    return subprocess.run(
        ["dpkg-deb", "-f", str(deb), "Version"], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_beta_package_gets_the_debian_spelling(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        set_deb_version, "canonical_version_identity", lambda: parse_app_version("1.0.0b1")
    )
    deb = _build_deb(tmp_path, "1.0.0-beta.1")
    assert set_deb_version.main([str(deb)]) == 0
    assert _version(deb) == "1.0.0~beta1"
    contents = subprocess.run(
        ["dpkg-deb", "-c", str(deb)], check=True, capture_output=True, text=True
    ).stdout
    assert "./usr/share/doc/demo/README" in contents and "root/root" in contents
    # dpkg orders it before the stable release, so 1.0.0 later installs as an upgrade.
    compare = ["dpkg", "--compare-versions", "1.0.0~beta1", "lt", "1.0.0"]
    assert subprocess.run(compare, check=False).returncode == 0


def test_a_final_version_leaves_the_package_as_built(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        set_deb_version, "canonical_version_identity", lambda: parse_app_version("1.0.0")
    )
    deb = _build_deb(tmp_path, "1.0.0")
    before = deb.read_bytes()
    assert set_deb_version.main([str(deb)]) == 0
    assert deb.read_bytes() == before
