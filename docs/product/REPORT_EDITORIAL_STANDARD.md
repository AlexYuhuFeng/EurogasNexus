# Market report editorial standard

Status: adopted 2026-11-16 (template `market-report/2`). The house standard the report
templates (`application/reports/render.py`, `charts.py`, `derive.py`, `findings.py`) implement
and `tests/unit/test_market_reports.py` (house standard block) checks. The AI editor works under
[REPORT_EDITORIAL_DIRECTIVE.md](REPORT_EDITORIAL_DIRECTIVE.md).

## What the study drew on

We looked at public material only, for its form, and copied no text, names, logos or
distinctive layouts. **Limits of access:** from this build environment the publishers' own sites
were not reachable (iea.org, its blob store, acer.europa.eu, entsog.eu, oxfordenergy.org,
iai.it and clingendaelenergy.com all failed DNS resolution). The study therefore rests on search
results and summaries of those publications (IEA Gas Market Report executive summaries 2022–2024
and the Q3 2026 deck, ENTSOG Winter Supply Outlook 2025/26 and its ACER opinion, OIES Quarterly
Gas Review issues, price-reporting agencies' public methodology and specification notices), plus
long-standing conventions of energy and financial publishing. What we take from each:

- **IEA Gas Market Report (quarterly).** Leads with an executive summary in prose whose first
  sentence is the finding ("a mild winter kept markets stable"), not the topic. Every level is
  given against a benchmark, typically the five-year average or range (storage "x% full, y%
  above the five-year average"). Charts are numbered figures with a declarative or descriptive
  title, a unit line and a "Source:" line naming the analysis basis; time series show the
  current year against the previous years' range. Forecasts are stated as forecasts with their
  assumptions in the text.
  *We take:* finding-first headlines and summaries; a comparison on every level; numbered
  exhibits with source lines; context series. *We differ:* the platform holds about 14 months of
  history, so the context is one prior year, and every exhibit says so instead of drawing a band.
- **ENTSOG/ACER seasonal outlooks.** Key findings first, then scenarios; storage trajectories
  against targets; assumptions and limitations named next to the result (ACER's opinion criticised
  an outlook for assuming away LNG risk). *We take:* the forecast is printed with its method and
  its main limitation in the same paragraph; a target line on storage charts; "no range is
  produced" said when it is not.
- **OIES Quarterly Gas Review.** Analytical prose, numbered figures with sources, benchmark hub
  prices compared side by side, short sections each opening with the conclusion. *We take:* a bold
  lead sentence per section followed by a short paragraph; small multiples for series that belong
  together.
- **Price-reporting agencies' methodology guides.** Every assessment is time-stamped and its basis
  stated (units, calorific basis, assessment window); methodology is a separate, versioned
  document; corrections are published. *We take:* the data cut-off on the masthead, units in
  every column head, a methodology and revisions section in the back matter, a template version on
  every issue.

## The standard

**Medium.** Print first: A4, margins 20 mm top and bottom and 18 mm at the sides (Letter-safe).
The screen view is the same three sheets (front page, body, back matter) centred on a grey desk.
No interface inside the document: no buttons, disclosures, banners, cards or rounded boxes. Print,
download and "summary only" are the viewer's controls.

**Grid.** A 174 mm text block. Body sections use a 118 mm text column (about 70 characters of
the serif at 9.5 pt) and a 48 mm side column for the section's key figures; exhibits run the full
174 mm or, as small multiples, two 83 mm halves side by side.

**Typography.** One text family, a serif (system fonts only: Charter, Cambria, Georgia, Noto or
DejaVu Serif, Times; Songti/SimSun for Chinese), 9.5 pt on 13.5 pt, ragged right with automatic
hyphenation (justified type without fine hyphenation control looks worse on screen than ragged
right). One sans with tabular lining figures for tables, exhibits, labels and page furniture.
Four levels: headline 19 pt, section titles 12 pt, exhibit titles 8.6 pt bold sans, body. Section
markers are letterspaced capitals over a hairline. Rules are 0.5 pt hairlines; one accent colour
(the token accent) plus greys. Numbers are tabular, right-aligned, negative values with a true
minus, units in column heads.

**Page furniture.** Masthead on page one (publication, report, issue number per report kind,
date, data cut-off, classification, "Demonstration data: simulated" when it is). From page two a
running header (publication · report); on every page a footer with the classification, "Page X
of Y" and the disclaimer reference, as CSS paged-media margin boxes (they render in Chromium 131
and later; checked in Chromium 140 and the current one). A demonstration report carries a dagger
next to every simulated value, the dagger's meaning in every page footer and a light diagonal
mark on every page, so a single page cannot be read as market data.

**Page one** is the report in miniature: headline (a sentence stating the lead finding), a
standfirst of two or three sentences on the state of the system, three to five key findings
(fact with magnitude and comparison, then one sentence of engine-derivable implication), the
"At a glance" table (latest, day, week, year where held; blank, never zero, where a comparison is
not held; a 30-day sparkline) and one lead exhibit.

**Narrative.** Each section opens with a bold lead sentence (its weightiest fact) followed by a
short paragraph: the other facts, one implication the engine can derive, scheduled events, and a
reference to the section's exhibits. No lists of facts in the body.

**Exhibits.** Numbered (Figure n, Table n), declarative title, subtitle with the measure and unit
(and the context: "against the same days a year earlier (1 prior year held)"), source line with
the data cut-off, notes where needed. Light horizontal gridlines only, no border, direct labels at
the line ends instead of legends, zero baseline for bars and areas, context in grey, forecasts
dashed, each series also distinguished by dash or hatch for greyscale. Fixed geometry: full
width 640 × 165 units, half 310 × 175, lead 640 × 130, all at one scale.

**Windows.** Daily: 30 days for flows, 12 months for prices, the gas year (October to September)
against the prior gas year for storage. Weekly: 13 weeks. Monthly: 13 months. The editor may pick
another permitted window per exhibit.

**Tables.** Edited, not dumped: body tables only where they earn their place (the hub board, the
outage schedule, the supply stack), at most eight rows, rules above the header and below the last
row, no zebra striping or cell borders. Series behind the exhibits go to a compact data annex
(small type, three columns; the report's own window: 14 days daily, 28 days weekly, the month
monthly) and, in full, to the viewer's CSV download.

**Length.** Measured on the demo desk with the pinned Chromium 140: daily shareable 7 pages
(1 front, 3 body, 3 back matter and annex); daily internal adds Our book; weekly and monthly
about 11; situation 6; asked 4. The body of a shareable daily meets the 2–3 page budget; the back
matter does not fit the budget yet (see "What still falls short" in the round-2 report). Summary
only = page one.

**Back matter.** Methodology and sources in small type, two columns: how each indicator is
computed, comparisons and gas-day conventions, what is forecast and how, revisions policy and the
revisions-since-previous-issue table, sources and freshness, attributions required by
`docs/legal/DATA_SOURCE_TERMS.md`, sections not in this issue and why, abbreviations and units,
editing note (model and directive version, or rule-edited), classification statement and the
no-advice disclaimer.

**Findings ranking (rules).** Each fact carries a materiality score and its reason: a change
against the standard deviation of the indicator's daily changes over the last 30 days held; a
storage level 5 points from a year earlier weighs 1; an outage by capacity offline against the
latest Norwegian landings; a forecast by the size of the change it projects; late, stale or
simulated facts weighed down. One finding per indicator family; if nothing scores 1, the first
finding says so. The editor may choose differently under the directive.
