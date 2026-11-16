"""Server-side exhibits for a market report: inline SVG drawn as a publisher draws charts.

No script, no font, no network. The exhibit's furniture (number, declarative title, subtitle
with measure and unit, source line, notes) is the renderer's; this module draws the plot:

- light horizontal gridlines only, no chart border, a darker zero line for bars and areas;
- direct labels at the end of each line or band instead of a legend;
- the main series in the accent colour; context (the same days a year earlier, the prior gas
  year) in grey; a forecast dashed; other series in the token palette, each with its own dash
  or hatch so a greyscale print still separates them;
- a missing value breaks a line; nothing is smoothed;
- fixed geometry: a full-width exhibit is 640 x 210 units, a half-width one 310 x 190, both at
  the same scale on the page, so type and strokes match across exhibits.

Every chart is ``role="img"`` with ``<title>``/``<desc>``; hover values are native SVG
tooltips. :func:`chart_table` gives the same numbers for the data annex (a test holds the
drawing to the data). Chart types are the catalogue's: ``line``, ``step``, ``stacked_area``,
``stacked_bar``, ``bar`` (horizontal, ranked) and ``sankey`` (kept for the API; the house
standard prints a supply-stack table instead), plus :func:`sparkline`.
"""

from __future__ import annotations

import math
from datetime import date
from html import escape
from typing import Any

from eurogas_nexus.application.reports.tokens import LIGHT, SERIES

FULL = (640, 165)
HALF = (310, 175)
PAD_LEFT = 40
PAD_TOP = 10
PAD_BOTTOM = 22
LABEL_ROOM = 92
CONTEXT = "#8f8f99"
INK_2 = LIGHT["text-2"]
GRID = "#e4e4e7"
DASHES = ("", "5 3", "2 2", "7 2 2 2", "1 2", "9 3", "4 2 1 2", "3 3")


def _e(text: Any) -> str:
    return escape(str(text), quote=True)


def _colour(index: int) -> str:
    return LIGHT[f"series-{index % SERIES + 1}"]


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


def _x_label(value: Any, span_days: float) -> str:
    try:
        moment = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{moment:%b %y}" if span_days > 120 else f"{moment.day} {moment:%b}"


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
    while value <= high + step * 0.5:
        ticks.append(round(value, 10))
        value += step
    return ticks


LEAD = (640, 130)


def _size(spec: dict) -> tuple[int, int]:
    if spec.get("lead"):
        return LEAD
    return HALF if spec.get("half") else FULL


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


def _patterns(chart_id: str, count: int) -> str:
    out = ["<defs>"]
    for index in range(count):
        colour = _colour(index)
        angle = 45 if index % 3 == 1 else -45 if index % 3 == 2 else 0
        out.append(
            f'<pattern id="{chart_id}-p{index}" patternUnits="userSpaceOnUse" width="5" '
            f'height="5" patternTransform="rotate({angle})">'
            f'<rect width="5" height="5" class="r-fill-{index % SERIES + 1}" fill="{colour}" '
            f'fill-opacity="0.7"/>'
            + ('<line x1="0" y1="0" x2="0" y2="5" stroke="#ffffff" stroke-width="1.4"/>'
               if angle else "")
            + "</pattern>"
        )
    out.append("</defs>")
    return "".join(out)


def _grid(ticks: list[float], scale, left: float, right: float, zero_line: bool) -> str:
    out = []
    for tick in ticks:
        y = scale(tick)
        strong = zero_line and abs(tick) < 1e-12
        out.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right:.1f}" y2="{y:.1f}" '
            f'stroke="{INK_2 if strong else GRID}" stroke-width="{0.9 if strong else 0.5}" '
            f'class="{"r-axis" if strong else "r-grid"}"/>'
            f'<text x="{left - 4}" y="{y + 3.2:.1f}" text-anchor="end" class="r-ink-3" '
            f'fill="{LIGHT["text-3"]}">{_e(_fmt(tick))}</text>'
        )
    return "".join(out)


def _x_axis(xs: list, scale_x, bottom: float, width: int) -> str:
    if not xs:
        return ""
    span = _parse_x(xs[-1]) - _parse_x(xs[0])
    count = min(5 if width < 400 else 7, len(xs))
    picks = sorted({round(i * (len(xs) - 1) / max(1, count - 1)) for i in range(count)})
    out = []
    for index in picks:
        x = scale_x(xs[index])
        anchor = "start" if index == 0 else "end" if index == len(xs) - 1 else "middle"
        out.append(
            f'<text x="{x:.1f}" y="{bottom + 13:.1f}" text-anchor="{anchor}" class="r-ink-3" '
            f'fill="{LIGHT["text-3"]}">{_e(_x_label(xs[index], span))}</text>'
        )
    return "".join(out)


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


def _place_labels(items: list[tuple[float, str, str]], top: float, bottom: float) -> list:
    """Direct labels at the series' last values, nudged apart (11 units minimum)."""

    placed = sorted(items, key=lambda item: item[0])
    for index in range(1, len(placed)):
        if placed[index][0] - placed[index - 1][0] < 11:
            y, text, colour = placed[index]
            placed[index] = (placed[index - 1][0] + 11, text, colour)
    overflow = placed[-1][0] - bottom if placed else 0
    if overflow > 0:
        placed = [(y - overflow, t, c) for y, t, c in placed]
    return [(max(y, top + 4), t, c) for y, t, c in placed]


def _line_chart(spec: dict, chart_id: str, step: bool) -> str:
    width, height = _size(spec)
    series_list = spec.get("series", [])
    xs = _all_x(spec)
    values = [y for s in series_list for _, y in s.get("points", []) if y is not None]
    refs = [r["value"] for r in spec.get("reference_lines", []) if r.get("value") is not None]
    if not values:
        return ""
    ticks = nice_ticks(min(values + refs), max(values + refs), 4 if width < 400 else 5)
    bottom = height - PAD_BOTTOM
    right = width - LABEL_ROOM
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
            f'<text x="{right + 3}" y="{y + 3:.1f}" class="r-ink-2" fill="{INK_2}">'
            f'{_e(ref.get("label", ""))}</text>'
        )
    labels = []
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
        if last_point is not None:
            labels.append((last_point[1], f"{series.get('name')} {_fmt(last_point[2])}", colour))
    for y, text, colour in _place_labels(labels, PAD_TOP, bottom):
        out.append(f'<text x="{right + 4}" y="{y + 3:.1f}" fill="{colour}" class="r-dl" '
                   'font-size="8.5">'
                   f"{_e(text)}</text>")
    out.append(_x_axis(xs, sx, bottom, width))
    out.append(_hover(spec, xs, sx, PAD_TOP, bottom))
    out.append("</svg>")
    return "".join(out)


def _stacked(spec: dict, chart_id: str, bars: bool) -> str:
    width, height = _size(spec)
    series_list = spec.get("series", [])
    xs = _all_x(spec)
    if not xs:
        return ""
    lookup = [{str(x): y for x, y in s.get("points", [])} for s in series_list]
    pos_tot = [sum(max(0.0, lk.get(str(x)) or 0.0) for lk in lookup) for x in xs]
    neg_tot = [sum(min(0.0, lk.get(str(x)) or 0.0) for lk in lookup) for x in xs]
    ticks = nice_ticks(min([0.0, *neg_tot]), max([0.0, *pos_tot]), 4 if width < 400 else 5)
    bottom = height - PAD_BOTTOM
    right = width - LABEL_ROOM
    lo, hi = ticks[0], ticks[-1]
    n = len(xs)
    band = (right - PAD_LEFT) / n
    index_of = {str(x): i for i, x in enumerate(xs)}

    def sx(value) -> float:
        i = index_of[str(value)]
        if bars:
            return PAD_LEFT + band * (i + 0.5)
        return PAD_LEFT + (i / max(1, n - 1)) * (right - PAD_LEFT)

    def sy(value: float) -> float:
        return bottom - (value - lo) / (hi - lo) * (bottom - PAD_TOP)

    out = [_svg_open(spec, chart_id, width, height), _patterns(chart_id, len(series_list)),
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
                    f'height="{max(abs(y0 - y1), 0.4):.1f}"'
                    f' fill="url(#{chart_id}-p{index})"/>'
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
                f'<polygon points="{" ".join(upper + lower)}" fill="url(#{chart_id}-p{index})"/>'
                f'<polyline points="{" ".join(upper)}" fill="none" stroke="{_colour(index)}" '
                f'class="r-stroke-{index % SERIES + 1}" stroke-width="0.8"/>'
            )
            tops_last.append((base[-1], tops[-1]))
            base = tops
    labels = [((sy(a) + sy(b)) / 2, f"{series_list[i].get('name')}", _colour(i))
              for i, (a, b) in enumerate(tops_last)]
    for y, text, colour in _place_labels(labels, PAD_TOP, bottom):
        out.append(f'<text x="{right + 4}" y="{y + 3:.1f}" fill="{colour}" class="r-dl" '
                   'font-size="8.5">'
                   f"{_e(text)}</text>")
    out.append(_x_axis(xs, sx, bottom, width))
    out.append(_hover(spec, xs, sx, PAD_TOP, bottom))
    out.append("</svg>")
    return "".join(out)


def _bar_chart(spec: dict, chart_id: str) -> str:
    """Horizontal bars, ranked, one per category (the first series)."""

    points = [(label, value) for label, value in (spec.get("series") or [{}])[0].get("points", [])
              if value is not None]
    if not points:
        return ""
    width = FULL[0]
    row = 16
    label_w = 230
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
        short = name if len(name) <= 38 else name[:37] + "…"
        out.append(
            f'<text x="{label_w - 6}" y="{y + 11:.1f}" text-anchor="end" class="r-ink-2" '
            f'fill="{INK_2}">{_e(short)}<title>{_e(name)}</title></text>'
            f'<rect x="{min(x0, x1):.1f}" y="{y + 3:.1f}" width="{max(abs(x1 - x0), 0.5):.1f}" '
            f'height="{row - 6}" fill="{_colour(0)}" class="r-fill-1"/>'
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
