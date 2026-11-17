# Market reports

Research → **Reports** (`?workspace=research&task=reports`), or **Report** beside **Why** on an
alert or an outage (Today, Events, the alert centre). A report is one self-contained HTML document
laid out as a printed publication (A4) to the house standard in
[REPORT_EDITORIAL_STANDARD.md](../product/REPORT_EDITORIAL_STANDARD.md): a masthead with issue
number, data cut-off and classification; a headline and standfirst; three to five key findings;
an At a glance indicator table; one lead exhibit; then the sections with numbered figures and
tables; methodology and sources; and, for weekly and monthly reports or when you tick **Print
the data annex**, a data annex. A daily prints in at most five pages. Running headers, footers
and page numbers print on every page. The viewer shows the pages and has **Print / Save as PDF**, **Print summary only**
(page one), **Download HTML** and **Download data (CSV)**.

**Who decides what is presented.** When the firm enables the AI model, the model acts as the
report's editor under the versioned
[editorial directive](../product/REPORT_EDITORIAL_DIRECTIVE.md): it chooses the findings and their
order, the section order and what is dropped, the exhibits and their windows, and writes the
narrative, from a fact sheet the engine builds. It never writes a number or queries data;
every element it writes is checked against the facts it cites, and a refused element is replaced
by the rule-written one (a refused key finding by the rule's finding on the same fact, in the
same place). The editor runs at temperature 0. The viewer says "Edited by: model …, directive
v…, temperature 0" or "Rule-edited", and
the editorial plan (what led and why, what was left out) can be opened under the report. Without
a model the rules select and write everything.

A report is *assembled*, not written by a model. Each section comes from a fixed catalogue
(`GET /api/reports/catalogue`), reads its figures through the same entitled read its page uses,
draws the chart the catalogue fixes for it, and its facts carry their comparisons (day, week, a year earlier where held, with the number of
prior years) and a materiality score with its reason. Simulated values carry a dagger (†)
explained in every page footer, forecasts are called forecasts with their method and limitation,
late and stale data are named. Nothing in a report is advice
to trade, and nothing describes execution, nomination or settlement.

## Kinds

| Kind | Period | What it adds |
|---|---|---|
| Daily, morning or end of day | the gas day | day changes; the balance forecast for the coming days |
| Weekly | the seven days to yesterday (or the dates you give) | averages over the week against the week before and the same days a year earlier; price change, average, high and low; outages that ended during the week; exhibits over 13 weeks |
| Monthly | the last full calendar month (or the dates you give) | the same aggregates over the month, a contents list; exhibits over 13 months |
| Situation | from an alert or a REMIT outage | the event (facility, zone, size, dates, version, reason), the hubs it touches first, Norwegian landings in the seven days before and since when the outage is in Norway, what to check next; then outages, landings, the balance, prices and, internally, the position at the affected hubs |
| Asked | your question | see "Asked reports" |

## Sections

| Section | Data | Chart |
|---|---|---|
| The event (situation) | the alert or REMIT message | table; landings line when Norwegian |
| Hub prices | licensed daily closes by your data scope (front month, else day-ahead), each hub in its quoted unit | line per unit |
| Open alerts | critical and watch alerts you may see (limits alerts are reported under Limits) | table |
| Norwegian landings | ENTSOG flows at the registry's landing points | stacked area: continental landings, UK terminals |
| LNG send-out | GIE ALSI (National Gas for GB) by country | stacked bars |
| Storage | GIE AGSI facilities with a working capacity | fill against a year earlier, EU target line |
| Gas-fired power | ENTSO-E and Elexon generation from gas, by bidding zone, and implied gas burn at the gas-for-power read's 50% efficiency (labelled implied) | stacked bars |
| Outages | REMIT messages, latest version | the outage schedule table, largest active first |
| Balance and outlook | the NW Europe balance read and its forecast | measured call against a year earlier with the forecast dashed; the supply-stack table; the forecast's method and the limit of its seasonal normal |
| Position, P&L, Limits, Contracts in effect (Our book) | the position ladder, day P&L change, imported P&L, credit lines and mandates, contracts in the books you may see | ladder and tables |

A section with no data is left out of the body and listed once under "Not in this report" in
the back matter with the reason (for example "No licensed close for any hub is available to this
report"); a report without licensed prices leads with what is held. The series behind every
exhibit are always in the CSV download and, when printed, in the data annex (the report's own
window); hover
shows values on screen; the report has no script and reads the same in e-mail clients.

## Audience

- **Internal** may include Our book. It is printed "Internal: not for distribution outside the
  firm".
- **Shareable** never contains positions, P&L, limits, counterparties or contract terms: those
  sections are not read at all for a shareable report, and asking for one is refused.
- **Licensed data.** A report that read a licensed source (an exchange or vendor family under
  your firm's licence) says "Internal use: contains licensed data from <source>" and cannot be
  generated as shareable unless the licence register marks that licence
  `redistribution_allowed`. Generating it as shareable is refused with the sections that hold the
  licensed data; choose Internal or remove them.
- Public sources are credited in Methodology as their terms ask (ENTSOG with the download date,
  GIE, REMIT/GIE IIP, ENTSO-E, the Elexon BMRS line, National Gas).

What a report contains is decided by the person (or service principal) who generates it: their
data scopes and books. Opening a stored report re-checks the reader: every source behind it must
be licensed to the reader, and an internal report's books must be books the reader may see.

## Asked reports

Type a question ("How are the recent Norwegian outages affecting the supply?") and press
**Generate**. You do not choose sections: the question decides the scope (when your firm enables
the AI model, the model proposes it as structured data, used only when it validates against the
catalogue and names no hub your question did not name; otherwise keyword rules). **Adjust scope**
opens the plan (sections, period, hubs) if you want to change it before generating. While the
report is made the form shows its stages (planning, collecting, writing, checking, laying out)
with **Cancel**.

The report answers the question:

- **Title and Answer.** The question is the title; page one opens with an **Answer** of two to
  four sentences on what the evidence shows, every figure from a fact the report holds. Where the
  held data does not answer part of the question it says so: "The data held does not show ...".
- **Question facts.** The engine adds facts for the question on top of each section's own. For
  outages and Norwegian supply: the outages tied to Norwegian supply (a Norwegian balancing zone,
  a Norwegian field, plant or export pipeline, or a landing terminal for Norwegian gas; the basis
  is stated) with their capacity as a share of the latest landings, and the landings averaged
  over the days those outages were active against the seven days before. The engine marks those
  two as computed together, so the report may say "over the days ... were active"; it never says
  the outage caused the change, because the data held cannot show that.
- **Evidence.** Only the sections that bear on the question, in order of relevance, each
  paragraph opening with how it bears on it; the outage schedule lists the outages tied to
  Norwegian supply first.
- **What the data cannot tell**: outages that cannot be tied to the question, flows not yet
  reported, sources that are not held, the forecast's missing range, and that a coincidence is
  not a measured effect. Then **What to watch** (scheduled events only).

A question the held data cannot answer at all (oil, carbon, Asian prices, vessel tracking) says
"Cannot answer from held data" and what is missing. A report for distribution never mentions the
book, even when the question asks about it.

## Your report library

The stored list shows the kind, the title (the question for an asked report), the period, when
and by whom it was generated, and whether it was AI-edited or rule-edited. **Rename** and
**Delete** in the viewer act on the open report; **Manage** deletes several at once after a
confirmation. You can rename or delete reports you generated; an administrator can delete any.
Each change is checked on the server and recorded in the audit trail (`report.manage`); a
deleted report cannot be restored.

## What the model does and does not do

When the firm enables the model and you hold the analysis capability, the model may reword each
market section's rule commentary for flow. It is sent only that section's rule lines, its sources
as `S1`-style aliases and the simulated and forecast flags. Its text is used only if it passes the
same checks as every desk note: no number, hub, unit, direction, superlative, source or name the
lines do not hold, no advice, no simulated price written as a market price. Otherwise the rule
text stands. Our book sections are never reworded. The report records which sections were
reworded and each check's verdict, and says so in Methodology.

## PDF

**Print / Save as PDF** in the viewer prints the report through the browser: A4 pages with a
running header, a footer with classification and "Page X of Y", exhibits never split,
greyscale-safe line styles. **Print summary only** prints page one. The API returns HTML
(`GET /api/reports/market/{id}/html`); it does not render PDF on the server, so no browser engine
runs in the server image.

## Records

Every generated report is stored once (`market_reports`, migration `0064_market_reports`): the
plan, audience, the data snapshot the HTML was drawn from and its SHA-256, the HTML and its
SHA-256, the template version, who generated it under which data scopes, the source systems,
licensed families and books behind it, the model use, and what started it (user, alert, outage).
Reopening shows the stored report exactly; a decision can cite its id. Provider revisions to the
observations since the previous report of the same kind are counted in each section's sources
line.

## Scheduling

Not part of this release: reports are generated on demand (the Reports task, the API or the SDK
`eurogas_nexus_sdk.reports`). A scheduled run must use a declared service principal with its own
data scopes, never an administrator.

## API

`GET /api/reports/catalogue`, `POST /api/reports/plan`, `POST /api/reports/market`,
`GET /api/reports/market`, `GET /api/reports/market/{report_id}`,
`GET /api/reports/market/{report_id}/html`, `PATCH` and `DELETE /api/reports/market/{report_id}`
(rename, delete) and `POST /api/reports/market/bulk-delete`.
