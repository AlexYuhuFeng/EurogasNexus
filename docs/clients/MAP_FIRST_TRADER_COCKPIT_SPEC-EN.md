# Map-First Trader Cockpit Spec - EN

## Purpose

The Eurogas Nexus home screen is a map-first trader decision cockpit, not a
generic dashboard. Its purpose is to let a gas trader understand upstream
portfolio exposure, route availability, live market movement, strategy process
state, warnings, and indicative PnL from one visual surface.

## Home Screen Layout

The first screen must be dominated by the European gas map. The map must show:

- upstream resource contracts and resource-pool exposure;
- LNG terminals, beach delivery points, hubs, interconnectors, storage, and
  major route corridors;
- route options from resource origin to sale/delivery target;
- available and blocked routes;
- TSO access constraints;
- capacity and outage state when backend data exists;
- live market movement relevant to selected portfolio routes;
- strategy status and warning overlays.

The map must not be a decorative background. It is the main work surface.

## Above-Map Price And Process Strip

Place a compact live strip above the map with:

- portfolio exposure volume;
- relevant hub/day-ahead reference prices;
- ICE OCM or other intraday marks when entitled;
- ECB FX when cross-currency economics are visible;
- live indicative PnL;
- active strategy process state;
- latest decision-support signal;
- warning count.

Every value must show source/freshness when the backend provides it.

## Map Interaction

Required interactions:

- search terminal, hub, TSO, balancing point, field, or source;
- toggle network, LNG, interconnector, hub, storage, weather, contract, market,
  route, and warning layers;
- click a route or asset to open an inspector;
- compare route alternatives visually;
- highlight blocked route causes such as missing TSO access, missing tariff,
  missing capacity, missing terminal slot, missing provider credential, or stale
  data;
- launch route-cost, LNG regas readiness, resource-pool, or strategy evaluation
  through backend API calls only.

## Separate Detail Tabs Or Windows

Detailed work must not crowd the home map. Provide separate tabs/windows for:

- price monitoring;
- portfolio/resource combinations;
- route-cost and LNG regas analysis;
- strategy backtest, shadow-run, and live monitoring;
- imported external order records;
- warning and alert center;
- source lineage and entitlement;
- glossary;
- user manual;
- credentials and settings.

Order records are imported/reference records only in V1. The product must not
place, route, amend, or cancel orders.

## Strategy UX

Strategy panels must support:

- backtest mode;
- shadow-run mode;
- live-monitor mode;
- configured resource pool;
- selected time window such as 15:00-17:00;
- bar size such as 5 minutes;
- components such as SAP versus ICIS day-ahead versus ICE OCM, mean reversion,
  scoring, best buckets, and weighted combinations;
- risk controls such as max OCM allocation, minimum day-ahead allocation,
  maximum single-market volume, minimum expected margin, stop-loss, stale-data
  blocking, and TSO-access blocking;
- paper allocation targets with rationale, missing inputs, warnings, sources,
  and human-review status.

The UI must use decision-support language: signal, candidate, option, target,
review. Do not use execution language.

## Visual Quality Bar

Commercial delivery quality means:

- dense but readable professional trading-workstation layout;
- restrained colors with clear semantic state;
- no marketing hero, landing page, or decorative filler;
- stable responsive dimensions;
- clear light/dark/system theme support;
- English and Mandarin Chinese strings through i18n;
- map and data panels remain usable on desktop and laptop screens;
- mobile/tablet degrade to map-first tabs, not a squeezed dashboard.

## Data Boundary

The cockpit must consume only backend `/api/v1` or SDK surfaces. It must not
read PostgreSQL, backend files, vendor files, `.env`, or credentials directly.
