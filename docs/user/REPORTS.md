# Market reports

Research → **Reports** (`?workspace=research&task=reports`), or **Report** beside **Why** on an
alert or an outage (Today, Events, the alert centre). A report is one self-contained HTML file
built from the data the platform already holds, in the platform's own house style: a headline,
a Key points box, the sections, and **Methodology and sources**.

A report is *assembled*, not written by a model. Each section comes from a fixed catalogue
(`GET /api/reports/catalogue`), reads its figures through the same entitled read its page uses,
draws the chart the catalogue fixes for it, and writes its commentary by fixed rules: a headline
and at most three facts, each figure with its unit, simulated values marked simulated next to
the value, forecasts called forecasts, late and stale data named. Nothing in a report is advice
to trade, and nothing describes execution, nomination or settlement.

## Kinds

| Kind | Period | What it adds |
|---|---|---|
| Daily, morning or end of day | the gas day | day changes; the balance forecast for the coming days |
| Weekly | the seven days to yesterday (or the dates you give) | averages over the week against the week before and the same days a year earlier; price range and change over the week |
| Monthly | the last full calendar month (or the dates you give) | the same aggregates over the month |
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
| Gas-fired power | ENTSO-E and Elexon generation from gas, by bidding zone | stacked bars (electricity, not gas burned) |
| Outages | REMIT messages, latest version | horizontal bars of the largest active |
| Balance and outlook | the NW Europe balance read and its forecast | stacked bars by component; measured and forecast line; Sankey of sources and uses |
| Position, P&L, Limits, Contracts in effect (Our book) | the position ladder, day P&L change, imported P&L, credit lines and mandates, contracts in the books you may see | ladder and tables |

A section with no data is left out of the body and listed under "Not in this report" in
Methodology with the reason (for example "No licensed close for any hub is available to this
report"). Every chart has its data table under it ("Chart data"); hover shows the values; the
report reads and prints completely with scripts off (e-mail clients).

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

Type a question ("Norwegian supply this week and outages affecting it") and press **Propose
plan**. The question becomes a *plan*: catalogue sections with hubs, countries and a period. When
your firm enables the AI model, the model proposes the plan as structured data; it is used only
when it validates against the catalogue and names no hub your question did not name (a question
about ETF never becomes a TTF report). Otherwise keyword rules propose it. You see and edit the
plan before anything is generated. A question the held data cannot answer (oil, carbon, Asian
prices, vessel tracking) says "Cannot answer from held data" and what is missing. The model never
writes SQL and is sent only the question and the catalogue.

## What the model does and does not do

When the firm enables the model and you hold the analysis capability, the model may reword each
market section's rule commentary for flow. It is sent only that section's rule lines, its sources
as `S1`-style aliases and the simulated and forecast flags. Its text is used only if it passes the
same checks as every desk note: no number, hub, unit, direction, superlative, source or name the
lines do not hold, no advice, no simulated price written as a market price. Otherwise the rule
text stands. Our book sections are never reworded. The report records which sections were
reworded and each check's verdict, and says so in Methodology.

## PDF

**Print / Save as PDF** in the viewer prints the report through the browser: A4 pages, repeated
table headers, charts not split across pages, greyscale-safe line styles. The API returns HTML
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
`GET /api/reports/market/{report_id}/html`.
