# UI information audit: what each element says, and whether it earns its space

Status: first pass 2026-11-06 (task #69). Related: `docs/product/COMPONENTS.md`,
`docs/product/UX_REFERENCE.md`, `docs/product/ADAPTIVE_CLIENT.md`.

Screen space belongs to the reading a trader acts on. Every element on a page must answer one
question a named user asks, and must not repeat an answer given elsewhere on the same screen.

## Rules applied

1. **One question per element.** If no user asks the question, the element goes.
2. **Say it once per screen.** The top bar already shows gas day, product, hub and data status, so a
   page does not repeat them.
3. **Empty is one line.** With no data, a panel collapses to its title plus one reason (and one
   next step when there is one). It does not show export buttons for an empty table, zero-count
   tiles, an empty inspector, or columns of "n/a".
4. **Columns earn their place.** A column that is empty for every row is not drawn, and a row that
   is empty in every column collapses into a single list of names.
5. **Labels and values, not tiles.** Counts read as `label value` lines. A 70 px box per number is
   kept only for headline figures (net position, MTM).
6. **Explanations fold.** Standing caveats and "how to read this" text go in a `<details>` or a
   tooltip, so they are read once rather than on every visit.
7. **Expert tools fold.** Query forms that need an exact identifier (for example an ENTSOG
   `point_id`) are folded under their name.
8. **Links are links.** A row of hand-offs to other pages is a link row, not a headed panel of
   buttons.
9. **Time-critical first.** On a page that mixes events and reference data, the events come first.

## Pages

Verdicts: **keep**, **fold** (behind a disclosure), **merge** (into another element), **remove**,
**empty-collapse** (one line when there is no data).

### Market › Overview

The Overview answers: *where are prices, what is happening on the network, and what in my book is
touched?*

| Element | Question it answers | Who | Verdict | Done |
|---|---|---|---|---|
| Market context strip (as-of, stale slices, time basis) | Can I trust what is below? | All | keep | – |
| Context line: gas day, product, hub, runtime | Already in the top bar | – | **remove**; the runtime-store state moves onto the board heading | yes |
| Major hub board | What is each hub's price, how fresh, from where? | Trader | keep; drop the bid/offer and spread columns when no hub has a live quote, and collapse unpriced hubs into one line (`No price from any connected source: ZTP THE PEG PSV`) | yes |
| Preview map | Duplicated the Network task at a size too small to read | – | **remove**; the Network task owns the map | yes |
| Today on the network (outages, cargoes, slots, entry flow, contracts) | Is anything on the network I should open the map for? | Trader, risk | keep as six `label value` lines plus an "Open the map" link | yes |
| Opportunities | Is the intraday scan offering a spread to review? | Trader | empty-collapse into one line; the panel appears only with candidates | yes |
| Portfolio relevance | Which of my supplies sit at the focused hub? | Trader | keep; hand-offs become links, and "Inspect observation" shows only when a hub is focused | yes |
| Copilot | Can I ask about this context? | Analyst | when every action is withheld, show one line with the reason instead of five disabled buttons | yes |
| North-west Europe balance (GWh/d) | How much NW Europe draws each gas day from Norway, LNG and storage: the last 7 days measured, the next 14 forecast. A fundamentals desk reads it as the "call" on flexible supply. | Analyst, trader | keep with a one-line meaning under the title; empty-collapse to the backend's one reason, with no export buttons | yes |
| Gas for power | How much gas is burned for power, and whether gas or coal is in the merit order (clean spark vs clean dark spread), per day and power zone | Analyst | keep the meaning line and the zone picker (another zone may have data); empty-collapse; exports only with rows | yes |
| Spread strip | Hub-to-TTF spreads | Trader | shown only when some spread exists | already |

Why the "NWE" panel sat under the map: it was appended to the Overview after the map and had no
explanation, and with no ENTSOG/GIE history it showed only two warnings and three export buttons.
It now sits under the hub board with its meaning stated, and is one line when empty.

### Market › Curves & Spreads

| Element | Question | Verdict | Done |
|---|---|---|---|
| Hub board (WD/DA/WE/MA, bid/offer, tick, spread) | The screen a Trayport user expects | keep: a fixed column set is the convention, and "–" marks a missing tenor | – |
| Intraday decision feed | Any spread candidates? | empty-collapse to one line | yes |
| Quotes by source / reference indices | Evidence behind the board | already folded | – |
| Trader desk: product strip, price converter, storage vs target | Delivery windows, unit conversion, storage trajectory | keep | – |

### Market › Network

The map is the page. The situation strip on the map (live, out now, scheduled, contracts, cargoes,
slots, entry flow) is the only place those counts repeat, and the Overview's network lines link here.
Keep as is.

### Market › Capacity & Events

| Element | Question | Verdict | Done |
|---|---|---|---|
| Outages (REMIT UMMs) | What is out now or soon? | keep, **moved first** | yes |
| Capacity operations header, view switch | Network, storage or LNG | keep | – |
| Search, country/TSO filters, posture filter, six zero-count tiles | Filter a board that has rows | hidden while the runtime has served no point | yes |
| Network operating board | Flow vs firm technical capacity per point | keep; no 610 px minimum when empty | yes |
| Point and access inspector | Detail for the selected point | hidden while there is no point | yes |
| Native ENTSOG capacity context (query by exact `point_id`) | Analyst's evidence query | **fold** | yes |
| Declared capacity profiles | Stored profiles | the how-to-read paragraph shows only with rows | yes |

Result at 1440 px with the walk-through data: page height drops from about 1,800 px to 870 px.

### Portfolio › Overview

| Element | Question | Verdict | Done |
|---|---|---|---|
| Quantity and evidence basis | Standing caveat on scenario quantities | **fold** closed by default (it was open at desktop widths) | yes |
| Position ladder headline (net, physical, financial, hedged, MTM, VaR) | My position and its risk | keep | – |
| Gross by month | Exposure hidden by offsetting months | shown only when it differs from the absolute net; equal to it, it repeats net | yes |
| Scenario strip (allocated, unallocated, net PnL) | Result of a scenario run | before a run, three "n/a" cells become "No scenario run yet" | yes |
| Scenario resource register | My supplies, cost and access | keep | – |
| Review warnings | Blockers before a decision | keep | – |
| Hand-offs panel | Navigation | **merge** into a link row | yes |

### Decision Center › Review

The day board, review context, decision cases (objective, due time, open/decided) and folded run
assessments are each one line or folded already. Keep.

### Admin › Data Sources

| Element | Question | Verdict | Done |
|---|---|---|---|
| Four KPI tiles (connected, needs attention, available, runtime records) | Health of the connector estate | one `label value` line | yes |
| Connector cards, three per row, about 110 px each | Which connectors need me, which run, which can I add? | **one line per connector**: name, description (one line, full text on hover), status, action | yes |
| Available group (30 connectors) | Long tail, read only when adding a source | **fold** unless the selected connector is in it | yes |
| Detail: nine boxed metric tiles | Connector state | two-column `label value` list | yes |

Result: page height drops from about 1,870 px to 990 px, and the attention group is visible
without scrolling.

## Applying this to new work

A new panel states, in a code comment or in its meaning line, the question it answers. Review
checks it against the rules above before merging. Most empty states should follow rule 3; the
`EmptyState` component in `COMPONENTS.md` is the shared form.

## Not yet audited in depth

Research (strategy, backtests, datasets), Portfolio › Resources/Routes/Exposure, Decision Center ›
Scenario/Optimize/Nomination/Storage dispatch, Admin › Runtime and Access, and Help & Settings were
walked but not changed in this pass. They follow the same rules, and the next pass takes them in
that order.
