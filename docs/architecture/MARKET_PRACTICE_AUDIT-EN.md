# Market Practice Alignment Audit - EN

## Purpose

This file is the execution reference for bringing non-route Eurogas Nexus V1
models closer to real European gas market practice. It is written for Claude
Code and other CLI agents that may not have internet access.

## Absolute Product Boundary

Eurogas Nexus supports trader decision-making and strategy review. It does not
place orders, route orders, submit nominations, capture trades, issue official
approvals, replace an ETRM, or provide legal advice. UI and API language must
say "decision support", "review", "candidate", "signal", or "option", not
"execute", "book", "nominate", or "official recommendation".

## DB-First Rule

PostgreSQL is the runtime source of truth. Web, Windows, CLI, and SDK clients
must access data only through `/api/v1` or the Python SDK. CSV/JSON files are
allowed only as templates, public-source archives, reports, tests, or explicit
development fallbacks. Trial and release modes must not silently fall back to
local files.

## Current Market-Practice Status

Route-cost layer:

- UK National Gas NTS only in this release.
- Do not hard-code the route-cost engine to Easington/Bacton examples. Any UK
  NTS entry/exit point may be priced when audited tariff rows exist in
  PostgreSQL.
- Supported business patterns include virtual hub sale, downstream physical
  delivery, beach delivery resource sale, storage injection/withdrawal support,
  and LNG regas delivery modes when the required inputs exist.
- Cost stack includes entry capacity, exit capacity where relevant, NTS
  commodity charge, contract tolerance allowance, and early recovered cash
  value.
- Route evaluation must consider company TSO access. If the company lacks access
  to a required TSO, the route is blocked or partial with an explicit warning.
- Live PnL uses bid marks for sellable options. It produces human-review
  decision-support signals only.

LNG regas layer:

- Terminal access, cargo arrival window, regas slot, cargo size, send-out
  capacity, storage/holding constraints, pricing basis, delivery mode, and
  downstream physical/virtual delivery requirements must be explicit inputs.
- Some LNG regas contracts require physical delivery at an entry point; some do
  not. The model must support terminal title transfer, virtual hub sale,
  physical entry delivery, and downstream physical delivery without forcing one
  mode onto all contracts.
- Cross-month regas windows must be split into month allocations for PnL and
  settlement review.
- Terminal capacity source and data freshness must be shown when available.

Portfolio/resource-pool layer:

- A customer may buy from multiple upstream contracts with different delivery
  terms, settlement lags, tolerances, costs, capacity ownership, TSO access, and
  eligible sale modes.
- Optimization must operate at portfolio level, allocate resources to compatible
  sale options, and include route costs, early recovered cash value, and access
  constraints.
- The system may produce candidate allocation targets and ranking signals, but
  it must not execute trades or submit nominations.

Market-price layer:

- `MarketObservation` is for assessments, indices, settlement, and derived
  prices.
- `MarketPriceMark` is for live screen marks from ICE OCM, EEX, Trayport,
  brokers, or other licensed sources.
- Sell-side option valuation must use executable or indicative bid where
  available; buy-side valuation must use ask.
- Each mark must carry venue, hub, product, delivery window, unit, currency,
  source, freshness, quality, and entitlement scope.

FX layer:

- `FxObservation` must distinguish pair, base currency, quote currency, rate
  type, source, and value date.
- ECB may be used as a public reference source when live ingestion is explicitly
  run by an operator.

Physical layer:

- Flow observations must carry point, direction, TSO, country, period,
  source, freshness, and whether the value is actual, nomination, allocation,
  or forecast.
- Capacity observations must distinguish technical, booked, available, firm,
  interruptible, product tenor, direction, and booking platform where known.
- Outage events must identify affected point/facility, operator, direction,
  start/end, status, and capacity impact.

Contract/capacity layer:

- Capacity contracts must be represented in energy units where possible
  (`MWh/day`) instead of relying only on `boe/d`.
- Route eligibility must include business model, required capacity products,
  required market marks, required physical signals, constraints, and confidence.
- Contract-specific inputs such as settlement lag, tolerance, allowed exit
  points, overrun handling, and owned capacity must remain configurable by the
  user or operator.

Strategy layer:

- V1 must support strategy backtest, shadow-run, and live-monitor evaluation
  contracts.
- Strategy examples include SAP versus ICIS Heren day-ahead versus ICE OCM,
  mean reversion, scoring, best buckets, and weighted combinations.
- Strategies must support configurable time windows such as 15:00-17:00, bar
  sizes such as 5 minutes, selected resources/resource pools, risk controls,
  max single-market volume, stop-loss, stale-data blocking, TSO-access blocking,
  and human-review warnings.
- Strategy output is a paper allocation target or decision-support signal. It
  must not be an official recommendation, order, nomination, booking, trade
  capture, or execution instruction.

Glossary layer:

- The glossary is a backend-served product surface, not static UI text.
- It must cover institutions, venues, concepts, prices, hubs, terminals,
  clearing, financial terms, contractual terms, capacity, storage, LNG, weather,
  route economics, and source governance.
- `/api/v1/glossary` and `/api/v1/glossary/{term}` must support `lang=en`,
  `lang=zh`, and `lang=zh-CN`.
- Python SDK, CLI, Web, and Windows clients must expose glossary access.
- Glossary terms must include category, English definition, Mandarin Chinese
  definition, aliases, related terms, and source references when available.

## Internet Requirements

No internet is required to implement the current contracts and tests.

Internet is required only when an operator or agent intentionally validates
current provider documentation, vendor API terms, market-source licenses,
package versions, or official TSO tariff PDFs.

## Next Implementation Priorities

1. Extend PostgreSQL migrations for durable live market marks, FX observations,
   capacity observations, outage events, and glossary terms.
2. Seed only public/demo data through scripts; do not commit real market data or
   customer data.
3. Add API routes that read DB-backed market marks, FX, capacity, outage, and
   glossary records.
4. Extend SDK DTOs before clients consume any new endpoint.
5. Update Web and Windows clients to show glossary, settings language/theme,
   source freshness, entitlement, and human-review warnings.
6. Keep route-cost UK National Gas NTS only until a later milestone adds
   audited European TSO tariff coverage and route optimization.
7. Extend strategy persistence and APIs so backtests, shadow runs, live monitor
   runs, allocation targets, and alerts are stored in PostgreSQL.
