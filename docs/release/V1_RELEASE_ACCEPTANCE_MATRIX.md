# V1 Release Acceptance Matrix

## Purpose

This matrix defines what evidence is required before Eurogas Nexus V1 can be
called a full project release.

## Acceptance Status Values

- `COMPLETE`: implemented, tested, documented, and validated.
- `PARTIAL`: implemented or documented only in part, with a gap report.
- `BLOCKED`: cannot proceed without user input or external state.
- `NOT_STARTED`: no implementation evidence yet.

## Foundation

| Area | Required Evidence |
| --- | --- |
| Repository governance | CI, contributing, security, issue/PR templates |
| Public repo data safety | docs warn against secrets, real vendor data, raw market data, contracts, strategy parameters |
| Import safety | app imports without DB URL or network |
| API prefix policy | `/api`, `/api/internal`, `/api/dev`, `/api/health` compatibility documented and tested |
| DB URL policy | `RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL`, legacy `EUROGAS_NEXUS_DB_DSN`, redaction tested |
| Live PostgreSQL validation | read-only validation script, no secret output, explicit operator command |

## Backend Runtime

| Area | Required Evidence |
| --- | --- |
| Alembic lifecycle | import-safe env, explicit migration commands, no automatic migrations |
| Runtime store | repository interfaces and DB-backed implementations for released tables |
| Required table registry | deterministic registry tied to migrations |
| Governance | entitlement/export fail-closed for unknown commercial data |
| Audit | audit event model for sensitive runtime actions |
| Data quality | freshness and quality metadata on released observations |

## Data And Domain Slices

| Slice | Required Evidence |
| --- | --- |
| Reference network | nodes, facilities, segments, mappings, synthetic fixtures, `/api/reference-network/*` |
| Source/ingestion | source registry, ingestion job/run, normalization status, mocked connectors |
| Market context | price/spread/FX observation metadata |
| Physical flow context | flow/capacity/outage observation metadata |
| LNG/regas | LNG terminal and observation metadata |
| Storage | storage site and observation metadata |
| Weather | weather/HDD/CDD/demand metric metadata |
| Route cost | input validation, cost component matching, result envelope |
| Indicative netback | market + route cost + assumptions result envelope |
| Feasibility | feasible/infeasible/unknown outputs and blockers |
| Allocation | allocation candidates, unallocated volume, constraints |
| Monitoring | research alerts and anomaly candidates |
| Nowcast | weather-adjusted demand/supply/price-pressure output |
| Backtest | strategy hypothesis and historical evaluation metrics |
| Shadow run | paper evaluation state with no orders/trades/nominations |
| Research brief | report output with required disclaimer and source lineage |

## API

| Area | Required Evidence |
| --- | --- |
| Health/runtime | health and runtime status routes |
| Source/ingestion | source and ingestion routes |
| Reference network | reference network routes |
| Context observations | market, flow, LNG, storage, weather routes |
| Research workflows | route-cost, netback, feasibility, allocation, nowcast, backtest, shadow-run, briefs |
| Monitoring | monitoring status, alerts, anomalies |
| Governance/audit | entitlement/export evaluation and audit query routes |
| Error model | safe error classification, no secret leakage |
| Response envelope | metadata preserved for research outputs |

## SDK

| Area | Required Evidence |
| --- | --- |
| Required V1 surface | SDK release milestone complete and covered by tests |
| API-only boundary | no imports from domain/application/runtime_store/db |
| Route prefix | SDK targets `/api` |
| Typed clients | clients for released route groups |
| Errors | safe exception model with redaction |
| Metadata | preserves warnings, assumptions, missing inputs, source refs, lineage |

## CLI

| Area | Required Evidence |
| --- | --- |
| SDK/API-only boundary | no business-internal imports; CLI calls SDK first or `/api` for documented SDK gaps |
| Health/runtime | commands or helpers for health/runtime validation |
| Source/scenario/research | inspection commands for released workflows |
| Output | human and JSON output where useful |
| Safety | read-only default, `--execute` for future write-like commands, secret redaction |

## Web Client

| Area | Required Evidence |
| --- | --- |
| SDK/API data boundary | web reaches PostgreSQL data only through backend `/api`; no direct DB/vendor/secret access |
| Runtime visibility | backend, DB, source, warning posture visible |
| Network workspace | map-ready reference network view |
| Capacity workspace | ENTSOG flow/capacity, TSO access, tariff, GIE storage/LNG context visible through backend API |
| Scenario workspace | inputs, missing inputs, assumptions |
| Market workspace | price, FX, and market-source observations only |
| Contracts workspace | EFET-style resource, delivery, pricing, settlement, and capacity terms |
| Review workspace | candidates, warnings, source refs, lineage, human-review state |
| Order Records workspace | read-only screen-order observations and portfolio PnL snapshots |
| Data Sources workspace | provider categories, credentials posture, diagnostics, and source lineage inspection |
| Settings | client preferences only, no secrets |
| Manual workspace | customer-facing page map and operating boundary |

## Windows Client

| Area | Required Evidence |
| --- | --- |
| Packaging | desktop shell exists and launches packaged/linked web workspace |
| Backend config | backend base URL configurable |
| Storage | only non-sensitive UI preferences stored |
| Runtime visibility | health/runtime/source posture visible |
| Safety | runtime data reached only through packaged web/API client and backend `/api`; no direct DB/vendor/secret access, no copied historical Desktop code |

## Release Pack

| Area | Required Evidence |
| --- | --- |
| Manifest | release file inventory |
| Exclusions | secrets, `.env`, raw/vendor/internal data excluded |
| Operator docs | local development, PostgreSQL validation, migrations, deployment notes |
| Client docs | SDK, CLI, web, Windows usage notes |
| Validation report | commands, results, route count, partial/blocked gaps |
| Gap report | accepted limitations only, no hidden missing required work |

## Final Release Gate

V1 release is ready only when every matrix row is `COMPLETE` or explicitly
accepted as `PARTIAL` by the user with a release gap report. Hidden, implicit,
or undocumented gaps fail the release gate.
