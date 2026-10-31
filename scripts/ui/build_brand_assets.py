"""Draw the Eurogas Nexus mark and every desktop asset made from it.

    python3 scripts/ui/build_brand_assets.py      # needs Pillow; run from the repo root

One mark everywhere (favicon, app icon, installer, splash): a dark navy tile with a white
hub and an orange core joined by teal spokes to three white nodes.
Writes, under clients/desktop/src-tauri/:

* icons/32x32.png, 128x128.png, 128x128@2x.png, icon.png and icon.ico (16-256 px) with
  transparent corners, so the tile sits cleanly on any taskbar or dock;
* installer/nsis-sidebar.bmp (164x314, welcome and finish pages) and
  installer/nsis-header.bmp (150x57, every other page), 24-bit as NSIS requires.

The text is set in Inter (SIL Open Font License), which permits rendering into images for
commercial use. Re-run after changing the mark; the outputs are committed.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
TAURI = ROOT / "clients" / "desktop" / "src-tauri"
NAVY_TOP, NAVY_BOTTOM = (16, 28, 52), (11, 19, 36)
TEAL, ORANGE, WHITE = (45, 212, 191), (249, 115, 22), (255, 255, 255)
FONT_DIR = Path("/usr/share/fonts/opentype/inter")


def _gradient(size: tuple[int, int], top, bottom) -> Image.Image:
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


def mark(size: int, *, tile: bool = True) -> Image.Image:
    """The mark at ``size`` px, drawn at 4x and reduced for clean anti-aliasing."""

    s = size * 4
    unit = s / 64
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if tile:
        mask = Image.new("L", (s, s), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, s - 1, s - 1], radius=round(13 * unit), fill=255
        )
        image.paste(_gradient((s, s), NAVY_TOP, NAVY_BOTTOM), (0, 0), mask)
    draw = ImageDraw.Draw(image)
    # A hub joined to three points: the connection point a nexus is. Teal spokes are the
    # flows, white nodes the points, and the orange core the firm at the centre.
    hub = (32 * unit, 34 * unit)
    points = [(15 * unit, 21 * unit), (49 * unit, 21 * unit), (32 * unit, 52 * unit)]
    for point in points:
        draw.line([hub, point], fill=TEAL, width=round(4.2 * unit))
    for x, y in points:
        r = 5 * unit
        draw.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)
    x, y = hub
    for radius, colour in ((8.5, WHITE), (4.2, ORANGE)):
        r = radius * unit
        draw.ellipse([x - r, y - r, x + r, y + r], fill=colour)
    return image.resize((size, size), Image.LANCZOS)


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for name in (f"Inter-{weight}.otf", f"InterDisplay-{weight}.otf"):
        path = FONT_DIR / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def sidebar() -> Image.Image:
    """Welcome and finish pages: navy panel, mark, product name, a quiet line."""

    image = _gradient((164, 314), NAVY_TOP, NAVY_BOTTOM)
    image.paste(mark(56), (20, 28), mark(56))
    draw = ImageDraw.Draw(image)
    draw.text((20, 100), "Eurogas", font=_font("SemiBold", 22), fill=WHITE)
    draw.text((20, 126), "Nexus", font=_font("SemiBold", 22), fill=WHITE)
    draw.line([(20, 162), (52, 162)], fill=TEAL, width=2)
    body = _font("Regular", 11)
    for i, line in enumerate(("European gas", "trading workstation")):
        draw.text((20, 174 + i * 16), line, font=body, fill=(186, 196, 214))
    draw.text((20, 286), "Decision support", font=_font("Regular", 9), fill=(120, 134, 160))
    return image


def header() -> Image.Image:
    """Inner pages: white band with the mark on the right, as Windows installers expect."""

    image = Image.new("RGB", (150, 57), WHITE)
    image.paste(mark(36), (104, 10), mark(36))
    return image


def main() -> int:
    icons = TAURI / "icons"
    for name, size in (
        ("32x32.png", 32),
        ("128x128.png", 128),
        ("128x128@2x.png", 256),
        ("icon.png", 512),
    ):
        mark(size).save(icons / name)
    mark(256).save(
        icons / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    out = TAURI / "installer"
    out.mkdir(exist_ok=True)
    sidebar().save(out / "nsis-sidebar.bmp")
    header().save(out / "nsis-header.bmp")
    print("brand assets written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
