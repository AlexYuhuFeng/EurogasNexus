"""One self-contained HTML file from a report snapshot: reads on screen, prints as the PDF.

No network request of any kind: the CSS is inline (token values from ``tokens.py``), the
charts are inline SVG (``charts.py``), there is no font, image or script URL. Four lines of
inline script add a Print button and a "show all data tables" toggle; with script off
(e-mail clients, print) the report is complete, because every chart has its data table and
hover values are native SVG tooltips.

The same snapshot always renders the same bytes (no clock, no random id), so a stored
report can be re-rendered and compared with its stored hash.
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from typing import Any

from eurogas_nexus.application.reports.catalogue import GROUPS, TEMPLATE_VERSION
from eurogas_nexus.application.reports.charts import chart_table, render_chart
from eurogas_nexus.application.reports.tokens import FONT, LIGHT, css_variables

STATE_WORDS = {"current": "current", "late": "late", "stale": "stale", "never": "no data",
               "manual": "manual"}

#: Attribution lines a public source's terms ask for (docs/legal/DATA_SOURCE_TERMS.md).
ATTRIBUTIONS: dict[str, str] = {
    "ENTSOG": "ENTSOG Transparency Platform, https://transparency.entsog.eu/ (data downloaded "
              "{day}). ENTSOG does not endorse this report.",
    "GIE": "Gas Infrastructure Europe: AGSI+ (storage) and ALSI (LNG) transparency platforms. "
           "GIE is the data source.",
    "REMIT": "REMIT inside information as published by the operators on their platforms "
             "(GIE IIP where collected there: GIE is the data source).",
    "ENTSOE": "ENTSO-E Transparency Platform.",
    "ELEXON": "Contains BMRS data © Elexon Limited copyright and database right.",
    "NATIONAL_GAS": "National Gas Transmission data portal (open data licence).",
    "NATIONAL_GAS_DEMAND": "National Gas Transmission data portal (open data licence).",
    "ECB": "European Central Bank reference rates.",
    "EIA": "U.S. Energy Information Administration.",
}

CSS = """
*{box-sizing:border-box}
html{background:var(--r-bg,#f7f7f8)}
body{margin:0;background:var(--r-bg,#f7f7f8);color:var(--r-text-1,#18181b);
font:13px/20px FONT;font-variant-numeric:tabular-nums}
.r-report{max-width:880px;margin:0 auto;padding:24px 16px 40px;background:var(--r-surface,#fff)}
.r-brand{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--r-text-2)}
h1{font-size:22px;line-height:28px;margin:4px 0 6px;font-weight:600}
h2{font-size:15px;line-height:22px;margin:28px 0 8px;padding-top:6px;font-weight:600;
border-top:2px solid var(--r-text-1)}
h3{font-size:13px;line-height:20px;margin:18px 0 4px;font-weight:600}
.r-meta{color:var(--r-text-2);font-size:12px;margin:0 0 8px}
.r-banner{border:1px solid var(--r-border);border-left-width:4px;padding:6px 10px;margin:6px 0;
font-size:12px;border-radius:4px}
.r-banner.sim{border-left-color:var(--r-status-simulated);background:var(--r-status-simulated-soft);
color:var(--r-status-simulated)}
.r-banner.lic{border-left-color:var(--r-status-watch);background:var(--r-status-watch-soft);
color:var(--r-status-watch)}
.r-banner.int{border-left-color:var(--r-status-info);background:var(--r-status-info-soft);
color:var(--r-status-info)}
.r-lead{font-size:15px;line-height:22px;font-weight:600;margin:12px 0}
.r-key{border:1px solid var(--r-border);border-radius:8px;padding:8px 14px;margin:10px 0 0;
background:var(--r-surface-2)}
.r-key h2{border:0;margin:0;padding:0;font-size:13px}
.r-key ul{margin:4px 0;padding-left:18px}
.r-head{font-weight:600;margin:4px 0}.r-prose{margin:4px 0 8px}
.r-bullets{margin:4px 0 8px;padding-left:18px;color:var(--r-text-1)}
.r-rewrite{font-size:11px;color:var(--r-text-3);margin:0 0 6px}
.r-sim{color:var(--r-status-simulated);font-size:11px;font-weight:500;white-space:nowrap}
.r-fc{color:var(--r-status-info);font-size:11px;font-weight:500}
.st-late{color:var(--r-status-watch)}.st-stale{color:var(--r-status-breach)}
.st-never{color:var(--r-text-3)}
figure{margin:10px 0;break-inside:avoid}
figcaption{font-size:12px;color:var(--r-text-2);margin:2px 0}
.r-chart{display:block;width:100%;max-width:640px;height:auto}
table{border-collapse:collapse;width:100%;margin:6px 0;font-size:12px}
caption{text-align:left;font-size:12px;color:var(--r-text-2);padding:2px 0}
th,td{padding:3px 6px;border-bottom:1px solid var(--r-border-subtle);vertical-align:top}
th{font-weight:600;text-align:left;background:var(--r-surface-2);font-size:11px}
td.n,th.n{text-align:right;white-space:nowrap}
.r-scroll{overflow-x:auto}
details.r-data summary{cursor:pointer;color:var(--r-accent);font-size:12px}
.r-ev{font-size:11px;line-height:16px;color:var(--r-text-2);margin:4px 0 12px}
.r-method dt{font-weight:600;margin-top:6px}.r-method dd{margin:0 0 4px}
.r-method{font-size:12px}
footer{margin-top:28px;border-top:1px solid var(--r-border);padding-top:8px;font-size:11px;
color:var(--r-text-3)}
.r-tools{display:flex;gap:8px;margin:8px 0}
.r-tools button{font:inherit;font-size:12px;height:28px;padding:0 10px;border-radius:4px;
border:1px solid var(--r-border);background:var(--r-surface);color:var(--r-text-1);cursor:pointer}
.r-tools button:focus-visible{outline:2px solid var(--r-accent);outline-offset:1px}
.r-ink-1{fill:var(--r-text-1)}.r-ink-2{fill:var(--r-text-2)}.r-ink-3{fill:var(--r-text-3)}
.r-grid{stroke:var(--r-border)}.r-axis{stroke:var(--r-text-3)}.r-node{fill:var(--r-text-2)}
SERIESCSS
@media (max-width:600px){.r-report{padding:16px}h1{font-size:18px;line-height:24px}}
@page{size:A4;margin:14mm 12mm 16mm}
@media print{
html,body,.r-report{background:#fff;color:#000}
.r-report{max-width:none;padding:0}
.r-tools{display:none}
h2,h3,.r-head,caption{break-after:avoid}.r-scroll{break-inside:avoid}h2+.r-section{break-before:avoid}
thead{display:table-header-group}
tr,figure,.r-key{break-inside:avoid}
.r-section{break-inside:auto}
.r-scroll{overflow:visible}
details.r-data:not([open]){display:none}
a{color:inherit;text-decoration:none}
}
"""

SCRIPT = (
    "(function(){var t=document.querySelector('.r-tools');if(!t)return;t.hidden=false;"
    "t.querySelector('[data-print]').onclick=function(){window.print()};"
    "var b=t.querySelector('[data-tables]');b.onclick=function(){var o=b.getAttribute("
    "'aria-pressed')!=='true';b.setAttribute('aria-pressed',o);document.querySelectorAll("
    "'details.r-data').forEach(function(d){d.open=o})}})();"
)


NUM = ' class="n"'


def _e(text: Any) -> str:
    return escape("" if text is None else str(text), quote=True)


def _css() -> str:
    series = "".join(
        f".r-stroke-{i}{{stroke:var(--r-series-{i})}}.r-fill-{i}{{fill:var(--r-series-{i})}}"
        for i in range(1, 9)
    )
    return (css_variables() + CSS.replace("FONT", FONT).replace("SERIESCSS", series)).replace(
        "\n", ""
    )


def fmt_number(value: Any, kind: str = "num") -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, int | float):
        return str(value)
    magnitude = abs(value)
    digits = 0 if magnitude >= 1000 else 1 if magnitude >= 100 else 2
    text = f"{value:,.{digits}f}"
    if kind == "signed" and value > 0:
        text = "+" + text
    return text.replace("-", "−") if value < 0 else text


def fmt_date(value: Any) -> str:
    if not value:
        return ""
    try:
        return date.fromisoformat(str(value)[:10]).strftime("%d %b %Y")
    except ValueError:
        return str(value)


def fmt_datetime(value: Any) -> str:
    if not value:
        return ""
    if value == "open":
        return "open"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return moment.strftime("%d %b %y %H:%M")


def _cell(row: dict, column: dict, first_number: str | None) -> str:
    key, kind = column["key"], column["kind"]
    value = row.get(key)
    if kind in {"num", "signed"}:
        text = _e(fmt_number(value, kind))
        if key == first_number and row.get("simulated") and value is not None:
            text += ' <span class="r-sim">simulated</span>'
        return f'<td class="n">{text}</td>'
    if kind == "date":
        return f"<td>{_e(fmt_date(value))}</td>"
    if kind == "datetime":
        return f"<td>{_e(fmt_datetime(value))}</td>"
    if kind == "state":
        word = STATE_WORDS.get(str(value), str(value or ""))
        return f'<td class="st-{_e(value)}">{_e(word)}</td>'
    return f"<td>{_e(value)}</td>"


def render_table(spec: dict) -> str:
    columns = spec["columns"]
    if not spec.get("rows"):
        return ""
    first_number = next((c["key"] for c in columns if c["kind"] in {"num", "signed"}), None)
    head = "".join(
        f'<th scope="col"{NUM if c["kind"] in {"num", "signed"} else ""}>{_e(c["label"])}</th>'
        for c in columns
    )
    body = "".join(
        "<tr>" + "".join(_cell(row, c, first_number) for c in columns) + "</tr>"
        for row in spec["rows"]
    )
    return (
        f'<div class="r-scroll"><table><caption>{_e(spec.get("caption"))}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def render_chart_figure(spec: dict, chart_id: str) -> str:
    svg = render_chart(spec, chart_id)
    if not svg:
        return ""
    header, rows = chart_table(spec)
    head = "".join(f'<th scope="col"{NUM if i else ""}>{_e(h)}</th>'
                   for i, h in enumerate(header))
    body = "".join(
        "<tr>" + "".join(
            f'<td class="n">{_e(c)}</td>' if i else f"<td>{_e(c)}</td>"
            for i, c in enumerate(row)
        ) + "</tr>"
        for row in rows
    )
    note = f" {spec['note']}" if spec.get("note") else ""
    return (
        f'<figure id="{chart_id}">{svg}'
        f"<figcaption>{_e(spec.get('title'))} ({_e(spec.get('unit'))}).{_e(note)}</figcaption>"
        f'<details class="r-data"><summary>Chart data ({len(rows)} rows)</summary>'
        f'<div class="r-scroll"><table data-chart="{chart_id}"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div></details></figure>"
    )


def _evidence_line(section: dict) -> str:
    ev = section["evidence"]
    parts = []
    for item in ev.get("sources") or []:
        state = item.get("state")
        text = f"{item['name']}: {item.get('source_system') or ''}"
        if item.get("as_of"):
            text += f", as of {fmt_date(item['as_of'])}"
        if state and state != "current":
            text += f" ({STATE_WORDS.get(state, state)})"
        if item.get("simulated"):
            text += " (simulated)"
        if item.get("licensed"):
            text += " (licensed)"
        parts.append(_e(text))
    rev = ev.get("revisions")
    if rev and rev.get("count") is not None:
        parts.append(_e(f"Provider revisions since the previous report "
                        f"({fmt_datetime(rev['since'])} UTC): {rev['count']}"))
    if ev.get("warnings"):
        parts.append(_e("Note: " + " ".join(ev["warnings"][:2])))
    return '<p class="r-ev">Sources: ' + "; ".join(parts) + "</p>" if parts else ""


def render_section(section: dict, index: int) -> str:
    sid = f"s-{section['key']}"
    commentary = section["commentary"]
    tag = ""
    if section.get("simulated"):
        tag += ' <span class="r-sim">simulated data</span>'
    if section.get("forecast"):
        tag += ' <span class="r-fc">includes a forecast</span>'
    out = [f'<section class="r-section" id="{sid}" aria-labelledby="{sid}-h">',
           f'<h3 id="{sid}-h">{_e(section["title"])}{tag}</h3>',
           f'<p class="r-{"prose" if commentary.get("basis") == "model" else "head"}">'
           f'{_e(commentary["headline"])}</p>']
    if commentary.get("bullets"):
        out.append('<ul class="r-bullets">' + "".join(
            f"<li>{_e(b)}</li>" for b in commentary["bullets"]) + "</ul>")
    if commentary.get("basis") == "model":
        out.append('<p class="r-rewrite">Wording edited by the AI model and checked against '
                   "the figures; the rule text is kept in the record.</p>")
    for number, chart in enumerate(section.get("charts") or []):
        out.append(render_chart_figure(chart, f"c{index}-{number}"))
    for spec in section.get("tables") or []:
        out.append(render_table(spec))
    out.append(_evidence_line(section))
    out.append("</section>")
    return "".join(out)


def _attributions(snapshot: dict) -> list[str]:
    families: set[str] = set()
    for section in snapshot["sections"]:
        for item in section["evidence"].get("sources") or []:
            if item.get("family") and not item.get("simulated"):
                families.add(item["family"])
    day = fmt_date(snapshot.get("as_of"))
    return [ATTRIBUTIONS[f].format(day=day) for f in sorted(families) if f in ATTRIBUTIONS]


def render_methodology(snapshot: dict) -> str:
    out = ['<section class="r-method" id="methodology" aria-labelledby="methodology-h">',
           '<h2 id="methodology-h">Methodology and sources</h2>']
    out.append(
        "<p>Every figure is read from the platform's own stores through the same entitled "
        "reads as its pages, as of "
        f"{_e(fmt_datetime(snapshot['as_of']))} UTC, for the "
        f"{_e(snapshot['audience'])} audience. Commentary is written by fixed rules from the "
        "figures shown; nothing in this report is advice to trade, and it describes no "
        "execution, nomination or settlement.</p>"
    )
    methods: dict[str, dict] = {}
    for section in snapshot["sections"]:
        for method in section["evidence"].get("methods") or []:
            methods.setdefault(method["key"], method)
    if methods:
        out.append("<h3>Methods</h3><dl>" + "".join(
            f"<dt>{_e(m['title'])}</dt><dd>{_e(m['text'])}</dd>" for m in methods.values()
        ) + "</dl>")
    rows = []
    for section in snapshot["sections"]:
        for item in section["evidence"].get("sources") or []:
            rows.append({
                "section": section["title"], "name": item["name"],
                "source": item.get("source_system"), "as_of": item.get("as_of"),
                "state": item.get("state"),
                "flags": ", ".join(f for f, on in (("simulated", item.get("simulated")),
                                                   ("licensed", item.get("licensed"))) if on),
            })
    if rows:
        out.append("<h3>Sources and freshness</h3>")
        out.append(render_table({
            "caption": "Each source as read for this report",
            "columns": [{"key": "section", "label": "Section", "kind": "text"},
                        {"key": "name", "label": "Data", "kind": "text"},
                        {"key": "source", "label": "Source", "kind": "text"},
                        {"key": "as_of", "label": "Newest data", "kind": "date"},
                        {"key": "state", "label": "State", "kind": "state"},
                        {"key": "flags", "label": "", "kind": "text"}],
            "rows": rows,
        }))
    attributions = _attributions(snapshot)
    if attributions:
        out.append("<h3>Attribution</h3><ul>" + "".join(f"<li>{_e(a)}</li>"
                                                         for a in attributions) + "</ul>")
    omitted = snapshot.get("omitted") or []
    if omitted:
        out.append("<h3>Not in this report</h3><ul>" + "".join(
            f"<li>{_e(item['title'])}: {_e(item['reason'])}"
            + (f" ({_e(item['action'])})" if item.get("action") else "") + "</li>"
            for item in omitted) + "</ul>")
    model = snapshot.get("model_use") or {}
    if model.get("attempted"):
        out.append(
            f"<p>AI model: {model.get('passed', 0)} of {model.get('attempted', 0)} section "
            "commentaries were reworded by the model and passed the checks (no new number, "
            "hub, unit, direction or advice); the others keep the rule text.</p>"
        )
    out.append("</section>")
    return "".join(out)


def render_report(snapshot: dict) -> str:
    """The report's HTML. Deterministic in ``snapshot``."""

    title = snapshot["title"]
    banners = []
    if snapshot.get("simulated"):
        banners.append('<p class="r-banner sim" role="note">Demo data: figures marked '
                       "simulated are generated for demonstration and are not market data."
                       "</p>")
    licensed = snapshot.get("licensed") or {}
    if licensed.get("sources"):
        banners.append(
            '<p class="r-banner lic" role="note">Internal use: contains licensed data from '
            + _e(", ".join(licensed["sources"])) + ". Do not forward outside the licence.</p>"
        )
    if snapshot["audience"] == "internal":
        banners.append('<p class="r-banner int" role="note">Internal: for the desk and risk; '
                       "not for distribution outside the firm.</p>")
    period = snapshot.get("period") or {}
    meta = (
        f"{_e(snapshot['kind_label'])} · period {_e(fmt_date(period.get('start')))} to "
        f"{_e(fmt_date(period.get('end')))} · data as of {_e(fmt_datetime(snapshot['as_of']))} "
        f"UTC · {_e(snapshot['audience'])}"
    )
    body = [
        '<main class="r-report">',
        '<p class="r-brand">Eurogas Nexus · Market report</p>',
        f"<h1>{_e(title)}</h1>",
        f'<p class="r-meta">{meta}</p>',
        '<div class="r-tools" hidden><button type="button" data-print>Print / Save as PDF'
        '</button><button type="button" data-tables aria-pressed="false">Show all data tables'
        "</button></div>",
        *banners,
        f'<p class="r-lead">{_e(snapshot["headline"])}</p>',
    ]
    if snapshot.get("question"):
        body.insert(4, f'<p class="r-meta">Question: {_e(snapshot["question"])}</p>')
    if snapshot.get("key_points"):
        body.append('<section class="r-key" aria-labelledby="key-h"><h2 id="key-h">Key points'
                    "</h2><ul>" + "".join(f"<li>{_e(p)}</li>" for p in snapshot["key_points"])
                    + "</ul></section>")
    shown = [s for s in snapshot["sections"] if s["status"] == "ok"]
    index = 0
    for group in GROUPS:
        members = [s for s in shown if s["group"] == group]
        if not members:
            continue
        body.append(f'<h2 id="g-{index}">{_e(group)}</h2>')
        for section in members:
            body.append(render_section(section, index))
            index += 1
    body.append(render_methodology(snapshot))
    body.append(
        f"<footer>Report {_e(snapshot['report_id'])} · template "
        f"{_e(snapshot.get('template_version', TEMPLATE_VERSION))} · generated "
        f"{_e(fmt_datetime(snapshot['generated_at']))} UTC by {_e(snapshot['generated_by'])}. "
        "Decision support only: not advice to trade; no execution, nomination or settlement."
        "</footer></main>"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="color-scheme" content="light dark"><title>{_e(title)}</title>'
        f"<style>{_css()}</style></head><body>{''.join(body)}"
        f"<script>{SCRIPT}</script></body></html>"
    )


__all__ = ["LIGHT", "render_report", "render_section", "render_table"]
