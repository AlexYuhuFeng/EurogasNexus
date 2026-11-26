"""Server-side exhibits for a market report: inline SVG drawn as a publisher draws charts.

No script, no font, no network. The exhibit's furniture (number, declarative title, subtitle
with measure and unit, source line, notes) is the renderer's; this module draws the plot:

- light horizontal gridlines only, no chart border, a darker zero line for bars and areas;
- direct labels at the end of each line or band instead of a legend;
- the main series in the accent colour; context (the same days a year earlier, the prior gas
  year) in grey; a forecast dashed; other lines in the accent ramp, each with its own dash so
  a greyscale print still separates them;
- a missing value breaks a line; nothing is smoothed;
- fixed geometry: a full-width exhibit is 640 x 165 units, a half-width one 310 x 140, both at
  the same scale on the page, so type and strokes match across exhibits; the end labels take
  only the room they need, so the plot fills the column;
- categorical stacks in a tonal ramp of the accent (darkest and largest at the bottom, at most
  four tones, the rest summed as "Other" in grey), hatched only where two neighbouring bands
  would print as the same grey;
- date ticks on calendar boundaries, the last day right-aligned at the plot's end, and never
  two labels closer than a gap (:func:`date_ticks`).

Every chart is ``role="img"`` with ``<title>``/``<desc>``; hover values are native SVG
tooltips. :func:`chart_table` gives the same numbers for the data annex (a test holds the
drawing to the data). Chart types are the catalogue's: ``line``, ``step``, ``stacked_area``,
``stacked_bar``, ``bar`` (horizontal, ranked) and ``sankey`` (kept for the API; the house
standard prints a supply-stack table instead), plus :func:`sparkline`. The in-app chart
standard adds two forms so reports and the app draw the same thing: ``band`` (lines over a
grey history range and its mean, the range labelled with the years it is drawn from) and
``term_structure`` (price by delivery month with a marker per month, prior curves in grey).
"""

from __future__ import annotations

import math
import re
from datetime import date
from html import escape
from typing import Any

from eurogas_nexus.application.reports.lang import T, zh
from eurogas_nexus.application.reports.tokens import LIGHT, SERIES

FULL = (640, 165)
HALF = (310, 140)
PAD_LEFT = 40
PAD_TOP = 10
PAD_BOTTOM = 22
#: Most room an end label may take: a fifth of a full exhibit, a quarter of a half one.
LABEL_ROOM = 120
HALF_LABEL_ROOM = 84
#: Approximate advance of one character of a 10-unit and an 8.5-unit sans label.
CHAR = 5.6
LABEL_CHAR = 4.9
CONTEXT = "#8f8f99"
INK_2 = LIGHT["text-2"]
GRID = "#e4e4e7"
DASHES = ("", "5 3", "2 2", "7 2 2 2", "1 2", "9 3", "4 2 1 2", "3 3")


def _e(text: Any) -> str:
    return escape(str(text), quote=True)


#: The accent's tonal ramp, darkest first (greyscale luma about 43, 79, 133 and 190), and
#: the grey of a summed "Other" band.
RAMP = ("#142a66", LIGHT["accent"], "#5f86e6", "#a9bff2")
OTHER = "#8f8f99"
#: Tones picked from the ramp for 1..4 categories: spread, the accent always among them.
RAMP_PICKS = {1: (1,), 2: (1, 3), 3: (1, 2, 3), 4: (0, 1, 2, 3)}
#: Two neighbouring bands closer than this in greyscale luma are hatched.
LUMA_STEP = 30


def _colour(index: int) -> str:
    """Line colours: the accent first, then the ramp's dark, mid and light tones."""

    return (LIGHT["accent"], RAMP[0], RAMP[2], OTHER)[index % 4]


def luma(colour: str) -> float:
    """Greyscale value (0-255) a print of ``colour`` gives (Rec. 601 weights)."""

    red, green, blue = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * red + 0.587 * green + 0.114 * blue


def stack_tones(count: int, other: bool = False) -> list[str]:
    """Fill colours for ``count`` stacked bands, largest first; the last is grey if ``other``."""

    named = count - 1 if other else count
    tones = [RAMP[i] for i in RAMP_PICKS.get(named, RAMP_PICKS[4])[:named]]
    return tones + ([OTHER] if other else [])


def _fmt(value: float | None, digits: int | None = None) -> str:
    if value is None:
        return "n/a"
    if digits is None:
        magnitude = abs(value)
        digits = 0 if magnitude >= 1000 else 1 if magnitude >= 100 else 2
    text = f"{abs(value):,.{digits}f}"
    return ("−" + text) if value < 0 else text


def _parse_x(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    return float(date.fromisoformat(str(value)[:10]).toordinal())


def _x_label(value: Any, span_days: float, months: bool = False) -> str:
    try:
        moment = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    if months:
        return f"{moment:%b}-{moment:%y}"
    if zh():
        return (f"{moment.year % 100}年{moment.month}月" if span_days > 120
                else f"{moment.month}/{moment.day}")
    return f"{moment:%b %y}" if span_days > 120 else f"{moment.day} {moment:%b}"


def date_ticks(xs: list, scale_x, left: float, right: float,
               months: bool = False) -> list[tuple[float, str, str]]:
    """(x, label, anchor) for a date axis: the last day right-aligned at the end of the plot,
    then calendar boundaries (weeks back from the last day for a month, month starts beyond),
    kept only where a label clears its neighbours; the first one starts at the left edge.
    ``months``: the points are delivery months (a term structure), labelled "Jan-27"."""

    if not xs:
        return []
    try:
        days = [date.fromisoformat(str(x)[:10]) for x in xs]
    except ValueError:
        days = []
    if not days:
        picks = sorted({0, len(xs) - 1})
        return [(scale_x(xs[i]), str(xs[i]), "start" if i == 0 else "end") for i in picks]
    by_day = {d: x for d, x in zip(days, xs, strict=True)}
    first, last = days[0], days[-1]
    span = (last - first).days

    def width(text: str) -> float:
        return len(text) * CHAR

    gap = 12.0
    ticks: list[tuple[float, str, str]] = []
    last_label = _x_label(by_day[last], span, months)
    last_x = min(scale_x(by_day[last]), right)
    ticks.append((last_x, last_label, "end"))
    occupied = [(last_x - width(last_label), last_x)]
    if months:
        step = max(1, math.ceil(len(days) / 8))
        candidates = [d for position, d in enumerate(reversed(days))
                      if d != last and position % step == 0]
    elif span <= 21:
        step_days = max(1, math.ceil(span / 4))
        candidates = [d for d in reversed(days) if (last - d).days % step_days == 0
                      and d != last]
    elif span <= 62:
        candidates = [d for d in reversed(days) if (last - d).days % 7 == 0 and d != last]
    else:
        step = 1 if span <= 200 else 2 if span <= 400 else 3
        candidates = [d for d in reversed(days) if d.day == 1 and d != last
                      and (d.month - 1) % step == 0]
        if span > 200 and not candidates:
            candidates = [d for d in reversed(days) if d.day == 1 and d != last]
    for day in candidates:
        x = scale_x(by_day[day])
        text = _x_label(by_day[day], span, months)
        w = width(text)
        lo, hi, anchor = x - w / 2, x + w / 2, "middle"
        if lo < left - 4:
            lo, hi, anchor = left, left + w, "start"
            x = left
        if any(lo < b + gap and hi > a - gap for a, b in occupied):
            continue
        occupied.append((lo, hi))
        ticks.append((x, text, anchor))
    return sorted(ticks)


def nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    """Round tick values covering ``low``..``high``."""

    if math.isclose(low, high):
        low, high = low - 1.0, high + 1.0
    span = high - low
    raw = span / max(1, count - 1)
    power = 10 ** math.floor(math.log10(raw))
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= raw)
    first = math.floor(low / step) * step
    ticks = []
    value = first
    while True:
        ticks.append(round(value, 10))
        if value >= high - 1e-12:
            break
        value += step
    return ticks


LEAD = (640, 130)


def _size(spec: dict) -> tuple[int, int]:
    """(width, height) in units; a lead exhibit's height is set to fill page one."""

    if spec.get("lead"):
        return LEAD[0], int(spec.get("height") or LEAD[1])
    return HALF if spec.get("half") else FULL


def _end_labels(series_list: list[dict]) -> list[str]:
    """End-label texts: the value alone when one series is drawn (the title names it)."""

    shown = [s for s in series_list if any(y is not None for _, y in s.get("points", []))]
    out = []
    for series in series_list:
        values = [y for x, y in sorted(series.get("points", []), key=lambda p: _parse_x(p[0]))
                  if y is not None]
        if not values:
            out.append("")
            continue
        value = _fmt(values[-1])
        out.append(value if len(shown) == 1 else f"{series.get('name')} {value}")
    return out


def _svg_open(spec: dict, chart_id: str, width: int, height: int) -> str:
    title = _e(spec.get("title") or "Chart")
    desc = _e(spec.get("description") or _describe(spec))
    return (
        f'<svg class="r-chart{" r-half" if spec.get("half") else ""}" '
        f'viewBox="0 0 {width} {height}" width="100%" preserveAspectRatio="xMidYMid meet" '
        f'role="img" aria-labelledby="{chart_id}-t {chart_id}-d" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="sans-serif" font-size="10">'
        f'<title id="{chart_id}-t">{title}</title><desc id="{chart_id}-d">{desc}</desc>'
    )


def _describe(spec: dict) -> str:
    kind = spec.get("type")
    if kind == "sankey":
        return f"Flows in {spec.get('unit', '')} from sources to uses; the data annex lists them."
    names = ", ".join(str(s.get("name")) for s in spec.get("series", []))
    return (f"{kind} chart of {names} in {spec.get('unit', '')}; the data annex lists the "
            "values.")


def _style(index: int, series: dict) -> tuple[str, str, float]:
    """(colour, dash, width) for a series: context grey, forecast dashed, main accent."""

    if series.get("context"):
        return CONTEXT, "", 1.2
    colour = _colour(index)
    dash = "4 3" if series.get("forecast") else DASHES[index % len(DASHES)]
    return colour, dash, 1.6 if index == 0 else 1.3


def _fills(chart_id: str, tones: list[str]) -> tuple[str, list[str]]:
    """``<defs>`` and the fill for each band: the flat tone, or a hatch of it where the band
    below would print as nearly the same grey."""

    defs, fills = [], []
    for index, tone in enumerate(tones):
        close = index > 0 and abs(luma(tone) - luma(tones[index - 1])) < LUMA_STEP
        if not close:
            fills.append(tone)
            continue
        defs.append(
            f'<pattern id="{chart_id}-h{index}" patternUnits="userSpaceOnUse" width="4" '
            f'height="4" patternTransform="rotate(45)"><rect width="4" height="4" '
            f'fill="{tone}"/><line x1="0" y1="0" x2="0" y2="4" stroke="#ffffff" '
            f'stroke-width="1.2"/></pattern>')
        fills.append(f"url(#{chart_id}-h{index})")
    return (f"<defs>{''.join(defs)}</defs>" if defs else ""), fills


def stack_order(series_list: list[dict], most: int = 4) -> list[dict]:
    """Bands largest first (by total size over the window); beyond ``most`` the rest are
    summed into one "Other" band (the data annex keeps every category)."""

    def size(series: dict) -> float:
        return sum(abs(y or 0.0) for _, y in series.get("points", []))

    ranked = sorted(series_list, key=lambda s: -size(s))
    if len(ranked) <= most:
        return ranked
    keep, rest = ranked[:most], ranked[most:]
    total: dict[str, float] = {}
    order: dict[str, Any] = {}
    for series in rest:
        for x, y in series.get("points", []):
            if y is None:
                continue
            total[str(x)] = total.get(str(x), 0.0) + y
            order.setdefault(str(x), x)
    other = {"name": T("Other", "其他"), "other": True,
             "points": [[order[k], round(v, 3)] for k, v in total.items()]}
    return keep + [other]


def tick_digits(ticks: list[float]) -> int:
    """One number of decimals for an axis, from its step (0, 500, 1,000; never 0.00 next to
    500.0)."""

    step = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else abs(ticks[0]) or 1.0
    if step >= 1 and all(float(t).is_integer() for t in ticks):
        return 0
    return 1 if step >= 0.1 else 2


def _grid(ticks: list[float], scale, left: float, right: float, zero_line: bool) -> str:
    out = []
    digits = tick_digits(ticks)
    for tick in ticks:
        y = scale(tick)
        strong = zero_line and abs(tick) < 1e-12
        out.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right:.1f}" y2="{y:.1f}" '
            f'stroke="{INK_2 if strong else GRID}" stroke-width="{0.9 if strong else 0.5}" '
            f'class="{"r-axis" if strong else "r-grid"}"/>'
            f'<text x="{left - 4}" y="{y + 3.2:.1f}" text-anchor="end" class="r-ink-3" '
            f'fill="{LIGHT["text-3"]}">{_e(_fmt(tick, digits))}</text>'
        )
    return "".join(out)


def _x_axis(xs: list, scale_x, bottom: float, left: float, right: float,
            months: bool = False) -> str:
    return "".join(
        f'<text x="{x:.1f}" y="{bottom + 13:.1f}" text-anchor="{anchor}" class="r-ink-3" '
        f'fill="{LIGHT["text-3"]}">{_e(text)}</text>'
        for x, text, anchor in date_ticks(xs, scale_x, left, right, months))


def _label_room(labels: list[str], width: int) -> float:
    """Room right of the plot for the longest end label, within the exhibit's budget."""

    longest = max((len(text) for text in labels), default=0)
    budget = HALF_LABEL_ROOM if width < 400 else LABEL_ROOM
    return min(budget, max(24.0, longest * LABEL_CHAR + 8))


def _end_label(text: str, x: float, y: float, colour: str, room: float, two_lines: bool) -> str:
    """One end label; on two lines (name, then value) when the chart's labels need it."""

    head = (f'<text x="{x}" y="{{y:.1f}}" fill="{colour}" class="r-dl" font-size="8.5">')
    name, _, value = text.rpartition(" ")
    if not two_lines or not name:
        return head.format(y=y + 3) + f"{_e(_fit_label(text, room))}</text>"
    return (head.format(y=y - 1.5) + f"{_e(_fit_label(name, room))}"
            f'<tspan x="{x}" dy="9">{_e(value)}</tspan></text>')


def _fit_label(text: str, room: float) -> str:
    """The label cut to the room it has: the name gives way, a trailing figure never does.
    A CJK character takes one and a half Latin widths."""

    most = max(4.0, (room - 6) / LABEL_CHAR)

    def width(part: str) -> float:
        return sum(1.5 if ord(c) >= 0x2E80 else 1.0 for c in part)

    if width(text) <= most:
        return text
    name, _, value = text.rpartition(" ")
    if not name or not any(c.isdigit() for c in value):
        name, value = text, ""
    keep = most - width(value) - (2 if value else 1)
    out = ""
    for char in name:
        if width(out + char) > keep:
            break
        out += char
    return (out.rstrip() + "…" + (" " + value if value else "")) if out else text


def _all_x(spec: dict) -> list:
    seen: dict[float, Any] = {}
    for series in spec.get("series", []):
        for x, _ in series.get("points", []):
            seen.setdefault(_parse_x(x), x)
    return [seen[key] for key in sorted(seen)]


def _hover(spec: dict, xs: list, scale_x, top: float, bottom: float) -> str:
    if not xs:
        return ""
    lookups = [(s.get("name"), {str(x): y for x, y in s.get("points", [])})
               for s in spec.get("series", [])]
    step = (scale_x(xs[-1]) - scale_x(xs[0])) / max(1, len(xs) - 1) if len(xs) > 1 else 20
    out = ['<g class="r-hover">']
    for x in xs:
        cx = scale_x(x)
        values = " · ".join(f"{n}: {_fmt(lk[str(x)])}" for n, lk in lookups
                            if lk.get(str(x)) is not None)
        out.append(
            f'<rect x="{cx - step / 2:.1f}" y="{top:.1f}" width="{max(step, 1.5):.1f}" '
            f'height="{bottom - top:.1f}" fill="transparent"><title>{_e(str(x)[:10])} · '
            f'{_e(values)} {_e(spec.get("unit", ""))}</title></rect>'
        )
    out.append("</g>")
    return "".join(out)


def _place_labels(items: list[tuple[float, str, str]], top: float, bottom: float,
                  gap: float = 11.0) -> list:
    """Direct labels at the series' last values, pushed apart so no two are closer than
    ``gap``: down from the highest, then the block lifted off the bottom and, if it then
    crosses the top, spread evenly between the two (labels never overlap)."""

    placed = sorted(items, key=lambda item: item[0])
    if not placed:
        return []
    ys = [y for y, _, _ in placed]
    ys[0] = max(ys[0], top + 4)
    for index in range(1, len(ys)):
        ys[index] = max(ys[index], ys[index - 1] + gap)
    overflow = ys[-1] - bottom
    if overflow > 0:
        ys = [y - overflow for y in ys]
        for index in range(len(ys) - 2, -1, -1):
            ys[index] = min(ys[index], ys[index + 1] - gap)
    if ys[0] < top + 4:
        step = max(gap * 0.82, (bottom - top - 4) / max(1, len(ys) - 1)) if len(ys) > 1 else 0
        ys = [top + 4 + i * step for i in range(len(ys))]
    return [(y, text, colour) for y, (_, text, colour) in zip(ys, placed, strict=True)]


def _line_chart(spec: dict, chart_id: str, step: bool, band: dict | None = None,
                markers: bool = False) -> str:
    """Lines (or steps) with end labels. ``band``: a history range drawn under the lines in
    grey (``low``/``high``/``mean`` point lists, ``label``, ``mean_label``); ``markers``: a dot
    per point (a term structure's delivery months). Without either the output is unchanged."""

    width, height = _size(spec)
    series_list = spec.get("series", [])
    xs = _all_x(spec)
    values = [y for s in series_list for _, y in s.get("points", []) if y is not None]
    if band:
        values += [y for key in ("low", "high", "mean") for _, y in band.get(key) or []
                   if y is not None]
    refs = [r["value"] for r in spec.get("reference_lines", []) if r.get("value") is not None]
    if not values:
        return ""
    ticks = nice_ticks(min(values + refs), max(values + refs), 4 if width < 400 else 5)
    bottom = height - PAD_BOTTOM
    texts = _end_labels(series_list)
    ref_texts = [str(r.get("label", "")) for r in spec.get("reference_lines", [])]
    if band:
        ref_texts += [str(band.get("label") or ""), str(band.get("mean_label") or "")]
    room = _label_room(texts + ref_texts, width)
    # A label that does not fit its room ("Year earlier 4,404" beside a half-width plot) is
    # set on two lines, the name over the value, instead of being cut short.
    two_lines = any(len(t) * LABEL_CHAR + 8 > room for t in texts if t)
    if two_lines:
        parts = [p for t in texts for p in t.rpartition(" ")[::2] if p]
        room = _label_room(parts + ref_texts, width)
    right = width - room
    lo, hi = ticks[0], ticks[-1]
    x_lo, x_hi = _parse_x(xs[0]), _parse_x(xs[-1])

    def sx(value) -> float:
        if x_hi == x_lo:
            return (PAD_LEFT + right) / 2
        return PAD_LEFT + (_parse_x(value) - x_lo) / (x_hi - x_lo) * (right - PAD_LEFT)

    def sy(value: float) -> float:
        return bottom - (value - lo) / (hi - lo) * (bottom - PAD_TOP)

    out = [_svg_open(spec, chart_id, width, height), _grid(ticks, sy, PAD_LEFT, right, False)]
    for ref in spec.get("reference_lines", []):
        y = sy(ref["value"])
        out.append(
            f'<line x1="{PAD_LEFT}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="{INK_2}" '
            f'stroke-dasharray="1 2" stroke-width="0.9" class="r-ref"/>'
            f'<text x="{right + 3}" y="{y + 3:.1f}" class="r-ink-2" fill="{INK_2}" '
            f'font-size="8.5">{_e(_fit_label(str(ref.get("label", "")), room))}</text>'
        )
    labels = []
    if band:
        out.append(_band_shapes(band, sx, sy, labels))
    # Context first, so the main series draws over it.
    order = sorted(range(len(series_list)), key=lambda i: not series_list[i].get("context"))
    for index in order:
        series = series_list[index]
        colour, dash, stroke = _style(index, series)
        cls = "" if series.get("context") else f' class="r-stroke-{index % SERIES + 1}"'
        segments: list[list[str]] = [[]]
        previous_y = None
        last_point = None
        for x, y in sorted(series.get("points", []), key=lambda p: _parse_x(p[0])):
            if y is None:
                segments.append([])
                previous_y = None
                continue
            px, py = sx(x), sy(y)
            if step and previous_y is not None and segments[-1]:
                segments[-1].append(f"{px:.1f},{previous_y:.1f}")
            segments[-1].append(f"{px:.1f},{py:.1f}")
            previous_y = py
            last_point = (px, py, y)
        for points in segments:
            if len(points) == 1:
                cx, cy = points[0].split(",")
                out.append(f'<circle cx="{cx}" cy="{cy}" r="2" fill="{colour}"/>')
            elif points:
                dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(
                    f'<polyline points="{" ".join(points)}" fill="none" stroke="{colour}"{cls} '
                    f'stroke-width="{stroke}" stroke-linejoin="round"{dash_attr}/>'
                )
                if markers and not series.get("context"):
                    out.extend(
                        f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="2.2" '
                        f'fill="#ffffff" stroke="{colour}" stroke-width="1.2"/>'
                        for p in points)
        if last_point is not None and texts[index]:
            labels.append((last_point[1], texts[index] if two_lines
                           else _fit_label(texts[index], room), colour))
    for y, text, colour in _place_labels(labels, PAD_TOP, bottom, gap=20.0 if two_lines else 11.0):
        out.append(_end_label(text, right + 4, y, colour, room, two_lines))
    out.append(_x_axis(xs, sx, bottom, PAD_LEFT, right, months=markers))
    out.append(_hover(spec, xs, sx, PAD_TOP, bottom))
    out.append("</svg>")
    return "".join(out)


def _band_shapes(band: dict, sx, sy, labels: list) -> str:
    """The history range as grey areas (one per run of days where low and high are both held:
    a missing day is a gap) and its mean as a dashed grey line; both labelled at their ends."""

    low = {str(x): y for x, y in band.get("low") or []}
    high = {str(x): y for x, y in band.get("high") or []}
    order = sorted({str(x): x for x, _ in band.get("low") or []}.values(), key=_parse_x)
    runs: list[list] = [[]]
    for x in order:
        if low.get(str(x)) is None or high.get(str(x)) is None:
            runs.append([])
            continue
        runs[-1].append(x)
    out = []
    last = None
    for run in runs:
        if len(run) < 2:
            continue
        top = [f"{sx(x):.1f},{sy(high[str(x)]):.1f}" for x in run]
        bottom = [f"{sx(x):.1f},{sy(low[str(x)]):.1f}" for x in reversed(run)]
        out.append(f'<polygon points="{" ".join(top + bottom)}" fill="{CONTEXT}" '
                   f'fill-opacity="0.22" stroke="none" class="r-band"/>')
        last = run[-1]
    if last is not None and band.get("label"):
        middle = (high[str(last)] + low[str(last)]) / 2
        # The end label names the range only ("5-yr range"); the years it covers are in the
        # subtitle and the data annex, so the label is never cut in the middle of a word.
        short = re.sub(r"\s+\d{4}/\d{2}.*$", "", str(band["label"]))
        labels.append((sy(middle), short, CONTEXT))
    mean = [(x, y) for x, y in sorted(band.get("mean") or [], key=lambda p: _parse_x(p[0]))]
    segment: list[str] = []
    segments = [segment]
    for x, y in mean:
        if y is None:
            segment = []
            segments.append(segment)
            continue
        segment.append(f"{sx(x):.1f},{sy(y):.1f}")
    for points in segments:
        if len(points) > 1:
            out.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="{CONTEXT}" '
                       f'stroke-width="1" stroke-dasharray="4 3" class="r-band-mean"/>')
    held = [(x, y) for x, y in mean if y is not None]
    if held and band.get("mean_label"):
        labels.append((sy(held[-1][1]), f"{band['mean_label']} {_fmt(held[-1][1])}", CONTEXT))
    return "".join(out)


def _term_structure(spec: dict, chart_id: str) -> str:
    """Price by delivery month: a line with a marker per month (never bars), prior curves as
    grey context lines, delivery months labelled "Jan-27". Points' x are months "2027-01"."""

    def month_day(x: Any) -> str:
        text = str(x)
        return f"{text[:7]}-01" if len(text) == 7 else text

    drawn = dict(spec)
    drawn["series"] = [{**s, "points": [[month_day(x), y] for x, y in s.get("points", [])]}
                       for s in spec.get("series", [])]
    return _line_chart(drawn, chart_id, step=False, markers=True)


def _stacked(spec: dict, chart_id: str, bars: bool) -> str:
    width, height = _size(spec)
    series_list = stack_order(spec.get("series", []))
    xs = _all_x(spec)
    if not xs:
        return ""
    other = bool(series_list and series_list[-1].get("other"))
    tones = stack_tones(len(series_list), other)
    defs, fills = _fills(chart_id, tones)
    lookup = [{str(x): y for x, y in s.get("points", [])} for s in series_list]
    pos_tot = [sum(max(0.0, lk.get(str(x)) or 0.0) for lk in lookup) for x in xs]
    neg_tot = [sum(min(0.0, lk.get(str(x)) or 0.0) for lk in lookup) for x in xs]
    ticks = nice_ticks(min([0.0, *neg_tot]), max([0.0, *pos_tot]), 4 if width < 400 else 5)
    bottom = height - PAD_BOTTOM
    names = [str(s.get("name")) for s in series_list]
    room = _label_room(names, width)
    right = width - room
    lo, hi = ticks[0], ticks[-1]
    n = len(xs)
    band = (right - PAD_LEFT) / n
    index_of = {str(x): i for i, x in enumerate(xs)}

    def sx(value) -> float:
        i = index_of[str(value)]
        if bars:
            return PAD_LEFT + band * (i + 0.5)
        return PAD_LEFT + (i / max(1, n - 1)) * (right - PAD_LEFT)

    def tick_x(value) -> float:
        # A bar's tick sits under the bar; the last one right-aligned at the plot's end.
        return right if bars and str(value) == str(xs[-1]) else sx(value)

    def sy(value: float) -> float:
        return bottom - (value - lo) / (hi - lo) * (bottom - PAD_TOP)

    out = [_svg_open(spec, chart_id, width, height), defs,
           _grid(ticks, sy, PAD_LEFT, right, True)]
    tops_last: list[tuple[float, float]] = []
    if bars:
        bar_w = max(0.8, band * 0.74)
        for i, x in enumerate(xs):
            up = down = 0.0
            for index, lk in enumerate(lookup):
                value = lk.get(str(x))
                if not value:
                    continue
                if value > 0:
                    y0, y1 = sy(up), sy(up + value)
                    up += value
                else:
                    y0, y1 = sy(down + value), sy(down)
                    down += value
                out.append(
                    f'<rect x="{PAD_LEFT + band * i + (band - bar_w) / 2:.1f}" '
                    f'y="{min(y0, y1):.1f}" width="{bar_w:.1f}" '
                    f'height="{max(abs(y0 - y1), 0.4):.1f}" fill="{fills[index]}"/>'
                )
        base = 0.0
        for lk in lookup:
            value = lk.get(str(xs[-1])) or 0.0
            tops_last.append((base, base + value))
            base += max(value, 0.0)
    else:
        base = [0.0] * n
        for index, lk in enumerate(lookup):
            tops = [base[i] + max(0.0, lk.get(str(x)) or 0.0) for i, x in enumerate(xs)]
            upper = [f"{sx(x):.1f},{sy(tops[i]):.1f}" for i, x in enumerate(xs)]
            lower = [f"{sx(x):.1f},{sy(base[i]):.1f}" for i, x in reversed(list(enumerate(xs)))]
            out.append(
                f'<polygon points="{" ".join(upper + lower)}" fill="{fills[index]}"/>'
                f'<polyline points="{" ".join(upper)}" fill="none" stroke="#ffffff" '
                'stroke-width="0.6"/>'
            )
            tops_last.append((base[-1], tops[-1]))
            base = tops
    labels = [((sy(a) + sy(b)) / 2, _fit_label(names[i], room),
               tones[i] if luma(tones[i]) < 120 else INK_2)
              for i, (a, b) in enumerate(tops_last)]
    for y, text, colour in _place_labels(labels, PAD_TOP, bottom):
        out.append(f'<text x="{right + 4}" y="{y + 3:.1f}" fill="{colour}" class="r-dl" '
                   'font-size="8.5">'
                   f"{_e(text)}</text>")
    out.append(_x_axis(xs, tick_x, bottom, PAD_LEFT, right, months=bool(spec.get("months"))))
    out.append(_hover(spec, xs, sx, PAD_TOP, bottom))
    out.append("</svg>")
    return "".join(out)


def _bar_chart(spec: dict, chart_id: str) -> str:
    """Horizontal bars, ranked, one per category (the first series)."""

    points = [(label, value) for label, value in (spec.get("series") or [{}])[0].get("points", [])
              if value is not None]
    if not points:
        return ""
    width = HALF[0] if spec.get("half") else FULL[0]
    row = 16
    label_w = 120 if spec.get("half") else 230
    height = PAD_TOP + row * len(points) + 8
    ticks = nice_ticks(min(min(v for _, v in points), 0.0), max(max(v for _, v in points), 0.0))
    lo, hi = ticks[0], ticks[-1]
    left, right = label_w, width - 50

    def sx(value: float) -> float:
        return left + (value - lo) / (hi - lo) * (right - left)

    out = [_svg_open(spec, chart_id, width, height)]
    for index, (label, value) in enumerate(points):
        y = PAD_TOP + index * row
        x0, x1 = sx(0.0), sx(value)
        name = str(label)
        most = 20 if spec.get("half") else 38
        short = name if len(name) <= most else name[: most - 1] + "…"
        out.append(
            f'<text x="{label_w - 6}" y="{y + 11:.1f}" text-anchor="end" class="r-ink-2" '
            f'fill="{INK_2}">{_e(short)}<title>{_e(name)}</title></text>'
            f'<rect x="{min(x0, x1):.1f}" y="{y + 3:.1f}" width="{max(abs(x1 - x0), 0.5):.1f}" '
            f'height="{row - 6}" fill="{LIGHT["accent"]}" class="r-fill-1"/>'
            f'<text x="{max(x0, x1) + 4:.1f}" y="{y + 11:.1f}" class="r-ink-1" '
            f'fill="{LIGHT["text-1"]}">{_e(_fmt(value))}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def _sankey(spec: dict, chart_id: str) -> str:
    nodes = {node["id"]: node for node in spec.get("nodes", [])}
    links = [link for link in spec.get("links", []) if (link.get("value") or 0) > 0]
    if not links:
        return ""
    width = FULL[0]
    left = [n for n in spec.get("nodes", []) if n.get("side") == "source"]
    right = [n for n in spec.get("nodes", []) if n.get("side") == "use"]
    out_total = {n["id"]: sum(lk["value"] for lk in links if lk["source"] == n["id"]) for n in left}
    in_total = {n["id"]: sum(lk["value"] for lk in links if lk["target"] == n["id"]) for n in right}
    left = [n for n in left if out_total[n["id"]] > 0]
    right = [n for n in right if in_total[n["id"]] > 0]
    total = max(sum(out_total.values()), sum(in_total.values()))
    gap, height = 10, 240
    scale = (height - 2 * PAD_TOP - gap * max(len(left), len(right))) / total if total else 0
    node_w, x_left, x_right = 10, 236, width - 202
    out = [_svg_open(spec, chart_id, width, height)]
    positions: dict[str, list[float]] = {}
    for column, x, totals, anchor, lx in ((left, x_left, out_total, "end", x_left - 6),
                                          (right, x_right, in_total, "start",
                                           x_right + node_w + 6)):
        y = PAD_TOP
        for node in column:
            h = totals[node["id"]] * scale
            positions[node["id"]] = [y, y]
            out.append(f'<rect x="{x}" y="{y:.1f}" width="{node_w}" height="{max(h, 1):.1f}" '
                       f'fill="{INK_2}"/><text x="{lx}" y="{y + max(h, 1) / 2 + 4:.1f}" '
                       f'text-anchor="{anchor}" fill="{LIGHT["text-1"]}">{_e(node["label"])} '
                       f'{_e(_fmt(totals[node["id"]], 0))}</text>')
            y += h + gap
    for link in links:
        h = link["value"] * scale
        s, t = positions[link["source"]], positions[link["target"]]
        y0, y1 = s[1] + h / 2, t[1] + h / 2
        s[1] += h
        t[1] += h
        x0, x1 = x_left + node_w, x_right
        mid = (x0 + x1) / 2
        ci = [n["id"] for n in left].index(link["source"])
        out.append(f'<path d="M{x0},{y0:.1f} C{mid},{y0:.1f} {mid},{y1:.1f} {x1},{y1:.1f}" '
                   f'fill="none" stroke="{_colour(ci)}" stroke-opacity="0.45" '
                   f'stroke-width="{max(h, 1):.1f}"><title>{_e(nodes[link["source"]]["label"])}'
                   f' to {_e(nodes[link["target"]]["label"])}: {_e(_fmt(link["value"], 0))}'
                   f'</title></path>')
    out.append("</svg>")
    return "".join(out)


def sparkline(values: list[float | None], *, label: str, width: int = 64, height: int = 14) -> str:
    """A small line without axes, for a table cell; the last value marked. Gaps break it."""

    real = [v for v in values if v is not None]
    if len(real) < 2:
        return ""
    lo, hi = min(real), max(real)
    span = (hi - lo) or 1.0
    segments: list[list[str]] = [[]]
    last = None
    for index, value in enumerate(values):
        if value is None:
            segments.append([])
            continue
        x = 1 + index * (width - 4) / max(1, len(values) - 1)
        y = height - 2 - (value - lo) / span * (height - 4)
        segments[-1].append(f"{x:.1f},{y:.1f}")
        last = (x, y)
    lines = "".join(
        f'<polyline points="{" ".join(points)}" fill="none" stroke="{INK_2}" '
        f'stroke-width="0.9"/>' for points in segments if len(points) > 1)
    dot = f'<circle cx="{last[0]:.1f}" cy="{last[1]:.1f}" r="1.6" fill="{_colour(0)}"/>' \
        if last else ""
    return (f'<svg class="r-spark" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" aria-label="{_e(label)}" '
            f'xmlns="http://www.w3.org/2000/svg">{lines}{dot}</svg>')


def render_chart(spec: dict, chart_id: str) -> str:
    """The SVG for a chart spec; ``""`` when the spec holds nothing to draw."""

    kind = spec.get("type")
    if kind in {"line", "step"}:
        return _line_chart(spec, chart_id, step=kind == "step")
    if kind == "band":
        return _line_chart(spec, chart_id, step=False, band=spec.get("band") or {})
    if kind == "term_structure":
        return _term_structure(spec, chart_id)
    if kind == "stacked_area":
        return _stacked(spec, chart_id, bars=False)
    if kind == "stacked_bar":
        return _stacked(spec, chart_id, bars=True)
    if kind == "bar":
        return _bar_chart(spec, chart_id)
    if kind == "sankey":
        return _sankey(spec, chart_id)
    raise ValueError(f"unknown chart type {kind!r}")


def chart_table(spec: dict) -> tuple[list[str], list[list[str]]]:
    """The chart's data as a table: header and rows of formatted cells (the same numbers)."""

    unit = spec.get("unit", "")
    if spec.get("type") == "sankey":
        nodes = {node["id"]: node["label"] for node in spec.get("nodes", [])}
        rows = [[nodes[link["source"]], nodes[link["target"]], _fmt(link["value"], 1)]
                for link in spec.get("links", []) if (link.get("value") or 0) > 0]
        return ["From", "To", f"Flow ({unit})"], rows
    if spec.get("type") == "bar":
        series = (spec.get("series") or [{}])[0]
        return (["", f"{series.get('name', '')} ({unit})"],
                [[str(label), _fmt(value)] for label, value in series.get("points", [])])
    xs = _all_x(spec)
    header = ["Day"] + [f"{s.get('name')} ({unit})" for s in spec.get("series", [])]
    lookups = [{str(x): y for x, y in s.get("points", [])} for s in spec.get("series", [])]
    band = spec.get("band") if spec.get("type") == "band" else None
    if band:
        for key, name in (("low", "low"), ("high", "high"), ("mean", "mean")):
            if band.get(key):
                header.append(f"{band.get('label', 'Range')} {name} ({unit})")
                lookups.append({str(x): y for x, y in band[key]})
    rows = []
    for x in xs:
        cells = [_fmt(lk.get(str(x))) if str(x) in lk else "" for lk in lookups]
        rows.append([str(x)[:10], *cells])
    return header, rows


def cut_window(spec: dict, first: date, last: date) -> dict:
    """The spec with each series cut to ``first``..``last`` (the exhibit's chosen window)."""

    if spec.get("type") in {"bar", "sankey"}:
        return spec
    out = dict(spec)
    out["series"] = [
        {**s, "points": [p for p in s.get("points", [])
                         if first.isoformat() <= str(p[0])[:10] <= last.isoformat()]}
        for s in spec.get("series", [])
    ]
    out["series"] = [s for s in out["series"] if s["points"]]
    return out


__all__ = ["chart_table", "cut_window", "nice_ticks", "render_chart", "sparkline"]
