"""The Eurogas Nexus mark as SVG text, for anything the server renders (reports, e-mail).

One geometry, written once here and once in ``clients/web/src/components/ui/BrandMark.tsx``;
``tests/unit/test_brand_mark.py`` holds the two to the same path data and checks that the
hexagon is regular. ``docs/product/BRAND_MARK.md`` explains the construction and where each
variant goes.

The mark is drawn on a 32-unit square: a regular hexagon (point up, circumradius 14, centred
at 16,16) stroked 2.5 units with round joins, broken where one wave passes through it. The
wave is a single cubic between two short horizontal runs: it enters the left side low and
leaves the right side high, so the mark is the same turned half a circle. Every coordinate is
a whole or half unit except the hexagon's two vertical sides, at 16 +/- 14 * sqrt(3) / 2.

Nothing here loads a font, an image or a URL: a report stays one self-contained file.
"""

from __future__ import annotations

import math
from html import escape
from typing import Literal

Tone = Literal["colour", "reverse", "mono", "adaptive"]

#: The construction (units of the 32-unit grid).
GRID = 32
CENTRE = 16.0
RADIUS = 14.0
STROKE = 2.5
#: Clear gap between the wave's edge and the broken ends of the hexagon.
GAP = 1.25
#: The wave sits this far below the centre on the left and above it on the right.
WAVE_OFFSET = 3.0

HALF_WIDTH = RADIUS * math.sqrt(3) / 2


def _n(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def hexagon_vertices() -> list[tuple[float, float]]:
    """The six vertices, clockwise from the top (point-up hexagon)."""

    return [
        (
            CENTRE + RADIUS * math.cos(math.radians(angle)),
            CENTRE - RADIUS * math.sin(math.radians(angle)),
        )
        for angle in (90, 30, -30, -90, -150, 150)
    ]


def _paths() -> tuple[str, str, str]:
    left, right = CENTRE - HALF_WIDTH, CENTRE + HALF_WIDTH
    low, high = CENTRE + WAVE_OFFSET, CENTRE - WAVE_OFFSET
    cut = STROKE / 2 + GAP
    top, upper, lower, bottom = (
        CENTRE - RADIUS,
        CENTRE - RADIUS / 2,
        CENTRE + RADIUS / 2,
        CENTRE + RADIUS,
    )
    hex_upper = (
        f"M{_n(left)} {_n(low - cut)}V{_n(upper)}L{_n(CENTRE)} {_n(top)}"
        f"L{_n(right)} {_n(upper)}V{_n(high - cut)}"
    )
    hex_lower = (
        f"M{_n(right)} {_n(high + cut)}V{_n(lower)}L{_n(CENTRE)} {_n(bottom)}"
        f"L{_n(left)} {_n(lower)}V{_n(low + cut)}"
    )
    wave = f"M1.5 {_n(low)}H5C15 {_n(low)} 17 {_n(high)} 27 {_n(high)}H30.5"
    return hex_upper, hex_lower, wave


#: SVG path data: the hexagon's two halves and the wave.
HEX_UPPER, HEX_LOWER, WAVE = _paths()

#: Brand colours (``--ds-brand-navy``, ``--ds-brand-blue`` and ``--ds-brand-blue-light`` in
#: ``clients/web/src/styles/tokens.css``; the two blues are the accent of the light and the
#: dark theme).
NAVY = "#101c34"
BLUE = "#1d4ed8"
BLUE_LIGHT = "#6ea8fe"
WHITE = "#ffffff"

#: The wordmark's face where no web font can be loaded (a report, a standalone file).
FONT = (
    'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", '
    "Arial, sans-serif"
)

_COLOURS: dict[str, tuple[str, str]] = {
    "colour": (NAVY, BLUE),
    "reverse": (WHITE, BLUE_LIGHT),
    "mono": ("currentColor", "currentColor"),
    # Light colours as attributes (print, e-mail); a screen in dark mode switches to reverse.
    "adaptive": (NAVY, BLUE),
}

_ADAPTIVE_STYLE = (
    "<style>@media screen and (prefers-color-scheme: dark){"
    f".egn-hex{{stroke:{WHITE}}}.egn-wave{{stroke:{BLUE_LIGHT}}}}}</style>"
)


def _a11y(title: str | None) -> str:
    if title is None:
        return ' aria-hidden="true" focusable="false"'
    return f' role="img" aria-label="{escape(title)}"'


def _strokes(tone: Tone) -> str:
    hexagon, wave = _COLOURS[tone]
    return (
        f'<g fill="none" stroke-width="{_n(STROKE)}" stroke-linejoin="round" stroke-linecap="butt">'
        f'<path class="egn-hex" d="{HEX_UPPER}" stroke="{hexagon}"/>'
        f'<path class="egn-hex" d="{HEX_LOWER}" stroke="{hexagon}"/>'
        f'<path class="egn-wave" d="{WAVE}" stroke="{wave}"/></g>'
    )


def mark_svg(
    tone: Tone = "colour", *, size: int | None = 24, title: str | None = "Eurogas Nexus"
) -> str:
    """The mark alone. ``title=None`` hides it from assistive technology (use that when the
    product name is written beside it). ``size=None`` leaves the SVG to its container."""

    if tone not in _COLOURS:
        raise ValueError(f"unknown tone {tone!r}")
    dims = "" if size is None else f' width="{size}" height="{size}"'
    style = _ADAPTIVE_STYLE if tone == "adaptive" else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}"{dims}{_a11y(title)}>'
        f"{style}{_strokes(tone)}</svg>"
    )


def lockup_svg(
    tone: Tone = "colour", *, height: int = 32, title: str | None = "Eurogas Nexus"
) -> str:
    """Mark and "Eurogas Nexus" side by side, the name in the system sans (no font file).

    For a place that takes one image. In HTML, prefer :func:`mark_svg` followed by the name as
    live text: it selects, translates and scales with the page.
    """

    if tone not in _COLOURS:
        raise ValueError(f"unknown tone {tone!r}")
    hexagon, wave = _COLOURS[tone]
    name = "currentColor" if tone == "mono" else hexagon
    nexus = "currentColor" if tone == "mono" else wave
    # 32 units of mark, 10 of space, then the name at 18 units on the mark's centre line;
    # the width leaves room for a wider system face than Inter.
    width = 182
    style = (
        "<style>@media screen and (prefers-color-scheme: dark){"
        f".egn-hex{{stroke:{WHITE}}}.egn-name{{fill:{WHITE}}}.egn-wave{{stroke:{BLUE_LIGHT}}}.egn-nexus{{fill:{BLUE_LIGHT}}}}}</style>"
        if tone == "adaptive"
        else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {GRID}" '
        f'width="{round(height * width / GRID)}" height="{height}"{_a11y(title)}>'
        f"{style}{_strokes(tone)}"
        f'<text x="42" y="22.5" font-family=\'{FONT}\' font-size="18" font-weight="600" '
        f'letter-spacing="-0.2" fill="{name}" class="egn-name">Eurogas '
        f'<tspan fill="{nexus}" class="egn-nexus">Nexus</tspan></text></svg>'
    )


def favicon_svg() -> str:
    """The browser-tab icon: colour on a light tab bar, reverse on a dark one."""

    return mark_svg("adaptive", size=None) + "\n"


def standalone_svgs() -> dict[str, str]:
    """The files under ``clients/web/public/brand/`` (``scripts/ui/build_brand_assets.py``
    writes them; a test keeps them equal to this module)."""

    return {
        "eurogas-nexus-mark.svg": mark_svg("colour", size=None) + "\n",
        "eurogas-nexus-mark-reverse.svg": mark_svg("reverse", size=None) + "\n",
        "eurogas-nexus-mark-mono.svg": mark_svg("mono", size=None) + "\n",
        "eurogas-nexus-lockup.svg": lockup_svg("colour") + "\n",
        "eurogas-nexus-lockup-reverse.svg": lockup_svg("reverse") + "\n",
    }
