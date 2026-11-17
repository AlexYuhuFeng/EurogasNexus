"""Fonts shipped inside the web client are recorded, licensed for shipping and noticed.

The client bundles its interface face (``clients/web/src/styles/fonts.css``) so product text
never depends on a device font's stylistic sets. The face reaches every artefact that carries the
built client (web build, Tauri desktop bundle, demo image), so each file is recorded with its
SHA-256 and licence, and the licence text is reproduced in ``THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from scripts.release import generate_sboms

ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = ROOT / generate_sboms.BUNDLED_FONTS_DIR
FONTS_CSS = ROOT / "clients" / "web" / "src" / "styles" / "fonts.css"


def test_every_shipped_font_file_is_recorded_with_an_approved_licence() -> None:
    fonts = generate_sboms.collect_bundled_fonts()
    assert fonts, "the web client ships its interface face"
    for font in fonts:
        assert font["license"] in generate_sboms.BUNDLED_FONT_LICENSES
        assert (
            "SIL OPEN FONT LICENSE" in font["license_text"].upper() or font["license"] != "OFL-1.1"
        )
        assert font["files"]


def test_the_stylesheet_loads_exactly_the_recorded_files() -> None:
    manifest = json.loads((FONTS_DIR / "fonts.json").read_text(encoding="utf-8"))
    recorded = {entry["path"] for font in manifest["fonts"] for entry in font["files"]}
    referenced = set(
        re.findall(r'url\("\.\./assets/fonts/([^"]+)"\)', FONTS_CSS.read_text("utf-8"))
    )
    assert referenced == recorded


def test_the_checked_in_notices_carry_each_font_and_its_licence() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "## Bundled fonts" in notices
    for font in generate_sboms.collect_bundled_fonts():
        for item in font["files"]:
            assert item["sha256"] in notices
        assert font["license_text"].splitlines()[0] in notices


def _copy_fonts(tmp_path: Path) -> Path:
    target = tmp_path / generate_sboms.BUNDLED_FONTS_DIR
    shutil.copytree(FONTS_DIR, target)
    return target


def test_an_unrecorded_font_file_fails_generation(tmp_path: Path) -> None:
    fonts = _copy_fonts(tmp_path)
    (fonts / "inter" / "extra.woff2").write_bytes(b"not recorded")
    with pytest.raises(generate_sboms.SbomInputError, match="not recorded"):
        generate_sboms.collect_bundled_fonts(root=tmp_path)


def test_a_changed_font_file_fails_generation(tmp_path: Path) -> None:
    fonts = _copy_fonts(tmp_path)
    manifest = json.loads((fonts / "fonts.json").read_text(encoding="utf-8"))
    first = fonts / manifest["fonts"][0]["files"][0]["path"]
    first.write_bytes(first.read_bytes() + b"\0")
    assert (
        hashlib.sha256(first.read_bytes()).hexdigest() != manifest["fonts"][0]["files"][0]["sha256"]
    )
    with pytest.raises(generate_sboms.SbomInputError, match="SHA-256"):
        generate_sboms.collect_bundled_fonts(root=tmp_path)


def test_a_font_without_a_shippable_licence_fails_generation(tmp_path: Path) -> None:
    fonts = _copy_fonts(tmp_path)
    manifest = json.loads((fonts / "fonts.json").read_text(encoding="utf-8"))
    manifest["fonts"][0]["license"] = "LicenseRef-personal-use-only"
    (fonts / "fonts.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(generate_sboms.SbomInputError, match="not approved"):
        generate_sboms.collect_bundled_fonts(root=tmp_path)


def test_generated_notices_and_manifest_record_the_fonts(tmp_path: Path) -> None:
    output = tmp_path / "sbom"
    assert (
        generate_sboms.main(
            ["--output-dir", str(output), "--notices", str(output / "THIRD_PARTY_NOTICES.md")]
        )
        == 0
    )
    notices = (output / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "## Bundled fonts" in notices
    manifest = json.loads((output / "sbom-manifest.json").read_text(encoding="utf-8"))
    assert [font["name"] for font in manifest["bundled_fonts"]] == ["Inter"]
    assert "license_text" not in manifest["bundled_fonts"][0]
