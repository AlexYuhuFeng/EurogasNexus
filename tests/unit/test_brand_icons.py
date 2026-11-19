"""Every icon a browser, phone, desktop shell or installer shows is drawn from the current mark.

``scripts/ui/build_brand_assets.py`` writes the icons and ``clients/web/public/brand/icons.json``
(the mark's hash, the cache-busting version and every derived file's hash) in one run. These
tests fail when the mark in ``application/brand.py`` changed and the icons were not rewritten,
when an icon was replaced by hand, or when a page links an icon without the current version
(a browser keeps a cached icon under an unchanged address: the demo showed the old logo).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from eurogas_nexus.application import brand

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads((ROOT / "clients/web/public/brand/icons.json").read_text(encoding="utf-8"))
REGENERATE = "run: python3 scripts/ui/build_brand_assets.py (needs Pillow)"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_icons_were_drawn_from_the_current_mark():
    current = hashlib.sha256(brand.favicon_svg().encode("utf-8")).hexdigest()
    assert MANIFEST["mark_sha256"] == current, f"the mark changed; {REGENERATE}"
    assert MANIFEST["version"] == current[:10]


def test_every_icon_file_is_the_one_the_generator_wrote():
    files = MANIFEST["files"]
    required = {
        "clients/web/public/favicon.svg",
        "clients/web/public/favicon.ico",
        "clients/web/public/apple-touch-icon.png",
        "clients/web/public/icons/icon-192.png",
        "clients/web/public/icons/icon-512.png",
        "clients/web/public/icons/icon-maskable-512.png",
        "clients/web/public/manifest.webmanifest",
        "clients/desktop/src-tauri/icons/icon.ico",
        "clients/desktop/src-tauri/icons/icon.png",
        "clients/desktop/src-tauri/icons/32x32.png",
        "clients/desktop/src-tauri/icons/128x128.png",
        "clients/desktop/src-tauri/icons/128x128@2x.png",
        "clients/desktop/src-tauri/installer/nsis-sidebar.bmp",
        "clients/desktop/src-tauri/installer/nsis-header.bmp",
    }
    assert required <= set(files), sorted(required - set(files))
    for name, digest in files.items():
        assert _sha(ROOT / name) == digest, f"{name} differs from the generated file; {REGENERATE}"


def test_no_icon_outside_the_manifest():
    """A raster icon nobody regenerates is how an old logo survives."""

    listed = set(MANIFEST["files"])
    candidates = [
        *(ROOT / "clients/web/public").glob("*.ico"),
        *(ROOT / "clients/web/public").glob("*.png"),
        *(ROOT / "clients/web/public/icons").glob("*"),
        *(ROOT / "clients/desktop/src-tauri/icons").glob("*"),
    ]
    stray = sorted(
        str(path.relative_to(ROOT))
        for path in candidates
        if path.is_file() and str(path.relative_to(ROOT)) not in listed
    )
    assert stray == [], f"icons not drawn by the generator: {stray}"


def test_pages_link_the_icons_with_the_current_version():
    version = MANIFEST["version"]
    html = (ROOT / "clients/web/index.html").read_text(encoding="utf-8")
    links = re.findall(r'href="(/[^"]+)"', html)
    for target in (
        "/favicon.ico",
        "/favicon.svg",
        "/apple-touch-icon.png",
        "/manifest.webmanifest",
    ):
        assert f"{target}?v={version}" in links, f"index.html must link {target}?v={version}"
    manifest = json.loads(
        (ROOT / "clients/web/public/manifest.webmanifest").read_text(encoding="utf-8")
    )
    assert {icon["src"].split("?v=")[1] for icon in manifest["icons"]} == {version}
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


def test_the_splash_and_the_desktop_shell_show_the_current_mark():
    splash = (ROOT / "clients/web/public/splash.html").read_text(encoding="utf-8")
    for path in (brand.HEX_UPPER, brand.HEX_LOWER, brand.WAVE):
        assert f'd="{path}"' in splash, "splash.html draws an old mark"
    tauri = json.loads(
        (ROOT / "clients/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )
    icons = tauri["bundle"]["icon"]
    assert icons and all(f"clients/desktop/src-tauri/{name}" in MANIFEST["files"] for name in icons)
