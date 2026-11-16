"""Write every file made from the Eurogas Nexus mark.

    python3 scripts/ui/build_brand_assets.py            # all assets; needs Pillow
    python3 scripts/ui/build_brand_assets.py --svg-only # the SVG files only (no Pillow)

The geometry and colours live in ``src/eurogas_nexus/application/brand.py`` (and its copy in
``clients/web/src/components/ui/BrandMark.tsx``); ``docs/product/BRAND_MARK.md`` explains the
mark. Run from the repository root after changing either; the outputs are committed.

Writes:

* ``clients/web/public/favicon.svg``: colour mark, reverse on a dark browser tab bar;
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

import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from eurogas_nexus.application import brand  # noqa: E402

WEB_PUBLIC = ROOT / "clients" / "web" / "public"
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


def mark(size: int, *, tile: bool = True):
    """The mark at ``size`` px in reverse colours, on the navy tile by default; drawn at 8x and
    reduced for clean anti-aliasing."""

    from PIL import Image, ImageDraw

    scale = 8
    s = size * scale
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if tile:
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, s - 1, s - 1], radius=round(s * 13 / 64), fill=255
        )
        image.paste(_gradient((s, s), NAVY_TOP, NAVY_BOTTOM), (0, 0), mask)
    # On the tile the mark spans 68% of it, centred (78% at taskbar sizes, where every pixel
    # of stroke counts); without a tile it fills the square.
    span = s * ((0.78 if size <= 32 else 0.68) if tile else 1.0)
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


def main(argv: list[str]) -> int:
    write_svgs()
    if "--svg-only" not in argv:
        write_rasters()
    print("brand assets written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
