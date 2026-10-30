# Trader acceptance review — 2026-10-30

Reviewer stance: a senior gas trader at an international trading house, receiving
Eurogas Nexus `0.5.0-preview` from the supplier/IT team for daily use on the European
gas desk (TTF, THE, PEG, ZTP, PSV, NBP; storage, LNG and cross-border capacity).

## Verdict

**Conditional acceptance: accepted for desk analysis and research use, not yet as
a primary daily desk tool.** The governance, provenance, security and release foundations
are well above what desks usually receive, and the product boundary (no order entry,
nomination or settlement) is correct. However, on handover `main` did not import one of
its own modules, and several conventions a desk uses every hour were missing. The blocker
and the most important convention gaps are fixed in this delivery (below). The remaining
items are listed by priority. Each needs licensed data or a product decision, so none was
faked.

## What a desk gets that is already good

- Correct gas-day handling: CAM Art. 3(16) 06:00–06:00 CET/CEST with versioned calendars
  and 23/25-hour DST days (`domain/market/gas_day.py`).
- Point-in-time provenance on every observation, entitlement filtering per source,
  stale/missing data shown as diagnostics rather than invented values.
- Route economics, capacity/tariff selection, storage-dispatch and nomination-window
  *assessment* without any execution path.
- RBAC/SSO, audit, backup/restore drill, release gates. These are well beyond a
  typical in-house tool.

## Blocker found on handover (fixed)

| Finding | Impact | Fix |
|---|---|---|
| Commit `d97fd56` imported `eurogas_nexus.ingestion.ecmwf_archive_evidence`, which was never committed | `db/repositories/ecmwf_forecasts.py`, the ECMWF ingest CLI and the weather archive tests failed with `ModuleNotFoundError`; a clean checkout of `main` could not run the unit suite | Restored the module as the single pure source of the S1 policy/method/evidence hashes and limitations. The S1 reconstruction now uses it, so S1 and the S3 repository recompute identical identities. Verified with real PostgreSQL: 54 archive persistence/repository tests pass, including replay and tamper refusals |

## Desk-convention gaps closed in this delivery

| Gap (trader view) | Delivered |
|---|---|
| Curves only had WD/DA/WE/MA. No BOM, M+n, quarters, seasons, gas years or Cal, and no exact delivery windows | `domain/market/products.py` plus `GET /api/market/products`: resolves `WD, DA (Friday→Monday), WE, BOM, M+n, Q+n, S+n, GY+n, Cal+n` and absolute codes (`Nov-26`, `Q1-27`, `Sum-27`, `Win-27`, `GY-27`, `Cal-27`) to first/last gas day, UTC interval and DST-true hours (MWh of 1 MW flat) |
| No p/th ↔ €/MWh ↔ $/MMBtu conversion; the hub board fallback shows NBP and continental hubs in GBP/MWh | `domain/market/units.py` plus `GET /api/market/price-conversion`: IT-BTU factors (1 MWh = 34.1214 th = 3.41214 MMBtu), FX is an explicit override or else the latest ECB rate, and the rate used is echoed. No rate is ever assumed. Volume→energy requires an explicit GCV |
| Storage shown as a site list only, with no view against the EU filling target | `domain/market/storage_targets.py` plus `GET /api/storage/target-trajectory`: fill, gap, required net injection/day to 1 Oct and to the deadline, recent pace, projected deadline fill and status. Target, deviation and window are configurable (default 90%, 1 Oct–1 Dec, 0 pp) |
| LNG contracts price FX on WM/Reuters (WMR) or Bloomberg BFIX fixes, often averaged over the pricing month; only ECB existed | `domain/market/fx_fixings.py`: named fixes (ECB reference, WMR 4pm/11am London, BFIX 4pm London/2pm CET), DST-correct fixing instants, USD-quoted pairs crossed to EUR, per-date or period-average selection. `scripts/ops/import_fx_fixings.py` imports the subscriber's own CSV export (no scraping: both are licensed). `WMR`/`BFIX` are commercial entitlement families, so rows reach only principals with that data-scope grant, and `/api/market/fx` is now row-entitlement filtered. The converter and the desk panel take the fix as an explicit choice |
| None of this was visible on the desk | **Trader desk** panel on the existing *Market → Curves* task (no new page): product strip, price converter, storage vs target. EN/ZH |

Tests: `tests/unit/test_trader_market_conventions.py` (26), `tests/api/test_trader_desk_api.py`
(6) and `clients/web/tests/traderDesk.test.ts` (5). The contract surface is re-declared
(194 paths / 208 operations).

## Front-end clarity pass (2026-10-30)

Reviewed every page (web; the Windows/Linux x64/arm64 desktop builds wrap the same
client) as a trader seeing it for the first time. Findings and changes:

| Finding | Change |
|---|---|
| App opened on an empty network map ("No basemap configured") | Default landing is Market → Curves; Market task order is Curves, Network, Capacity |
| The same six hub prices appeared four times on one page (ticker cards, curve lanes, latest marks, regional comparison) | One hub × tenor board: bid/ask, mid, tick, spread vs TTF, WD/DA/WE/MA mids, source, unit · age; hub cell focuses every panel (keyboard accessible) |
| Every page opened with a two-row STALE/UNKNOWN slice table | One-line context summary (as-of, coloured degraded count); slice table on demand |
| Expired spread candidates filled the decision feed | Hidden behind "Show expired (n)" |
| Admin posture (credential counts, record counts) and an empty EEX evidence panel on the trader page | Moved out / behind "Quotes by source, source matrix and reference indices" |
| Two status badges for normal operation ("Polling fallback", runtime data) plus two header rows | Live-stream chip only when streaming; header is one row on desktop widths |
| Raw codes and store jargon ("MARKET_PRICE_FX_UNAVAILABLE:TTF (EUR->GBP)", "Runtime PostgreSQL", "measured empty result") | Plain messages that say what to do; codes kept in tooltips |
| Storage card said "A dependency is unavailable" when no AGSI series exists | Says there is no AGSI series yet and what fills it |

The guidance that produced the clutter was amended: see "Trader-first presentation
rules" in `UX_REFERENCE.md` and the landing change in
`PRODUCT_INFORMATION_ARCHITECTURE.md`.

Not yet done (next UI slices): the Strategy Lab design form is a single long page
of research fields and should become a stepwise builder. The ENTSOG native-capacity
query still asks for raw point ids and ISO timestamps; it should pick a point from
the operating board. The resource pool is GBP-denominated throughout API/SDK, so a
EUR reporting currency needs an ADR-backed contract migration.

## Remaining gaps before it is a daily desk tool (priority order)

1. **Licensed real-time prices.** Without ICE Endex / EEX / broker feeds the board relies
   on public settlement data and simulated rows. Simulated rows are labelled, but a
   desk cannot trade off them. This is a procurement and licensing step, not code.
2. **Forward curve construction.** Build a daily settlement curve per hub on the product
   calendar now available. Use explicit shaping/interpolation rules, and keep spreads
   (TTF–THE, TTF–NBP in a common unit, summer–winter) as first-class series.
3. **Reporting-currency choice.** `normalized_view.py` pins `TARGET_CURRENCY = "GBP"`.
   A continental desk reports in EUR. Make the target a deployment setting, keep native
   units (EUR/MWh, GBp/th) on screen, and show the converted value beside them.
4. **Fundamentals board.** Add REMIT UMMs (Norwegian outages from Gassco), LNG send-out vs
   capacity (ALSI), HDD vs normal and day-ahead demand next to prices. Ingestion exists
   for several of these, but there is no single morning view.
5. **Exchange holiday calendars** (EEX/ICE) for DA/WE/BOM roll and settlement dates.
6. **Position and exposure view** (read-only, imported from the ETRM) by tenor bucket on
   the product calendar, so route and storage assessments show their delta.
7. **Alerting into the trader's channel** (email/Teams) for UMMs, storage status changes
   and spread thresholds. Monitoring exists, but it only lives in the app.

## Architecture recommendations

These follow the repository's own rules: no big-bang rewrite, and no new datastore or
service without an ADR and a measured need.

- **Ontology (OWL/GRM).** `docs/ontology/eurogas-nexus-grm.ttl` and the semantic kernel
  are used for vocabulary gates and AI grounding. The highest-value next step is to bind
  *products/tenors, units and hubs* as ontology concepts. Desk conventions
  (`products.py`, `units.py`) are then queryable by agents, and the enum gate checks them
  too. Keep OWL as a validation and grounding layer; do not adopt a triple store.
- **Computation.** Domain calculations are pure and deterministic, which is the right
  pattern. Keep new desk analytics (curve building, storage valuation, spread
  statistics) as pure domain modules with API/SDK as thin adapters, as was done here.
  Heavy research fitting already runs out of the request path through jobs.
- **Transmission.** The web client polls quotes, opportunities and monitoring every 10 s.
  A streaming contract already exists (`streaming/`). Move the price board and alerts to
  it once a live licensed feed exists, and keep polling as the fallback.
  `/api/market/observations` is unbounded (`market_observations()` reads every row), and
  the web client no longer calls it. Bound it with `limit`/`since` before an SDK user
  hits it on a large store.
- **Storage.** PostgreSQL with Alembic is sufficient. When tick or quote history grows,
  first add time-range partitioning on the observation tables and a retained
  settlement-curve table keyed by (hub, product label, trade date). Consider a time-series
  extension only after measurement, through an ADR.
- **Process.** The Architecture V2 programme uses many autonomous worker commits pushed
  straight to `main`. The missing-module blocker shows the risk. Require the hosted
  `validate` job to pass on a fresh checkout before a push to `main` is accepted
  (branch protection), not only on the worker's own tree.
