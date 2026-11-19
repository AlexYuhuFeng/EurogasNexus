"""Write every file made from the Eurogas Nexus mark.

    python3 scripts/ui/build_brand_assets.py            # all assets; needs Pillow
    python3 scripts/ui/build_brand_assets.py --svg-only # the SVG files only (no Pillow)

The geometry and colours live in ``src/eurogas_nexus/application/brand.py`` (and its copy in
``clients/web/src/components/ui/BrandMark.tsx``); ``docs/product/BRAND_MARK.md`` explains the
mark. Run from the repository root after changing either; the outputs are committed.

Writes:

* ``clients/web/public/favicon.svg``: colour mark, reverse on a dark browser tab bar;
* ``clients/web/public/favicon.ico`` (16, 32, 48 px), ``apple-touch-icon.png`` (180 px, full
  navy square: iOS rounds it), ``icons/icon-192.png``, ``icons/icon-512.png`` and
  ``icons/icon-maskable-512.png`` (the mark inside the 80% safe zone), and
  ``manifest.webmanifest``: what a browser asks for besides the SVG (``/favicon.ico`` by
  default, the home-screen icon, an installed web app);
* the icon links in ``clients/web/index.html`` (between the ``brand-icons`` markers), each with
  ``?v=<version>`` so a browser that cached an older mark under the same address fetches the new
  one: the version is the first 10 hex digits of the SHA-256 of ``favicon.svg``;
* ``clients/web/public/brand/icons.json``: that version, the hash of the mark it was drawn from
  and the SHA-256 of every file listed here; ``tests/unit/test_brand_icons.py`` fails when the
  mark changes and the files were not rewritten, or when a file was changed by hand;
* ``clients/web/public/brand/*.svg``: the mark (colour, reverse, mono) and the horizontal
  lock-up (colour, reverse) as standalone files;
* under ``clients/desktop/src-tauri/``: ``icons/32x32.png``, ``128x128.png``,
  ``128x128@2x.png``, ``icon.png`` and ``icon.ico`` (16-256 px), the reverse mark on a navy
  tile with transparent corners so it sits cleanly on any taskbar or dock; and
  ``installer/nsis-sidebar.bmp`` (164x314, welcome and finish pages) and
  ``installer/nsis-header.bmp`` (150x57, every other page), 24-bit as NSIS requires.

The installer text is set in Inter (SIL Open Font License), which permits rendering into
images for commercial use.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from eurogas_nexus.application import brand  # noqa: E402

WEB_PUBLIC = ROOT / "clients" / "web" / "public"
WEB_INDEX = ROOT / "clients" / "web" / "index.html"
ICON_MANIFEST = WEB_PUBLIC / "brand" / "icons.json"
ICONS_START, ICONS_END = "<!-- brand-icons:start -->", "<!-- brand-icons:end -->"
TAURI = ROOT / "clients" / "desktop" / "src-tauri"
FONT_DIR = Path("/usr/share/fonts/opentype/inter")


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    value = hex_colour.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


NAVY_TOP, NAVY_BOTTOM = _rgb(brand.NAVY), (11, 19, 36)  # --ds-brand-navy, --ds-brand-navy-deep
WHITE, BLUE_LIGHT = _rgb(brand.WHITE), _rgb(brand.BLUE_LIGHT)
TEXT_2, TEXT_3 = (185, 196, 214), (127, 140, 163)  # --ds-on-brand-2, --ds-on-brand-3


def write_svgs() -> None:
    (WEB_PUBLIC / "favicon.svg").write_text(brand.favicon_svg(), encoding="utf-8")
    out = WEB_PUBLIC / "brand"
    out.mkdir(exist_ok=True)
    for name, text in brand.standalone_svgs().items():
        (out / name).write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- raster (Pillow)


def _polyline(path: str) -> list[tuple[float, float]]:
    """Points of one of the module's paths (M, L, H, V and C), each cubic sampled finely."""

    points: list[tuple[float, float]] = []
    for command, args in re.findall(r"([MLHVC])([^MLHVC]*)", path):
        values = [float(v) for v in args.replace(",", " ").split()]
        x, y = points[-1] if points else (0.0, 0.0)
        if command in "ML":
            points.append((values[0], values[1]))
        elif command == "H":
            points.append((values[0], y))
        elif command == "V":
            points.append((x, values[0]))
        else:
            x1, y1, x2, y2, x3, y3 = values
            for i in range(1, 97):
                t = i / 96
                u = 1 - t
                points.append(
                    (
                        u**3 * x + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
                        u**3 * y + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
                    )
                )
    return points


def _gradient(size: tuple[int, int], top, bottom):
    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        draw.line(
            [(0, y), (width, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)),
        )
    return image


def mark(size: int, *, tile: bool = True, square: bool = False, span_share: float | None = None):
    """The mark at ``size`` px in reverse colours, on the navy tile by default; drawn at 8x and
    reduced for clean anti-aliasing. ``square`` fills the whole image (no rounded corners: the
    platform rounds or masks it); ``span_share`` overrides how much of the side the mark spans."""

    from PIL import Image, ImageDraw

    scale = 8
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if tile:
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, s - 1, s - 1], radius=0 if square else round(s * 13 / 64), fill=255
        )
        image.paste(_gradient((s, s), NAVY_TOP, NAVY_BOTTOM), (0, 0), mask)
    # On the tile the mark spans 68% of it, centred (78% at taskbar sizes, where every pixel
    # of stroke counts); without a tile it fills the square.
    share = span_share if span_share is not None else (0.78 if size <= 32 else 0.68)
    span = s * (share if tile else 1.0)
    unit = span / brand.GRID
    offset = (s - span) / 2
    width = max(1, round(brand.STROKE * unit))
    draw = ImageDraw.Draw(image)
    for path in (brand.HEX_UPPER, brand.HEX_LOWER):
        points = [(offset + x * unit, offset + y * unit) for x, y in _polyline(path)]
        draw.line(points, fill=WHITE, width=width, joint="curve")
    # The wave as a filled outline (the curve offset by half the stroke on each side): a wide
    # polyline through many short segments leaves a ragged edge.
    centre = [(offset + x * unit, offset + y * unit) for x, y in _polyline(brand.WAVE)]
    half = brand.STROKE * unit / 2
    left, right = [], []
    for i, (x, y) in enumerate(centre):
        (ax, ay), (bx, by) = centre[max(0, i - 1)], centre[min(len(centre) - 1, i + 1)]
        length = math.hypot(bx - ax, by - ay) or 1.0
        nx, ny = -(by - ay) / length, (bx - ax) / length
        left.append((x + nx * half, y + ny * half))
        right.append((x - nx * half, y - ny * half))
    draw.polygon(left + right[::-1], fill=BLUE_LIGHT)
    return image.resize((size, size), Image.LANCZOS)


def _font(weight: str, size: int):
    from PIL import ImageFont

    for name in (f"Inter-{weight}.otf", f"InterDisplay-{weight}.otf"):
        path = FONT_DIR / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def sidebar():
    """Welcome and finish pages: navy panel, the mark, the product name, a quiet line."""

    from PIL import ImageDraw

    image = _gradient((164, 314), NAVY_TOP, NAVY_BOTTOM)
    glyph = mark(44, tile=False)
    image.paste(glyph, (20, 32), glyph)
    draw = ImageDraw.Draw(image)
    draw.text((20, 100), "Eurogas", font=_font("SemiBold", 22), fill=WHITE)
    draw.text((20, 126), "Nexus", font=_font("SemiBold", 22), fill=BLUE_LIGHT)
    body = _font("Regular", 11)
    for i, line in enumerate(("European gas", "trading workstation")):
        draw.text((20, 172 + i * 16), line, font=body, fill=TEXT_2)
    draw.text((20, 286), "Decision support", font=_font("Regular", 9), fill=TEXT_3)
    return image


def header():
    """Inner pages: white band with the tiled mark on the right, as Windows installers expect."""

    from PIL import Image

    image = Image.new("RGB", (150, 57), WHITE)
    glyph = mark(36)
    image.paste(glyph, (104, 10), glyph)
    return image


def write_rasters() -> None:
    icons = TAURI / "icons"
    for name, size in (
        ("32x32.png", 32),
        ("128x128.png", 128),
        ("128x128@2x.png", 256),
        ("icon.png", 512),
    ):
        mark(size).save(icons / name)
    # Each icon size drawn at its own size (not one image reduced), so small sizes stay sharp.
    sizes = (16, 24, 32, 48, 64, 128, 256)
    mark(256).save(
        icons / "icon.ico",
        sizes=[(n, n) for n in sizes],
        append_images=[mark(n) for n in sizes[:-1]],
    )
    out = TAURI / "installer"
    out.mkdir(exist_ok=True)
    sidebar().save(out / "nsis-sidebar.bmp")
    header().save(out / "nsis-header.bmp")


def icon_version() -> str:
    """The cache-busting version: the first 10 hex digits of the favicon's SHA-256."""

    return hashlib.sha256(brand.favicon_svg().encode("utf-8")).hexdigest()[:10]


def web_manifest(version: str) -> str:
    icons = [
        {"src": f"/icons/icon-192.png?v={version}", "sizes": "192x192", "type": "image/png"},
        {"src": f"/icons/icon-512.png?v={version}", "sizes": "512x512", "type": "image/png"},
        {
            "src": f"/icons/icon-maskable-512.png?v={version}",
            "sizes": "512x512",
            "type": "image/png",
            "purpose": "maskable",
        },
    ]
    manifest = {
        "name": "Eurogas Nexus",
        "short_name": "Eurogas Nexus",
        "start_url": "/",
        "display": "standalone",
        "background_color": brand.NAVY,
        "theme_color": brand.NAVY,
        "icons": icons,
    }
    return json.dumps(manifest, indent=2) + "\n"


def icon_links(version: str) -> str:
    return "\n".join(
        [
            ICONS_START,
            # The ICO first with a size, the SVG after: browsers that read SVG icons take it.
            f'  <link rel="icon" href="/favicon.ico?v={version}" sizes="32x32" />',
            f'  <link rel="icon" type="image/svg+xml" href="/favicon.svg?v={version}" />',
            f'  <link rel="apple-touch-icon" href="/apple-touch-icon.png?v={version}" />',
            f'  <link rel="manifest" href="/manifest.webmanifest?v={version}" />',
            f'  <meta name="theme-color" content="{brand.NAVY}" />',
            f"  {ICONS_END}",
        ]
    )


def write_web_icons() -> None:
    """The web client's icons, its manifest and the versioned links in ``index.html``."""

    version = icon_version()
    sizes = (16, 32, 48)
    mark(48).save(
        WEB_PUBLIC / "favicon.ico",
        sizes=[(n, n) for n in sizes],
        append_images=[mark(n) for n in sizes[:-1]],
    )
    mark(180, square=True).save(WEB_PUBLIC / "apple-touch-icon.png")
    icons = WEB_PUBLIC / "icons"
    icons.mkdir(exist_ok=True)
    mark(192).save(icons / "icon-192.png")
    mark(512).save(icons / "icon-512.png")
    # A maskable icon may be cut to a circle: the mark stays inside the central 80%.
    mark(512, square=True, span_share=0.56).save(icons / "icon-maskable-512.png")
    (WEB_PUBLIC / "manifest.webmanifest").write_text(web_manifest(version), encoding="utf-8")
    html = WEB_INDEX.read_text(encoding="utf-8")
    block = re.compile(re.escape(ICONS_START) + r".*?" + re.escape(ICONS_END), re.S)
    if block.search(html):
        html = block.sub(lambda _: icon_links(version), html)
    else:
        html = re.sub(
            r'  <link rel="icon"[^>]*/>', lambda _: "  " + icon_links(version), html, count=1
        )
    WEB_INDEX.write_text(html, encoding="utf-8")


#: Every file drawn from the mark, relative to the repository root (icons.json lists them all).
DERIVED_FILES = (
    "clients/web/public/favicon.svg",
    "clients/web/public/favicon.ico",
    "clients/web/public/apple-touch-icon.png",
    "clients/web/public/icons/icon-192.png",
    "clients/web/public/icons/icon-512.png",
    "clients/web/public/icons/icon-maskable-512.png",
    "clients/web/public/manifest.webmanifest",
    "clients/web/public/brand/eurogas-nexus-mark.svg",
    "clients/web/public/brand/eurogas-nexus-mark-reverse.svg",
    "clients/web/public/brand/eurogas-nexus-mark-mono.svg",
    "clients/web/public/brand/eurogas-nexus-lockup.svg",
    "clients/web/public/brand/eurogas-nexus-lockup-reverse.svg",
    "clients/desktop/src-tauri/icons/32x32.png",
    "clients/desktop/src-tauri/icons/128x128.png",
    "clients/desktop/src-tauri/icons/128x128@2x.png",
    "clients/desktop/src-tauri/icons/icon.png",
    "clients/desktop/src-tauri/icons/icon.ico",
    "clients/desktop/src-tauri/installer/nsis-sidebar.bmp",
    "clients/desktop/src-tauri/installer/nsis-header.bmp",
)


def write_manifest() -> None:
    files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in DERIVED_FILES}
    manifest = {
        "about": "Written by scripts/ui/build_brand_assets.py; do not edit by hand.",
        "source": "src/eurogas_nexus/application/brand.py",
        "mark_sha256": hashlib.sha256(brand.favicon_svg().encode("utf-8")).hexdigest(),
        "version": icon_version(),
        "files": files,
    }
    ICON_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    write_svgs()
    if "--svg-only" not in argv:
        write_rasters()
        write_web_icons()
        write_manifest()
    print("brand assets written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
