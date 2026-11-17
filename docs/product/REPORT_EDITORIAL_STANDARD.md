# Market report editorial standard

Status: adopted 2026-11-16 (template `market-report/3`; round 3 added page economy, the
brand mark, the accent ramp and the LINKING rule). The house standard the report
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

**Grid.** A 174 mm text block. Every body exhibit is a half (84 mm). A section with one exhibit
(or an odd number) sets its text in the left half beside the first exhibit; a section with a
pair sets its text in a 118 mm column with a 48 mm side column of key figures, the pair beneath;
tables run the full width. Only an exhibit (and a short text block) is kept from splitting,
never a whole section, so a heading and its text travel with their exhibit and no paragraph is
left above an empty quarter page. Page one stands alone; the body flows straight into the back
matter.

**Typography.** One text family, a serif (system fonts only: Charter, Cambria, Georgia, Noto or
DejaVu Serif, Times; Songti/SimSun for Chinese), 9.5 pt on 13.5 pt, ragged right with automatic
hyphenation (justified type without fine hyphenation control looks worse on screen than ragged
right). One sans with tabular lining figures for tables, exhibits, labels and page furniture.
Four levels: headline 19 pt, section titles 12 pt, exhibit titles 8.6 pt bold sans, body. Section
markers are letterspaced capitals over a hairline. Rules are 0.5 pt hairlines; one accent colour
(the token accent) plus greys. Numbers are tabular, right-aligned, negative values with a true
minus, units in column heads.

**Page furniture.** Masthead on page one (the brand mark, `brand.mark_svg("colour", size=20,
title=None)`, inline before the publication name: the report's paper is white in every medium,
so the mark keeps its colour tone rather than switching to reverse on a dark screen; publication, report, issue number per report kind,
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
not held; a 30-day sparkline) and the lead exhibit: the first chart of the first finding that
has one (its own, else its section's), sized from an estimate of the text above it to fill the
rest of the page (30 to 80 mm of plot). In a finding only the lead clause, the fact up to the
first clause break, is bold; the comparison and implication are regular weight. Text columns of
a table are left-aligned (row heads included), numbers right-aligned, the unit in a narrow
column or the head.

**Narrative.** Each section opens with a bold lead sentence (its weightiest fact) followed by a
short paragraph: the other facts, one implication the engine can derive, scheduled events, and a
reference to the section's exhibits. No lists of facts in the body.

**Exhibits.** Numbered (Figure n, Table n), declarative title, subtitle with the measure and unit
(and the context: "against the same days a year earlier (1 prior year held)"), source line with
the data cut-off, notes where needed. Light horizontal gridlines only, no border, direct labels at
the line ends instead of legends, zero baseline for bars and areas, context in grey, forecasts
dashed. Categorical stacks (LNG by country, generation by zone) use a tonal ramp of the accent,
at most four tones ordered by size with the largest and darkest at the bottom, the rest summed as
"Other" in grey; a band is hatched only where its greyscale is within 30 of the band below it.
Fixed geometry: full width 640 × 165 units (45 mm), half 310 × 140 (38 mm), the lead 640 wide
and as tall as page one allows, all at one scale. End labels take only the room their text
needs (a single series is labelled with its value alone) and never collide; date ticks sit on
calendar boundaries (weekly back from the last day for a month, month starts beyond), the last
day right-aligned at the plot's end, never two labels within 12 units; one number of decimals
per axis.

**Windows.** Daily: 30 days for flows, 12 months for prices, the gas year (October to September)
against the prior gas year for storage. Weekly: 13 weeks. Monthly: 13 months. The editor may pick
another permitted window per exhibit.

**Tables.** Edited, not dumped: body tables only where they earn their place (the hub board, the
outage schedule, the supply stack), at most eight rows, rules above the header and below the last
row, no zebra striping or cell borders. A daily prints one book table of at most five rows per
book section (none for P&L and contracts, whose sentences give every row). Series behind the
exhibits always go to the viewer's CSV download; the printed data annex is on request (the
`annex` option), printed by default for weekly and monthly reports only, compact (small type,
narrow tables in three columns, five-column ones in two, wider ones full width; the report's own
window: 14 days daily, the week, the month).

**Length.** Budgets: daily at most 5 pages (page one, two to three body pages, at most one page
of back matter), weekly 8, monthly 10, situation 4, asked 4. Measured with the pinned Chromium
140 (round 3): demo daily shareable 5 (rule and editor), internal 5, weekly 7, monthly 9,
situation 4, asked 2–3; public store daily shareable 5, asked 3. Summary only = page one.

**Back matter.** Methodology and sources in 6.7 pt run-in paragraphs, three columns, at most a
page: how each indicator is computed (forecast methods on one line), comparisons and gas-day
conventions, revisions since the previous issue in a sentence, one line per source with the
sections it feeds and its freshness, attributions required by `docs/legal/DATA_SOURCE_TERMS.md`,
sections not in this issue and why, the abbreviations the report uses (only those), then editing
(model, directive version and temperature, or rule-edited), data (where the series are),
classification and the no-advice disclaimer. "What to watch" never repeats a sentence the body
already prints.

**Findings ranking (rules).** Each fact carries a materiality score and its reason: a change
against the standard deviation of the indicator's daily changes over the last 30 days held; a
storage level 5 points from a year earlier weighs 1; an outage by capacity offline against the
latest Norwegian landings (10 × its share, for one outage and for the total offline alike, so
15% of landings offline outweighs a routine one-day change in storage withdrawal); a forecast by
the size of the change it projects, capped at 1.5; late, stale or simulated facts weighed down. One finding per indicator family; if nothing scores 1, the first
finding says so. The editor may choose differently under the directive.

**Chinese edition.** A report generated in Chinese prints its furniture (labels, section and
group titles, page footer, "Page X of Y") in Chinese and carries the editor's Chinese text where
it passes the checks; rule-written fallbacks, chart subtitles, fact labels in At a glance and
the methodology stay in English (the methodology heading says so).

**Asked reports.** The question is the title; page one opens with the Answer (two to four
sentences, every figure cited to a fact, "The data held does not show ..." for what it cannot
answer), then the key findings, At a glance and the lead exhibit. The body is headed Evidence:
only the sections that bear on the question, ordered by relevance (those holding the answer's
facts first), each paragraph led by the question's own fact. Then "What the data cannot tell"
and "What to watch". Question facts and their engine-declared relations are built in
`application/reports/answer.py`; the rule answer is the fallback for the editor's.
