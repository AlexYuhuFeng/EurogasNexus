"""The Eurogas Nexus mark: one geometry for the server (reports) and the web client.

``src/eurogas_nexus/application/brand.py`` and ``clients/web/src/components/ui/BrandMark.tsx``
carry the same path data; the standalone SVG files and the favicon are written from the module
by ``scripts/ui/build_brand_assets.py``. These tests hold all of them together and check the
construction docs/product/BRAND_MARK.md describes.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from eurogas_nexus.application import brand

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "clients" / "web"


def _numbers(path: str) -> list[float]:
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", path)]


def test_the_hexagon_is_regular_and_centred():
    vertices = brand.hexagon_vertices()
    sides = [math.dist(a, b) for a, b in zip(vertices, vertices[1:] + vertices[:1], strict=True)]
    assert all(abs(side - brand.RADIUS) < 1e-9 for side in sides)
    assert all(
        abs(math.dist(v, (brand.CENTRE, brand.CENTRE)) - brand.RADIUS) < 1e-9 for v in vertices
    )
    # The path data rounds the two vertical sides to 3 decimals: under 0.001 of a unit.
    left, right = vertices[5][0], vertices[1][0]
    assert (round(left, 3), round(right, 3)) == (3.876, 28.124)
    for path in (brand.HEX_UPPER, brand.HEX_LOWER):
        drawn = [x for x in _numbers(path) if x * 2 != int(x * 2)]
        assert drawn and all(min(abs(x - left), abs(x - right)) < 5e-4 for x in drawn)


def test_the_mark_is_the_same_turned_half_a_circle():
    upper = _numbers(brand.HEX_UPPER)
    lower = _numbers(brand.HEX_LOWER)
    assert [round(brand.GRID - v, 3) for v in upper] == lower
    # M x y H x C x y x y x y H x: turned about the centre, the wave is its own reverse.
    wave = _numbers(brand.WAVE)
    assert wave == [1.5, 19, 5, 15, 19, 17, 13, 27, 13, 30.5]
    points = [(1.5, 19), (5, 19), (15, 19), (17, 13), (27, 13), (30.5, 13)]
    assert [(32 - x, 32 - y) for x, y in reversed(points)] == points


def test_the_wave_crosses_the_sides_horizontally_with_a_clear_gap():
    left = 16 - brand.HALF_WIDTH
    # The horizontal runs reach past both vertical sides, so each crossing is square.
    assert 1.5 < left - brand.STROKE / 2 and 5 > left
    # The broken ends of the hexagon stand GAP clear of the wave's edge.
    upper = _numbers(brand.HEX_UPPER)
    assert upper[1] == 19 - brand.STROKE / 2 - brand.GAP
    assert upper[-1] == 13 - brand.STROKE / 2 - brand.GAP
    # Every coordinate but the vertical sides is a whole or half unit.
    for path in (brand.HEX_UPPER, brand.HEX_LOWER, brand.WAVE):
        for value in _numbers(path):
            if round(value, 3) in {3.876, 28.124}:
                continue
            assert value * 2 == int(value * 2), value


def test_the_web_component_draws_the_same_paths():
    source = (WEB / "src" / "components" / "ui" / "BrandMark.tsx").read_text(encoding="utf-8")
    assert f'BRAND_HEX_UPPER = "{brand.HEX_UPPER}"' in source
    assert f'BRAND_HEX_LOWER = "{brand.HEX_LOWER}"' in source
    assert f'BRAND_WAVE = "{brand.WAVE}"' in source
    assert f"BRAND_STROKE = {brand.STROKE}" in source


def test_brand_colours_are_the_web_tokens():
    tokens = (WEB / "src" / "styles" / "tokens.css").read_text(encoding="utf-8")
    assert f"--ds-brand-navy: {brand.NAVY};" in tokens
    assert f"--ds-brand-blue: {brand.BLUE};" in tokens
    assert f"--ds-brand-blue-light: {brand.BLUE_LIGHT};" in tokens


def test_committed_svg_files_are_the_module_output():
    """Re-run ``python3 scripts/ui/build_brand_assets.py`` when this fails."""

    assert (WEB / "public" / "favicon.svg").read_text(encoding="utf-8") == brand.favicon_svg()
    for name, text in brand.standalone_svgs().items():
        assert (WEB / "public" / "brand" / name).read_text(encoding="utf-8") == text, name


@pytest.mark.parametrize("tone", ["colour", "reverse", "mono", "adaptive"])
def test_the_svg_is_self_contained(tone):
    for svg in (brand.mark_svg(tone), brand.lockup_svg(tone)):
        assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
        assert "href" not in svg and "url(" not in svg and "@import" not in svg
        assert "<image" not in svg and "@font-face" not in svg
    assert 'aria-label="Eurogas Nexus"' in brand.mark_svg(tone)
    assert "aria-hidden" in brand.mark_svg(tone, title=None)


def test_adaptive_switches_to_reverse_on_a_dark_screen_only():
    svg = brand.mark_svg("adaptive")
    assert f'stroke="{brand.NAVY}"' in svg and f'stroke="{brand.BLUE}"' in svg
    assert "@media screen and (prefers-color-scheme: dark)" in svg
    assert brand.BLUE_LIGHT in svg


def test_mark_svg_is_deterministic_and_rejects_unknown_tones():
    assert brand.mark_svg("colour", size=28) == brand.mark_svg("colour", size=28)
    with pytest.raises(ValueError):
        brand.mark_svg("rainbow")  # type: ignore[arg-type]
