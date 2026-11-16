# Brand mark

The Eurogas Nexus mark is a regular hexagon with one wave passing through it: the wave reads as
gas flowing through the network and as a price curve moving from a lower level to a higher one.
It is drawn by hand as SVG (no tracing, no raster, no font) and is the same everywhere: the
application, the sign-in screen, the browser tab, the desktop app and installer, and reports.

## Construction

![Construction of the mark on its 32-unit grid](../../clients/web/public/brand/eurogas-nexus-mark.svg)

- **Grid.** A 32-unit square, centre at (16, 16). The mark spans x 1.5 to 30.5 and y 0.75 to
  31.25 (stroke included), so it is optically square and centred.
- **Hexagon.** Regular, point up, circumradius 14: vertices at (16, 2), (28.124, 9),
  (28.124, 23), (16, 30), (3.876, 23), (3.876, 9). The vertical sides sit at
  16 ± 14·√3/2; every other coordinate in the mark is a whole or half unit.
- **Stroke.** 2.5 units everywhere, hexagon and wave alike. Round joins (the corners of the
  hexagon read clean at small sizes and match the round shoulders of the interface face); butt
  ends where the hexagon is broken and at the ends of the wave, so every cut is square.
- **Wave.** One cubic between two short horizontal runs: `M1.5 19 H5 C15 19 17 13 27 13 H30.5`.
  It enters the left side 3 units below the centre and leaves the right side 3 units above it;
  the runs cross each side at right angles and stand 1.25 units proud of its outer edge.
- **Gaps.** The hexagon breaks 1.25 units clear of the wave's edge on each side of a crossing.
- **Symmetry.** Turned half a circle about the centre, the mark is itself.

The geometry is written once in `src/eurogas_nexus/application/brand.py` and once in
`clients/web/src/components/ui/BrandMark.tsx`; `tests/unit/test_brand_mark.py` checks that the
hexagon is regular, the mark is point-symmetric, the gaps are as stated, and the two copies and
the committed files agree.

## Variants

| Variant | Use |
|---|---|
| Mark + "Eurogas Nexus" (`wordmark`) | Wherever there is room: the top bar at wide widths, sign-in, report header, installer |
| Mark + "EN" (`monogram`) | Narrow fixed slots where the full name does not fit but a mark alone is too anonymous (a collapsed rail, a slide footer) |
| Mark only (`mark`) | The top bar at medium and compact widths, the favicon, app icons, inline next to the written name |

The name is set in the interface face (`--ds-font-ui`, semibold, −0.01 em) as live text, and
stays "Eurogas Nexus" in English and Chinese. Standalone SVG files cannot rely on a font, so
only the mark and one horizontal lock-up (system sans) exist as files.

## Colour

| Tone | Hexagon | Wave | Name | Where |
|---|---|---|---|---|
| Mono | `currentColor` | `currentColor` | `currentColor` | Application chrome (the top bar): follows the theme, never competes with prices |
| Colour | `--ds-brand-navy` `#101c34` | `--ds-brand-blue` `#1d4ed8` | navy, "Nexus" blue | Light grounds: reports, print, a light sign-in card |
| Reverse | white | `--ds-brand-blue-light` `#6ea8fe` | white, "Nexus" light blue | The navy sign-in panel, splash, installer, desktop icon tile |
| Auto | colour in light, reverse in dark | | | A surface that follows the theme (the sign-in card on a phone) |

The two blues are the light and dark theme accents; the brand adds no new hue.
`clients/web/tests/tokenContrast.test.ts` holds navy and blue on every light surface, and white
and light blue on the navy panel, to 4.5:1 (the name is text). Colour is never used on a dark
surface and reverse never on a light one; mono works on both.

## Clear space and minimum size

- **Clear space:** at least a quarter of the mark's height (8 of 32 units) on every side, free
  of other text, controls and edges. In the top bar the 8 px gap to the lines of work is the
  rule at 24 px.
- **Mark to name:** 8 px at 20 and 24 px marks, 12 px at 32 and 40 px.
- **Minimum size:** 16 px for the mark (favicon), 20 px for a lock-up. Below 24 px prefer mono
  or the tiled desktop icon: at 16 px the gaps are about one pixel.

## Do and don't

- Do use `BrandMark` in the web client and `brand.mark_svg()` / `lockup_svg()` on the server;
  do run `python3 scripts/ui/build_brand_assets.py` after changing either copy of the geometry.
- Don't redraw, stretch, rotate, outline, add effects or a container shape (the desktop icon's
  navy tile is the one exception, because a taskbar needs a solid ground).
- Don't recolour the wave in a status or P&L colour, and don't put the mark next to a price:
  it must never read as data.
- Don't translate or abbreviate the name except as the "EN" monogram.

## Where it is placed

| Place | Variant and tone | Source |
|---|---|---|
| Sign-in panel | wordmark, reverse, xl | `SignInScreen.tsx` |
| Sign-in card below 760 px (panel folded) | wordmark, auto, lg | `SignInScreen.tsx` |
| Top bar, top-left | wordmark at wide widths, mark at medium and compact; mono, md (24 px) | `WorkspaceTopBar.tsx` |
| Browser tab | mark, colour; reverse on a dark tab bar (`prefers-color-scheme` inside the SVG) | `clients/web/public/favicon.svg` |
| Desktop splash | mark, reverse | `clients/web/public/splash.html` |
| Desktop icons, installer | reverse mark on the navy tile; installer sidebar with the name | `clients/desktop/src-tauri/icons/`, `installer/` (from `scripts/ui/build_brand_assets.py`) |
| Standalone files | mark (colour, reverse, mono), lock-up (colour, reverse) | `clients/web/public/brand/` |
| Reports | mark, adaptive (colour; reverse on a dark screen), with the name as text | `eurogas_nexus.application.brand.mark_svg` |

### Report header

A report is one self-contained HTML file, so it takes the mark as inline SVG text from
`eurogas_nexus.application.brand`, never as a URL:

```python
from eurogas_nexus.application.brand import mark_svg

brand = (
    '<p class="r-brand">'
    + mark_svg("adaptive", size=20, title=None)
    + "<span>Eurogas Nexus · Market report</span></p>"
)
```

with `.r-brand{display:flex;align-items:center;gap:8px}` and `.r-brand svg{flex:none}` in the
report CSS. `adaptive` prints and mails in colour (the stroke attributes) and switches to the
reverse colours on a dark screen (a `prefers-color-scheme` rule scoped to `screen`); `title=None`
hides the mark from assistive technology because the name is written beside it. The output is
deterministic, so a stored report re-renders to the same bytes.
