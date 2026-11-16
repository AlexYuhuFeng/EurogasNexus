"""Server-side charts for a market report: inline SVG, no script, no font, no network.

A report is a record that must print, open in a mail client and look the same in five years,
so its charts are drawn here once, as SVG text, from the same series the report's tables
show. The chart type is the catalogue's choice for the section, never a model's:

- ``line`` and ``step``: time series (prices, fill, landings); a missing value breaks the
  line, it is never bridged by a smooth illustrative curve (UX_REFERENCE, CR-05);
- ``stacked_area``: supply components over time; ``stacked_bar``: components per day with
  negative parts (injection) below zero;
- ``bar``: horizontal bars by category (outages by facility);
- ``sankey``: flows from sources to uses (the NW Europe balance);
- ``sparkline``: a small line without axes.

Every chart is ``role="img"`` with a ``<title>`` and ``<desc>``; colours are the token
series in the light theme as attributes (print and mail) with CSS classes that follow the
dark theme on screen; each series also has its own dash pattern or hatch, so a greyscale
print still tells the series apart. Hover values are native SVG ``<title>`` tooltips (no
script needed). :func:`chart_table` is the data-table alternative printed under each chart:
the same numbers, so a test can hold the drawing to the data.
"""

from __future__ import annotations

import math
from datetime import date
from html import escape
from typing import Any

from eurogas_nexus.application.reports.tokens import LIGHT, SERIES

WIDTH = 640
HEIGHT = 240
PAD_LEFT = 56
PAD_RIGHT = 16
PAD_TOP = 24
PAD_BOTTOM = 28
LEGEND_ROW = 18
#: Dash per series index: distinct in greyscale as well as colour.
DASHES = ("", "6 3", "2 3", "8 3 2 3", "1 2", "10 4", "4 2 1 2", "3 3")


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
    return f"{value:,.{digits}f}"


def _parse_x(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    return float(date.fromisoformat(str(value)[:10]).toordinal())


def _x_label(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b")
    except ValueError:
        return str(value)


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


def _svg_open(spec: dict, chart_id: str, height: int) -> str:
    title = _e(spec.get("title") or "Chart")
    desc = _e(spec.get("description") or _describe(spec))
    return (
        f'<svg class="r-chart" viewBox="0 0 {WIDTH} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-labelledby="{chart_id}-t {chart_id}-d" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="sans-serif" font-size="11">'
        f'<title id="{chart_id}-t">{title}</title><desc id="{chart_id}-d">{desc}</desc>'
    )


def _describe(spec: dict) -> str:
    kind = spec.get("type")
    if kind == "sankey":
        return f"Flows in {spec.get('unit', '')} from sources to uses; the table below lists them."
    names = ", ".join(str(s.get("name")) for s in spec.get("series", []))
    return f"{kind} chart of {names} in {spec.get('unit', '')}; the table below lists the values."


def _patterns(chart_id: str, count: int) -> str:
    """Hatch patterns for filled series: every second series hatched, for greyscale."""

    out = ["<defs>"]
    for index in range(count):
        colour = _colour(index)
        angle = 45 if index % 4 == 1 else -45 if index % 4 == 3 else 0
        out.append(
            f'<pattern id="{chart_id}-p{index}" patternUnits="userSpaceOnUse" width="6" '
            f'height="6" patternTransform="rotate({angle})">'
            f'<rect width="6" height="6" class="r-fill-{index % SERIES + 1}" '
            f'fill="{colour}" fill-opacity="0.55"/>'
            + (
                f'<line x1="0" y1="0" x2="0" y2="6" stroke="{LIGHT["surface"]}" '
                'stroke-width="2"/>'
                if angle
                else ""
            )
            + "</pattern>"
        )
    out.append("</defs>")
    return "".join(out)


def _legend(spec: dict, top: float, chart_id: str, filled: bool) -> str:
    out = []
    x = PAD_LEFT
    y = top
    for index, series in enumerate(spec.get("series", [])):
        name = str(series.get("name"))
        width = 28 + 6.2 * len(name)
        if x + width > WIDTH - PAD_RIGHT:
            x = PAD_LEFT
            y += LEGEND_ROW
        if filled:
            out.append(
                f'<rect x="{x:.1f}" y="{y - 8:.1f}" width="16" height="9" '
                f'fill="url(#{chart_id}-p{index})" stroke="{_colour(index)}" '
                f'class="r-stroke-{index % SERIES + 1}"/>'
            )
        else:
            dash = _dash(index, series)
            out.append(
                f'<line x1="{x:.1f}" y1="{y - 4:.1f}" x2="{x + 16:.1f}" y2="{y - 4:.1f}" '
                f'stroke="{_colour(index)}" class="r-stroke-{index % SERIES + 1}" '
                f'stroke-width="2"{dash}/>'
            )
        out.append(
            f'<text x="{x + 20:.1f}" y="{y:.1f}" class="r-ink-2" fill="{LIGHT["text-2"]}">'
            f"{_e(name)}</text>"
        )
        x += width
    return "".join(out), y


def _legend_height(spec: dict) -> int:
    rows, x = 1, PAD_LEFT
    for series in spec.get("series", []):
        width = 28 + 6.2 * len(str(series.get("name")))
        if x + width > WIDTH - PAD_RIGHT:
            rows += 1
            x = PAD_LEFT
        x += width
    return rows * LEGEND_ROW + 6


def _dash(index: int, series: dict) -> str:
    dash = "5 4" if series.get("forecast") and not DASHES[index % len(DASHES)] else DASHES[
        index % len(DASHES)
    ]
    return f' stroke-dasharray="{dash}"' if dash else ""


def _y_axis(ticks: list[float], scale, unit: str, plot_right: float) -> str:
    out = []
    for tick in ticks:
        y = scale(tick)
        out.append(
            f'<line x1="{PAD_LEFT}" y1="{y:.1f}" x2="{plot_right:.1f}" y2="{y:.1f}" '
            f'stroke="{LIGHT["border"]}" class="r-grid"/>'
            f'<text x="{PAD_LEFT - 6}" y="{y + 3.5:.1f}" text-anchor="end" class="r-ink-3" '
            f'fill="{LIGHT["text-3"]}">{_e(_fmt(tick))}</text>'
        )
    out.append(
        f'<text x="4" y="12" class="r-ink-3" fill="{LIGHT["text-3"]}">{_e(unit)}</text>'
    )
    return "".join(out)


def _x_axis(xs: list, scale_x, bottom: float) -> str:
    if not xs:
        return ""
    count = min(6, len(xs))
    picks = sorted({round(i * (len(xs) - 1) / max(1, count - 1)) for i in range(count)})
    out = [
        f'<line x1="{PAD_LEFT}" y1="{bottom:.1f}" x2="{WIDTH - PAD_RIGHT}" y2="{bottom:.1f}" '
        f'stroke="{LIGHT["text-3"]}" class="r-axis"/>'
    ]
    for index in picks:
        x = scale_x(xs[index])
        anchor = "start" if index == 0 else "end" if index == len(xs) - 1 else "middle"
        out.append(
            f'<text x="{x:.1f}" y="{bottom + 14:.1f}" text-anchor="{anchor}" class="r-ink-3" '
            f'fill="{LIGHT["text-3"]}">{_e(_x_label(xs[index]))}</text>'
        )
    return "".join(out)


def _all_x(spec: dict) -> list:
    seen: dict[float, Any] = {}
    for series in spec.get("series", []):
        for x, _ in series.get("points", []):
            seen.setdefault(_parse_x(x), x)
    return [seen[key] for key in sorted(seen)]


def _hover_columns(spec: dict, xs: list, scale_x, top: float, bottom: float) -> str:
    """One transparent column per x with a native tooltip of every series' value there."""

    if not xs:
        return ""
    values: dict[Any, list[str]] = {x: [] for x in xs}
    for series in spec.get("series", []):
        lookup = {str(x): y for x, y in series.get("points", [])}
        for x in xs:
            if str(x) in lookup:
                values[x].append(f"{series.get('name')}: {_fmt(lookup[str(x)])}")
    step = (scale_x(xs[-1]) - scale_x(xs[0])) / max(1, len(xs) - 1) if len(xs) > 1 else 20
    out = ['<g class="r-hover">']
    for x in xs:
        cx = scale_x(x)
        label = f"{_x_label(x)} · " + " · ".join(values[x]) + f" {spec.get('unit', '')}"
        out.append(
            f'<rect x="{cx - step / 2:.1f}" y="{top:.1f}" width="{max(step, 2):.1f}" '
            f'height="{bottom - top:.1f}" fill="transparent" data-x="{_e(x)}">'
            f"<title>{_e(label)}</title></rect>"
        )
    out.append("</g>")
    return "".join(out)


def _line_chart(spec: dict, chart_id: str, step: bool) -> str:
    series_list = spec.get("series", [])
    xs = _all_x(spec)
    values = [y for s in series_list for _, y in s.get("points", []) if y is not None]
    refs = [r["value"] for r in spec.get("reference_lines", []) if r.get("value") is not None]
    if not values:
        return ""
    ticks = nice_ticks(min(values + refs), max(values + refs))
    legend_h = _legend_height(spec)
    height = HEIGHT + legend_h
    plot_bottom = HEIGHT - PAD_BOTTOM
    plot_right = WIDTH - PAD_RIGHT
    lo, hi = ticks[0], ticks[-1]
    x_lo, x_hi = _parse_x(xs[0]), _parse_x(xs[-1])

    def sx(value) -> float:
        if x_hi == x_lo:
            return (PAD_LEFT + plot_right) / 2
        return PAD_LEFT + (_parse_x(value) - x_lo) / (x_hi - x_lo) * (plot_right - PAD_LEFT)

    def sy(value: float) -> float:
        return plot_bottom - (value - lo) / (hi - lo) * (plot_bottom - PAD_TOP)

    out = [_svg_open(spec, chart_id, height), _y_axis(ticks, sy, spec.get("unit", ""), plot_right)]
    for ref in spec.get("reference_lines", []):
        y = sy(ref["value"])
        out.append(
            f'<line x1="{PAD_LEFT}" y1="{y:.1f}" x2="{plot_right}" y2="{y:.1f}" '
            f'stroke="{LIGHT["status-watch"]}" class="r-ref" stroke-dasharray="1 3" '
            f'stroke-width="1.5"/><text x="{plot_right - 2}" y="{y - 4:.1f}" text-anchor="end" '
            f'class="r-ref-label" fill="{LIGHT["status-watch"]}">{_e(ref.get("label", ""))}</text>'
        )
    for index, series in enumerate(series_list):
        segments: list[list[str]] = [[]]
        previous_y = None
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
        for points in segments:
            if len(points) == 1:
                cx, cy = points[0].split(",")
                out.append(
                    f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="{_colour(index)}" '
                    f'class="r-fill-{index % SERIES + 1}"/>'
                )
            elif points:
                out.append(
                    f'<polyline points="{" ".join(points)}" fill="none" '
                    f'stroke="{_colour(index)}" class="r-stroke-{index % SERIES + 1}" '
                    f'stroke-width="{1.75 if not series.get("forecast") else 1.5}" '
                    f'stroke-linejoin="round"{_dash(index, series)}/>'
                )
    out.append(_x_axis(xs, sx, plot_bottom))
    out.append(_hover_columns(spec, xs, sx, PAD_TOP, plot_bottom))
    legend, _ = _legend(spec, HEIGHT + 4, chart_id, filled=False)
    out.append(legend)
    out.append("</svg>")
    return "".join(out)


def _stacked(spec: dict, chart_id: str, bars: bool) -> str:
    series_list = spec.get("series", [])
    xs = _all_x(spec)
    if not xs:
        return ""
    lookup = [{str(x): y for x, y in s.get("points", [])} for s in series_list]
    pos_tot = [sum(max(0.0, lk.get(str(x)) or 0.0) for lk in lookup) for x in xs]
    neg_tot = [sum(min(0.0, lk.get(str(x)) or 0.0) for lk in lookup) for x in xs]
    ticks = nice_ticks(min([0.0, *neg_tot]), max([0.0, *pos_tot]))
    legend_h = _legend_height(spec)
    height = HEIGHT + legend_h
    plot_bottom = HEIGHT - PAD_BOTTOM
    plot_right = WIDTH - PAD_RIGHT
    lo, hi = ticks[0], ticks[-1]
    n = len(xs)
    band = (plot_right - PAD_LEFT) / n

    def sx(value) -> float:
        index = next(i for i, x in enumerate(xs) if str(x) == str(value))
        if bars:
            return PAD_LEFT + band * (index + 0.5)
        return PAD_LEFT + (index / max(1, n - 1)) * (plot_right - PAD_LEFT)

    def sy(value: float) -> float:
        return plot_bottom - (value - lo) / (hi - lo) * (plot_bottom - PAD_TOP)

    out = [
        _svg_open(spec, chart_id, height),
        _patterns(chart_id, len(series_list)),
        _y_axis(ticks, sy, spec.get("unit", ""), plot_right),
    ]
    if bars:
        width = max(1.0, band * 0.72)
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
                top, h = min(y0, y1), abs(y0 - y1)
                out.append(
                    f'<rect x="{PAD_LEFT + band * i + (band - width) / 2:.1f}" y="{top:.1f}" '
                    f'width="{width:.1f}" height="{max(h, 0.5):.1f}" '
                    f'fill="url(#{chart_id}-p{index})" stroke="{_colour(index)}" '
                    f'stroke-width="0.6" class="r-stroke-{index % SERIES + 1}"/>'
                )
    else:
        base = [0.0] * n
        for index, lk in enumerate(lookup):
            tops = [base[i] + max(0.0, lk.get(str(x)) or 0.0) for i, x in enumerate(xs)]
            upper = [f"{sx(x):.1f},{sy(tops[i]):.1f}" for i, x in enumerate(xs)]
            lower = [f"{sx(x):.1f},{sy(base[i]):.1f}" for i, x in reversed(list(enumerate(xs)))]
            out.append(
                f'<polygon points="{" ".join(upper + lower)}" fill="url(#{chart_id}-p{index})"/>'
                f'<polyline points="{" ".join(upper)}" fill="none" stroke="{_colour(index)}" '
                f'class="r-stroke-{index % SERIES + 1}" stroke-width="1.25"/>'
            )
            base = tops
    zero = sy(0.0)
    out.append(
        f'<line x1="{PAD_LEFT}" y1="{zero:.1f}" x2="{plot_right}" y2="{zero:.1f}" '
        f'stroke="{LIGHT["text-3"]}" class="r-axis"/>'
    )
    out.append(_x_axis(xs, sx, plot_bottom))
    out.append(_hover_columns(spec, xs, sx, PAD_TOP, plot_bottom))
    legend, _ = _legend(spec, HEIGHT + 4, chart_id, filled=True)
    out.append(legend)
    out.append("</svg>")
    return "".join(out)


def _bar_chart(spec: dict, chart_id: str) -> str:
    """Horizontal bars, one per category (the first series)."""

    points = [(label, value) for label, value in (spec.get("series") or [{}])[0].get("points", [])
              if value is not None]
    if not points:
        return ""
    row = 20
    label_w = 230
    height = PAD_TOP + row * len(points) + 24
    hi = max(max(v for _, v in points), 0.0)
    lo = min(min(v for _, v in points), 0.0)
    ticks = nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    left, right = label_w, WIDTH - PAD_RIGHT - 48

    def sx(value: float) -> float:
        return left + (value - lo) / (hi - lo) * (right - left)

    out = [_svg_open(spec, chart_id, height), _patterns(chart_id, 1)]
    for index, (label, value) in enumerate(points):
        y = PAD_TOP + index * row
        x0, x1 = sx(0.0), sx(value)
        name = str(label)
        short = name if len(name) <= 36 else name[:35] + "…"
        out.append(
            f'<text x="{label_w - 6}" y="{y + 13:.1f}" text-anchor="end" class="r-ink-2" '
            f'fill="{LIGHT["text-2"]}">{_e(short)}<title>{_e(name)}</title></text>'
            f'<rect x="{min(x0, x1):.1f}" y="{y + 3:.1f}" width="{max(abs(x1 - x0), 0.5):.1f}" '
            f'height="{row - 6}" fill="url(#{chart_id}-p0)" stroke="{_colour(0)}" '
            f'class="r-stroke-1"><title>{_e(name)}: {_e(_fmt(value))} '
            f'{_e(spec.get("unit", ""))}</title></rect>'
            f'<text x="{max(x0, x1) + 4:.1f}" y="{y + 13:.1f}" class="r-ink-1" '
            f'fill="{LIGHT["text-1"]}">{_e(_fmt(value))}</text>'
        )
    bottom = PAD_TOP + row * len(points) + 4
    out.append(
        f'<text x="{right:.1f}" y="{bottom + 14:.1f}" text-anchor="end" class="r-ink-3" '
        f'fill="{LIGHT["text-3"]}">{_e(spec.get("unit", ""))}</text>'
    )
    out.append("</svg>")
    return "".join(out)


def _sankey(spec: dict, chart_id: str) -> str:
    """Sources on the left, uses on the right, bands proportional to the flow."""

    nodes = {node["id"]: node for node in spec.get("nodes", [])}
    links = [link for link in spec.get("links", []) if (link.get("value") or 0) > 0]
    if not links:
        return ""
    left = [n for n in spec.get("nodes", []) if n.get("side") == "source"]
    right = [n for n in spec.get("nodes", []) if n.get("side") == "use"]
    out_total = {n["id"]: sum(lk["value"] for lk in links if lk["source"] == n["id"]) for n in left}
    in_total = {n["id"]: sum(lk["value"] for lk in links if lk["target"] == n["id"]) for n in right}
    left = [n for n in left if out_total[n["id"]] > 0]
    right = [n for n in right if in_total[n["id"]] > 0]
    total = max(sum(out_total.values()), sum(in_total.values()))
    gap = 10
    height = 260
    usable = height - PAD_TOP * 2 - gap * max(len(left), len(right))
    scale = usable / total if total else 0
    node_w, x_left, x_right = 12, 236, WIDTH - 190 - 12
    out = [_svg_open(spec, chart_id, height)]
    positions: dict[str, list[float]] = {}
    for column, x, totals, anchor, lx in (
        (left, x_left, out_total, "end", x_left - 6),
        (right, x_right, in_total, "start", x_right + node_w + 6),
    ):
        y = PAD_TOP
        for index, node in enumerate(column):
            h = totals[node["id"]] * scale
            positions[node["id"]] = [y, y]  # running offsets for links
            colour = LIGHT["text-2"]
            out.append(
                f'<rect x="{x}" y="{y:.1f}" width="{node_w}" height="{max(h, 1):.1f}" '
                f'fill="{colour}" class="r-node"/>'
                f'<text x="{lx}" y="{y + max(h, 1) / 2 + 4:.1f}" text-anchor="{anchor}" '
                f'class="r-ink-1" fill="{LIGHT["text-1"]}">{_e(node["label"])} '
                f'{_e(_fmt(totals[node["id"]], 0))}</text>'
            )
            y += h + gap
            del index
    for index, link in enumerate(links):
        h = link["value"] * scale
        s, t = positions[link["source"]], positions[link["target"]]
        y0, y1 = s[1] + h / 2, t[1] + h / 2
        s[1] += h
        t[1] += h
        x0, x1 = x_left + node_w, x_right
        mid = (x0 + x1) / 2
        colour_index = [n["id"] for n in left].index(link["source"])
        out.append(
            f'<path d="M{x0},{y0:.1f} C{mid},{y0:.1f} {mid},{y1:.1f} {x1},{y1:.1f}" fill="none" '
            f'stroke="{_colour(colour_index)}" class="r-stroke-{colour_index % SERIES + 1}" '
            f'stroke-opacity="0.45" stroke-width="{max(h, 1):.1f}"{_dash(colour_index, {})}>'
            f"<title>{_e(nodes[link['source']]['label'])} to {_e(nodes[link['target']]['label'])}: "
            f"{_e(_fmt(link['value'], 0))} {_e(spec.get('unit', ''))}</title></path>"
        )
        del index
    out.append("</svg>")
    return "".join(out)


def sparkline(values: list[float | None], *, label: str, width: int = 96, height: int = 20) -> str:
    """A small line without axes, for a table cell. Gaps break the line."""

    real = [v for v in values if v is not None]
    if len(real) < 2:
        return ""
    lo, hi = min(real), max(real)
    span = (hi - lo) or 1.0
    segments: list[list[str]] = [[]]
    for index, value in enumerate(values):
        if value is None:
            segments.append([])
            continue
        x = 1 + index * (width - 2) / max(1, len(values) - 1)
        y = height - 2 - (value - lo) / span * (height - 4)
        segments[-1].append(f"{x:.1f},{y:.1f}")
    lines = "".join(
        f'<polyline points="{" ".join(points)}" fill="none" stroke="{_colour(0)}" '
        f'class="r-stroke-1" stroke-width="1.25"/>'
        for points in segments
        if len(points) > 1
    )
    return (
        f'<svg class="r-spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="{_e(label)}" xmlns="http://www.w3.org/2000/svg">{lines}</svg>'
    )


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
        rows = [
            [nodes[link["source"]], nodes[link["target"]], _fmt(link["value"], 1)]
            for link in spec.get("links", [])
            if (link.get("value") or 0) > 0
        ]
        return ["From", "To", f"Flow ({unit})"], rows
    if spec.get("type") == "bar":
        series = (spec.get("series") or [{}])[0]
        return (
            ["", f"{series.get('name', '')} ({unit})"],
            [[str(label), _fmt(value)] for label, value in series.get("points", [])],
        )
    xs = _all_x(spec)
    header = ["Day"] + [f"{s.get('name')} ({unit})" for s in spec.get("series", [])]
    lookups = [{str(x): y for x, y in s.get("points", [])} for s in spec.get("series", [])]
    rows = []
    for x in xs:
        cells = [_fmt(lk.get(str(x))) if str(x) in lk else "" for lk in lookups]
        rows.append([str(x)[:10], *cells])
    return header, rows


__all__ = ["chart_table", "nice_ticks", "render_chart", "sparkline"]
