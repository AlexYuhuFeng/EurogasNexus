"""One self-contained HTML document from a report snapshot, laid out as a printed publication.

The house standard is ``docs/product/REPORT_EDITORIAL_STANDARD.md``. In short:

- **Print first.** A4 pages, 20 mm top and bottom and 18 mm side margins; running header from
  page 2 and a footer on every page (classification, page X of Y, disclaimer reference) as CSS
  paged-media margin boxes; exhibits never split; widows and orphans held. On screen the same
  three sheets (front page, body, back matter) sit centred on a grey desk like a PDF viewer.
- **One text family plus a tabular sans.** A serif for headline, standfirst and prose (system
  fonts only: Charter, Georgia, Cambria, Noto/DejaVu Serif ...), ragged right with
  hyphenation; a sans with tabular lining figures for tables, figures, labels and furniture.
- **Page one is the report in miniature:** masthead, headline, standfirst, three to five key
  findings, the At a glance indicator table, one lead exhibit.
- **Exhibits** are numbered (Figure n, Table n), with a declarative title, a subtitle naming
  the measure and unit, the source line and notes; the text refers to each one.
- **No interface in the document:** no buttons, disclosures, banners or cards. Classification
  and "simulated" are typography: a dagger next to each simulated value, the footnote in the
  page footer and a light diagonal mark on every page of a demonstration report.

Nothing is fetched: CSS inline, charts inline SVG, no script (a JSON data block for the
viewer's CSV download is data, not code). The same snapshot renders the same bytes.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from html import escape
from typing import Any

from eurogas_nexus.application.reports.catalogue import GROUPS, TEMPLATE_VERSION
from eurogas_nexus.application.reports.charts import (
    cut_window,
    render_chart,
    sparkline,
)
from eurogas_nexus.application.reports.facts import window_start
from eurogas_nexus.application.reports.tokens import FONT, LIGHT

PUBLICATION = "Eurogas Nexus · Gas Markets"
SERIF = ('Charter, "Bitstream Charter", "Sitka Text", Cambria, Georgia, "Noto Serif", '
         '"DejaVu Serif", "Liberation Serif", "Times New Roman", "Songti SC", "SimSun", serif')
DAGGER = "†"
STATE_WORDS = {"current": "current", "late": "late", "stale": "stale", "never": "no data",
               "manual": "manual"}
CLASSIFICATION = {"internal": "INTERNAL", "shareable": "FOR DISTRIBUTION"}
DISCLAIMER = ("Decision support only: not advice to trade, and nothing here describes "
              "execution, nomination or settlement.")

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
GLOSSARY = (
    ("DA", "Day-ahead: gas delivered on the next gas day."),
    ("Front month", "The nearest calendar month traded; it rolls at each month end."),
    ("Gas day", "06:00 to 06:00 local time on the continent (05:00 to 05:00 UTC in winter)."),
    ("Gas year", "1 October to 30 September."),
    ("GWh/d", "Gigawatt hours per gas day (energy, gross calorific value)."),
    ("TWh", "Terawatt hours of energy."),
    ("EUR/MWh", "Euro per megawatt hour; continental hub prices."),
    ("GBp/th", "Pence sterling per therm; NBP prices."),
    ("MWh/d", "Megawatt hours per gas day; book positions."),
    ("Points", "Percentage points (storage fill)."),
    ("Supply call", "Norwegian pipeline landings plus LNG send-out plus net storage withdrawal "
                    "into NW Europe."),
    ("Net withdrawal", "Storage withdrawal less injection; negative when storage fills."),
    ("REMIT / UMM", "EU market-integrity rules / urgent market message: published outages."),
    ("AGSI+ / ALSI", "GIE's storage and LNG transparency platforms."),
    ("Implied gas burn", "Gas-fired electricity divided by an assumed plant efficiency."),
)

CSS_TEMPLATE = """
*{box-sizing:border-box}
:root{--ink:#18181b;--ink-2:#52525b;--ink-3:#5f5f68;--rule:#a1a1aa;--hair:#d4d4d8;
--accent:ACCENT;--paper:#fff;--desk:#e4e4e7}
html{background:var(--desk)}
body{margin:0;background:var(--desk);color:var(--ink);font:9.5pt/13.5pt SERIF;
hyphens:auto;-webkit-hyphens:auto;font-kerning:normal;text-rendering:optimizeLegibility}
.r-sheet{width:210mm;min-height:297mm;margin:10mm auto;padding:20mm 18mm 22mm;
background:var(--paper);
box-shadow:0 1px 3px rgba(0,0,0,.18)}
.r-sans,.r-masthead,.r-label,figcaption,table,.r-source,.r-notes,.r-glance,.r-side,.r-annex,
.r-back,.r-contents{font-family:SANS;font-variant-numeric:tabular-nums lining-nums}
.r-masthead{display:grid;grid-template-columns:1fr auto;gap:2mm 6mm;
border-top:2.4pt solid var(--ink);
border-bottom:0.5pt solid var(--ink);padding:2.5mm 0 2mm;margin-bottom:6mm;font-size:7.5pt;
line-height:10pt;color:var(--ink-2)}
.r-pub{font-size:10pt;letter-spacing:.08em;white-space:nowrap;text-transform:uppercase;
color:var(--ink);font-weight:600}
.r-mast-right{text-align:right}
.r-class{letter-spacing:.12em;font-weight:600;color:var(--ink)}
.r-label{font-size:7pt;line-height:10pt;letter-spacing:.14em;text-transform:uppercase;
color:var(--ink-2);font-weight:600;margin:0 0 1.5mm}
h1{font:600 19pt/23pt SERIF;margin:0 0 3mm;max-width:150mm;letter-spacing:-.005em}
.r-standfirst{font-size:11pt;line-height:14.5pt;margin:0 0 4mm;max-width:128mm;color:var(--ink)}
.r-findings{border-top:0.5pt solid var(--ink);padding-top:2mm;margin-bottom:5mm}
.r-findings ol{margin:0;padding:0;list-style:none;counter-reset:f;max-width:150mm}
.r-findings li{counter-increment:f;position:relative;padding-left:7mm;margin:0 0 1.6mm;
font-size:9pt;line-height:12.4pt}
.r-findings li::before{content:counter(f);position:absolute;left:0;top:0;font:600 9pt/13.5pt SANS;
color:var(--accent)}
.r-findings strong{font-weight:600}
h2{font:600 12pt/15pt SERIF;margin:0 0 2mm;break-after:avoid}
.r-group{border-top:0.5pt solid var(--ink);padding-top:1.5mm;margin:7mm 0 1mm;break-after:avoid}
.r-section{margin:0 0 5mm}
.r-cols{display:grid;grid-template-columns:118mm 1fr;gap:0 8mm}
.r-text p{margin:0 0 2mm;max-width:118mm;widows:2;orphans:2}
.r-lead{font-weight:600}
.r-side{font-size:7.5pt;line-height:10.5pt;color:var(--ink-2);border-left:0.5pt solid var(--hair);
padding-left:3mm}
.r-side dt{color:var(--ink);font-weight:600}.r-side dd{margin:0 0 1.5mm}
.r-ex-row{display:grid;grid-template-columns:1fr 1fr;gap:6mm;margin:2mm 0 3mm}
figure{margin:2mm 0 4mm;break-inside:avoid;page-break-inside:avoid}
figcaption{font-size:8pt;line-height:10.5pt;margin-bottom:1.5mm}
.r-exno{display:block;font-size:6.8pt;letter-spacing:.14em;text-transform:uppercase;
color:var(--accent);
font-weight:600}
.r-extitle{display:block;font-weight:600;color:var(--ink);font-size:8.6pt;line-height:11pt}
.r-exsub{display:block;color:var(--ink-2)}
.r-chart{display:block;width:100%;height:auto}
.r-source,.r-notes{font-size:6.8pt;line-height:9pt;color:var(--ink-3);margin:1mm 0 0}
table{border-collapse:collapse;width:100%;font-size:7.8pt;line-height:10.5pt}
thead th{border-top:0.8pt solid var(--ink);border-bottom:0.5pt solid var(--ink);font-weight:600;
text-align:left;padding:1mm 1.5mm;vertical-align:bottom;color:var(--ink)}
tbody td{padding:0.7mm 1.5mm;border-bottom:0.25pt solid var(--hair);vertical-align:top}
tbody tr:last-child td{border-bottom:0.8pt solid var(--ink)}
tr.r-total td{border-top:0.5pt solid var(--ink);font-weight:600}
td.n,th.n{text-align:right;white-space:nowrap}
.r-dag{font-size:70%;vertical-align:super;line-height:0;color:var(--ink-2)}
.st-late{color:#854d0e}.st-stale{color:#b91c1c}
.r-glance td,.r-glance th{padding-top:.35mm;padding-bottom:.35mm}.r-glance td.r-sp{width:18mm}
.r-glance .r-blank{color:var(--ink-3)}
.r-spark{display:block}
.r-contents{font-size:8pt;margin:0 0 5mm}.r-contents ol{margin:0;padding-left:5mm;columns:2}
.r-watch{border-top:0.5pt solid var(--ink);padding-top:2mm;margin-top:4mm;break-inside:avoid}
.r-watch ul{margin:0;padding-left:4mm}
.r-back{font-size:7.6pt;line-height:10.4pt;color:var(--ink)}
.r-back h2{font:600 10pt/13pt SANS;margin:5mm 0 1.5mm}
.r-back h3{font:600 8pt/11pt SANS;margin:3mm 0 1mm}
.r-back p,.r-back dd{margin:0 0 1.5mm}.r-back dt{font-weight:600}
.r-two{columns:2;column-gap:7mm}
.r-two>*{break-inside:avoid}
.r-annex table{font-size:6.6pt;line-height:8.6pt}
.r-annex figure{break-inside:avoid;margin:0 0 3mm}
.r-annex .r-two{columns:3;column-gap:5mm}
.r-mark{display:none}
.r-demo .r-mark{display:block;position:fixed;top:45%;left:0;right:0;text-align:center;
transform:rotate(-30deg);font:600 30pt/1 SANS;letter-spacing:.2em;color:rgba(109,40,217,.055);
pointer-events:none;z-index:0;text-transform:uppercase}
.r-ink-1{fill:var(--ink)}.r-ink-2{fill:var(--ink-2)}.r-ink-3{fill:var(--ink-3)}
.r-label-svg{font-size:9px}
@media screen and (max-width:820px){
.r-sheet{width:auto;min-height:0;margin:0;padding:6mm 4mm;box-shadow:none}
.r-cols,.r-ex-row{grid-template-columns:1fr}
.r-two{columns:1}.r-side{border-left:0;padding-left:0}
table{display:block;overflow-x:auto}
.r-masthead{grid-template-columns:1fr}.r-mast-right{text-align:left}}
@page{size:A4;margin:20mm 18mm 20mm 18mm;
@top-left{content:"HEADER_LEFT";font:7pt SANS;color:#52525b;vertical-align:bottom;
padding-bottom:3mm}
@top-right{content:"CLASS";font:600 7pt SANS;letter-spacing:.1em;color:#18181b;
vertical-align:bottom;
padding-bottom:3mm}
@bottom-left{content:"CLASS · Not advice to trade: see Methodology";font:6.8pt SANS;color:#52525b;
vertical-align:top;padding-top:3mm}
@bottom-center{content:"FOOT_CENTER";font:6.8pt SANS;color:#52525b;vertical-align:top;
padding-top:3mm}
@bottom-right{content:"Page " counter(page) " of " counter(pages);font:6.8pt SANS;color:#52525b;
vertical-align:top;padding-top:3mm}}
@page:first{@top-left{content:none}@top-right{content:none}}
@media print{
html,body{background:#fff}
.r-sheet{width:auto;min-height:0;margin:0;padding:0;box-shadow:none}
.r-sheet+.r-sheet{break-before:page}
h1,h2,h3,figcaption,.r-label,.r-group{break-after:avoid}
p{widows:2;orphans:2}
tr{break-inside:avoid}
thead{display:table-header-group}
a{color:inherit;text-decoration:none}}
"""


def _e(text: Any) -> str:
    return escape("" if text is None else str(text), quote=True)


def _css_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _css(snapshot: dict) -> str:
    classification = CLASSIFICATION.get(snapshot["audience"], "INTERNAL")
    header = f"{PUBLICATION} · {snapshot['title']}"
    foot = (f"{DAGGER} Simulated demonstration data, not market prices"
            if snapshot.get("simulated") else "")
    css = (CSS_TEMPLATE.replace("SERIF", SERIF).replace("SANS", FONT)
           .replace("ACCENT", LIGHT["accent"])
           .replace("HEADER_LEFT", _css_string(header))
           .replace("CLASS", _css_string(classification))
           .replace("FOOT_CENTER", _css_string(foot)))
    return "".join(line.strip() for line in css.splitlines())


def mark_simulated(text: str) -> str:
    """Escape ``text`` and print each "(simulated)" as a dagger after the value."""

    return _e(text).replace(" (simulated)", f'<span class="r-dag" title="simulated">{DAGGER}'
                                            "</span>")


def fmt_number(value: Any, kind: str = "num") -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, int | float):
        return str(value)
    magnitude = abs(value)
    digits = 0 if magnitude >= 1000 else 1 if magnitude >= 100 else 2
    text = f"{abs(value):,.{digits}f}"
    if value < 0:
        return "−" + text
    if kind == "signed" and value > 0:
        return "+" + text
    return text


def fmt_date(value: Any) -> str:
    if not value:
        return ""
    try:
        moment = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{moment.day} {moment:%b %Y}"


def fmt_short(value: Any) -> str:
    try:
        moment = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value or "")
    return f"{moment.day} {moment:%b}"


def fmt_datetime(value: Any) -> str:
    if not value:
        return ""
    if value == "open":
        return "open"
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return f"{moment.day} {moment:%b %y %H:%M}"


class Numbering:
    """Figure and table numbers in print order."""

    def __init__(self) -> None:
        self.figures = 0
        self.tables = 0

    def figure(self) -> int:
        self.figures += 1
        return self.figures

    def table(self) -> int:
        self.tables += 1
        return self.tables


def _cell(row: dict, column: dict, first_number: str | None) -> str:
    key, kind = column["key"], column["kind"]
    value = row.get(key)
    if kind in {"num", "signed"}:
        text = _e(fmt_number(value, kind))
        if key == first_number and row.get("simulated") and value is not None:
            text += f'<span class="r-dag">{DAGGER}</span>'
        return f'<td class="n">{text}</td>'
    if kind == "date":
        return f"<td>{_e(fmt_short(value))}</td>"
    if kind == "datetime":
        return f"<td>{_e(fmt_datetime(value or 'open'))}</td>"
    if kind == "state":
        return f'<td class="st-{_e(value)}">{_e(STATE_WORDS.get(str(value), value or ""))}</td>'
    return f"<td>{_e(value)}</td>"


def table_html(spec: dict) -> str:
    columns = spec["columns"]
    first_number = next((c["key"] for c in columns if c["kind"] in {"num", "signed"}), None)
    head = "".join(
        f'<th scope="col"{NUM if c["kind"] in {"num", "signed"} else ""}>{_e(c["label"])}</th>'
        for c in columns)
    body = "".join(
        f'<tr{TOTAL if row.get("total") else ""}>'
        + "".join(_cell(row, c, first_number) for c in columns) + "</tr>"
        for row in spec["rows"])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


NUM = ' class="n"'
TOTAL = ' class="r-total"'


def _furniture(label: str, title: str, subtitle: str) -> str:
    return (f'<figcaption><span class="r-exno">{_e(label)}</span>'
            f'<span class="r-extitle">{mark_simulated(title)}</span>'
            + (f'<span class="r-exsub">{_e(subtitle)}</span>' if subtitle else "")
            + "</figcaption>")


def _source_line(source: str, as_of: str, notes: str = "") -> str:
    out = f'<p class="r-source">Source: {_e(source)} Data as of {_e(fmt_datetime(as_of))} UTC.</p>'
    if notes:
        out += f'<p class="r-notes">Note: {_e(notes)}</p>'
    return out


def table_exhibit(spec: dict, number: int, as_of: str) -> str:
    if not spec.get("rows"):
        return ""
    return (f'<figure class="r-exhibit r-table" id="t{number}">'
            + _furniture(f"Table {number}", spec.get("caption", ""), spec.get("subtitle", ""))
            + table_html(spec)
            + _source_line(spec.get("source") or "Eurogas Nexus.", as_of, spec.get("notes", ""))
            + "</figure>")


def chart_exhibit(spec: dict, number: int, as_of: str, end: date) -> str:
    window = spec.get("window")
    shown = cut_window(spec, window_start(window, end), end) if window else spec
    svg = render_chart(shown, f"f{number}")
    if not svg:
        return ""
    return (f'<figure class="r-exhibit{" r-half-ex" if spec.get("half") else ""}" '
            f'id="f{number}">'
            + _furniture(f"Figure {number}", spec.get("title", ""), spec.get("subtitle", ""))
            + svg + _source_line(spec.get("source", ""), as_of, spec.get("notes", ""))
            + "</figure>")


# ------------------------------------------------------------------------- front page


def _masthead(snapshot: dict) -> str:
    classification = CLASSIFICATION.get(snapshot["audience"], "INTERNAL")
    period = snapshot.get("period") or {}
    issue = snapshot.get("issue")
    demo = (' · <span class="r-class">DEMONSTRATION DATA: SIMULATED</span>'
            if snapshot.get("simulated") else "")
    licensed = (snapshot.get("licensed") or {}).get("sources")
    if licensed:
        classification += f" · Licensed data from {', '.join(licensed)}: internal use"
    span = ""
    if period.get("start") and period.get("end") and period["start"] != period["end"]:
        span = f" · Period {fmt_short(period['start'])} to {fmt_date(period['end'])}"
    return (
        '<header class="r-masthead"><div><div class="r-pub">'
        f"{_e(PUBLICATION)}</div><div>{_e(snapshot['kind_label'])} · "
        f"{_e(snapshot['title'])}</div></div>"
        f'<div class="r-mast-right"><div class="r-class">{_e(classification)}</div>'
        f"<div>Issue {issue if issue else 1} · {_e(fmt_date(snapshot['as_of']))}{_e(span)}</div>"
        f"<div>Data as of {_e(fmt_datetime(snapshot['as_of']))} UTC{demo}</div></div></header>"
    )


def _glance(snapshot: dict, number: int) -> str:
    rows = snapshot.get("glance") or []
    if not rows:
        return ""
    has_year = any(r["year"] is not None for r in rows)
    has_norm = any(r.get("norm") is not None for r in rows)
    head = ['<th scope="col">Indicator</th>', '<th scope="col">Unit</th>',
            f'<th scope="col"{NUM}>Latest</th>', f'<th scope="col"{NUM}>Day</th>',
            f'<th scope="col"{NUM}>Week</th>']
    if has_year:
        head.append(f'<th scope="col"{NUM}>Year</th>')
    if has_norm:
        head.append(f'<th scope="col"{NUM}>vs norm</th>')
    head += ['<th scope="col">As of</th>', '<th scope="col">30 days</th>']
    body = []
    for r in rows:
        dag = f'<span class="r-dag">{DAGGER}</span>' if r["simulated"] else ""
        cells = [f'<th scope="row">{_e(r["label"])}</th>',
                 f"<td>{_e(r['unit'])}</td>",
                 f'<td class="n">{_e(fmt_number(r["latest"]))}{dag}</td>']
        for key in ["day", "week"] + (["year"] if has_year else []) + (["norm"] if has_norm
                                                                        else []):
            value = r.get(key)
            cells.append(f'<td class="n">{_e(fmt_number(value, "signed"))}</td>'
                         if value is not None else '<td class="n r-blank"></td>')
        state = "" if r["state"] == "current" else f" ({r['state']})"
        cells.append(f'<td class="st-{_e(r["state"])}">{_e(fmt_short(r["as_of"]))}{_e(state)}</td>')
        cells.append(f'<td class="r-sp">{sparkline(r.get("spark") or [], label=r["label"])}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<figure class="r-exhibit r-glance" id="t{number}">'
            + _furniture(f"Table {number}", "At a glance",
                         "Latest value and change; points for storage fill; blank where no "
                         "comparison is held")
            + f'<table><thead><tr>{"".join(head)}</tr></thead><tbody>{"".join(body)}</tbody>'
            "</table>" + _source_line("Eurogas Nexus calculations from the sources listed in "
                                      "Methodology.", snapshot["as_of"]) + "</figure>")


def _findings(snapshot: dict) -> str:
    items = []
    for f in snapshot.get("findings") or []:
        text = f'<strong>{mark_simulated(f["text"])}</strong>'
        if f.get("implication"):
            text += " " + mark_simulated(f["implication"])
        items.append(f"<li>{text}</li>")
    if not items:
        return ""
    return ('<section class="r-findings" aria-labelledby="kf"><h2 class="r-label" id="kf">'
            f"Key findings</h2><ol>{''.join(items)}</ol></section>")


# ------------------------------------------------------------------------- body


def _section(section: dict, numbers: Numbering, refs: dict, snapshot: dict, end: date) -> str:
    commentary = section["commentary"]
    as_of = snapshot["as_of"]
    exhibits_html: list[str] = []
    cited = []
    charts = [c for c in section.get("charts") or [] if c.get("type") != "sankey"]
    pending_half: list[str] = []
    for chart in charts:
        number = numbers.figure()
        html = chart_exhibit(chart, number, as_of, end)
        if not html:
            numbers.figures -= 1
            continue
        refs[chart.get("id", f"f{number}")] = f"Figure {number}"
        cited.append(f"Figure {number}")
        if chart.get("half"):
            pending_half.append(html)
            if len(pending_half) == 2:
                exhibits_html.append(f'<div class="r-ex-row">{"".join(pending_half)}</div>')
                pending_half = []
        else:
            exhibits_html.extend(pending_half)
            pending_half = []
            exhibits_html.append(html)
    exhibits_html.extend(pending_half)
    for spec in section.get("tables") or []:
        if not spec.get("rows"):
            continue
        number = numbers.table()
        refs[spec.get("id", f"t{number}")] = f"Table {number}"
        cited.append(f"Table {number}")
        exhibits_html.append(table_exhibit(spec, number, as_of))
    paragraph = " ".join(commentary.get("bullets") or [])
    if cited:
        paragraph += (" " if paragraph else "") + f"({'; '.join(cited)}.)"
    basis = commentary.get("basis", "rule")
    side = _side(section)
    text = (f'<div class="r-text"><p><span class="r-lead">{mark_simulated(commentary["headline"])}'
            f"</span> {mark_simulated(paragraph)}</p></div>")
    edited = ' data-edited="model"' if basis == "model" else ""
    return (f'<section class="r-section" id="s-{section["key"]}"{edited} '
            f'aria-labelledby="h-{section["key"]}">'
            f'<h2 id="h-{section["key"]}">{_e(section["title"])}</h2>'
            f'<div class="r-cols">{text}{side}</div>' + "".join(exhibits_html) + "</section>")


def _side(section: dict) -> str:
    rows = []
    for fact in (section.get("facts") or [])[:3]:
        if fact.get("value") is None or not fact.get("indicator", True):
            continue
        c = fact["comparisons"]
        parts = [f"{fmt_number(fact['value'])} {fact['unit']}"]
        if c.get("day") is not None:
            parts.append(f"day {fmt_number(c['day'], 'signed')}")
        if c.get("year") is not None:
            parts.append(f"year {fmt_number(c['year'], 'signed')}")
        dag = f'<span class="r-dag">{DAGGER}</span>' if fact["simulated"] else ""
        rows.append(f"<dt>{_e(fact['label'])}</dt><dd>{_e(' · '.join(parts))}{dag}</dd>")
    return f'<aside class="r-side"><dl>{"".join(rows)}</dl></aside>' if rows else "<div></div>"


# ------------------------------------------------------------------------- back matter


def _attributions(snapshot: dict) -> list[str]:
    families: set[str] = set()
    for section in snapshot["sections"]:
        for item in section["evidence"].get("sources") or []:
            if item.get("family") and not item.get("simulated"):
                families.add(item["family"])
    day = fmt_date(snapshot.get("as_of"))
    return [ATTRIBUTIONS[f].format(day=day) for f in sorted(families) if f in ATTRIBUTIONS]


def _back(snapshot: dict, numbers: Numbering) -> str:
    shown = [s for s in snapshot["sections"] if s["status"] == "ok"]
    out = ['<section class="r-back" aria-labelledby="mh">',
           '<h2 id="mh">Methodology and sources</h2><div class="r-two">']
    out.append(
        "<p>Every figure is read from the platform's own stores through the same entitled reads "
        f"as its pages, as of {_e(fmt_datetime(snapshot['as_of']))} UTC, for the "
        f"{_e(snapshot['audience'])} audience. Gas days run 06:00 to 06:00 continental time. "
        "Comparisons: day is the previous gas day, week seven days earlier, year the same day a "
        "year earlier; a range or norm is shown only where held, with the number of years. "
        "No change is given across a front-month roll.</p>")
    methods: dict[str, dict] = {}
    for section in shown:
        for method in section["evidence"].get("methods") or []:
            methods.setdefault(method["key"], method)
    if methods:
        out.append("<h3>How each indicator is computed</h3><dl>" + "".join(
            f"<dt>{_e(m['title'])}</dt><dd>{_e(m['text'])}</dd>" for m in methods.values())
            + "</dl>")
    forecasts = [f for f in snapshot.get("fact_sheet") or [] if f.get("forecast")]
    if forecasts:
        out.append("<h3>What is forecast and how</h3><p>" + _e(
            " ".join(sorted({f["sentence"] for f in forecasts}))) + "</p>")
    out.append("<h3>Revisions policy</h3><p>Providers revise published flows, storage and LNG; "
               "each replaced value is kept. The table counts revisions received since the "
               "previous issue of this report.</p>")
    revisions = [{"section": s["title"],
                  "count": (s["evidence"].get("revisions") or {}).get("count")}
                 for s in shown if s["evidence"].get("revisions")]
    if revisions and any(r["count"] is not None for r in revisions):
        out.append(table_html({"columns": [{"key": "section", "label": "Section", "kind": "text"},
                                           {"key": "count", "label": "Revisions", "kind": "num"}],
                               "rows": revisions}))
    elif revisions:
        out.append("<p>First issue of this report kind: no earlier issue to compare with.</p>")
    rows = []
    for section in shown:
        for item in section["evidence"].get("sources") or []:
            rows.append({"section": section["title"], "source": item.get("source_system"),
                         "as_of": item.get("as_of"), "state": item.get("state"),
                         "flags": ", ".join(k for k in ("simulated", "licensed") if item.get(k))})
    if rows:
        out.append("<h3>Sources and freshness</h3>" + table_html({
            "columns": [{"key": "section", "label": "Section", "kind": "text"},
                        {"key": "source", "label": "Source", "kind": "text"},
                        {"key": "as_of", "label": "Newest", "kind": "date"},
                        {"key": "state", "label": "State", "kind": "state"},
                        {"key": "flags", "label": "", "kind": "text"}], "rows": rows}))
    attributions = _attributions(snapshot)
    if attributions:
        out.append("<h3>Attribution</h3>" + "".join(f"<p>{_e(a)}</p>" for a in attributions))
    omitted = snapshot.get("omitted") or []
    if omitted:
        out.append("<h3>Not in this report</h3>" + "".join(
            f"<p>{_e(item['title'])}: {_e(item['reason'])}.</p>" for item in omitted))
    out.append("<h3>Abbreviations and units</h3><dl>" + "".join(
        f"<dt>{_e(a)}</dt><dd>{_e(b)}</dd>" for a, b in GLOSSARY) + "</dl>")
    record = snapshot.get("editorial") or {}
    if record.get("basis") == "model":
        kept = sum(1 for v in (record.get("elements") or {}).values() if v.get("ok"))
        out.append(f"<h3>Editing</h3><p>Edited by the AI model {_e(record.get('model'))} under "
                   f"directive {_e(record.get('directive'))}: {kept} of "
                   f"{len(record.get('elements') or {})} elements passed the checks and are the "
                   "model's wording; the others are rule-written. No figure was written by the "
                   "model.</p>")
    else:
        out.append("<h3>Editing</h3><p>Rule-edited: the findings, their order and every "
                   "sentence were selected and written by fixed rules from the figures.</p>")
    licensed = (snapshot.get("licensed") or {}).get("sources")
    classification = CLASSIFICATION.get(snapshot["audience"], "INTERNAL")
    out.append(f"<h3>Classification</h3><p>{_e(classification)}. "
               + ("For the desk and risk; not for distribution outside the firm. "
                  if snapshot["audience"] == "internal" else
                  "May be distributed outside the firm; it holds no position, P&L, limit, "
                  "counterparty or contract term. ")
               + (f"Contains licensed data from {_e(', '.join(licensed))}: internal use only. "
                  if licensed else "")
               + (f"{DAGGER} marks simulated demonstration values: not market data. "
                  if snapshot.get("simulated") else "") + "</p>")
    out.append(f"<h3>Disclaimer</h3><p>{_e(DISCLAIMER)}</p></div></section>")
    return "".join(out)


def _annex(snapshot: dict, numbers: Numbering) -> str:
    blocks = []
    for section in snapshot["sections"]:
        if section["status"] != "ok":
            continue
        for spec in section.get("annex") or []:
            if not spec.get("rows"):
                continue
            number = numbers.table()
            rows = [r for r in spec["rows"] if not spec.get("print_from")
                    or str(r.get("day", "")) >= spec["print_from"]]
            spec = {**spec, "rows": rows}
            blocks.append(f'<figure id="t{number}">'
                          + _furniture(f"Table {number}", spec.get("caption", ""),
                                       f"{section['title']}: {len(rows)} rows, newest first")
                          + table_html(spec) + "</figure>")
    if not blocks:
        return ""
    return ('<section class="r-annex" aria-labelledby="ah"><h2 id="ah" class="r-label">Data '
            f'annex</h2><div class="r-two">{"".join(blocks)}</div></section>')


def _data_block(snapshot: dict) -> str:
    """The annex series as JSON for the viewer's CSV download (data, never executed)."""

    tables = [{"section": s["key"], "caption": spec.get("caption"),
               "columns": [c["key"] for c in spec["columns"]], "rows": spec["rows"]}
              for s in snapshot["sections"] if s["status"] == "ok"
              for spec in s.get("annex") or []]
    text = json.dumps({"report_id": snapshot["report_id"], "tables": tables},
                      ensure_ascii=False, default=str, separators=(",", ":"))
    return ('<script type="application/json" id="report-data">'
            + text.replace("</", "<\\/") + "</script>")


def render_report(snapshot: dict) -> str:
    """The report's HTML. Deterministic in ``snapshot``."""

    numbers = Numbering()
    refs: dict[str, str] = {}
    end = date.fromisoformat((snapshot.get("period") or {}).get("end") or snapshot["as_of"][:10])
    shown = [s for s in snapshot["sections"] if s["status"] == "ok"]
    order = snapshot.get("section_order") or []
    if order:
        rank = {key: i for i, key in enumerate(order)}
        shown = sorted(shown, key=lambda s: rank.get(s["key"], 99))
        shown = [s for s in shown if s["key"] in rank]
    # Page one.
    front = [_masthead(snapshot), f"<h1>{mark_simulated(snapshot['headline'])}</h1>"]
    if snapshot.get("question"):
        front.append(f'<p class="r-label">Question: {_e(snapshot["question"])}</p>')
    if snapshot.get("standfirst"):
        front.append(f'<p class="r-standfirst">{mark_simulated(snapshot["standfirst"])}</p>')
    front.append(_findings(snapshot))
    front.append(_glance(snapshot, numbers.table()))
    lead_chart = None
    lead_fact = None
    for f in snapshot.get("findings") or []:
        lead_fact = next((x for x in snapshot.get("fact_sheet") or []
                          if x.get("id") in f["fact_ids"] and x.get("exhibits")), None)
        if lead_fact:
            break
    if lead_fact:
        for section in shown:
            lead_chart = next((c for c in section.get("charts") or []
                               if c.get("id") == lead_fact["exhibits"][0]), None)
            if lead_chart:
                break
    if lead_chart:
        number = numbers.figure()
        front.append(chart_exhibit({**lead_chart, "half": False, "lead": True}, number,
                                   snapshot["as_of"], end))
        refs[lead_chart["id"]] = f"Figure {number}"
    # Body: groups in the house order (or the editor's order), each section once.
    body: list[str] = []
    if snapshot.get("kind") == "monthly":
        body.append('<nav class="r-contents" aria-label="Contents"><p class="r-label">Contents</p>'
                    "<ol>" + "".join(f"<li>{_e(s['title'])}</li>" for s in shown)
                    + "<li>Methodology and sources</li><li>Data annex</li></ol></nav>")
    groups = GROUPS if not order else tuple(dict.fromkeys(s["group"] for s in shown))
    for group in groups:
        members = [s for s in shown if s["group"] == group]
        if not members:
            continue
        body.append(f'<p class="r-label r-group">{_e(group)}</p>')
        for section in members:
            if lead_chart is not None:
                section = {**section, "charts": [c for c in section.get("charts") or []
                                                 if c is not lead_chart
                                                 and c.get("id") != lead_chart["id"]]}
            body.append(_section(section, numbers, refs, snapshot, end))
    watch = snapshot.get("watch") or []
    if watch:
        body.append('<section class="r-watch" aria-labelledby="wh"><h2 class="r-label" id="wh">'
                    "What to watch</h2><ul>" + "".join(
                        f"<li>{mark_simulated(w['text'])}</li>" for w in watch) + "</ul></section>")
    back = _back(snapshot, numbers) + _annex(snapshot, numbers)
    title = snapshot["title"]
    demo_class = ' class="r-demo"' if snapshot.get("simulated") else ""
    mark = ('<div class="r-mark" aria-hidden="true">Demonstration · simulated data</div>'
            if snapshot.get("simulated") else "")
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="generator" content="'
        f'{_e(snapshot.get("template_version", TEMPLATE_VERSION))}">'
        f"<title>{_e(title)}</title><style>{_css(snapshot)}</style></head>"
        f"<body{demo_class}>{mark}<main>"
        f'<article class="r-sheet r-front" aria-label="Summary">{"".join(front)}</article>'
        f'<article class="r-sheet r-body" aria-label="Report">{"".join(body)}</article>'
        f'<article class="r-sheet r-back-sheet" aria-label="Methodology and data">{back}'
        f'<p class="r-source">Report {_e(snapshot["report_id"])} · template '
        f'{_e(snapshot.get("template_version", TEMPLATE_VERSION))} · {_e(DISCLAIMER)}</p>'
        f"</article></main>{_data_block(snapshot)}</body></html>"
    )


__all__ = ["render_report", "table_html"]
